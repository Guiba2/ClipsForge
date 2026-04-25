"""
Processamento de vídeo com FFmpeg.
- Download via yt-dlp
- Extração de áudio
- Geração de clipes verticais 9:16 com blur de fundo
- Detecção de informações do vídeo
"""
import os
import re
import json
import uuid
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List

from models import ClipSuggestion, GeneratedClip
import config

logger = logging.getLogger(__name__)

# Diretórios internos do backend
_BASE = Path(__file__).parent
UPLOAD_DIR = _BASE / "uploads"
OUTPUT_DIR = _BASE / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ─── Utilitários ───────────────────────────────────────────────────────────────

def _run(cmd: List[str], description: str = "") -> subprocess.CompletedProcess:
    """Executa um comando e lança exceção em caso de erro."""
    logger.info(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Falha ao {description or 'executar comando'}\n"
            f"stderr: {result.stderr[-1000:]}"
        )
    return result


def get_video_info(video_path: str) -> dict:
    """Retorna informações básicas do vídeo via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            video_path,
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)

    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if not video_stream:
        raise ValueError("Nenhuma stream de vídeo encontrada.")

    duration = float(data.get("format", {}).get("duration", 0))
    return {
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "duration": duration,
    }


# ─── Download ──────────────────────────────────────────────────────────────────

def download_video(url: str, job_id: str) -> str:
    """
    Baixa o vídeo da URL usando yt-dlp.
    Retorna o caminho do arquivo baixado.
    """
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    output_template = str(job_dir / "video.%(ext)s")

    logger.info(f"[yt-dlp] Baixando: {url}")
    _run(
        [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", output_template,
            url,
        ],
        "baixar vídeo",
    )

    # Localiza o arquivo baixado
    for ext in ["mp4", "mkv", "webm", "avi"]:
        candidate = job_dir / f"video.{ext}"
        if candidate.exists():
            # Converte para mp4 se necessário
            if ext != "mp4":
                mp4_path = str(job_dir / "video.mp4")
                _run(
                    ["ffmpeg", "-i", str(candidate), "-c", "copy", mp4_path, "-y"],
                    "converter para mp4",
                )
                candidate.unlink()
                return mp4_path
            return str(candidate)

    raise FileNotFoundError(f"Arquivo de vídeo não encontrado após download em {job_dir}")


def save_upload(file_bytes: bytes, original_filename: str, job_id: str) -> str:
    """Salva arquivo de upload local e retorna o caminho."""
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    ext = Path(original_filename).suffix.lower() or ".mp4"
    dest = job_dir / f"video{ext}"
    dest.write_bytes(file_bytes)
    logger.info(f"[Upload] Salvo em {dest} ({len(file_bytes) / 1_048_576:.1f} MB)")
    return str(dest)


# ─── Extração de Áudio ─────────────────────────────────────────────────────────

def extract_audio(video_path: str) -> str:
    """Extrai áudio do vídeo como WAV mono 16kHz (ideal para Whisper)."""
    audio_path = str(Path(video_path).with_suffix(".wav"))
    _run(
        [
            "ffmpeg", "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path, "-y",
        ],
        "extrair áudio",
    )
    logger.info(f"[FFmpeg] Áudio extraído: {audio_path}")
    return audio_path


# ─── Geração de Clipes ─────────────────────────────────────────────────────────

def _build_vertical_filter(width: int, height: int, aspect: str = "9:16") -> str:
    """
    Constrói o filtro FFmpeg para converter para vídeo vertical.
    Usa fundo borrado (blur) com o conteúdo original centralizado.
    """
    # Target: 1080x1920 para 9:16
    if aspect == "9:16":
        tw, th = 1080, 1920
    else:
        # Fallback para 9:16
        tw, th = 1080, 1920

    is_already_vertical = height > width

    if is_already_vertical:
        # Só redimensiona para o tamanho alvo
        return f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2"

    # Landscape → Portrait:
    # 1. Escala o vídeo para preencher o fundo (maior que o target), depois borra
    # 2. Escala o vídeo original para caber na tela vertical
    # 3. Sobrepõe o original centralizado sobre o fundo borrado
    return (
        f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase,"
        f"crop={tw}:{th},"
        f"gblur=sigma=25[bg];"
        f"[0:v]scale=-2:{th}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
    )


def create_clip(
    video_path: str,
    start: float,
    end: float,
    output_path: str,
    video_info: dict,
) -> None:
    """Corta e converte um trecho do vídeo para formato vertical."""
    duration = end - start
    width = video_info["width"]
    height = video_info["height"]
    aspect = config.OUTPUT_ASPECT_RATIO

    vf = _build_vertical_filter(width, height, aspect)
    is_complex = ";" in vf  # filter_complex tem múltiplos streams

    if is_complex:
        cmd = [
            "ffmpeg",
            "-ss", str(start), "-i", video_path, "-t", str(duration),
            "-filter_complex", vf,
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path, "-y",
        ]
    else:
        cmd = [
            "ffmpeg",
            "-ss", str(start), "-i", video_path, "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path, "-y",
        ]

    _run(cmd, f"gerar clipe {Path(output_path).name}")


def process_clips(
    video_path: str,
    suggestions: List[ClipSuggestion],
    job_id: str,
) -> List[GeneratedClip]:
    """
    Gera os arquivos de vídeo para cada sugestão de clipe.
    Retorna lista de GeneratedClip com URLs de download.
    """
    output_job_dir = OUTPUT_DIR / job_id
    output_job_dir.mkdir(exist_ok=True)

    video_info = get_video_info(video_path)
    video_duration = video_info["duration"]

    generated = []

    for i, suggestion in enumerate(suggestions, start=1):
        clip_id = str(uuid.uuid4())[:8]
        # Garante que o clipe não ultrapasse a duração do vídeo
        start = max(0.0, suggestion.start_time)
        end = min(video_duration, suggestion.end_time)

        if end <= start:
            logger.warning(f"Clipe {i} tem duração inválida ({start:.1f}s - {end:.1f}s), pulando.")
            continue

        safe_title = re.sub(r'[^\w\s-]', '', suggestion.title)[:30].strip().replace(" ", "_")
        filename = f"clip_{i:02d}_{safe_title}_{clip_id}.{config.OUTPUT_FORMAT}"
        output_path = str(output_job_dir / filename)

        logger.info(f"[FFmpeg] Gerando clipe {i}/{len(suggestions)}: {filename}")
        try:
            create_clip(video_path, start, end, output_path, video_info)
        except Exception as e:
            logger.error(f"Erro ao gerar clipe {i}: {e}")
            continue

        generated.append(GeneratedClip(
            id=clip_id,
            title=suggestion.title,
            start_time=start,
            end_time=end,
            duration=round(end - start, 2),
            reason=suggestion.reason,
            confidence=suggestion.confidence,
            filename=filename,
            download_url=f"/api/download/{job_id}/{filename}",
        ))

    return generated
