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
VIGN   = 55           # pixels do fade cosseno top/bottom
IS_WIN = platform.system() == "Windows"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: List[str], desc: str = "") -> None:
    logger.info(f"$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ({desc}):\n{r.stderr[-1600:]}")


def _escape_path(path: str) -> str:
    """
    Normaliza path para uso dentro de filtros FFmpeg.
    No Windows: converte backslashes → forward slashes e escapa o ':' do drive.
    Ex: C:\\foo\\bar.ass → C\\:/foo/bar.ass
    """
    p = Path(path).as_posix()       # C:/foo/bar.ass
    if IS_WIN:
        # FFmpeg filtergraph usa ':' como separador de opções;
        # o ':' do drive letter precisa ser escapado com '\'
        p = p.replace(":", "\\:")   # C\\:/foo/bar.ass
    return p


# ─── Filtro principal ─────────────────────────────────────────────────────────

def _build_filter(fg_h: int, blur_sigma: int, vign: int) -> str:
    """
    filter_complex FFmpeg para o layout center blur.

    Streams de entrada: [0:v] — vídeo fonte usado DUAS vezes (bg e fg).

    FIX vs versão anterior:
      Antes: scale=-2:{fg_h}  →  escala pela altura, mas se a entrada já for
             9:16 (ex.: 1080×1920), a largura resultante fica abaixo de 1080
             e o crop subsequente falha com "Invalid size".

      Agora: scale={CW}:{fg_h}:force_original_aspect_ratio=increase
             →  garante que AMBAS as dimensões sejam >= alvo antes do crop,
             funcionando tanto com landscape quanto com vídeos já em portrait.
    """

    # ── Fundo: cover scale + gblur + leve escurecimento ──────────────────────
    bg = (
        f"[0:v]"
        f"scale={CW}:{CH}:force_original_aspect_ratio=increase,"
        f"crop={CW}:{CH},"
        f"gblur=sigma={blur_sigma},"
        f"eq=brightness=-0.10:saturation=0.85"
        f"[bg]"
    )

    # ── Foreground: cover scale para {CW}×{fg_h}, crop central, alpha ────────
    # force_original_aspect_ratio=increase → dimensão menor define o scale,
    # garantindo largura >= CW E altura >= fg_h antes do crop.
    fg_prep = (
        f"[0:v]"
        f"scale={CW}:{fg_h}:force_original_aspect_ratio=increase,"
        f"crop={CW}:{fg_h},"           # crop lateral/vertical centralizado
        f"setsar=1,"
        f"format=yuva420p"             # canal alpha necessário para geq
        f"[fg_raw]"
    )

    # ── Alpha fade cosseno nas bordas top/bottom do FG ────────────────────────
    # Curva: (1 - cos(π·t)) / 2  — mesma usada na composição Python aprovada.
    # Os \, dentro da string já são os literais que o FFmpeg espera no
    # filter_complex; ao passar via subprocess list não há interpretação shell.
    fade_expr = (
        f"if(lt(Y\\,{vign})\\,"
        f"255*(1-cos(PI*Y/{vign}))/2\\,"
        f"if(gt(Y\\,{fg_h}-{vign})\\,"
        f"255*(1-cos(PI*({fg_h}-Y)/{vign}))/2\\,"
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

    # ── Overlay: fg centralizado sobre bg ─────────────────────────────────────
    comp = f"[bg][fg_a]overlay=(W-w)/2:(H-h)/2,setsar=1[out]"

    return ";".join([bg, fg_prep, fg_alpha, comp])


def _burn_subtitles_local(
    video_in: str,
    ass_path: str,
    font_path: str,
    video_out: str,
) -> None:
    """
    Queima legendas ASS no vídeo com tratamento de path para Windows.
    Mantido localmente para não depender da versão de viral_edit.py do usuário.
    """
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


# ─── Interface pública ────────────────────────────────────────────────────────

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

    1. Composição FFmpeg: bg borrado + fg nítido com fade cosseno
    2. Se add_captions=True, queima legendas ASS por cima

    Retorna o caminho output_video gerado.
    """
    ratio      = max(0.3, min(0.95, options.video_height_ratio))
    blur_sigma = max(5, min(100, options.blur_strength))
    fg_h       = int(CH * ratio)
    fg_h       = (fg_h // 2) * 2          # par obrigatório para libx264
    style      = options.caption_style.value if options.caption_style else "tiktok"
    font_p     = config.FONT_PATH or ""

    logger.info(
        f"[blur] center_blur: ratio={ratio:.0%}  fg_h={fg_h}px  "
        f"blur=σ{blur_sigma}  captions={options.add_captions}  "
        f"win={IS_WIN}"
    )

    filt = _build_filter(fg_h, blur_sigma, VIGN)

    with tempfile.TemporaryDirectory(prefix="clipforge_blur_") as tmp:

        # ── Passo 1: composição ────────────────────────────────────────────────
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

        # ── Passo 2: legendas ──────────────────────────────────────────────────
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
            # Usa _burn_subtitles_local (path-safe para Windows)
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