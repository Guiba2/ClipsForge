"""
Camada unificada de análise com IA.
Suporta: Gemini, Ollama (local), OpenRouter.
Recebe segmentos da transcrição e retorna sugestões de clipes.
"""
import json
import re
import logging
from typing import List
from models import TranscriptSegment, ClipSuggestion
import config

logger = logging.getLogger(__name__)


def _build_prompt(segments: List[TranscriptSegment]) -> str:
    """Monta o prompt para o LLM com a transcrição formatada."""
    transcript_text = "\n".join(
        f"[{_fmt_time(s.start)} - {_fmt_time(s.end)}] {s.text}"
        for s in segments
    )

    total_duration = segments[-1].end if segments else 0

    return f"""You are a viral content strategist specialized in short-form video (YouTube Shorts, Instagram Reels, TikTok). Your job is to identify the moments that make viewers stop scrolling, watch until the end, and share.

## TASK
Analyze the transcript below and extract the {config.MAX_CLIPS} highest-potential clips for short-form content.

## WHAT MAKES A CLIP GO VIRAL
Prioritize segments that contain ONE OR MORE of these triggers:
- **Pattern interrupt**: Something unexpected, counterintuitive, or shocking
- **Emotional peak**: Laughter, awe, anger, inspiration, relatability
- **Information gap**: A question is raised that demands an answer ("The reason most people fail at X is...")
- **Proof moment**: A concrete result, transformation, or demonstration
- **Strong opinion**: A bold or polarizing take that sparks reaction
- **Narrative payoff**: A setup that delivers a satisfying or surprising conclusion
- **Quotable line**: A sentence so good people screenshot it

## CLIP STRUCTURE (ideal)
Every clip should follow: **Hook (0-3s) → Build (middle) → Payoff (final 3s)**
- The first 3 seconds MUST be able to stand alone as a hook — if someone sees only that, they should feel compelled to keep watching
- The last 3 seconds should leave the viewer satisfied OR wanting more

## TECHNICAL REQUIREMENTS
- Duration: {config.MIN_CLIP_SECONDS}s – {config.MAX_CLIP_SECONDS}s per clip
- Non-overlapping segments
- Clips must be self-contained (no "as I mentioned before", no incomplete thoughts)
- Total video duration: {_fmt_time(total_duration)}

## SCORING GUIDE (confidence)
- 0.90–1.0 → Extremely strong hook + clear payoff + high shareability
- 0.75–0.89 → Good hook, solid content, minor weaknesses
- 0.60–0.74 → Decent moment but missing one key viral element
- Below 0.60 → Do not include

## TRANSCRIPT
{transcript_text}

## OUTPUT
Return ONLY a valid JSON array. No markdown, no explanation, no code fences — just the raw array.
Order by confidence descending. Return exactly {config.MAX_CLIPS} clips.

[
  {{
    "start_time": 12.5,
    "end_time": 45.0,
    "title": "Punchy, curiosity-driven title (max 8 words)",
    "hook": "The exact first sentence of this clip",
    "reason": "Specific reason this works: which viral trigger it hits and why the hook lands",
    "confidence": 0.92
  }}
]

Constraints:
- start_time and end_time are floats (seconds)
- end_time - start_time must be between {config.MIN_CLIP_SECONDS} and {config.MAX_CLIP_SECONDS}
- Clips must not overlap
- No clip should start within 5 seconds of another clip's end, unless the transcript has fewer strong moments than {config.MAX_CLIPS}"""


def _fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"


def _parse_llm_response(text: str) -> List[ClipSuggestion]:
    """Extrai e valida JSON da resposta do LLM."""
    # Remove blocos de código markdown se presentes
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Tenta encontrar array JSON no texto
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"Nenhum array JSON encontrado na resposta do LLM:\n{text[:500]}")

    raw = json.loads(match.group())
    clips = []

    for item in raw:
        try:
            start = float(item["start_time"])
            end = float(item["end_time"])
            duration = end - start

            # Valida e corrige duração
            if duration < config.MIN_CLIP_SECONDS:
                end = start + config.MIN_CLIP_SECONDS
            elif duration > config.MAX_CLIP_SECONDS:
                end = start + config.MAX_CLIP_SECONDS

            clips.append(ClipSuggestion(
                start_time=round(start, 2),
                end_time=round(end, 2),
                title=str(item.get("title", "Clipe sem título"))[:80],
                reason=str(item.get("reason", ""))[:300],
                confidence=min(1.0, max(0.0, float(item.get("confidence", 0.5)))),
            ))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Ignorando item inválido do LLM: {item} | Erro: {e}")

    return clips[:config.MAX_CLIPS]


# ─── Provedores ────────────────────────────────────────────────────────────────

async def _analyze_gemini(prompt: str) -> str:
    import google.generativeai as genai

    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY não configurada no .env")

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    logger.info("[Gemini] Enviando prompt...")
    response = model.generate_content(prompt)
    return response.text


async def _analyze_ollama(prompt: str) -> str:
    import httpx

    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    logger.info(f"[Ollama] Enviando para {url} com modelo '{config.OLLAMA_MODEL}'...")

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["response"]


async def _analyze_openrouter(prompt: str) -> str:
    import httpx

    if not config.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY não configurada no .env")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "ClipForge",
    }
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    logger.info(f"[OpenRouter] Usando modelo '{config.OPENROUTER_MODEL}'...")

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ─── Interface pública ─────────────────────────────────────────────────────────

async def analyze(
    segments: List[TranscriptSegment],
    provider: str | None = None,
) -> List[ClipSuggestion]:
    """
    Analisa os segmentos da transcrição e retorna sugestões de clipes.
    Provider pode ser sobrescrito; caso contrário usa o valor do .env.
    """
    if not segments:
        raise ValueError("Nenhum segmento de transcrição para analisar.")

    p = (provider or config.LLM_PROVIDER).lower()
    prompt = _build_prompt(segments)

    if p == "gemini":
        raw = await _analyze_gemini(prompt)
    elif p == "ollama":
        raw = await _analyze_ollama(prompt)
    elif p == "openrouter":
        raw = await _analyze_openrouter(prompt)
    else:
        raise ValueError(f"LLM_PROVIDER inválido: '{p}'. Use 'gemini', 'ollama' ou 'openrouter'.")

    logger.info(f"[{p.upper()}] Resposta recebida. Parseando JSON...")
    return _parse_llm_response(raw)
