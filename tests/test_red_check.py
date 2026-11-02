
import unittest


class RedCheck(unittest.TestCase):
    def test_fails_on_purpose(self):
        self.fail("015: a red check must block the merge")
