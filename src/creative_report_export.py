"""Build a read-only TikTok GMV Max creative-detail export payload."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


CREATIVE_HEADERS = (
    "创意素材",
    "作品 ID",
    "商品名称",
    "商品 ID",
    "TikTok 账号",
    "授权类型",
    "探索状态",
    "发布时间",
    "广告计划名称",
    "成本",
    "SKU 订单数",
    "平均下单成本",
    "总收入",
    "商品广告曝光数",
    "商品广告点击数",
    "商品广告点击率",
    "广告转化率",
    "广告视频播放达 2 秒播放率",
    "广告视频播放达 6 秒播放率",
    "广告视频播放达 25% 播放率",
    "广告视频播放达 50% 播放率",
    "广告视频播放达 75% 播放率",
    "广告视频完播率",
)

BASE_URL = "https://business-api.tiktok.com"
CREATIVE_REPORT_METRICS = (
    "creative_delivery_status",
    "cost",
    "orders",
    "cost_per_order",
    "gross_revenue",
    "product_impressions",
    "product_clicks",
    "product_click_rate",
    "ad_conversion_rate",
    "ad_video_view_rate_2s",
    "ad_video_view_rate_6s",
    "ad_video_view_rate_p25",
    "ad_video_view_rate_p50",
    "ad_video_view_rate_p75",
    "ad_video_view_rate_p100",
)
READ_ONLY_ENDPOINTS = frozenset(
    {
        "/open_api/v1.3/gmv_max/store/list/",
        "/open_api/v1.3/gmv_max/campaign/get/",
        "/open_api/v1.3/campaign/gmv_max/info/",
        "/open_api/v1.3/store/product/get/",
        "/open_api/v1.3/gmv_max/identity/get/",
        "/open_api/v1.3/gmv_max/video/get/",
        "/open_api/v1.3/gmv_max/report/get/",
    }
)


class TikTokApiError(RuntimeError):
    """A non-successful TikTok API response without sensitive request details."""


@dataclass
class TikTokReadOnlyClient:
    access_token: str
    opener: Any = urlopen
    base_url: str = BASE_URL

    def __post_init__(self) -> None:
        if not self.access_token:
            raise ValueError("access_token is required")

    def get(self, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if endpoint not in READ_ONLY_ENDPOINTS:
            raise ValueError(f"endpoint is not in the read-only allowlist: {endpoint}")
        encoded: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (Mapping, list, tuple)):
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            elif isinstance(value, bool):
                value = "true" if value else "false"
            else:
                value = str(value)
            encoded.append((key, value))
        url = f"{self.base_url.rstrip('/')}{endpoint}?{urlencode(encoded)}"
        request = Request(
            url,
            headers={"Access-Token": self.access_token, "Accept": "application/json"},
            method="GET",
        )
        with self.opener(request, timeout=30) as response:
            body = response.read()
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TikTokApiError("TikTok API returned invalid JSON") from error
        if not isinstance(payload, Mapping):
            raise TikTokApiError("TikTok API returned an invalid response")
        return payload


def _response_code(response: Mapping[str, Any]) -> int:
    code = response.get("code", -1)
    return int(code) if isinstance(code, (int, float, str)) and str(code).lstrip("-").isdigit() else -1


def _require_success(response: Mapping[str, Any], endpoint: str) -> Mapping[str, Any]:
    if _response_code(response) != 0:
        raise TikTokApiError(f"TikTok API request failed for {endpoint}")
    return response


def _rows_from_value(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if not isinstance(value, Mapping):
        return []
    for key in ("list", "store_list", "identity_list", "item_list", "product_list"):
        rows = _rows_from_value(value.get(key))
        if rows:
            return rows
    return []


def _extract_rows(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _rows_from_value(response.get("data", response))


def _page_count(response: Mapping[str, Any]) -> int:
    data = _mapping(response.get("data"))
    page_info = _mapping(data.get("page_info"))
    value = page_info.get("total_page") or page_info.get("total_pages") or 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _fetch_pages(
    client: TikTokReadOnlyClient,
    endpoint: str,
    params: Mapping[str, Any],
) -> list[dict[str, Any]]:
    page_params = dict(params)
    page_params["page"] = 1
    first = _require_success(client.get(endpoint, page_params), endpoint)
    rows = _extract_rows(first)
    for page in range(2, _page_count(first) + 1):
        page_params["page"] = page
        response = _require_success(client.get(endpoint, page_params), endpoint)
        rows.extend(_extract_rows(response))
    return rows


def _store_contexts(stores: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    contexts = []
    for store in stores:
        store_id = _first_value(store, ("store_id", "shop_id"))
        bc_id = _first_value(store, ("store_authorized_bc_id", "authorized_bc_id", "bc_id"))
        if store_id and bc_id:
            contexts.append((store_id, bc_id))
    return contexts


def download_creative_report(
    *,
    client: TikTokReadOnlyClient,
    advertiser_id: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Fetch the read-only sources required for the creative-detail workbook."""

    stores_response = _require_success(
        client.get("/open_api/v1.3/gmv_max/store/list/", {"advertiser_id": advertiser_id}),
        "/open_api/v1.3/gmv_max/store/list/",
    )
    stores = _extract_rows(stores_response)
    store_ids = [store_id for store_id, _ in _store_contexts(stores)]
    if not store_ids:
        raise TikTokApiError("TikTok API returned no accessible GMV Max shop")

    campaigns = _fetch_pages(
        client,
        "/open_api/v1.3/gmv_max/campaign/get/",
        {
            "advertiser_id": advertiser_id,
            "page_size": 100,
            "filtering": {"gmv_max_promotion_types": ["PRODUCT_GMV_MAX"]},
        },
    )
    campaign_details = []
    for campaign in campaigns:
        campaign_id = _first_value(campaign, ("campaign_id", "id"))
        if not campaign_id:
            continue
        response = _require_success(
            client.get(
                "/open_api/v1.3/campaign/gmv_max/info/",
                {"advertiser_id": advertiser_id, "campaign_id": campaign_id},
            ),
            "/open_api/v1.3/campaign/gmv_max/info/",
        )
        data = _mapping(response.get("data"))
        campaign_details.append(dict(data) if data else {})

    products: list[dict[str, Any]] = []
    for store_id in store_ids:
        response = client.get(
            "/open_api/v1.3/store/product/get/",
            {"advertiser_id": advertiser_id, "store_id": store_id, "page": 1, "page_size": 100},
        )
        if _response_code(response) == 0:
            products.extend(_extract_rows(response))

    identities: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    for store_id, bc_id in _store_contexts(stores):
        identities.extend(
            _fetch_pages(
                client,
                "/open_api/v1.3/gmv_max/identity/get/",
                {"advertiser_id": advertiser_id, "store_id": store_id, "store_authorized_bc_id": bc_id, "page_size": 100},
            )
        )
        videos.extend(
            _fetch_pages(
                client,
                "/open_api/v1.3/gmv_max/video/get/",
                {
                    "advertiser_id": advertiser_id,
                    "store_id": store_id,
                    "store_authorized_bc_id": bc_id,
                    "need_auth_code_video": True,
                    "page_size": 100,
                },
            )
        )

    campaign_ids = [_first_value(campaign, ("campaign_id", "id")) for campaign in campaigns]
    campaign_ids = [campaign_id for campaign_id in campaign_ids if campaign_id][:100]
    item_group_ids = list(
        dict.fromkeys(
            item_group_id
            for detail in campaign_details
            for item_group_id in _item_group_ids(detail)
        )
    )[:100]
    if not campaign_ids or not item_group_ids:
        raise TikTokApiError("TikTok API returned no product GMV Max campaign or product ID")

    creative_rows = _fetch_pages(
        client,
        "/open_api/v1.3/gmv_max/report/get/",
        {
            "advertiser_id": advertiser_id,
            "store_ids": store_ids,
            "start_date": start_date,
            "end_date": end_date,
            "metrics": list(CREATIVE_REPORT_METRICS),
            "dimensions": ["item_id"],
            "gmv_max_promotion_types": ["PRODUCT"],
            "filtering": {"campaign_ids": campaign_ids, "item_group_ids": item_group_ids},
            "enable_total_metrics": True,
            "page_size": 1000,
        },
    )
    return {
        "headers": list(CREATIVE_HEADERS),
        "rows": build_creative_rows(
            creative_rows=creative_rows,
            videos=videos,
            campaigns=campaigns,
            campaign_details=campaign_details,
            products=products,
        ),
        "metadata": {
            "start_date": start_date,
            "end_date": end_date,
            "creative_row_count": len(creative_rows),
            "product_name_available": bool(products),
            "identity_count": len(identities),
        },
    }


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def complete_natural_date_range(reference_date: str | date | None = None) -> tuple[str, str]:
    """Return the last seven complete calendar days in the ad-account timezone."""

    if reference_date is None:
        today = datetime.now(ZoneInfo("Asia/Singapore")).date()
    elif isinstance(reference_date, str):
        today = date.fromisoformat(reference_date)
    else:
        today = reference_date
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=6)
    return start_date.isoformat(), end_date.isoformat()


