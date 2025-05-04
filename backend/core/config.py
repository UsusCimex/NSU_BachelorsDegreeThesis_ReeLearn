from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROGRAM_NAME: str = "ReeLearn"
    PROGRAM_VERSION: str = "2.0.0"
    TIMEZONE: str = "UTC"
    API_V1_STR: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = ["http://localhost", "http://localhost:3000"]
    POSTGRES_USER: str = "reelearndb"
    POSTGRES_PASSWORD: str = "reelearndb"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5433"
    POSTGRES_DB: str = "reelearndb"
    VIDEO_MIN_FRAGMENT_DURATION: float = 3.0
    VIDEO_MAX_FRAGMENT_DURATION: float = 60.0
    VIDEO_OPTIMAL_DURATION: float = 4.5
    VIDEO_DEFAULT_LANGUAGE: str = "en"
    VIDEO_SUPPORTED_LANGUAGES: List[str] = ["en", "ru"]
    VIDEO_MAX_SENTENCES_PER_FRAGMENT: int = 2
    ELASTICSEARCH_HOST: str = "localhost"
    ELASTICSEARCH_PORT: int = 9200
    ELASTICSEARCH_INDEX_NAME: str = "reelearn_index"
    ELASTICSEARCH_BATCH_SIZE: int = 100
    ELASTICSEARCH_TIMEOUT: int = 30
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_PUBLIC_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "videos"
    FFMPEG_THREADS: int = 0
    FFMPEG_PRESET: str = "medium"
    FFMPEG_CRF: int = 23
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    TEMP_UPLOAD_DIR: str = "/tmp/videos"
    TEMP_VIDEO_DIR: str = "/tmp/videos"
    VIDEO_TEMP_SUBDIR: str = "fragments"
    MAX_UPLOAD_SIZE: int = 15 * 1024 * 1024 * 1024  # 15 ГБ максимальный размер файла
    UPLOAD_CHUNK_SIZE: int = 5 * 1024 * 1024  # 5 МБ размер чанка для потоковой передачи
    MIN_FREE_SPACE_PERCENTAGE: float = 20.0  # Минимальный процент свободного места на диске
    TEMP_FILES_MAX_AGE_HOURS: int = 24  # Максимальное время хранения временных файлов в часах
    AUTO_CLEANUP_TEMP_FILES: bool = True  # Автоматическая очистка временных файлов
    CRITICAL_FREE_SPACE_MB: int = 1024  # Критический размер свободного места в MB (1 ГБ)
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
