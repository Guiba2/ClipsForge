"""
center_blur.py — Layout "vídeo central com fundo desfocado".

Composição final (9:16 / 1080×1920):
  ┌──────────────────┐
  │  fundo blur top  │  ← mesmo vídeo, cover + gblur forte
  ├ ·  ·  ·  ·  ·  ·┤  ← fade cosseno (transição imperceptível)
  │                  │
  │  vídeo principal │  ← nítido, ~70% da altura, centralizado
  │    (nítido)      │
  │                  │
  ├ ·  ·  ·  ·  ·  ·┤  ← fade cosseno
  │ fundo blur bot.  │
  └──────────────────┘

FG usa force_original_aspect_ratio=increase para funcionar tanto com
vídeos landscape QUANTO com clipes já em 9:16 (saída do pipeline).
Paths compatíveis com Windows via _escape_path().
"""
import logging
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from models import CenterBlurOptions, TranscriptSegment
import config

logger = logging.getLogger(__name__)

CW, CH = 1080, 1920   # canvas 9:16
VIGN = 55              # fade cosseno top/bottom
IS_WIN = platform.system() == "Windows"


def _run(cmd: List[str], desc: str = "") -> None:
    logger.info(f"$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ({desc}):\n{r.stderr[-1600:]}")


def _escape_path(path: str) -> str:
    p = Path(path).as_posix()
    if IS_WIN:
        p = p.replace(":", "\\:")
    return p


def _build_filter(fg_h: int, blur_sigma: int, vign: int, fg_zoom: float = 1.0) -> str:
    """
    Layout:
    - fundo ocupa o canvas inteiro com blur
    - foreground ocupa toda a largura do canvas
    - foreground fica centralizado e com fade nas bordas de cima/baixo
    """

    fg_scaled_h = max(2, int(fg_h * fg_zoom))
    fg_scaled_h = (fg_scaled_h // 2) * 2  # garante altura par

    # Fundo: cover + blur
    bg = (
        f"[0:v]"
        f"scale={CW}:{CH}:force_original_aspect_ratio=increase,"
        f"crop={CW}:{CH},"
        f"gblur=sigma={blur_sigma},"
        f"eq=brightness=-0.10:saturation=0.85"
        f"[bg]"
    )

    # Foreground: preencher a largura do canvas
    # Isso faz o vídeo "abrir" até as laterais esquerda/direita
    fg_prep = (
        f"[0:v]"
        f"scale={CW}:{fg_scaled_h}:force_original_aspect_ratio=increase,"
        f"crop={CW}:{fg_scaled_h},"
        f"setsar=1,"
        f"format=yuva420p"
        f"[fg_raw]"
    )

    # Fade vertical nas bordas superior e inferior
    fade_expr = (
        f"if(lt(Y\\,{vign})\\,"
        f"255*(1-cos(PI*Y/{vign}))/2\\,"
        f"if(gt(Y\\,{fg_scaled_h}-{vign})\\,"
        f"255*(1-cos(PI*({fg_scaled_h}-Y)/{vign}))/2\\,"
        f"255))"
    )

    fg_alpha = (
        f"[fg_raw]"
        f"geq="
        f"lum='lum(X\\,Y)':"
        f"cb='cb(X\\,Y)':"
        f"cr='cr(X\\,Y)':"
        f"a='{fade_expr}'"
        f"[fg_a]"
    )

    # Centraliza no canvas
    comp = f"[bg][fg_a]overlay=(W-w)/2:(H-h)/2,setsar=1[out]"

    return ";".join([bg, fg_prep, fg_alpha, comp])


def _burn_subtitles_local(
    video_in: str,
    ass_path: str,
    font_path: str,
    video_out: str,
) -> None:
    ass_esc = _escape_path(ass_path)

    if font_path and Path(font_path).exists():
        fonts_dir = _escape_path(str(Path(font_path).parent))
        sub_filter = f"subtitles=filename='{ass_esc}':fontsdir='{fonts_dir}'"
    else:
        sub_filter = f"subtitles=filename='{ass_esc}'"

    _run(
        [
            "ffmpeg", "-i", video_in,
            "-vf", sub_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "21",
            "-c:a", "copy",
            "-movflags", "+faststart",
            video_out, "-y",
        ],
        "queimar legendas",
    )


def generate_center_blur_video(
    input_video: str,
    output_video: str,
    options: CenterBlurOptions,
    segments: List[TranscriptSegment],
    clip_start: float,
    clip_end: float,
) -> str:
    ratio = max(0.3, min(0.95, options.video_height_ratio))
    blur_sigma = max(5, min(100, options.blur_strength))

    fg_h = int(CH * ratio)
    fg_h = (fg_h // 2) * 2  # par obrigatório para libx264

    # Se sua classe tiver esse campo, ele funciona; se não tiver, fica 1.0
    fg_zoom = float(getattr(options, "video_zoom", 1.0))

    style = options.caption_style.value if options.caption_style else "tiktok"
    font_p = config.FONT_PATH or ""

    logger.info(
        f"[blur] center_blur: ratio={ratio:.0%} fg_h={fg_h}px "
        f"zoom={fg_zoom:.2f} blur=σ{blur_sigma} captions={options.add_captions} win={IS_WIN}"
    )

    filt = _build_filter(fg_h, blur_sigma, VIGN, fg_zoom=fg_zoom)

    with tempfile.TemporaryDirectory(prefix="clipforge_blur_") as tmp:
        composed = str(Path(tmp) / "composed.mp4")

        _run(
            [
                "ffmpeg", "-i", input_video,
                "-filter_complex", filt,
                "-map", "[out]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                composed, "-y",
            ],
            "composição center blur",
        )

        if options.add_captions and segments:
            from viral_edit import generate_ass_subtitles

            ass_path = str(Path(tmp) / "captions.ass")
            generate_ass_subtitles(
                segments=segments,
                clip_start=clip_start,
                clip_end=clip_end,
                style=style,
                font_path=font_p,
                output_path=ass_path,
            )

            _burn_subtitles_local(
                video_in=composed,
                ass_path=ass_path,
                font_path=font_p,
                video_out=output_video,
            )
        else:
            shutil.copy2(composed, output_video)

    logger.info(f"[blur] ✅ Gerado: {output_video}")
    return output_video