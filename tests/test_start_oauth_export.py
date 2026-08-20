import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from start_oauth_export import build_workbook_atomically, resolve_date_range, safe_failure_detail


class StartOAuthExportTests(unittest.TestCase):
    def test_safe_failure_detail_only_keeps_known_safe_tiktok_api_messages(self):
        self.assertEqual(
            safe_failure_detail(RuntimeError("TikTok API request failed for /open_api/v1.3/gmv_max/report/get/")),
            "TikTok API request failed for /open_api/v1.3/gmv_max/report/get/",
        )
        self.assertEqual(
            safe_failure_detail(RuntimeError("TikTok API network failure for /open_api/v1.3/gmv_max/store/list/")),
            "TikTok API network failure for /open_api/v1.3/gmv_max/store/list/",
        )
        self.assertEqual(safe_failure_detail(ValueError("secret-like detail")), "ValueError")

    def test_resolve_date_range_defaults_to_last_seven_complete_days(self):
        self.assertEqual(
            resolve_date_range({}, reference_date="2026-08-20"),
            ("2026-08-13", "2026-08-19"),
        )
        self.assertEqual(
            resolve_date_range({"TIKTOK_START_DATE": "2026-08-01", "TIKTOK_END_DATE": "2026-08-02"}),
            ("2026-08-01", "2026-08-02"),
        )
        with self.assertRaises(RuntimeError):
            resolve_date_range({"TIKTOK_START_DATE": "2026-08-01"})

    def test_build_workbook_atomically_replaces_target_only_after_builder_succeeds(self):
        directory = Path(tempfile.mkdtemp())
        payload = directory / "payload.json"
        payload.write_text("{}", encoding="utf-8")
        target = directory / "output" / "TikTok_创意明细.xlsx"
        target.parent.mkdir()
        target.write_bytes(b"previous-workbook")

        def successful_builder(command, check, env):
            self.assertNotIn("TIKTOK_APP_SECRET", env)
            self.assertNotIn("TIKTOK_ACCESS_TOKEN", env)
            Path(command[-1]).write_bytes(b"new-workbook")

        with (
            patch.dict(
                "start_oauth_export.os.environ",
                {"TIKTOK_APP_SECRET": "TEST_SECRET", "TIKTOK_ACCESS_TOKEN": "TEST_ACCESS_VALUE"},
                clear=True,
            ),
            patch("start_oauth_export.subprocess.run", side_effect=successful_builder),
        ):
            build_workbook_atomically(
                node_command="node",
                builder_path=Path("builder.mjs"),
                payload_path=payload,
                output_path=target,
            )

        self.assertEqual(target.read_bytes(), b"new-workbook")
        self.assertFalse(list(target.parent.glob(".*.tmp.xlsx")))

    def test_build_workbook_atomically_preserves_previous_target_on_builder_failure(self):
        directory = Path(tempfile.mkdtemp())
        payload = directory / "payload.json"
        payload.write_text("{}", encoding="utf-8")
        target = directory / "TikTok_创意明细.xlsx"
        target.write_bytes(b"previous-workbook")

        with patch("start_oauth_export.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["node"])):
            with self.assertRaises(subprocess.CalledProcessError):
                build_workbook_atomically(
                    node_command="node",
                    builder_path=Path("builder.mjs"),
                    payload_path=payload,
                    output_path=target,
                )

        self.assertEqual(target.read_bytes(), b"previous-workbook")

    def test_build_workbook_atomically_refuses_excel_locked_target(self):
        directory = Path(tempfile.mkdtemp())
        payload = directory / "payload.json"
        payload.write_text("{}", encoding="utf-8")
        target = directory / "TikTok_创意明细.xlsx"
        target.write_bytes(b"previous-workbook")
        target.with_name(f"~${target.name}").write_bytes(b"excel-lock")

        with patch("start_oauth_export.subprocess.run") as builder:
            with self.assertRaisesRegex(RuntimeError, "Excel"):
                build_workbook_atomically(
                    node_command="node",
                    builder_path=Path("builder.mjs"),
                    payload_path=payload,
                    output_path=target,
                )

        builder.assert_not_called()
        self.assertEqual(target.read_bytes(), b"previous-workbook")

    def test_main_uses_persisted_token_without_starting_oauth_server(self):
        environment = {
            "TIKTOK_ADVERTISER_ID": "TEST_ADVERTISER",
            "TIKTOK_ARTIFACT_NODE": "/tmp/node",
            "TIKTOK_OUTPUT_FILE": "/tmp/report.xlsx",
        }
        with (
            patch.dict("start_oauth_export.os.environ", environment, clear=True),
            patch("start_oauth_export.load_access_token", return_value="TEST_ACCESS_VALUE"),
            patch("start_oauth_export.export_report") as export_report,
            patch("start_oauth_export.create_local_server") as create_server,
        ):
            from start_oauth_export import main

            main()

        export_report.assert_called_once()
        self.assertEqual(export_report.call_args.kwargs["access_token"], "TEST_ACCESS_VALUE")
        create_server.assert_not_called()

    def test_force_oauth_ignores_saved_token_and_replaces_it(self):
        environment = {
            "TIKTOK_APP_ID": "TEST_APP",
            "TIKTOK_APP_SECRET": "TEST_SECRET",
            "TIKTOK_ADVERTISER_ID": "TEST_ADVERTISER",
            "TIKTOK_ARTIFACT_NODE": "/tmp/node",
            "TIKTOK_OUTPUT_FILE": "/tmp/report.xlsx",
            "TIKTOK_FORCE_OAUTH": "1",
        }

        class FakeServer:
            def __init__(self, callback):
                self.callback = callback

            def serve_forever(self):
                self.callback("NEW_ACCESS_VALUE")

            def server_close(self):
                return None

        with (
            patch.dict("start_oauth_export.os.environ", environment, clear=True),
            patch("start_oauth_export.load_access_token", return_value="OLD_ACCESS_VALUE"),
            patch("start_oauth_export.save_access_token") as save_access_token,
            patch("start_oauth_export.export_report") as export_report,
            patch(
                "start_oauth_export.create_local_server",
                side_effect=lambda **kwargs: FakeServer(kwargs["on_access_token"]),
            ) as create_server,
        ):
            from start_oauth_export import main

            main()

        create_server.assert_called_once()
        save_access_token.assert_called_once_with("NEW_ACCESS_VALUE")
        self.assertEqual(export_report.call_args.kwargs["access_token"], "NEW_ACCESS_VALUE")

    def test_oauth_callback_saves_long_term_token_before_export(self):
        environment = {
            "TIKTOK_APP_ID": "TEST_APP",
            "TIKTOK_APP_SECRET": "TEST_SECRET",
            "TIKTOK_ADVERTISER_ID": "TEST_ADVERTISER",
            "TIKTOK_ARTIFACT_NODE": "/tmp/node",
            "TIKTOK_OUTPUT_FILE": "/tmp/report.xlsx",
        }

        class FakeServer:
            def __init__(self, callback):
                self.callback = callback

            def serve_forever(self):
                self.callback("TEST_ACCESS_VALUE")

            def server_close(self):
                return None

        def fake_create_server(**kwargs):
            return FakeServer(kwargs["on_access_token"])

        with (
            patch.dict("start_oauth_export.os.environ", environment, clear=True),
            patch("start_oauth_export.load_access_token", return_value=None),
            patch("start_oauth_export.save_access_token") as save_access_token,
            patch("start_oauth_export.export_report") as export_report,
            patch("start_oauth_export.create_local_server", side_effect=fake_create_server),
        ):
            from start_oauth_export import main

            main()

        save_access_token.assert_called_once_with("TEST_ACCESS_VALUE")
        export_report.assert_called_once()

    def test_oauth_can_load_app_credentials_directly_from_keychain(self):
        environment = {
            "TIKTOK_ADVERTISER_ID": "TEST_ADVERTISER",
            "TIKTOK_ARTIFACT_NODE": "/tmp/node",
            "TIKTOK_OUTPUT_FILE": "/tmp/report.xlsx",
        }

        class FakeServer:
            def serve_forever(self):
                return None

            def server_close(self):
                return None

        with (
            patch.dict("start_oauth_export.os.environ", environment, clear=True),
            patch("start_oauth_export.load_access_token", return_value=None),
            patch("start_oauth_export.load_app_id", return_value="TEST_APP"),
            patch("start_oauth_export.load_app_secret", return_value="TEST_SECRET"),
            patch("start_oauth_export.create_local_server", return_value=FakeServer()) as create_server,
        ):
            from start_oauth_export import main

            main()

        self.assertEqual(create_server.call_args.kwargs["app_id"], "TEST_APP")
        self.assertEqual(create_server.call_args.kwargs["app_secret"], "TEST_SECRET")


if __name__ == "__main__":
    unittest.main()
