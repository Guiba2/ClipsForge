"""
viral_edit.py — Modo viral: layout dual-panel + legendas estilo TikTok.

Pipeline interno:
  1. Detectar rosto (opencv, opcional) → crop da panel superior
  2. Montar layout 9:16 com vstack: panel superior (40%) + panel inferior (60%)
  3. Gerar arquivo de legendas ASS com estilo TikTok/bold
  4. Gravar legenda no vídeo via ffmpeg subtitles filter
  5. Retornar caminho do vídeo viral final

Não tem dependências pesadas obrigatórias:
  - OpenCV é opcional (FACE_DETECTION=true); sem ele usa crop central.
  - Pillow NÃO é necessário.
  - Tudo feito com FFmpeg + stdlib Python.
"""
import re
import os
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from models import TranscriptSegment, ViralOptions
import config

logger = logging.getLogger(__name__)

# Canvas final: 1080 × 1920 (9:16)
TW, TH = 1080, 1920
# Split: 40% top (facecam) / 60% bottom (gameplay)
TOP_H    = int(TH * 0.40)   # 768 px
BOTTOM_H = TH - TOP_H       # 1152 px


# ─── Helpers FFmpeg ───────────────────────────────────────────────────────────

def _run(cmd: List[str], desc: str = "") -> subprocess.CompletedProcess:
    logger.info(f"$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ({desc}):\n{r.stderr[-1200:]}")
    return r


