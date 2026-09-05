import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import execute_query
from llm import generate_text
from tracing import TraceRecorder


class _FakeResponse:
    text = "SELECT value FROM sample"


class _FakeModels:
    def generate_content(self, *, model, contents):
        return _FakeResponse()


class _FakeClient:
    models = _FakeModels()


class TraceRecorderTests(unittest.TestCase):
    def test_records_user_llm_database_and_final_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "test.sqlite"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE sample (value INTEGER)")
                conn.execute("INSERT INTO sample VALUES (42)")
                conn.commit()
            finally:
                conn.close()

            trace = TraceRecorder("What is the value?", trace_dir=temp_path / "traces")
            sql = generate_text(
                _FakeClient(),
                "Return SQL",
                trace=trace,
                purpose="final_sql_generation",
            )
            columns, rows = execute_query(
                db_path,
                sql,
                trace=trace,
                purpose="final_sql_execution",
            )
            trace.finish(
                "succeeded",
                final_output={"sql": sql, "rows": [dict(row) for row in rows]},
            )

            payload = json.loads(trace.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "succeeded")
            self.assertEqual(
                [turn["type"] for turn in payload["turns"]],
                ["user", "llm", "database"],
            )
            self.assertEqual(payload["turns"][1]["inputs"]["prompt"], "Return SQL")
            self.assertEqual(payload["turns"][1]["outputs"]["text"], sql)
            self.assertEqual(payload["turns"][2]["outputs"]["row_count"], 1)
            self.assertEqual(payload["turns"][2]["outputs"]["rows"], [{"value": 42}])
            self.assertEqual(payload["final_output"]["rows"], [{"value": 42}])


if __name__ == "__main__":
    unittest.main()
