import unittest
from urllib.parse import parse_qs, urlparse

from tiktok_oauth import OAuthStateStore, build_authorization_url, extract_access_token


class TikTokOAuthTests(unittest.TestCase):
    def test_authorization_url_uses_single_use_state(self):
        states = OAuthStateStore()
        state = states.put("state-for-test")
        url = build_authorization_url("app-for-test", state=state)
        query = parse_qs(urlparse(url).query)

        self.assertEqual(query["app_id"], ["app-for-test"])
        self.assertEqual(query["state"], ["state-for-test"])
        self.assertTrue(states.consume("state-for-test"))
        self.assertFalse(states.consume("state-for-test"))

    def test_extract_access_token_reads_only_expected_response_shape(self):
        self.assertEqual(extract_access_token({"data": {"access_token": "token-for-test"}}), "token-for-test")
        self.assertIsNone(extract_access_token({"data": {}}))


if __name__ == "__main__":
    unittest.main()
