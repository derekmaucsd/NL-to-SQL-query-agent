import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRACE_DIR = Path("traces")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return str(value)


def _question_slug(question: str, limit: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")
    return (slug[:limit].rstrip("-") or "question")


class TraceRecorder:
    """Incrementally records one agent run as a JSON trace."""

    def __init__(
        self,
        question: str,
        trace_dir: Path = TRACE_DIR,
    ) -> None:
        self.trace_id = uuid.uuid4().hex
        self.started_at = _utc_now()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        filename = f"{timestamp}_{_question_slug(question)}_{self.trace_id[:8]}.json"

        trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = trace_dir / filename
        self.data: dict[str, Any] = {
            "trace_id": self.trace_id,
            "question": question,
            "started_at": self.started_at,
            "completed_at": None,
            "status": "running",
            "turns": [],
            "final_output": None,
            "error": None,
        }
        self.record_turn(
            turn_type="user",
            name="question",
            inputs={"text": question},
            outputs=None,
        )

    def _write(self) -> None:
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    def record_turn(
        self,
        turn_type: str,
        name: str,
        inputs: Any = None,
        outputs: Any = None,
        *,
        status: str = "succeeded",
        started_at: str | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        turn = {
            "turn": len(self.data["turns"]) + 1,
            "type": turn_type,
            "name": name,
            "started_at": started_at or _utc_now(),
            "completed_at": _utc_now(),
            "duration_ms": round(duration_ms, 3) if duration_ms is not None else None,
            "status": status,
            "inputs": _json_value(inputs),
            "outputs": _json_value(outputs),
            "error": error,
        }
        self.data["turns"].append(turn)
        self._write()

    def record_llm_call(
        self,
        *,
        name: str,
        model: str,
        prompt: str,
        response: str | None,
        started_at: str,
        started_timer: float,
        error: str | None = None,
    ) -> None:
        self.record_turn(
            turn_type="llm",
            name=name,
            inputs={"model": model, "prompt": prompt},
            outputs={"text": response} if response is not None else None,
            status="failed" if error else "succeeded",
            started_at=started_at,
            duration_ms=(time.perf_counter() - started_timer) * 1000,
            error=error,
        )

    def record_database_call(
        self,
        *,
        name: str,
        sql: str,
        columns: list[str] | None,
        rows: list[Any] | None,
        started_at: str,
        started_timer: float,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        outputs = None
        if rows is not None:
            outputs = {
                "columns": columns or [],
                "row_count": len(rows),
                "rows": [_json_value(row) for row in rows],
            }
        self.record_turn(
            turn_type="database",
            name=name,
            inputs={"sql": sql, "metadata": metadata or {}},
            outputs=outputs,
            status="failed" if error else "succeeded",
            started_at=started_at,
            duration_ms=(time.perf_counter() - started_timer) * 1000,
            error=error,
        )

    def finish(
        self,
        status: str,
        *,
        final_output: Any = None,
        error: str | None = None,
    ) -> None:
        self.data["status"] = status
        self.data["completed_at"] = _utc_now()
        self.data["final_output"] = _json_value(final_output)
        self.data["error"] = error
        self._write()
