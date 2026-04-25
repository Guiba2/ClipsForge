"""
Camada unificada de transcrição.
Suporta: faster-whisper (local) e AssemblyAI (API).
Retorna sempre uma lista de TranscriptSegment.
"""
import logging
from typing import List
from models import TranscriptSegment
import config

logger = logging.getLogger(__name__)


# ─── Whisper local ─────────────────────────────────────────────────────────────

def _transcribe_whisper(audio_path: str) -> List[TranscriptSegment]:
    """Usa faster-whisper para transcrição local."""
    from faster_whisper import WhisperModel

    logger.info(f"[Whisper] Carregando modelo '{config.WHISPER_MODEL}'...")
    model = WhisperModel(
        config.WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
    )

    logger.info("[Whisper] Transcrevendo áudio...")
    segments, info = model.transcribe(
        audio_path,
        beam_size=5,
        language=None,  # detecta automaticamente
        vad_filter=True,
    )

    result = []
    for seg in segments:
        result.append(TranscriptSegment(
            start=round(seg.start, 2),
            end=round(seg.end, 2),
            text=seg.text.strip(),
        ))

    logger.info(f"[Whisper] {len(result)} segmentos transcritos. Idioma detectado: {info.language}")
    return result


# ─── AssemblyAI ────────────────────────────────────────────────────────────────

def _transcribe_assemblyai(audio_path: str) -> List[TranscriptSegment]:
    """Usa AssemblyAI para transcrição via API."""
    import assemblyai as aai

    if not config.ASSEMBLYAI_API_KEY:
        raise ValueError("ASSEMBLYAI_API_KEY não configurada no .env")

    aai.settings.api_key = config.ASSEMBLYAI_API_KEY
    transcriber = aai.Transcriber()

    logger.info("[AssemblyAI] Enviando áudio para transcrição...")
    transcript = transcriber.transcribe(audio_path)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"Erro AssemblyAI: {transcript.error}")

    # Agrupa palavras em segmentos de ~20 palavras para manter granularidade
    words = transcript.words or []
    if not words:
        logger.warning("[AssemblyAI] Nenhuma palavra retornada.")
        return []

    segments = []
    chunk_size = 20
    for i in range(0, len(words), chunk_size):
        chunk = words[i : i + chunk_size]
        segments.append(TranscriptSegment(
            start=round(chunk[0].start / 1000.0, 2),
            end=round(chunk[-1].end / 1000.0, 2),
            text=" ".join(w.text for w in chunk),
        ))

    logger.info(f"[AssemblyAI] {len(segments)} segmentos criados.")
    return segments


# ─── Interface pública ─────────────────────────────────────────────────────────

def transcribe(audio_path: str, provider: str | None = None) -> List[TranscriptSegment]:
    """
    Transcreve o áudio e retorna segmentos com timestamps.
    O provider pode ser sobrescrito; caso contrário usa o valor do .env.
    """
    p = (provider or config.TRANSCRIPTION_PROVIDER).lower()

    if p == "whisper":
        return _transcribe_whisper(audio_path)
    elif p == "assemblyai":
        return _transcribe_assemblyai(audio_path)
    else:
        raise ValueError(f"TRANSCRIPTION_PROVIDER inválido: '{p}'. Use 'whisper' ou 'assemblyai'.")
