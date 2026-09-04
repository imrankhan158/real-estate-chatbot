"""
Central configuration – all env vars read once at startup.
"""
import logging
import os
from pathlib import Path


class Settings:
    openrouter_api_key: str = os.environ.get("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Pinecone (cloud vector DB)
    pinecone_api_key: str = os.environ.get("PINECONE_API_KEY", "")
    pinecone_index_name: str = os.environ.get("PINECONE_INDEX_NAME", "real-estate")

    data_dir: Path = Path(os.environ.get("DATA_DIR", "/app/data"))

    allowed_origins: list[str] = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384  # all-MiniLM-L6-v2 output size

    # OpenRouter attribution headers (shown in your OpenRouter dashboard)
    app_url: str = os.environ.get("APP_URL", "http://localhost:3000")
    app_title: str = os.environ.get("APP_TITLE", "Real Estate AI Chatbot")

    # Free OpenRouter models in fallback order (verified Sept 2026)
    llm_models: list[str] = [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "minimax/minimax-m3:free",
        "nvidia/nemotron-3.5-lightning:free",
        "thinkingmachines/inkling:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]


settings = Settings()