def _video_info(path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(r.stdout)
    vs = next((s for s in data["streams"] if s.get("codec_type") == "video"), {})
    return {
        "width":    int(vs.get("width", 0)),
        "height":   int(vs.get("height", 0)),
        "duration": float(data.get("format", {}).get("duration", 0)),
    }


# ─── Detecção de rosto (OpenCV) ───────────────────────────────────────────────

def _detect_face_crop(video_path: str, target_w: int, target_h: int) -> Optional[Tuple[int, int]]:
    """
    Extrai um frame do meio do vídeo, roda o classificador Haar de rostos.
    Retorna (x, y) do centro do rosto detectado no espaço do vídeo original,
    ou None se não encontrar / OpenCV não instalado.
    """
    try:
        import cv2
    except ImportError:
        logger.info("[viral] OpenCV não instalado — usando crop central.")
        return None

    info = _video_info(video_path)
    mid  = info["duration"] / 2.0

    # Extrai 1 frame do meio para um arquivo temporário
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        subprocess.run(
            ["ffmpeg", "-ss", str(mid), "-i", video_path,
             "-frames:v", "1", "-q:v", "2", tmp_path, "-y"],
            capture_output=True, check=True,
        )
        frame = cv2.imread(tmp_path)
    except Exception as e:
        logger.warning(f"[viral] Falha ao extrair frame para detecção: {e}")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if frame is None:
        return None

    gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Cascade Haar frontal — incluso no OpenCV, sem download extra
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    faces   = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

    if len(faces) == 0:
        logger.info("[viral] Nenhum rosto detectado — usando crop central.")
        return None

    # Pega o maior rosto detectado
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    cx = x + w // 2
    cy = y + h // 2
    logger.info(f"[viral] Rosto detectado: centro ({cx}, {cy}), tamanho {w}×{h}")
    return (cx, cy)


def _face_crop_filter(video_path: str, out_w: int, out_h: int) -> str:
    """
    Retorna fragmento de filtro FFmpeg para recortar a região do rosto.
    Se não detectar rosto, usa crop central.
    """
    info  = _video_info(video_path)
    src_w = info["width"]
    src_h = info["height"]

    face  = None
    if config.FACE_DETECTION:
        face = _detect_face_crop(video_path, out_w, out_h)

    if face:
        cx, cy = face
        # Garante que o crop fica dentro dos limites
        x = max(0, min(cx - out_w // 2, src_w - out_w))
        y = max(0, min(cy - out_h // 2, src_h - out_h))
        return f"crop={out_w}:{out_h}:{x}:{y},scale={out_w}:{out_h}"
    else:
        # Crop central inteligente + scale
        return (
            f"crop=min(iw\\,iw*{out_h}/{out_h}):min(ih\\,ih):"
            f"(iw-min(iw\\,iw))/2:(ih-min(ih\\,ih))/2,"
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}"
        )


# ─── Legendas ASS ─────────────────────────────────────────────────────────────

# Palavras que merecem destaque automático (heurística simples)
_HIGHLIGHT_WORDS = {
    "nunca", "jamais", "incrível", "absurdo", "impossível", "chocante",
    "never", "insane", "crazy", "wild", "amazing", "shocking", "wait",
    "wow", "omg", "viral", "secret", "truth", "lie", "exposed",
    "isso", "esse", "essa", "aqui", "agora", "hoje", "por que",
}


def _is_highlight(word: str) -> bool:
    return word.lower().strip(".,!?\"'") in _HIGHLIGHT_WORDS


def _ass_time(seconds: float) -> str:
    """Converte segundos para formato ASS: H:MM:SS.cc"""
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = seconds % 60
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _make_ass_header(style: str, font_path: str) -> str:
    """Cabeçalho ASS com estilo configurável."""
    font_name = "Arial"
    if font_path and Path(font_path).exists():
        # Extrai nome da fonte do arquivo (heurística pelo nome do arquivo)
        font_name = Path(font_path).stem.replace("-", " ").replace("_", " ")

    if style == "tiktok":
        # Estilo TikTok: branco com borda preta grossa, grande, centralizado no topo
        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {TW}
PlayResY: {TH}
WrapStyle: 1

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font_name},88,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,5,2,8,60,60,120,1
Style: Highlight,{font_name},88,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,5,2,8,60,60,120,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    else:
        # Estilo bold: amarelo, maior, borda escura
        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {TW}
PlayResY: {TH}
WrapStyle: 1

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font_name},96,&H00FFFF00,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,0,0,1,6,3,8,60,60,120,1
Style: Highlight,{font_name},96,&H0000FFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,105,105,0,0,1,6,3,8,60,60,120,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def _chunk_segments(
    segments: List[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    max_chars: int = 40,
) -> List[dict]:
    """
    Recorta os segmentos que pertencem ao clipe e divide em chunks de legenda.
    Retorna lista de {start, end, text, has_highlight}.
    Os timestamps são relativos ao início do clipe (t=0).
    """
    # Filtra segmentos que se sobrepõem ao clipe
    relevant = [
        s for s in segments
        if s.end > clip_start and s.start < clip_end
    ]

    chunks = []
    for seg in relevant:
        # Ajusta timestamps para serem relativos ao início do clipe
        rel_start = max(0.0, seg.start - clip_start)
        rel_end   = min(clip_end - clip_start, seg.end - clip_start)
        if rel_end <= rel_start:
            continue

        text  = seg.text.strip()
        words = text.split()

        # Quebra em linhas de no máximo max_chars caracteres
        lines, current = [], []
        for word in words:
            if sum(len(w) for w in current) + len(current) + len(word) > max_chars and current:
                lines.append(current)
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(current)

        # Distribui o tempo do segmento proporcionalmente entre as linhas
        n     = len(lines)
        dt    = (rel_end - rel_start) / n if n else 0
        for j, line_words in enumerate(lines):
            t0  = rel_start + j * dt
            t1  = rel_start + (j + 1) * dt
            txt = " ".join(line_words)
            has_hl = any(_is_highlight(w) for w in line_words)
            chunks.append({"start": t0, "end": t1, "text": txt, "has_highlight": has_hl})

    return chunks


def _word_tagged(text: str) -> str:
    r"""
    Retorna o texto com palavras de destaque entre tags ASS {\c&H00FFFF&}.
    """
    parts = []
    for word in text.split():
        clean = word.strip(".,!?\"'")
        if _is_highlight(clean):
            parts.append(r"{\c&H00FFFF&}" + word + r"{\c&HFFFFFF&}")
        else:
            parts.append(word)
    return " ".join(parts)


def generate_ass_subtitles(
    segments: List[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    style: str,
    font_path: str,
    output_path: str,
) -> str:
    """
    Gera arquivo .ass com legendas estilo TikTok/bold para um clipe específico.
    Retorna o caminho do arquivo gerado.
    """
    chunks = _chunk_segments(segments, clip_start, clip_end)
    header = _make_ass_header(style, font_path)

    lines = [header]
    for c in chunks:
        t0  = _ass_time(c["start"])
        t1  = _ass_time(c["end"])
        txt = _word_tagged(c["text"]) if style == "tiktok" else c["text"].upper()
        # Highlight de linha inteira se estilo bold e tem palavra-chave
        s   = "Highlight" if c["has_highlight"] and style == "bold" else "Default"
        lines.append(f"Dialogue: 0,{t0},{t1},{s},,0,0,0,,{txt}")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"[viral] ASS gerado: {output_path} ({len(chunks)} linhas)")
    return output_path


# ─── Layout dual-panel ────────────────────────────────────────────────────────

def _prepare_top_panel(clip_path: str, tmp_dir: str, face_detected: bool) -> str:
    """
    Prepara o vídeo para o painel superior (facecam / conteúdo principal).
    Saída: 1080 × 768 (TOP_H).
    """
    out = str(Path(tmp_dir) / "top_panel.mp4")
    info = _video_info(clip_path)
    w, h = info["width"], info["height"]

    # Se já for vertical, usa diretamente com scale+crop
    if h >= w:
        vf = (
            f"scale={TW}:-2:force_original_aspect_ratio=increase,"
            f"crop={TW}:{TOP_H}"
        )
    else:
        # Landscape: zoom + crop central no terço superior (onde geralmente fica o rosto)
        # Tenta detectar rosto para posicionar o crop
        face = None
        if config.FACE_DETECTION:
            face = _detect_face_crop(clip_path, TW, TOP_H)

        if face:
            cx, cy = face
            # Escala o vídeo para caber na largura alvo mantendo proporção
            scale_factor = TW / w
            scaled_h     = int(h * scale_factor)
            scaled_cy    = int(cy * scale_factor)
            crop_y       = max(0, min(scaled_cy - TOP_H // 2, scaled_h - TOP_H))
            vf = (
                f"scale={TW}:{scaled_h},"
                f"crop={TW}:{TOP_H}:0:{crop_y}"
            )
        else:
            # Crop central do terço superior
            vf = (
                f"scale={TW}:-2:force_original_aspect_ratio=increase,"
                f"crop={TW}:{TOP_H}:0:0"
            )

    _run(
        ["ffmpeg", "-i", clip_path, "-vf", vf,
         "-c:v", "libx264", "-preset", "fast", "-crf", "22",
         "-an", out, "-y"],
        "preparar painel superior",
    )
    return out


def _prepare_bottom_panel(
    clip_path: str,
    bg_video_path: Optional[str],
    clip_duration: float,
    tmp_dir: str,
) -> str:
    """
    Prepara o painel inferior (gameplay ou loop do próprio vídeo).
    Saída: 1080 × 1152 (BOTTOM_H).
    Se bg_video_path fornecido, usa ele; senão duplica o clipe com crop diferente.
    """
    out = str(Path(tmp_dir) / "bottom_panel.mp4")

    if bg_video_path and Path(bg_video_path).exists():
        # Usa o gameplay externo — loop até cobrir a duração do clipe
        bg_info = _video_info(bg_video_path)
        bg_dur  = bg_info["duration"]
        loops   = max(1, int(clip_duration / bg_dur) + 1)

        # Cria lista de concatenação temporária
        concat_list = str(Path(tmp_dir) / "bg_concat.txt")
        with open(concat_list, "w") as f:
            for _ in range(loops):
                f.write(f"file '{bg_video_path}'\n")

        looped_bg = str(Path(tmp_dir) / "bg_looped.mp4")
        _run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list,
             "-t", str(clip_duration),
             "-c:v", "libx264", "-preset", "fast", "-crf", "24",
             "-an", looped_bg, "-y"],
            "fazer loop do gameplay",
        )
        src = looped_bg
    else:
        # Sem gameplay → duplica o clipe com crop do terço inferior (ângulo diferente)
        src = clip_path

    info = _video_info(src)
    w, h = info["width"], info["height"]

    if h >= w:
        # Já vertical
        vf = (
            f"scale={TW}:-2:force_original_aspect_ratio=increase,"
            f"crop={TW}:{BOTTOM_H}"
        )
    else:
        # Landscape: crop do terço inferior + blur lateral para preencher
        vf = (
            f"[0:v]scale={TW}:{BOTTOM_H}:force_original_aspect_ratio=increase,"
            f"crop={TW}:{BOTTOM_H},"
            f"gblur=sigma=30[bg];"
            f"[0:v]scale=-2:{BOTTOM_H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )

    is_complex = ";" in vf
    base_cmd   = ["ffmpeg", "-i", src]
    if is_complex:
        enc = ["-filter_complex", vf, "-map", "[v]"]
    else:
        enc = ["-vf", vf]

    _run(
        base_cmd + enc +
        ["-t", str(clip_duration),
         "-c:v", "libx264", "-preset", "fast", "-crf", "22",
         "-an", out, "-y"],
        "preparar painel inferior",
    )
    return out


def _stack_panels(top: str, bottom: str, audio_src: str, duration: float, out: str) -> None:
    """
    Empilha painel superior e inferior verticalmente (vstack) e mescla o áudio original.
    """
    _run(
        [
            "ffmpeg",
            "-i", top, "-i", bottom, "-i", audio_src,
            "-filter_complex",
            f"[0:v]setpts=PTS-STARTPTS[top];"
            f"[1:v]setpts=PTS-STARTPTS[bot];"
            f"[top][bot]vstack=inputs=2[stacked]",
            "-map", "[stacked]", "-map", "2:a?",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "21",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            out, "-y",
        ],
        "empilhar painéis",
    )


def _burn_subtitles(video_in: str, ass_path: str, font_path: str, video_out: str) -> None:
    """
    Queima as legendas ASS no vídeo via filtro subtitles do FFmpeg.
    """
    # O filtro subtitles aceita force_style para sobrescrever fonte se necessário
    if font_path and Path(font_path).exists():
        sub_filter = f"subtitles='{ass_path}':fontsdir='{Path(font_path).parent}'"
    else:
        sub_filter = f"subtitles='{ass_path}'"

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

def generate_viral_clip(
    input_clip_path: str,
    segments: List[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    options: ViralOptions,
    output_path: str,
) -> str:
    """
    Transforma um clipe já cortado em versão viral.

    Passos:
      1. Prepara painel superior (face/crop inteligente)
      2. Prepara painel inferior (gameplay ou loop)
      3. Empilha com vstack (9:16 final)
      4. Gera legendas ASS (se habilitado)
      5. Queima legendas no vídeo final

    Retorna o caminho do arquivo viral gerado.
    """
    duration = clip_end - clip_start
    style    = options.caption_style.value if options.caption_style else "tiktok"
    font_p   = options.font_path if hasattr(options, "font_path") else config.FONT_PATH
    bg_path  = options.background_video_path or config.BACKGROUND_VIDEO_PATH or None

    logger.info(f"[viral] Iniciando viral edit: {Path(input_clip_path).name}")
    logger.info(f"[viral] Duração: {duration:.1f}s | Estilo: {style} | BG: {bg_path or 'loop'}")

    with tempfile.TemporaryDirectory(prefix="clipforge_viral_") as tmp_dir:
        # 1 & 2: Painéis
        top_path    = _prepare_top_panel(input_clip_path, tmp_dir, config.FACE_DETECTION)
        bottom_path = _prepare_bottom_panel(input_clip_path, bg_path, duration, tmp_dir)

        # 3: Stack
        stacked_path = str(Path(tmp_dir) / "stacked.mp4")
        _stack_panels(top_path, bottom_path, input_clip_path, duration, stacked_path)

        # 4 & 5: Legendas
        if options.add_captions and segments:
            ass_path = str(Path(tmp_dir) / "captions.ass")
            generate_ass_subtitles(
                segments, clip_start, clip_end, style,
                font_p or "", ass_path,
            )
            _burn_subtitles(stacked_path, ass_path, font_p or "", output_path)
        else:
            import shutil
            shutil.copy2(stacked_path, output_path)

    logger.info(f"[viral] ✅ Viral edit concluído: {output_path}")
    return output_path
