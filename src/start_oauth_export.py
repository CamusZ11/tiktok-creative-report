"""Start local OAuth, fetch a report, and atomically replace the XLSX on success."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

from creative_report_export import complete_natural_date_range
from run_creative_report import run_export
from tiktok_oauth import create_local_server


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = PROJECT_ROOT / "scripts" / "build_creative_workbook.mjs"


def build_workbook_atomically(
    *,
    node_command: str,
    builder_path: Path,
    payload_path: Path,
    output_path: Path,
) -> Path:
    """Keep the prior workbook in place unless a complete replacement was built."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.stem}-{uuid4().hex}.tmp.xlsx")
    try:
        subprocess.run(
            [node_command, str(builder_path), str(payload_path), str(temporary_path)],
            check=True,
        )
        if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            raise RuntimeError("workbook builder produced no XLSX")
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def resolve_date_range(
    environment: dict[str, str],
    *,
    reference_date: str | None = None,
) -> tuple[str, str]:
    start_date = environment.get("TIKTOK_START_DATE", "")
    end_date = environment.get("TIKTOK_END_DATE", "")
    if bool(start_date) != bool(end_date):
        raise RuntimeError("TIKTOK_START_DATE and TIKTOK_END_DATE must be set together")
    if start_date and end_date:
        return start_date, end_date
    return complete_natural_date_range(reference_date)


def safe_failure_detail(error: Exception) -> str:
    """Expose only endpoint-level errors that cannot contain credentials or identifiers."""

    message = str(error)
    if message.startswith("TikTok API request failed for /open_api/"):
        return message
    return type(error).__name__


def main() -> None:
    app_id = _required_environment("TIKTOK_APP_ID")
    app_secret = _required_environment("TIKTOK_APP_SECRET")
    advertiser_id = _required_environment("TIKTOK_ADVERTISER_ID")
    node_command = _required_environment("TIKTOK_ARTIFACT_NODE")
    output_path = Path(
        os.environ.get("TIKTOK_OUTPUT_FILE", str(PROJECT_ROOT / "output" / "TikTok_创意明细.xlsx"))
    ).expanduser()
    start_date, end_date = resolve_date_range(dict(os.environ))

    def on_access_token(access_token: str) -> None:
        with tempfile.TemporaryDirectory(prefix="tiktok-creative-report-") as directory:
            payload_path = Path(directory) / "creative-report.json"
            try:
                print("阶段：正在拉取 TikTok 创意明细。", flush=True)
                run_export(
                    access_token=access_token,
                    advertiser_id=advertiser_id,
                    payload_path=payload_path,
                    start_date=start_date,
                    end_date=end_date,
                )
                print("阶段：TikTok 数据拉取完成，正在生成 XLSX。", flush=True)
                build_workbook_atomically(
                    node_command=node_command,
                    builder_path=BUILDER_PATH,
                    payload_path=payload_path,
                    output_path=output_path,
                )
                print("阶段：XLSX 已原子替换完成。", flush=True)
            except Exception as error:
                print(f"阶段：导出失败，原因：{safe_failure_detail(error)}", flush=True)
                raise

    server = create_local_server(app_id=app_id, app_secret=app_secret, on_access_token=on_access_token)
    print("在浏览器打开：http://127.0.0.1:3000/api/oauth/tiktok/start", flush=True)
    print("授权并完成导出后按 Ctrl+C 结束本地服务。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
