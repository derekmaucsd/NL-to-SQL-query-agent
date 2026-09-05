import unittest

from sql_utils import is_read_only_sql


class IsReadOnlySqlTests(unittest.TestCase):
    def test_accepts_select_followed_by_newline(self):
        self.assertTrue(is_read_only_sql("SELECT\n  value FROM sample"))

    def test_accepts_with_followed_by_newline(self):
        self.assertTrue(
            is_read_only_sql("WITH\n  sample AS (SELECT 1) SELECT * FROM sample")
        )

    def test_accepts_select_followed_by_space(self):
        self.assertTrue(is_read_only_sql("SELECT 1"))

    def test_rejects_non_query_and_multiple_statements(self):
        self.assertFalse(is_read_only_sql("SELECTED value FROM sample"))
        self.assertFalse(is_read_only_sql("DELETE FROM sample"))
        self.assertFalse(is_read_only_sql("SELECT 1; SELECT 2"))


if __name__ == "__main__":
    unittest.main()
