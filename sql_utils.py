import json
import re
from typing import Any


def clean_sql(text: str) -> str:
    sql = text.strip()
    if sql.startswith("```"):
        sql = sql.split("\n", 1)[1] if "\n" in sql else ""
        sql = sql.replace("```", "").strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


def clean_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def is_read_only_sql(sql_query: str) -> bool:
    normalized = sql_query.strip().rstrip(";").strip()
    if not normalized:
        return False
    if ";" in normalized:
        return False
    return re.match(r"^(select|with)\b", normalized, flags=re.IGNORECASE) is not None
