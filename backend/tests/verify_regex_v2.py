import re
import unittest


class TestPlaybookRegexV2(unittest.TestCase):
    def setUp(self):
        # The updated regex from executor.py
        self.regex_pattern = (
            r"(?:using|playbook:|playbook)\s+[`'\"]?([a-z0-9_]+)[`'\"]?(?:\s+playbook)?"
        )

    def extract_playbook(self, text):
        match = re.search(self.regex_pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def test_backticks_case(self):
        # This is the user's specific failure case
        text = "1. 分析您追蹤的 Instagram 帳號列表並進行分類 (using `ig_analyze_following` playbook)"
        self.assertEqual(self.extract_playbook(text), "ig_analyze_following")

    def test_single_quotes_case(self):
        text = "Try using 'ig_analyze_following' playbook"
        self.assertEqual(self.extract_playbook(text), "ig_analyze_following")

    def test_original_plain_case(self):
        text = "(using ig_analyze_following)"
        self.assertEqual(self.extract_playbook(text), "ig_analyze_following")


if __name__ == "__main__":
    unittest.main()
