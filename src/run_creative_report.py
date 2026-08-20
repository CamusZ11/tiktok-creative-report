"""Run the read-only creative-detail export after OAuth returns an access token."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from creative_report_export import (
    TikTokReadOnlyClient,
    config_from_environment,
    download_creative_report,
    write_payload_file,
)


def run_export(
    *,
    access_token: str,
    advertiser_id: str,
    payload_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Fetch report data and write the credential-free payload used by the XLSX builder."""

    payload = download_creative_report(
        client=TikTokReadOnlyClient(access_token),
        advertiser_id=advertiser_id,
        start_date=start_date,
        end_date=end_date,
    )
    write_payload_file(payload, payload_path)
    metadata = payload.get("metadata", {})
    return dict(metadata) if isinstance(metadata, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 TikTok GMV Max 创意明细到临时 JSON。")
    parser.add_argument("--payload-file", required=True, type=Path)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()

    config = config_from_environment(start_date=args.start_date, end_date=args.end_date)
    summary = run_export(
        access_token=config["access_token"],
        advertiser_id=config["advertiser_id"],
        payload_path=args.payload_file,
        start_date=config["start_date"],
        end_date=config["end_date"],
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
