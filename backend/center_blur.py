"""
center_blur.py — Layout "vídeo central com fundo desfocado".

Composição final (9:16 / 1080×1920):
  ┌──────────────────┐
  │  fundo blur top  │  ← mesmo vídeo, cover + gblur forte
  ├ ·  ·  ·  ·  ·  ·┤  ← fade cosseno (transição imperceptível)
  │                  │
  │  vídeo principal │  ← nítido, altura controlada por CENTER_VIDEO_HEIGHT_RATIO
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
VIGN_Default = 90              # fade cosseno top/bottom — transição suave
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


def _probe_fg_height(input_video: str, fg_zoom: float = 1.0, height_ratio: float = 1.0) -> tuple[int, int]:
    """
    Define o tamanho da área central do vídeo.

    Regra:
    - CENTER_VIDEO_HEIGHT_RATIO define a altura do bloco central.
    - a largura do bloco central fica presa ao canvas (CW), para evitar
      ultrapassar a tela em vídeos 16:9 ou 9:16.
    """
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            input_video,
        ],
        capture_output=True, text=True,
    )

    if r.returncode != 0 or not r.stdout.strip():
        logger.warning("[blur] ffprobe falhou, usando fallback 16:9")
        vw, vh = 1920, 1080
    else:
        vw, vh = map(int, r.stdout.strip().split(","))

    # altura fixa do bloco central
    fg_h = int(CH * height_ratio)

    # garante par (ffmpeg costuma exigir isso em vários cenários)
    fg_h = max(2, (fg_h // 2) * 2)

    # largura do bloco central fica presa no canvas
    fg_w = CW

    logger.info(
        f"[blur] FG FIXO: {fg_w}x{fg_h} "
        f"({height_ratio:.0%} da altura, src={vw}x{vh}, zoom={fg_zoom:.2f})"
    )

    return fg_w, fg_h


def _build_filter(fg_w: int, fg_h: int, blur_sigma: int, vign: int, fg_zoom: float = 1.0) -> str:
    """
    Layout de Shorts 9:16:
      ┌─────────────────┐
      │   fundo blur    │
      ├─────────────────┤
      │ vídeo principal │  ← centralizado e com altura fixa
      ├─────────────────┤
      │   fundo blur    │
      └─────────────────┘

    fg_w e fg_h são calculados por _probe_fg_height().
    """
    # ── BACKGROUND ──────────────────────────────────────────────────────────
    bg = (
        f"[0:v]"
        f"scale={CW}:{CH}:force_original_aspect_ratio=increase,"
        f"crop={CW}:{CH},"
        f"split[bg1][bg2];"
        f"[bg1]gblur=sigma={blur_sigma}[bpass1];"
        f"[bpass1]gblur=sigma={blur_sigma//2}[bpass2];"
        f"[bpass2]eq=brightness=-0.18:saturation=0.60[bg]"
    )

    # ── FOREGROUND ──────────────────────────────────────────────────────────
    # A ideia aqui é:
    # - fazer o vídeo cobrir a área central inteira (CW x fg_h)
    # - se fg_zoom > 1.0, ampliar ainda mais antes do crop central
    zoom_h = max(fg_h, int(fg_h * max(1.0, fg_zoom)))
    zoom_h = (zoom_h // 2) * 2

    fg_prep = (
        f"[0:v]"
        f"scale={CW}:{zoom_h}:force_original_aspect_ratio=increase,"
        f"crop={CW}:{fg_h}:(iw-{CW})/2:(ih-{fg_h})/2,"
        f"setsar=1,"
        f"format=yuva420p"
        f"[fg_raw]"
    )

    # ── FADE COSSENO ────────────────────────────────────────────────────────
    # geq não suporta 'ih' do jeito que a gente precisa aqui, então usamos fg_h já calculado.
    fade_expr = (
        f"if(lt(Y\\,{vign})\\,"
        f"(1-cos(PI*Y/{vign}))/2\\,"
        f"if(gt(Y\\,{fg_h}-{vign})\\,"
        f"(1-cos(PI*({fg_h}-Y)/{vign}))/2\\,"
        f"1))"
    )

    fg_alpha = (
        f"[fg_raw]"
        f"geq="
        f"lum='lum(X\\,Y)':"
        f"cb='cb(X\\,Y)':"
        f"cr='cr(X\\,Y)':"
        f"a='alpha(X\\,Y)*{fade_expr}'"
        f"[fg_a]"
    )

    # Descarta bg2 (split auxiliar)
    discard = f"[bg2]nullsink"

    # Overlay: centralizado horizontal e verticalmente
    comp = f"[bg][fg_a]overlay=(W-w)/2:(H-h)/2,setsar=1[out]"

    return ";".join([bg, fg_prep, fg_alpha, discard, comp])


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
    # blur_sigma >= 20 garante fundo realmente desfocado (dois passes no filtro)
    blur_sigma = max(20, min(100, options.blur_strength))

    # zoom adicional opcional
    fg_zoom = float(getattr(options, "video_zoom", 1.0))

    # controla o "tamanho" do vídeo principal na tela
    height_ratio = float(getattr(options, "video_height_ratio", 0.6))
    height_ratio = max(0.2, min(1.0, height_ratio))  # intervalo seguro

    #controla o tamanho do fade
    vign = int(getattr(options, "vign_strength", VIGN_Default))
    vign = max(0, min(vign, 300))
               
    # calcula o bloco central
    fg_w, fg_h = _probe_fg_height(input_video, fg_zoom, height_ratio)

    style = options.caption_style.value if options.caption_style else "tiktok"
    font_p = config.FONT_PATH or ""

    logger.info(
        f"[blur] center_blur: fg={fg_w}×{fg_h}px ratio={height_ratio:.0%} "
        f"zoom={fg_zoom:.2f} blur=σ{blur_sigma} captions={options.add_captions} win={IS_WIN}"
    )

    filt = _build_filter(fg_w, fg_h, blur_sigma, vign, fg_zoom=fg_zoom)

    duration = clip_end - clip_start

    with tempfile.TemporaryDirectory(prefix="clipforge_blur_") as tmp:
        composed = str(Path(tmp) / "composed.mp4")

        _run(
            [
                "ffmpeg",
                "-ss", str(clip_start), "-i", input_video, "-t", str(duration),
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