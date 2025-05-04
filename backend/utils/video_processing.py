import os
import shutil
import uuid
from pathlib import Path
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException
from db.models.video_fragment import VideoFragment
from core.config import settings
from core.logger import logger
from utils.s3_utils import upload_file_to_s3
from services.processing_service import VideoProcessor
from typing import List
import subprocess

class SmartVideoFragmenter:
    def __init__(self, min_duration: float = settings.VIDEO_MIN_FRAGMENT_DURATION,
                 max_duration: float = settings.VIDEO_MAX_FRAGMENT_DURATION,
                 optimal_duration: float = settings.VIDEO_OPTIMAL_DURATION,
                 default_language: str = settings.VIDEO_DEFAULT_LANGUAGE,
                 max_sentences: int = settings.VIDEO_MAX_SENTENCES_PER_FRAGMENT,
                 max_video_duration: float = 29.0):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.optimal_duration = optimal_duration
        self.default_language = default_language
        self.max_sentences = max_sentences
        self.max_video_duration = max_video_duration 
        self.temp_dir = Path(settings.TEMP_VIDEO_DIR)
        self.temp_fragments_dir = self.temp_dir / settings.VIDEO_TEMP_SUBDIR
        self._ensure_temp_dirs()

    def _ensure_temp_dirs(self):
        """Ensure temporary directories exist"""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.temp_fragments_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def detect_language(text: str) -> str:
        try:
            lang = detect(text)
            if lang in settings.VIDEO_SUPPORTED_LANGUAGES:
                return lang
        except LangDetectException:
            pass
        return settings.VIDEO_DEFAULT_LANGUAGE

    def filter_short_fragments(self, fragments: List[VideoFragment]) -> List[VideoFragment]:
        """Фильтрация фрагментов, длительность которых менее 1.5 секунд"""
        new_fragments = []
        for i, frag in enumerate(fragments):
            if frag.end_time - frag.start_time < 1.5:
                if new_fragments:
                    prev_frag = new_fragments[-1]
                    prev_frag.end_time = frag.end_time
                    prev_frag.text += " " + frag.text
                else:
                    new_fragments.append(frag)
            else:
                new_fragments.append(frag)
        return new_fragments


    def upload_fragment_to_s3(self, fragment: VideoFragment, video_name: str, fragment_id: int) -> str:
        """Загрузка фрагмента в S3 с ключом /fragments/{video_name}/fragment_{fragment_id}.mp4 и возврат URL"""
        
        # Убедитесь, что в фрагменте есть путь к файлу
        if not fragment.s3_url:
            raise ValueError("Фрагмент не содержит пути к файлу для загрузки.")

        s3_key = f"fragments/{video_name}/fragment_{fragment_id}.mp4"
        s3_url = upload_file_to_s3(fragment.s3_url, s3_key)
        return s3_url

    def process_subtitles(self, segments: List[dict]) -> List[VideoFragment]:
        """Обработка субтитров: оптимизация границ фрагментов и разбиение текста на предложения"""
        adjusted_segments = self._adjust_fragment_boundaries(segments)
        logger.info(f"Найдено {len(adjusted_segments)} сегментов")
        fragments = []
        
        for seg in adjusted_segments:
            sentences = self._split_into_sentences(seg["text"], seg["language"])
            fragment = VideoFragment(
                start_time=seg["start_time"],
                end_time=seg["end_time"],
                text=seg["text"],  # Отображаем полный текст
                sentences=sentences,
                language=seg["language"],
                tags=[],
                s3_url="",
                speech_confidence=1.0,  # Можно скорректировать, если есть данные о доверии распознавания
                no_speech_prob=0.0
            )
            logger.info(f"Сегмент: {fragment.start_time:.2f} - {fragment.end_time:.2f} ({len(sentences)} предложений)")
            fragments.append(fragment)
        return fragments


    def _split_into_sentences(self, text: str, language: str):
        try:
            tokenizer = nltk.data.load(f"tokenizers/punkt/{'english' if language == 'en' else 'russian'}.pickle")
            return tokenizer.tokenize(text)
        except Exception:
            return text.split(".")

    def _adjust_fragment_boundaries(self, segments):
        if not segments:
            return []
        
        adjusted = []
        current_segment = {
            "start_time": segments[0]["start_time"],
            "end_time": segments[0]["end_time"],
            "text": segments[0]["text"],
            "language": segments[0]["language"],
            "sentences": [segments[0]]
        }
        
        for segment in segments[1:]:
            gap = segment["start_time"] - current_segment["end_time"]
            
            if gap > 0.3:  # если разрыв больше 0.3 секунды
                adjusted.append(current_segment)
                current_segment = {
                    "start_time": segment["start_time"],
                    "end_time": segment["end_time"],
                    "text": segment["text"],
                    "language": segment["language"],
                    "sentences": [segment]
                }
            else:
                # Объединяем сегменты
                current_segment["end_time"] = segment["end_time"]
                current_segment["text"] = f"{current_segment['text']} {segment['text']}"
                current_segment["sentences"].append(segment)
        
        # Добавляем последний сегмент
        if current_segment:
            adjusted.append(current_segment)
        
        return adjusted

    def process_video(self, task, video_path: str) -> List[VideoFragment]:
        logger.info(f"Начало обработки видео: {video_path}")
        processor = VideoProcessor()

        video_duration = self.get_video_duration(video_path)
        
        if video_duration > self.max_video_duration:
            number_of_parts = int(video_duration // self.max_video_duration) + 1
            parts = []
            logger.info(f"Разделение видео на {number_of_parts} частей")

            # Store each part along with its offset.
            for i in range(number_of_parts):
                start_time = i * self.max_video_duration
                end_time = min((i + 1) * self.max_video_duration, video_duration)
                part_path = self.split_video(video_path, start_time, end_time)
                parts.append((part_path, start_time))

            all_fragments = []
            for idx, (part, offset) in enumerate(parts):
                prog = 10 + int((idx + 1) / len(parts) * 55)
                task.update_state(state='PROGRESS', meta={'progress': prog, 'current_operation': f'Фрагмент {idx + 1}/{len(parts)}: извлечение субтитров'})
                logger.info(f"Фрагмент {idx + 1}/{len(parts)}: извлечение субтитров")
                
                raw_fragments = processor.extract_subtitles(part)
                segments = self.extract_and_process_fragments(raw_fragments)
                
                # Adjust each fragment's timecodes by adding the part's offset.
                for frag in segments:
                    frag.start_time += offset
                    frag.end_time += offset
                    # s3_url will be set after cutting the original video
                    all_fragments.append(frag)
                    
                shutil.rmtree(part, ignore_errors=True)

            return all_fragments
        else:
            # Если видео длится меньше x секунд, сразу извлекаем субтитры
            raw_fragments = processor.extract_subtitles(video_path)
            segments = self.extract_and_process_fragments(raw_fragments)
            # s3_url will be set later using the original video
            return segments

    def extract_and_process_fragments(self, raw_fragments):
        segments = []
        for frag in raw_fragments:
            lang = self.detect_language(frag.text)
            frag.language = lang
            segments.append({
                "start_time": frag.start_time,
                "end_time": frag.end_time,
                "text": frag.text,
                "language": lang
            })
        return self.process_subtitles(segments)

    def get_video_duration(self, video_path: str) -> float:
        """Получаем длительность видео с помощью ffmpeg"""
        command = ["ffmpeg", "-i", video_path]
        result = subprocess.run(command, capture_output=True, text=True)
        for line in result.stderr.splitlines():
            if "Duration" in line:
                duration_str = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = map(float, duration_str.split(":"))
                return h * 3600 + m * 60 + s
        raise ValueError(f"Не удалось получить длительность видео: {video_path}")

    def split_video(self, video_path: str, start_time: float, end_time: float) -> str:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Файл {video_path} не найден!")
        
        # Use temp fragments directory
        output_path = str(self.temp_fragments_dir / f"split_{uuid.uuid4()}_{start_time:.1f}_{end_time:.1f}.mp4")
        
        MIN_FREE_SPACE = 100 * 1024 * 1024  # 100 MB
        free_space = shutil.disk_usage(str(self.temp_dir)).free
        if free_space < MIN_FREE_SPACE:
            raise RuntimeError(f"Недостаточно свободного места в {self.temp_dir}: доступно {free_space} байт")
        
        try:
            command = ["ffmpeg", "-y", "-i", video_path, 
                      "-ss", f"{start_time:.3f}", 
                      "-to", f"{end_time:.3f}",
                      "-c", "copy", output_path]
            
            proc = subprocess.run(command, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {proc.stderr}")
            
            if not os.path.exists(output_path):
                raise FileNotFoundError(f"Failed to create file {output_path}")
            
            return output_path
            
        except Exception as e:
            if os.path.exists(output_path):
                os.remove(output_path)
            raise RuntimeError(f"Error splitting video: {str(e)}")

