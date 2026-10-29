import unittest
from datetime import date

try:
    from employment_agent.validation import normalize_query
except ImportError:
    normalize_query = None


class QueryValidationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(normalize_query, "Query validation is not implemented")

    def test_defaults_and_setting_separation(self):
        query = normalize_query({"country": " 日本 ", "nationality": " 中国 ", "api_key": "private", "model": "m"})
        self.assertEqual(query, {"country": "日本", "nationality": "中国", "subdivision": "", "employment_model": "unspecified", "query_mode": "rules", "as_of_date": date.today().isoformat(), "details": ""})

    def test_explicit_fields_trimmed(self):
        query = normalize_query({"country": "A", "nationality": "B", "subdivision": " C ", "details": " facts ", "employment_model": "eor", "query_mode": "case", "as_of_date": "2024-02-29"})
        self.assertEqual(query["details"], "facts")
        self.assertEqual(query["subdivision"], "C")
        self.assertEqual(query["as_of_date"], "2024-02-29")

    def test_invalid_inputs_fail_closed(self):
        cases = [None, [], {}, {"country": " ", "nationality": "B"}]
        for field, value in [("country", 1), ("nationality", None), ("details", []), ("query_mode", "arbitrary"), ("employment_model", "contractor"), ("as_of_date", "2025-02-29"), ("as_of_date", "20260101"), ("country", "a" * 121), ("details", "a" * 12001)]:
            cases.append({"country": "A", "nationality": "B", field: value})
        for data in cases:
            with self.subTest(data=str(data)[:100]):
                with self.assertRaises(ValueError):
                    normalize_query(data)


if __name__ == "__main__":
    unittest.main()