def write_payload_file(payload: Mapping[str, Any], path: Path) -> Path:
    """Write a temporary, credential-free workbook payload for the JS builder."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def config_from_environment(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    reference_date: str | date | None = None,
) -> dict[str, str]:
    """Read process-scoped credentials and report dates without persisting them."""

    access_token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    advertiser_id = os.environ.get("TIKTOK_ADVERTISER_ID", "")
    if not access_token:
        raise ValueError("TIKTOK_ACCESS_TOKEN is required")
    if not advertiser_id:
        raise ValueError("TIKTOK_ADVERTISER_ID is required")
    if bool(start_date) != bool(end_date):
        raise ValueError("start_date and end_date must be supplied together")
    if not start_date or not end_date:
        start_date, end_date = complete_natural_date_range(reference_date)
    return {
        "access_token": access_token,
        "advertiser_id": advertiser_id,
        "start_date": start_date,
        "end_date": end_date,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_value(row: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _item_group_ids(row: Mapping[str, Any]) -> list[str]:
    values = row.get("item_group_ids") or row.get("item_group_id") or []
    if not isinstance(values, list):
        values = [values]
    return [str(value) for value in values if value not in (None, "")]


def build_creative_rows(
    *,
    creative_rows: Iterable[Mapping[str, Any]],
    videos: Iterable[Mapping[str, Any]],
    campaigns: Iterable[Mapping[str, Any]],
    campaign_details: Iterable[Mapping[str, Any]],
    products: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join read-only endpoint results into the fixed creative-report columns."""

    video_by_item = {
        _first_value(video, ("item_id", "id")): video
        for video in videos
        if _first_value(video, ("item_id", "id"))
    }
    product_name_by_id = {
        _first_value(product, ("item_group_id", "spu_id", "product_id")): _first_value(
            product, ("product_name", "name", "title")
        )
        for product in products
        if _first_value(product, ("item_group_id", "spu_id", "product_id"))
    }
    campaign_name_by_id = {
        _first_value(campaign, ("campaign_id", "id")): _first_value(
            campaign, ("campaign_name", "name")
        )
        for campaign in campaigns
        if _first_value(campaign, ("campaign_id", "id"))
    }
    campaign_by_product_id: dict[str, str] = {}
    for detail in campaign_details:
        campaign_id = _first_value(detail, ("campaign_id", "id"))
        for item_group_id in _item_group_ids(detail):
            campaign_by_product_id.setdefault(item_group_id, campaign_id)

    result: list[dict[str, Any]] = []
    for creative in creative_rows:
        dimensions = _mapping(creative.get("dimensions"))
        metrics = _mapping(creative.get("metrics"))
        item_id = _first_value(dimensions, ("item_id", "id"))
        item_group_id = _first_value(dimensions, ("item_group_id", "spu_id", "product_id"))
        video = _mapping(video_by_item.get(item_id))
        identity = _mapping(video.get("identity_info"))
        video_info = _mapping(video.get("video_info"))
        campaign_id = campaign_by_product_id.get(item_group_id, "")

        row = {
            "创意素材": _first_value(video, ("text", "title", "name")),
            "作品 ID": _first_value(video_info, ("video_id", "item_id")) or item_id,
            "商品名称": product_name_by_id.get(item_group_id, ""),
            "商品 ID": item_group_id,
            "TikTok 账号": _first_value(identity, ("display_name", "user_name")),
            "授权类型": _first_value(identity, ("identity_type",)),
            "探索状态": _text(metrics.get("creative_delivery_status")),
            "发布时间": _first_value(video_info, ("create_time", "publish_time")),
            "广告计划名称": campaign_name_by_id.get(campaign_id, ""),
            "成本": metrics.get("cost", ""),
            "SKU 订单数": metrics.get("orders", ""),
            "平均下单成本": metrics.get("cost_per_order", ""),
            "总收入": metrics.get("gross_revenue", ""),
            "商品广告曝光数": metrics.get("product_impressions", ""),
            "商品广告点击数": metrics.get("product_clicks", ""),
            "商品广告点击率": metrics.get("product_click_rate", ""),
            "广告转化率": metrics.get("ad_conversion_rate", ""),
            "广告视频播放达 2 秒播放率": metrics.get("ad_video_view_rate_2s", ""),
            "广告视频播放达 6 秒播放率": metrics.get("ad_video_view_rate_6s", ""),
            "广告视频播放达 25% 播放率": metrics.get("ad_video_view_rate_p25", ""),
            "广告视频播放达 50% 播放率": metrics.get("ad_video_view_rate_p50", ""),
            "广告视频播放达 75% 播放率": metrics.get("ad_video_view_rate_p75", ""),
            "广告视频完播率": metrics.get("ad_video_view_rate_p100", ""),
        }
        result.append({header: row[header] for header in CREATIVE_HEADERS})
    return result
