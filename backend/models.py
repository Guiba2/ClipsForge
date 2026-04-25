from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from enum import Enum


class TranscriptionProvider(str, Enum):
    whisper = "whisper"
    assemblyai = "assemblyai"


class LLMProvider(str, Enum):
    gemini = "gemini"
    ollama = "ollama"
    openrouter = "openrouter"


class UrlRequest(BaseModel):
    url: str
    # Providers opcionais — se omitidos, usa os valores do .env
    transcription_provider: Optional[TranscriptionProvider] = None
    llm_provider: Optional[LLMProvider] = None


class AnalyzeRequest(BaseModel):
    transcription_provider: Optional[TranscriptionProvider] = None
    llm_provider: Optional[LLMProvider] = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class ClipSuggestion(BaseModel):
    start_time: float
    end_time: float
    title: str
    reason: str
    confidence: float  # 0.0 a 1.0


class GeneratedClip(BaseModel):
    id: str
    title: str
    start_time: float
    end_time: float
    duration: float
    reason: str
    confidence: float
    filename: str
    download_url: str


class JobStatus(str, Enum):
    idle = "idle"
    downloading = "downloading"
    transcribing = "transcribing"
    analyzing = "analyzing"
    processing = "processing"
    done = "done"
    error = "error"


class JobState(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.idle
    progress: int = 0
    message: str = "Aguardando..."
    video_path: Optional[str] = None
    clips: Optional[List[GeneratedClip]] = None
    error: Optional[str] = None
