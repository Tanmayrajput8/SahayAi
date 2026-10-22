import os
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SahayAI Emergency"
    PROJECT_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # CORS Configuration
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return []

    # Database Configuration — absolute path so it resolves identically regardless of cwd
    DATABASE_URL: str = f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'sahayai_emergency.db')}"

    # JWT Authentication
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # AI & LLM Providers (Groq Cloud LLM / Grok / xAI REST API + Mock Provider)
    LLM_PROVIDER: str = "groq"  # "groq", "grok", or "mock"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROK_API_KEY: str = ""
    GROK_BASE_URL: str = "https://api.x.ai/v1"
    GROK_API_URL: str = "https://api.x.ai/v1/chat/completions"
    GROK_MODEL: str = "grok-4.6"
    LLM_TIMEOUT_SECONDS: float = 20.0
    LLM_MAX_RETRIES: int = 2
    MOCK_MODE: bool = False

    # Speech-to-Text Providers (Sarvam AI Saaras / Groq Whisper / Mock Provider)
    SPEECH_PROVIDER: str = "sarvam"  # "sarvam", "groq", "external", or "mock"
    SARVAM_API_KEY: str = ""
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_STT_URL: str = "https://api.sarvam.ai/speech-to-text"
    SARVAM_TIMEOUT_SECONDS: float = 20.0
    STT_API_KEY: str = ""
    STT_API_URL: str = "https://api.groq.com/openai/v1/audio/transcriptions"
    STT_MODEL: str = "whisper-large-v3"
    STT_TIMEOUT_SECONDS: float = 20.0
    MAX_AUDIO_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB max
    AUDIO_UPLOAD_DIR: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "storage",
        "audio",
    )

    # Geocoding Settings (OpenStreetMap Nominatim REST API / Mock Provider)
    GEOCODING_PROVIDER: str = "mock"  # "nominatim" or "mock"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org/search"
    NOMINATIM_USER_AGENT: str = "SahayAI-Emergency/1.0"
    GEOCODING_TIMEOUT_SECONDS: float = 5.0
    GEOCODING_MAX_RETRIES: int = 2

    # Routing Providers (OSRM / OpenRouteService REST API with Haversine Fallback)
    ROUTING_PROVIDER: str = "osrm"  # "osrm", "openrouteservice", "fallback", "mock"
    OSRM_BASE_URL: str = "https://router.project-osrm.org/route/v1/driving"
    OPENROUTESERVICE_BASE_URL: str = "https://api.openrouteservice.org/v2/directions/driving-car"
    OPENROUTESERVICE_API_KEY: str = ""
    ROUTING_TIMEOUT_SECONDS: float = 5.0
    ROUTING_MAX_RETRIES: int = 2

    # Embedding and RAG Settings (External Embedding REST API / Mock Provider)
    EMBEDDING_PROVIDER: str = "mock"  # "external" or "mock"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_API_URL: str = "https://api.openai.com/v1/embeddings"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_TIMEOUT_SECONDS: float = 10.0
    RAG_TOP_K: int = 3
    RAG_SIMILARITY_THRESHOLD: float = 0.45
    KNOWLEDGE_BASE_DIR: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ai",
        "rag",
        "knowledge_base",
    )

    # Duplicate Detection Multi-Signal System Settings
    DUPLICATE_SEMANTIC_WEIGHT: float = 0.40
    DUPLICATE_LOCATION_WEIGHT: float = 0.30
    DUPLICATE_TIME_WEIGHT: float = 0.15
    DUPLICATE_TYPE_WEIGHT: float = 0.15
    DUPLICATE_THRESHOLD: float = 0.80
    DUPLICATE_POSSIBLE_THRESHOLD: float = 0.60
    DUPLICATE_TIME_WINDOW_MINUTES: float = 120.0
    DUPLICATE_LOCATION_RADIUS_KM: float = 5.0

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
