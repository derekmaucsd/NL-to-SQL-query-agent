import argparse
from pathlib import Path

from agent_core import generate_sql, generate_validated_sql_result
from config import DB_PATH, DEFAULT_MAX_RETRIES
from database import build_schema_summary, execute_query
from llm import get_client
from render import print_table
from tracing import TraceRecorder


def main():
    parser = argparse.ArgumentParser(description="Run Gemini-to-SQL against nba.sqlite.")
    parser.add_argument(
        "--question",
        default="How many games were there total in the NBA?",
        help="Natural language question to send to Gemini.",
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help="Path to the local SQLite database.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum final-query generation attempts after subquery validation.",
    )
    parser.add_argument(
        "--one-shot",
        action="store_true",
        help="Skip subquery planning and retry validation; use the original one-shot flow.",
    )
    args = parser.parse_args()

    trace = TraceRecorder(args.question)
    trace.record_turn(
        turn_type="agent",
        name="run_configuration",
        inputs={
            "database": args.db,
            "one_shot": args.one_shot,
            "max_retries": args.max_retries,
        },
        outputs=None,
    )

    try:
        db_path = Path(args.db)
        if not db_path.exists():
            raise SystemExit(f"Database not found: {db_path}")

        client = get_client()
        schema_summary = build_schema_summary(db_path)
        trace.record_turn(
            turn_type="agent",
            name="schema_inspection",
            inputs={"database": str(db_path)},
            outputs={"schema_summary": schema_summary},
        )

        print(f"User question: {args.question}")
        if args.one_shot:
            print("\nGenerating SQL...")
            sql_query = generate_sql(
                client,
                args.question,
                schema_summary,
                trace=trace,
            )
            print(sql_query)

            print("\nExecuting query...")
            try:
                columns, rows = execute_query(
                    db_path,
                    sql_query,
                    trace=trace,
                    purpose="final_sql_execution",
                    trace_metadata={"attempt": 1, "one_shot": True},
                )
            except Exception as exc:
                print(f"Database error: {exc}")
                raise SystemExit(1)
        else:
            print("\nPlanning and validating subqueries...")
            result = generate_validated_sql_result(
                client,
                db_path,
                args.question,
                schema_summary,
                max_retries=args.max_retries,
                trace=trace,
            )
            if result.evidence:
                print("\nValidation subqueries:")
                print(result.evidence)

            attempt = result.attempt
            sql_query = attempt.sql
            print("\nFinal SQL:")
            print(attempt.sql)
            if attempt.error:
                print(f"\nDatabase error after retries: {attempt.error}")
                raise SystemExit(1)
            columns = attempt.columns
            rows = attempt.rows

        print("\nQuery result:")
        print_table(columns, rows)
        trace.finish(
            "succeeded",
            final_output={
                "sql": sql_query,
                "columns": columns,
                "row_count": len(rows),
                "rows": [dict(row) for row in rows],
            },
        )
    except BaseException as exc:
        trace.finish("failed", error=str(exc))
        raise
    finally:
        print(f"\nTrace: {trace.path}")


if __name__ == "__main__":
    main()
