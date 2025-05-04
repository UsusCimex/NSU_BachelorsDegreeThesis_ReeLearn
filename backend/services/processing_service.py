import subprocess
import os
import uuid
import shutil
from utils.s3_utils import upload_file_to_s3
from db.models.video_fragment import VideoFragment
from core.config import settings
from core.logger import logger
from whisper import load_model
from typing import Optional
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using {device} for processing")

class VideoProcessor:
    def __init__(self, model_name: str = "turbo"):
        self.model = load_model(model_name, device=device)
    
    def optimize_fragments(self, fragments, target_duration: float = settings.VIDEO_OPTIMAL_DURATION, 
                      max_duration: float = settings.VIDEO_MAX_FRAGMENT_DURATION,
                      min_duration: float = 5.0):  # минимальная длительность фрагмента
        if not fragments:
            return []
        
        # Сортируем фрагменты по времени начала
        sorted_fragments = sorted(fragments, key=lambda x: x.start_time)
        optimized = []
        
        current = sorted_fragments[0]
        
        for next_fragment in sorted_fragments[1:]:
            # Проверяем пересечение фрагментов
            if next_fragment.start_time <= current.end_time:
                # Если следующий фрагмент заканчивается позже - расширяем текущий
                if next_fragment.end_time > current.end_time:
                    current.end_time = next_fragment.end_time
                    current.text = f"{current.text} {next_fragment.text}"
                    current.sentences.extend(next_fragment.sentences)
            else:
                # Проверяем длительность текущего фрагмента
                duration = current.end_time - current.start_time
                
                # Если фрагмент слишком короткий и есть следующий фрагмент
                if duration < min_duration and next_fragment is not None:
                    # Объединяем с следующим фрагментом
                    gap = next_fragment.start_time - current.end_time
                    if gap < 2.0:  # если разрыв меньше 2 секунд
                        current.end_time = next_fragment.end_time
                        current.text = f"{current.text} {next_fragment.text}"
                        current.sentences.extend(next_fragment.sentences)
                        continue
                
                # Если фрагмент слишком длинный - разделяем
                if duration > max_duration:
                    parts = max(2, int(duration / target_duration))
                    part_duration = duration / parts
                    
                    for i in range(parts):
                        start = current.start_time + (i * part_duration)
                        end = start + part_duration if i < parts - 1 else current.end_time
                        
                        # Находим субтитры для данного временного отрезка
                        part_sentences = [s for s in current.sentences 
                                       if s.start >= start and s.end <= end]
                        part_text = " ".join([s.text for s in part_sentences])
                        
                        new_fragment = VideoFragment(
                            start_time=start,
                            end_time=end,
                            text=part_text,
                            sentences=part_sentences,
                            language=current.language,
                            tags=current.tags,
                            s3_url="",
                            speech_confidence=current.speech_confidence,
                            no_speech_prob=current.no_speech_prob
                        )
                        optimized.append(new_fragment)
                else:
                    optimized.append(current)
                
                current = next_fragment
        
        # Добавляем последний фрагмент
        if current and current not in optimized:
            duration = current.end_time - current.start_time
            if duration >= min_duration:
                optimized.append(current)
        
        # Финальная проверка и сортировка
        final_fragments = sorted(optimized, key=lambda x: x.start_time)
        
        # Удаляем дубликаты по времени
        unique_fragments = []
        for frag in final_fragments:
            if not any(existing.start_time == frag.start_time 
                      and existing.end_time == frag.end_time 
                      for existing in unique_fragments):
                unique_fragments.append(frag)
        
        return unique_fragments
    
    def extract_audio(self, video_path: str) -> str:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
            
        audio_path = os.path.splitext(video_path)[0] + ".wav"
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path
        ]
        
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Failed to create audio file: {audio_path}")
            return audio_path
            
        except subprocess.CalledProcessError as e:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            raise RuntimeError(f"FFmpeg error: {e.stderr}")
        except Exception as e:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            raise RuntimeError(f"Failed to extract audio: {str(e)}")
    
    def extract_subtitles(self, video_path: str):
        result = self.model.transcribe(video_path, task="transcribe", language=None, word_timestamps=True)
        # logger.info(f"Результат распознавания: {result}")
        fragments = []
        for seg in result["segments"]:
            if seg.get("no_speech_prob", 0) > 0.5:
                continue
            frag = VideoFragment(start_time=float(seg["start"]), end_time=float(seg["end"]), text=seg["text"].strip(), sentences=[seg["text"].strip()], language="", tags=[], s3_url="", speech_confidence=1.0 - seg.get("no_speech_prob", 0), no_speech_prob=seg.get("no_speech_prob", 0))
            fragments.append(frag)
        return self.optimize_fragments(fragments)
    
    def cut_video_segment(self, video_path: str, output_path: str, start_time: float, end_time: float) -> bool:
        cmd = ["ffmpeg", "-i", video_path, "-ss", str(start_time), "-t", str(end_time - start_time), "-c:v", "libx264", "-c:a", "aac", "-y", output_path]
        logger.info(f"Выполняется команда: {cmd}")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode == 0

    def process_and_upload_fragment(self, video_path: str, temp_dir: str, fragment: VideoFragment) -> Optional[str]:
        try:
            fragment_filename = f"fragment_{uuid.uuid4()}.mp4"
            fragment_path = os.path.join(temp_dir, fragment_filename)
            logger.info(f"Начинается нарезка видео: [{fragment.start_time} - {fragment.end_time}] в файл {fragment_path}")
            
            if not self.cut_video_segment(video_path, fragment_path, fragment.start_time, fragment.end_time):
                logger.error(f"Не удалось нарезать видео для фрагмента [{fragment.start_time} - {fragment.end_time}]")
                return None
            logger.info(f"Успешно нарезан фрагмент: {fragment_path}")
            
            s3_key = upload_file_to_s3(fragment_path, f"fragments/{fragment_filename}")
            logger.info(f"Фрагмент загружен в S3 с ключом: {s3_key}")
            
            try:
                os.remove(fragment_path)
                logger.info(f"Временный файл успешно удалён: {fragment_path}")
            except Exception as e:
                logger.warning(f"Ошибка при удалении временного файла {fragment_path}: {e}")
            
            return s3_key
        except Exception as e:
            logger.error(f"Ошибка при обработке фрагмента: {e}", exc_info=True)
            return None
