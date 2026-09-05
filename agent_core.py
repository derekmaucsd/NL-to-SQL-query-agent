import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config import DEFAULT_MAX_RETRIES, MAX_SUBQUERIES, SUBQUERY_VALIDATION_ROUNDS
from database import execute_query_attempt
from llm import generate_text
from models import QueryAttempt, ValidatedQueryResult
from prompts import (
    build_evidence_validation_prompt,
    build_final_sql_prompt,
    build_subquery_plan_prompt,
)
from render import format_attempt
from sql_utils import clean_json, clean_sql

if TYPE_CHECKING:
    from tracing import TraceRecorder


def generate_sql(
    client: Any,
    user_question: str,
    schema_summary: str,
    evidence: str = "",
    previous_attempts: str = "",
    trace: "TraceRecorder | None" = None,
) -> str:
    prompt = build_final_sql_prompt(
        user_question=user_question,
        schema_summary=schema_summary,
        evidence=evidence,
        previous_attempts=previous_attempts,
    )
    return clean_sql(
        generate_text(client, prompt, trace=trace, purpose="final_sql_generation")
    )


def generate_subquery_plan(
    client: Any,
    user_question: str,
    schema_summary: str,
    max_subqueries: int = MAX_SUBQUERIES,
    previous_evidence: str = "",
    validation_feedback: str = "",
    trace: "TraceRecorder | None" = None,
) -> list[dict[str, str]]:
    prompt = build_subquery_plan_prompt(
        user_question=user_question,
        schema_summary=schema_summary,
        max_subqueries=max_subqueries,
        previous_evidence=previous_evidence,
        validation_feedback=validation_feedback,
    )
    data = clean_json(
        generate_text(client, prompt, trace=trace, purpose="subquery_planning") or "{}"
    )
    subqueries = data.get("subqueries", [])
    if not isinstance(subqueries, list):
        return []
    return [
        item
        for item in subqueries[:max_subqueries]
        if isinstance(item, dict) and isinstance(item.get("sql"), str)
    ]


def validate_subquery_evidence(
    client: Any,
    user_question: str,
    schema_summary: str,
    evidence: str,
    trace: "TraceRecorder | None" = None,
) -> dict[str, Any]:
    prompt = build_evidence_validation_prompt(
        user_question=user_question,
        schema_summary=schema_summary,
        evidence=evidence,
    )
    data = clean_json(
        generate_text(client, prompt, trace=trace, purpose="evidence_validation")
        or "{}"
    )
    return data if isinstance(data, dict) else {}


def run_subquery_plan(
    db_path: Path,
    subqueries: list[dict[str, str]],
    trace: "TraceRecorder | None" = None,
) -> str:
    evidence_blocks = []
    for idx, subquery in enumerate(subqueries, start=1):
        name = subquery.get("name", f"subquery_{idx}")
        purpose = subquery.get("purpose", "")
        expected_signal = subquery.get("expected_signal", "")
        sql_query = clean_sql(subquery["sql"])
        attempt = execute_query_attempt(
            db_path,
            sql_query,
            trace=trace,
            purpose="validation_subquery",
            trace_metadata={
                "index": idx,
                "name": name,
                "purpose": purpose,
                "expected_signal": expected_signal,
            },
        )

        evidence_blocks.append(
            "\n".join(
                [
                    f"Subquery {idx}: {name}",
                    f"Purpose: {purpose}",
                    f"Expected signal: {expected_signal}",
                    format_attempt(attempt),
                ]
            )
        )
    return "\n\n".join(evidence_blocks)


def collect_validated_evidence(
    client: Any,
    db_path: Path,
    user_question: str,
    schema_summary: str,
    rounds: int = SUBQUERY_VALIDATION_ROUNDS,
    trace: "TraceRecorder | None" = None,
) -> str:
    evidence_blocks = []
    validation_feedback = ""

    for _ in range(max(1, rounds)):
        subqueries = generate_subquery_plan(
            client,
            user_question,
            schema_summary,
            previous_evidence="\n\n".join(evidence_blocks),
            validation_feedback=validation_feedback,
            trace=trace,
        )
        if not subqueries:
            break

        evidence = run_subquery_plan(db_path, subqueries, trace=trace)
        evidence_blocks.append(evidence)
        combined_evidence = "\n\n".join(evidence_blocks)

        validation = validate_subquery_evidence(
            client,
            user_question,
            schema_summary,
            combined_evidence,
            trace=trace,
        )
        validation_feedback = json.dumps(validation, default=str)
        if validation.get("is_sufficient") is True:
            evidence_blocks.append(f"Subquery validation: {validation_feedback}")
            break

    if validation_feedback and not any(
        block.startswith("Subquery validation:") for block in evidence_blocks
    ):
        evidence_blocks.append(f"Subquery validation: {validation_feedback}")

    return "\n\n".join(evidence_blocks)


def generate_validated_sql_result(
    client: Any,
    db_path: Path,
    user_question: str,
    schema_summary: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    trace: "TraceRecorder | None" = None,
) -> ValidatedQueryResult:
    try:
        evidence = collect_validated_evidence(
            client,
            db_path,
            user_question,
            schema_summary,
            trace=trace,
        )
    except Exception as exc:
        evidence = f"Subquery planning failed: {exc}"
    previous_attempts = []
    attempt = QueryAttempt(sql="", columns=[], rows=[], error="No attempts were run.")

    for _ in range(max(1, max_retries)):
        sql_query = generate_sql(
            client,
            user_question,
            schema_summary,
            evidence=evidence,
            previous_attempts="\n\n".join(previous_attempts),
            trace=trace,
        )
        attempt = execute_query_attempt(
            db_path,
            sql_query,
            trace=trace,
            purpose="final_sql_execution",
            trace_metadata={"attempt": len(previous_attempts) + 1},
        )
        if not attempt.error:
            return ValidatedQueryResult(attempt=attempt, evidence=evidence)

        previous_attempts.append(format_attempt(attempt))

    return ValidatedQueryResult(attempt=attempt, evidence=evidence)


def generate_validated_sql(
    client: Any,
    db_path: Path,
    user_question: str,
    schema_summary: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    trace: "TraceRecorder | None" = None,
) -> QueryAttempt:
    result = generate_validated_sql_result(
        client=client,
        db_path=db_path,
        user_question=user_question,
        schema_summary=schema_summary,
        max_retries=max_retries,
        trace=trace,
    )
    return result.attempt
