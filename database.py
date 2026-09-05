import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from models import QueryAttempt
from sql_utils import is_read_only_sql

if TYPE_CHECKING:
    from tracing import TraceRecorder


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def build_schema_summary(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        tables = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        lines = []
        for (table_name,) in tables:
            columns = conn.execute(
                f"PRAGMA table_info({quote_ident(table_name)})"
            ).fetchall()
            col_text = ", ".join(f"{col[1]} ({col[2]})" for col in columns)
            row_count = conn.execute(
                f"SELECT COUNT(*) FROM {quote_ident(table_name)}"
            ).fetchone()[0]
            lines.append(f"- {table_name} [{row_count} rows]: {col_text}")
        return "\n".join(lines)
    finally:
        conn.close()


def execute_query(
    db_path: Path,
    sql_query: str,
    trace: "TraceRecorder | None" = None,
    purpose: str = "sql_query",
    trace_metadata: dict[str, Any] | None = None,
):
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    started_timer = time.perf_counter()
    conn = None
    try:
        if not is_read_only_sql(sql_query):
            raise ValueError(
                "Generated SQL must be a single read-only SELECT/WITH statement."
            )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql_query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description] if cursor.description else []
        if trace:
            trace.record_database_call(
                name=purpose,
                sql=sql_query,
                columns=columns,
                rows=rows,
                started_at=started_at,
                started_timer=started_timer,
                metadata=trace_metadata,
            )
        return columns, rows
    except Exception as exc:
        if trace:
            trace.record_database_call(
                name=purpose,
                sql=sql_query,
                columns=None,
                rows=None,
                started_at=started_at,
                started_timer=started_timer,
                metadata=trace_metadata,
                error=str(exc),
            )
        raise
    finally:
        if conn is not None:
            conn.close()


def execute_query_attempt(
    db_path: Path,
    sql_query: str,
    trace: "TraceRecorder | None" = None,
    purpose: str = "sql_query",
    trace_metadata: dict[str, Any] | None = None,
) -> QueryAttempt:
    try:
        columns, rows = execute_query(
            db_path,
            sql_query,
            trace=trace,
            purpose=purpose,
            trace_metadata=trace_metadata,
        )
        return QueryAttempt(sql=sql_query, columns=columns, rows=rows)
    except Exception as exc:
        return QueryAttempt(sql=sql_query, columns=[], rows=[], error=str(exc))
