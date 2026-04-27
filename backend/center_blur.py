"""
center_blur.py — Layout "vídeo central com fundo desfocado".

Composição final (9:16 / 1080×1920):
  ┌──────────────────┐
  │  fundo blur top  │  ← mesmo vídeo, ampliado e fortemente borrado
  ├──────────────────┤
  │                  │
  │  vídeo principal │  ← nítido, ~70% da altura, centralizado
  │    (nítido)      │
  │                  │
  ├──────────────────┤
  │ fundo blur bot.  │  ← continuação do fundo borrado
  └──────────────────┘

Implementação: 100% FFmpeg, sem dependências extras.
Legendas reutilizadas de viral_edit.py.
"""
import logging
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import List

from models import CenterBlurOptions, TranscriptSegment
import config

logger = logging.getLogger(__name__)

# Canvas 9:16
TW, TH = 1080, 1920


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: List[str], desc: str = "") -> None:
    logger.info(f"$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ({desc}):\n{r.stderr[-1400:]}")


# ─── Filtro de composição ─────────────────────────────────────────────────────

def _build_center_blur_filter(
    fg_h: int,
    blur_sigma: int,
) -> str:
    """
    Constrói o filter_complex FFmpeg para o layout center blur.

    Streams de entrada:
      [0:v]  — vídeo fonte (usado tanto para fundo quanto para foreground)

    Saída:
      [out]  — canvas 1080×1920 com fundo borrado + vídeo central nítido

    Estratégia:
      1. [bg]  scale para cobrir 1080×1920 (increase) → crop 1080×1920 → gblur
      2. [fg]  scale para caber em 1080×fg_h (decrease) → dimensões pares (libx264)
      3. overlay: fg centralizado sobre bg
    """
    return (
        # ── Fundo ──────────────────────────────────────────────────────────────
        f"[0:v]scale={TW}:{TH}:force_original_aspect_ratio=increase,"
        f"crop={TW}:{TH},"
        f"gblur=sigma={blur_sigma}[bg];"

        # ── Foreground nítido ──────────────────────────────────────────────────
        # scale para caber em 1080×fg_h mantendo proporção,
        # depois garante dimensões pares (obrigatório para libx264)
        f"[0:v]scale={TW}:{fg_h}:force_original_aspect_ratio=increase,"
        f"crop={TW}:{fg_h}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1[fg];"

        # ── Composição ────────────────────────────────────────────────────────
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[out]"
    )


# ─── Geração do vídeo blur ────────────────────────────────────────────────────

def generate_center_blur_video(
    input_video: str,
    output_video: str,
    options: CenterBlurOptions,
    segments: List[TranscriptSegment],
    clip_start: float,
    clip_end: float,
) -> str:
    """
    Gera a versão "center blur" de um clipe.

    Passos:
      1. Compõe fundo borrado + vídeo central nítido via filter_complex
      2. Se add_captions=True, queima legendas ASS estilo TikTok/bold por cima

    Parâmetros
    ----------
    input_video  : caminho do clipe já cortado (saída de create_clip)
    output_video : caminho de destino final
    options      : CenterBlurOptions (ratio, blur, captions, style)
    segments     : segmentos da transcrição completa (para gerar as legendas)
    clip_start   : timestamp de início do clipe no vídeo original (segundos)
    clip_end     : timestamp de fim do clipe no vídeo original (segundos)

    Retorna o caminho output_video gerado.
    """
    ratio      = max(0.3, min(0.95, options.video_height_ratio))
    blur_sigma = max(5, min(100, options.blur_strength))
    fg_h       = int(TH * ratio)
    # Garante par
    fg_h       = (fg_h // 2) * 2

    style  = options.caption_style.value if options.caption_style else "tiktok"
    font_p = config.FONT_PATH or ""

    logger.info(
        f"[blur] Iniciando center blur: ratio={ratio} fg_h={fg_h}px "
        f"blur=sigma{blur_sigma} captions={options.add_captions}"
    )

    filter_complex = _build_center_blur_filter(fg_h, blur_sigma)

    with tempfile.TemporaryDirectory(prefix="clipforge_blur_") as tmp:
        # ── Passo 1: composição blur ───────────────────────────────────────────
        composed = str(Path(tmp) / "composed.mp4")
        _run(
            [
                "ffmpeg", "-i", input_video,
                "-filter_complex", filter_complex,
                "-map", "[out]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                composed, "-y",
            ],
            "composição center blur",
        )

        # ── Passo 2: legendas ──────────────────────────────────────────────────
        if options.add_captions and segments:
            # Importa funções de legendas de viral_edit (sem duplicar código)
            from viral_edit import generate_ass_subtitles, _burn_subtitles

            ass_path = str(Path(tmp) / "captions.ass")
            generate_ass_subtitles(
                segments=segments,
                clip_start=clip_start,
                clip_end=clip_end,
                style=style,
                font_path=font_p,
                output_path=ass_path,
            )
            _burn_subtitles(
                video_in=composed,
                ass_path=ass_path,
                font_path=font_p,
                video_out=output_video,
            )
        else:
            shutil.copy2(composed, output_video)

    logger.info(f"[blur] ✅ Center blur gerado: {output_video}")
    return output_video
