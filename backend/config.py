import os
from dotenv import load_dotenv
from pathlib import Path

# Carrega o .env da raiz do projeto (dois níveis acima de /backend)
_root = Path(__file__).parent.parent
load_dotenv(_root / ".env")

# ─── Transcrição ───────────────────────────────────────────────────────────────
TRANSCRIPTION_PROVIDER: str = os.getenv("TRANSCRIPTION_PROVIDER", "whisper").lower()
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
ASSEMBLYAI_API_KEY: str = os.getenv("ASSEMBLYAI_API_KEY", "")

# ─── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")

# ─── Processamento de clipes ───────────────────────────────────────────────────
MAX_CLIPS: int = int(os.getenv("MAX_CLIPS", "5"))
MIN_CLIP_SECONDS: int = int(os.getenv("MIN_CLIP_SECONDS", "15"))
MAX_CLIP_SECONDS: int = int(os.getenv("MAX_CLIP_SECONDS", "60"))
OUTPUT_FORMAT: str = os.getenv("OUTPUT_FORMAT", "mp4")
OUTPUT_ASPECT_RATIO: str = os.getenv("OUTPUT_ASPECT_RATIO", "9:16")
