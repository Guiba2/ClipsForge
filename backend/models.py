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
    enabled: bool                        = False
    face_detection: bool                 = True
    add_captions: bool                   = True
    caption_style: CaptionStyle          = CaptionStyle.tiktok
    background_video_path: Optional[str] = None


# ─── Opções do center blur layout ─────────────────────────────────────────────

class CenterBlurOptions(BaseModel):
    enabled: bool               = False
    video_height_ratio: float   = 0.70   # 0.0–1.0, porção da altura ocupada pelo vídeo central
    blur_strength: int          = 20     # sigma do gblur no fundo
    vign_strength: int          = 90     # tamanho do fade cosseno entre vídeo central e fundo (px)
    add_captions: bool          = True
    caption_style: CaptionStyle = CaptionStyle.tiktok


# ─── Requests ─────────────────────────────────────────────────────────────────

class UrlRequest(BaseModel):
    url: str
    transcription_provider: Optional[TranscriptionProvider] = None
    llm_provider: Optional[LLMProvider]                     = None
    viral: Optional[ViralOptions]                           = None
    center_blur: Optional[CenterBlurOptions]                = None


class AnalyzeRequest(BaseModel):
    transcription_provider: Optional[TranscriptionProvider] = None
    llm_provider: Optional[LLMProvider]                     = None
    viral: Optional[ViralOptions]                           = None
    center_blur: Optional[CenterBlurOptions]                = None


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
    confidence: float


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
    # versão viral (dual-panel + legenda)
    viral_filename:     Optional[str] = None
    viral_download_url: Optional[str] = None
    # versão center blur (fundo desfocado + legenda)
    blur_filename:     Optional[str] = None
    blur_download_url: Optional[str] = None


# ─── Status do Job ────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    idle         = "idle"
    downloading  = "downloading"
    transcribing = "transcribing"
    analyzing    = "analyzing"
    processing   = "processing"
    viral        = "viral"
    done         = "done"
    error        = "error"


class JobState(BaseModel):
    job_id:     str
    status:     JobStatus               = JobStatus.idle
    progress:   int                     = 0
    message:    str                     = "Aguardando..."
    video_path: Optional[str]           = None
    clips:      Optional[List[GeneratedClip]] = None
    error:      Optional[str]           = None