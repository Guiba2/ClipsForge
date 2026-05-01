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

CW, CH = 1080, 1920
VIGN = 90
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


def _even(n: int) -> int:
    return max(2, (n // 2) * 2)


def _build_filter(fg_h: int, blur_sigma: int, vign: int, fg_zoom: float = 1.0) -> str:
    """
    O foreground fica com altura fixa baseada no ratio.
    O zoom aumenta o vídeo, mas a altura final continua controlada pelo fg_h.
    """
    bg = (
        f"[0:v]"
        f"scale={CW}:{CH}:force_original_aspect_ratio=increase,"
        f"crop={CW}:{CH},"
        f"split[bg1][bg2];"
        f"[bg1]gblur=sigma={blur_sigma}[bpass1];"
        f"[bpass1]gblur=sigma={blur_sigma//2}[bpass2];"
        f"[bpass2]eq=brightness=-0.18:saturation=0.60[bg]"
    )

    # Foreground:
    # - fg_h define a altura final visível do vídeo no canvas
    # - scale=-2:fg_h preserva aspecto original
    # - se fg_zoom > 1.0, ampliamos antes e depois recortamos de volta para fg_h
    if fg_zoom > 1.0:
        zoom_h = _even(int(fg_h * fg_zoom))
        fg_prep = (
            f"[0:v]"
            f"scale=-2:{zoom_h},"
            f"crop=iw:{fg_h}:0:(ih-{fg_h})/2,"
            f"setsar=1,"
            f"format=yuva420p"
            f"[fg_raw]"
        )
    else:
        fg_prep = (
            f"[0:v]"
            f"scale=-2:{fg_h}:force_original_aspect_ratio=decrease,"
            f"setsar=1,"
            f"format=yuva420p"
            f"[fg_raw]"
        )

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

    discard = f"[bg2]nullsink"
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
    blur_sigma = max(20, min(100, options.blur_strength))
    fg_zoom = float(getattr(options, "video_zoom", 1.0))

    # Agora o ratio controla diretamente a altura visível do vídeo.
    height_ratio = float(getattr(config, "CENTER_VIDEO_HEIGHT_RATIO", 0.6))
    height_ratio = max(0.2, min(1.0, height_ratio))

    fg_h = _even(int(CH * height_ratio))

    style = options.caption_style.value if options.caption_style else "tiktok"
    font_p = config.FONT_PATH or ""

    logger.info(
        f"[blur] center_blur: fg_h={fg_h}px ratio={height_ratio:.0%} "
        f"zoom={fg_zoom:.2f} blur=σ{blur_sigma} captions={options.add_captions} win={IS_WIN}"
    )

    filt = _build_filter(fg_h, blur_sigma, VIGN, fg_zoom=fg_zoom)
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