"""
Central configuration – all env vars read once at startup.
"""
import os
import logging
from pathlib import Path


class Settings:
    openrouter_api_key: str = os.environ.get("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    chroma_host: str = os.environ.get("CHROMA_HOST", "vectordb")
    chroma_port: int = int(os.environ.get("CHROMA_PORT", "8000"))

    data_dir: Path = Path(os.environ.get("DATA_DIR", "/app/data"))

    allowed_origins: list[str] = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_collection: str = "properties"

    # OpenRouter attribution headers (shown in your OpenRouter dashboard)
    app_url: str = os.environ.get("APP_URL", "http://localhost:3000")
    app_title: str = os.environ.get("APP_TITLE", "Real Estate AI Chatbot")

    # Free OpenRouter models
    llm_models: list[str] = [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "minimax/minimax-m3:free",
        "nvidia/nemotron-3.5-lightning:free",
        "thinkingmachines/inkling:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]


settings = Settings()
