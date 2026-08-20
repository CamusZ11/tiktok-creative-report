import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from token_store import load_access_token, load_app_id, load_app_secret, save_access_token


class TokenStoreTests(unittest.TestCase):
    def test_load_access_token_returns_keychain_value_without_printing_it(self):
        completed = subprocess.CompletedProcess(["security"], 0, stdout="TEST_ACCESS_VALUE\n", stderr="")
        with patch("token_store.subprocess.run", return_value=completed) as runner:
            self.assertEqual(load_access_token(), "TEST_ACCESS_VALUE")

        command = runner.call_args.args[0]
        self.assertIn("find-generic-password", command)
        self.assertIn("com.codex.tiktok-workflow.access-token", command)

    def test_load_access_token_returns_none_when_keychain_item_is_missing(self):
        completed = subprocess.CompletedProcess(["security"], 44, stdout="", stderr="not found")
        with patch("token_store.subprocess.run", return_value=completed):
            self.assertIsNone(load_access_token())

    def test_load_app_credentials_from_separate_keychain_items(self):
        def fake_run(command, **kwargs):
            service = command[command.index("-s") + 1]
            value = {
                "com.codex.tiktok-workflow.app-id": "TEST_APP",
                "com.codex.tiktok-workflow.app-secret": "TEST_SECRET",
            }[service]
            return subprocess.CompletedProcess(command, 0, stdout=f"{value}\n", stderr="")

        with patch("token_store.subprocess.run", side_effect=fake_run):
            self.assertEqual(load_app_id(), "TEST_APP")
            self.assertEqual(load_app_secret(), "TEST_SECRET")

    def test_save_access_token_updates_keychain_item(self):
        completed = subprocess.CompletedProcess(["security"], 0, stdout="", stderr="")
        with patch("token_store.subprocess.run", return_value=completed) as runner:
            save_access_token("TEST_ACCESS_VALUE")

        command = runner.call_args.args[0]
        self.assertIn("add-generic-password", command)
        self.assertIn("com.codex.tiktok-workflow.access-token", command)
        self.assertNotIn("TEST_ACCESS_VALUE", command)
        self.assertEqual(command[-1], "-w")
        self.assertEqual(runner.call_args.kwargs["input"], "TEST_ACCESS_VALUE\n")

    def test_credential_setup_script_does_not_put_secret_in_security_argv(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "save_tiktok_credentials_to_keychain.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn('-w "$app_secret"', script)
        self.assertIn('<<< "$app_secret"', script)


if __name__ == "__main__":
    unittest.main()
