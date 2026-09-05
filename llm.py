import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from google import genai

from config import ENV_PATH, MODEL_NAME

if TYPE_CHECKING:
    from tracing import TraceRecorder


def load_env_file(env_path: Path = ENV_PATH) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def get_client() -> genai.Client:
    load_env_file()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing Gemini API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) before running."
        )
    return genai.Client(api_key=api_key)


def generate_text(
    client: genai.Client,
    prompt: str,
    trace: "TraceRecorder | None" = None,
    purpose: str = "generate_text",
) -> str:
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    started_timer = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        response_text = response.text or ""
    except Exception as exc:
        if trace:
            trace.record_llm_call(
                name=purpose,
                model=MODEL_NAME,
                prompt=prompt,
                response=None,
                started_at=started_at,
                started_timer=started_timer,
                error=str(exc),
            )
        raise

    if trace:
        trace.record_llm_call(
            name=purpose,
            model=MODEL_NAME,
            prompt=prompt,
            response=response_text,
            started_at=started_at,
            started_timer=started_timer,
        )
    return response_text
