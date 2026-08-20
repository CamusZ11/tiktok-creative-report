import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from start_oauth_export import build_workbook_atomically, resolve_date_range


class StartOAuthExportTests(unittest.TestCase):
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

        def successful_builder(command, check):
            Path(command[-1]).write_bytes(b"new-workbook")

        with patch("start_oauth_export.subprocess.run", side_effect=successful_builder):
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


if __name__ == "__main__":
    unittest.main()
