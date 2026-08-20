"""Start local OAuth, fetch a report, and atomically replace the XLSX on success."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from creative_report_export import complete_natural_date_range
from run_creative_report import run_export
from tiktok_oauth import create_local_server
from token_store import load_access_token, load_app_id, load_app_secret, save_access_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = PROJECT_ROOT / "scripts" / "build_creative_workbook.mjs"


def build_workbook_atomically(
    *,
    node_command: str,
    builder_path: Path,
    payload_path: Path,
    output_path: Path,
    metadata_source_path: Path | None = None,
) -> Path:
    """Keep the prior workbook in place unless a complete replacement was built."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    excel_lock_path = output_path.with_name(f"~${output_path.name}")
    if excel_lock_path.exists():
        raise RuntimeError("目标 XLSX 正在被 Excel 占用，请关闭工作簿后重试")
    temporary_path = output_path.with_name(f".{output_path.stem}-{uuid4().hex}.tmp.xlsx")
    try:
        builder_environment = dict(os.environ)
        for name in ("TIKTOK_APP_SECRET", "TIKTOK_ACCESS_TOKEN"):
            builder_environment.pop(name, None)
        subprocess.run(
            [
                node_command,
                str(builder_path),
                str(payload_path),
                str(output_path) if output_path.exists() else "",
                str(metadata_source_path) if metadata_source_path else "",
                str(temporary_path),
            ],
            check=True,
            env=builder_environment,
        )
        if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            raise RuntimeError("workbook builder produced no XLSX")
        if excel_lock_path.exists():
            raise RuntimeError("目标 XLSX 正在被 Excel 占用，请关闭工作簿后重试")
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
    if message.startswith("TikTok API request failed for /open_api/") or message.startswith(
        "TikTok API network failure for /open_api/"
    ):
        return message
    return type(error).__name__


def export_report(
    *,
    access_token: str,
    advertiser_id: str,
    node_command: str,
    output_path: Path,
    start_date: str,
    end_date: str,
    metadata_source_path: Path | None = None,
) -> None:
    """Fetch report data and replace the workbook only after a successful build."""

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
                metadata_source_path=metadata_source_path,
            )
            print("阶段：XLSX 已原子替换完成。", flush=True)
        except Exception as error:
            print(f"阶段：导出失败，原因：{safe_failure_detail(error)}", flush=True)
            raise


def main() -> None:
    advertiser_id = _required_environment("TIKTOK_ADVERTISER_ID")
    node_command = _required_environment("TIKTOK_ARTIFACT_NODE")
    output_path = Path(
        os.environ.get("TIKTOK_OUTPUT_FILE", str(PROJECT_ROOT / "output" / "TikTok_创意明细.xlsx"))
    ).expanduser()
    metadata_source_value = os.environ.get("TIKTOK_METADATA_SOURCE_XLSX", "")
    metadata_source_path = Path(metadata_source_value).expanduser() if metadata_source_value else None
    start_date, end_date = resolve_date_range(dict(os.environ))

    def on_access_token(access_token: str) -> None:
        save_access_token(access_token)
        export_report(
            access_token=access_token,
            advertiser_id=advertiser_id,
            node_command=node_command,
            output_path=output_path,
            start_date=start_date,
            end_date=end_date,
            metadata_source_path=metadata_source_path,
        )

    force_oauth = os.environ.get("TIKTOK_FORCE_OAUTH", "") == "1"
    access_token = None if force_oauth else load_access_token()
    if access_token:
        print("阶段：已从 macOS Keychain 读取长期 Token，无需浏览器授权。", flush=True)
        try:
            export_report(
                access_token=access_token,
                advertiser_id=advertiser_id,
                node_command=node_command,
                output_path=output_path,
                start_date=start_date,
                end_date=end_date,
                metadata_source_path=metadata_source_path,
            )
        except Exception:
            print(
                "长期 Token 若已撤销或失效，请运行：TIKTOK_FORCE_OAUTH=1 ./scripts/run_creative_report.sh",
                flush=True,
            )
            raise
        return

    app_id = os.environ.get("TIKTOK_APP_ID", "") or load_app_id() or ""
    app_secret = os.environ.get("TIKTOK_APP_SECRET", "") or load_app_secret() or ""
    if not app_id:
        raise RuntimeError("TIKTOK_APP_ID is required in Keychain or environment")
    if not app_secret:
        raise RuntimeError("TIKTOK_APP_SECRET is required in Keychain or environment")
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
