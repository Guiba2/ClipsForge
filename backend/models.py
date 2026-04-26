from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class TranscriptionProvider(str, Enum):
    whisper    = "whisper"
    assemblyai = "assemblyai"


class LLMProvider(str, Enum):
    gemini     = "gemini"
    ollama     = "ollama"
    openrouter = "openrouter"


class CaptionStyle(str, Enum):
    bold   = "bold"
    tiktok = "tiktok"


# ─── Opções do modo viral ──────────────────────────────────────────────────────

class ViralOptions(BaseModel):
    enabled: bool                          = False
    face_detection: bool                   = True
    add_captions: bool                     = True
    caption_style: CaptionStyle            = CaptionStyle.tiktok
    background_video_path: Optional[str]   = None  # path do gameplay no servidor


# ─── Requests ─────────────────────────────────────────────────────────────────

class UrlRequest(BaseModel):
    url: str
    transcription_provider: Optional[TranscriptionProvider] = None
    llm_provider: Optional[LLMProvider]                     = None
    viral: Optional[ViralOptions]                           = None


class AnalyzeRequest(BaseModel):
    transcription_provider: Optional[TranscriptionProvider] = None
    llm_provider: Optional[LLMProvider]                     = None
    viral: Optional[ViralOptions]                           = None


# ─── Transcrição ──────────────────────────────────────────────────────────────

class TranscriptSegment(BaseModel):
    start: float
    end:   float
    text:  str


# ─── Sugestões / Clipes ───────────────────────────────────────────────────────

class ClipSuggestion(BaseModel):
    start_time: float
    end_time:   float
    title:      str
    reason:     str
    confidence: float  # 0.0 a 1.0


class GeneratedClip(BaseModel):
    id:           str
    title:        str
    start_time:   float
    end_time:     float
    duration:     float
    reason:       str
    confidence:   float
    filename:     str
    download_url: str
    viral_filename:     Optional[str] = None   # versão viral, se gerada
    viral_download_url: Optional[str] = None


# ─── Status do Job ────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    idle        = "idle"
    downloading = "downloading"
    transcribing = "transcribing"
    analyzing   = "analyzing"
    processing  = "processing"
    viral       = "viral"          # novo passo: aplicando viral edit
    done        = "done"
    error       = "error"


class JobState(BaseModel):
    job_id:     str
    status:     JobStatus          = JobStatus.idle
    progress:   int                = 0
    message:    str                = "Aguardando..."
    video_path: Optional[str]      = None
    clips:      Optional[List[GeneratedClip]] = None
    error:      Optional[str]      = None
