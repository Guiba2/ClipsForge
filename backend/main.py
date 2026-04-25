"""
ClipForge API - Backend principal
FastAPI + Background Tasks + In-memory job store
"""
import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import AnalyzeRequest, UrlRequest
from video_processor import (
    download_video, save_upload, extract_audio,
    process_clips, OUTPUT_DIR, UPLOAD_DIR,
)
import config

# ─── Setup ─────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("clipforge")

app = FastAPI(title="ClipForge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store (sem banco de dados)
_jobs: dict[str, dict] = {}

# Thread pool para operações CPU-bound (Whisper, FFmpeg)
_executor = ThreadPoolExecutor(max_workers=2)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _get_job(job_id: str) -> dict:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' não encontrado.")
    return _jobs[job_id]


def _update_job(job_id: str, status: str, progress: int, message: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(status=status, progress=progress, message=message, **kwargs)
        logger.info(f"[Job {job_id[:8]}] [{status.upper()}] {progress}% – {message}")


def _new_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "idle",
        "progress": 0,
        "message": "Job criado.",
        "video_path": None,
        "clips": None,
        "error": None,
    }
    return job_id


# ─── Pipeline de Processamento ─────────────────────────────────────────────────

async def _run_pipeline(
    job_id: str,
    transcription_provider: Optional[str],
    llm_provider: Optional[str],
):
    """Pipeline completo: transcrição → análise → geração de clipes."""
    from transcription import transcribe
    from analysis import analyze

    loop = asyncio.get_running_loop()

    try:
        video_path = _jobs[job_id]["video_path"]
        if not video_path or not Path(video_path).exists():
            raise FileNotFoundError("Arquivo de vídeo não encontrado.")

        # 1. Extrai áudio
        _update_job(job_id, "transcribing", 10, "Extraindo áudio do vídeo...")
        audio_path = await loop.run_in_executor(_executor, extract_audio, video_path)

        # 2. Transcreve (CPU-bound → executor)
        _update_job(job_id, "transcribing", 20, "Transcrevendo áudio...")
        segments = await loop.run_in_executor(
            _executor, transcribe, audio_path, transcription_provider,
        )

        if not segments:
            raise ValueError("Transcrição vazia. Verifique se o vídeo possui áudio.")

        logger.info(f"[Pipeline] {len(segments)} segmentos transcritos.")

        # 3. Analisa com IA
        _update_job(job_id, "analyzing", 55, "Analisando conteúdo com IA...")
        suggestions = await analyze(segments, llm_provider)

        if not suggestions:
            raise ValueError("A IA não retornou sugestões. Tente outro provedor ou modelo.")

        logger.info(f"[Pipeline] {len(suggestions)} sugestões de clipes.")

        # 4. Gera clipes com FFmpeg (CPU-bound → executor)
        _update_job(job_id, "processing", 70, f"Gerando {len(suggestions)} clipes verticais...")
        clips = await loop.run_in_executor(
            _executor, process_clips, video_path, suggestions, job_id,
        )

        if not clips:
            raise ValueError("Nenhum clipe foi gerado pelo FFmpeg. Verifique os logs.")

        # 5. Concluído
        _update_job(
            job_id, "done", 100,
            f"{len(clips)} clipe(s) gerado(s) com sucesso!",
            clips=[c.model_dump() for c in clips],
        )

    except Exception as exc:
        logger.exception(f"[Pipeline] Erro no job {job_id[:8]}: {exc}")
        _update_job(job_id, "error", 0, f"Erro: {str(exc)[:200]}", error=str(exc))


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/upload", summary="Upload de arquivo de vídeo local")
async def upload_video(file: UploadFile = File(...)):
    """
    Recebe um arquivo de vídeo, salva e retorna job_id.
    Após isso, chame POST /api/analyze/{job_id} para iniciar a análise.
    """
    allowed = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Formato não suportado: '{ext}'. Use: {', '.join(sorted(allowed))}")

    content = await file.read()
    if len(content) > 2 * 1024 ** 3:
        raise HTTPException(413, "Arquivo muito grande (máx. 2 GB).")
    if len(content) == 0:
        raise HTTPException(400, "Arquivo vazio.")

    job_id = _new_job()
    loop = asyncio.get_running_loop()
    video_path = await loop.run_in_executor(
        _executor, save_upload, content, file.filename, job_id
    )
    _jobs[job_id]["video_path"] = video_path
    _update_job(job_id, "idle", 5, "Vídeo recebido. Pronto para análise.")

    logger.info(f"[Upload] Job {job_id[:8]} — '{file.filename}' ({len(content)/1_048_576:.1f} MB)")
    return {
        "job_id": job_id,
        "filename": file.filename,
        "size_mb": round(len(content) / 1_048_576, 1),
    }


@app.post("/api/upload-url", summary="Baixar vídeo de URL e iniciar análise automaticamente")
async def upload_url(data: UrlRequest, background_tasks: BackgroundTasks):
    """
    Baixa vídeo de URL (YouTube, Vimeo, etc.) e encadeia o pipeline
    automaticamente. Não é necessário chamar /analyze separado.
    """
    url = data.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL inválida. Deve começar com http:// ou https://")

    job_id = _new_job()
    _update_job(job_id, "downloading", 2, "Baixando vídeo...")

    # Captura provedores para encadear o pipeline após o download
    t_provider = data.transcription_provider
    l_provider = data.llm_provider

    async def _download_then_analyze():
        """Baixa e encadeia pipeline — elimina race condition do frontend."""
        loop = asyncio.get_running_loop()
        try:
            video_path = await loop.run_in_executor(
                _executor, download_video, url, job_id
            )
            _jobs[job_id]["video_path"] = video_path
            _update_job(job_id, "transcribing", 8, "Download concluído. Iniciando transcrição...")
            await _run_pipeline(job_id, t_provider, l_provider)
        except Exception as e:
            _update_job(job_id, "error", 0, f"Erro: {str(e)[:200]}", error=str(e))

    background_tasks.add_task(_download_then_analyze)

    return {
        "job_id": job_id,
        "url": url,
        "message": "Download e análise iniciados.",
    }


@app.post("/api/analyze/{job_id}", summary="Iniciar análise (após upload de arquivo)")
async def analyze_video(
    job_id: str,
    options: AnalyzeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Inicia pipeline para jobs criados via /upload (arquivo local).
    Jobs criados via /upload-url já iniciam automaticamente.
    """
    job = _get_job(job_id)
    active = ("transcribing", "analyzing", "processing", "downloading")

    if job["status"] in active:
        raise HTTPException(409, f"Operação em andamento: '{job['status']}'. Aguarde.")

    if not job.get("video_path") or not Path(job["video_path"]).exists():
        raise HTTPException(400, "Vídeo não encontrado. Faça upload primeiro.")

    _update_job(job_id, "transcribing", 5, "Pipeline iniciado...")
    background_tasks.add_task(
        _run_pipeline, job_id,
        options.transcription_provider,
        options.llm_provider,
    )

    return {"job_id": job_id, "message": "Análise iniciada."}


@app.get("/api/status/{job_id}", summary="Status e progresso do job")
async def get_status(job_id: str):
    return _get_job(job_id)


@app.get("/api/clips/{job_id}", summary="Lista de clipes gerados")
async def get_clips(job_id: str):
    job = _get_job(job_id)
    if job["status"] != "done":
        raise HTTPException(400, f"Clipes não disponíveis. Status atual: '{job['status']}'")
    return {"job_id": job_id, "clips": job.get("clips", [])}


@app.get("/api/download/{job_id}/{filename}", summary="Download de clipe")
async def download_clip(job_id: str, filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Nome de arquivo inválido.")

    file_path = OUTPUT_DIR / job_id / filename
    if not file_path.exists():
        raise HTTPException(404, "Arquivo não encontrado.")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/jobs/{job_id}", summary="Remove job e arquivos")
async def delete_job(job_id: str):
    _get_job(job_id)
    for d in [UPLOAD_DIR / job_id, OUTPUT_DIR / job_id]:
        if d.exists():
            shutil.rmtree(d)
    del _jobs[job_id]
    return {"message": f"Job {job_id} removido."}


@app.get("/api/jobs", summary="Lista jobs em memória (debug)")
async def list_jobs():
    return [
        {"job_id": j["job_id"], "status": j["status"], "progress": j["progress"]}
        for j in _jobs.values()
    ]


@app.get("/api/config", summary="Configuração ativa")
async def get_config():
    return {
        "transcription_provider": config.TRANSCRIPTION_PROVIDER,
        "llm_provider": config.LLM_PROVIDER,
        "whisper_model": config.WHISPER_MODEL,
        "max_clips": config.MAX_CLIPS,
        "min_clip_seconds": config.MIN_CLIP_SECONDS,
        "max_clip_seconds": config.MAX_CLIP_SECONDS,
        "output_format": config.OUTPUT_FORMAT,
        "output_aspect_ratio": config.OUTPUT_ASPECT_RATIO,
    }
