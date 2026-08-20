import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from creative_report_export import (
    CREATIVE_HEADERS,
    TikTokApiError,
    TikTokReadOnlyClient,
    _fetch_store_products,
    _report_filters,
    build_creative_rows,
    config_from_environment,
    complete_natural_date_range,
    download_creative_report,
    write_payload_file,
)
from run_creative_report import run_export


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status = 200

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class CreativeReportExportTests(unittest.TestCase):
    def test_default_date_range_uses_last_seven_complete_days(self):
        self.assertEqual(
            complete_natural_date_range("2026-08-20"),
            ("2026-08-13", "2026-08-19"),
        )

    def test_write_payload_file_writes_only_report_data(self):
        path = Path(tempfile.mkdtemp()) / "report.json"
        write_payload_file(
            {"headers": list(CREATIVE_HEADERS), "rows": [{"作品 ID": "video-1"}]},
            path,
        )
        content = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(content["rows"][0]["作品 ID"], "video-1")
        self.assertNotIn("access_token", path.read_text(encoding="utf-8"))

    def test_run_export_creates_a_credential_free_payload(self):
        path = Path(tempfile.mkdtemp()) / "report.json"
        expected_payload = {
            "headers": list(CREATIVE_HEADERS),
            "rows": [{"作品 ID": "video-1"}],
            "metadata": {"creative_row_count": 1},
        }
        with patch("run_creative_report.download_creative_report", return_value=expected_payload):
            summary = run_export(
                access_token="token-123",
                advertiser_id="advertiser-1",
                payload_path=path,
                start_date="2026-08-13",
                end_date="2026-08-19",
            )

        self.assertEqual(summary, {"creative_row_count": 1})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["rows"][0]["作品 ID"], "video-1")
        self.assertNotIn("token-123", path.read_text(encoding="utf-8"))

    def test_config_from_environment_uses_default_date_range_without_exposing_token(self):
        with patch.dict(
            "os.environ",
            {"TIKTOK_ACCESS_TOKEN": "token-123", "TIKTOK_ADVERTISER_ID": "advertiser-1"},
            clear=True,
        ):
            config = config_from_environment(reference_date="2026-08-20")

        self.assertEqual(config["advertiser_id"], "advertiser-1")
        self.assertEqual(config["start_date"], "2026-08-13")
        self.assertEqual(config["end_date"], "2026-08-19")
        self.assertNotIn("access_token", {key: value for key, value in config.items() if key != "access_token"})

    def test_download_creative_report_is_get_only_and_tolerates_product_permission_gap(self):
        requests = []

        def opener(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("Access-token"), "token-123")
            parsed = urlparse(request.full_url)
            endpoint = parsed.path
            query = parse_qs(parsed.query)
            requests.append(endpoint)
            if endpoint.endswith("/gmv_max/store/list/"):
                return FakeResponse({"code": 0, "data": {"store_list": [{"store_id": "store-1", "store_authorized_bc_id": "bc-1"}]}})
            if endpoint.endswith("/gmv_max/campaign/get/"):
                return FakeResponse({"code": 0, "data": {"list": [{"campaign_id": "campaign-1", "campaign_name": "GMV Max Plan"}], "page_info": {"total_page": 1}}})
            if endpoint.endswith("/campaign/gmv_max/info/"):
                return FakeResponse({"code": 0, "data": {"campaign_id": "campaign-1", "item_group_ids": ["sku-1"]}})
            if endpoint.endswith("/store/product/get/"):
                return FakeResponse({"code": 40001, "message": "permission denied", "data": {}})
            if endpoint.endswith("/gmv_max/identity/get/"):
                return FakeResponse({
                    "code": 0,
                    "data": {
                        "identity_list": [
                            {
                                "identity_id": "identity-1",
                                "identity_type": "BC_AUTH_TT",
                                "identity_authorized_bc_id": "bc-1",
                                "product_gmv_max_available": True,
                            }
                        ]
                    },
                })
            if endpoint.endswith("/gmv_max/video/get/"):
                self.assertEqual(query["page_size"], ["50"])
                identity_list = json.loads(query["identity_list"][0])
                self.assertEqual(identity_list[0]["identity_id"], "identity-1")
                self.assertEqual(identity_list[0]["identity_type"], "BC_AUTH_TT")
                return FakeResponse({"code": 0, "data": {"item_list": [{"item_id": "post-1", "text": "creative caption", "identity_info": {"display_name": "Into Beauty", "identity_type": "AUTH_CODE"}, "video_info": {"video_id": "video-1"}}], "page_info": {"total_page": 1}}})
            if endpoint.endswith("/gmv_max/report/get/"):
                self.assertEqual(query["dimensions"], ['["item_id"]'])
                filtering = json.loads(query["filtering"][0])
                self.assertEqual(
                    filtering,
                    {"campaign_ids": ["campaign-1"], "item_group_ids": ["sku-1"]},
                )
                return FakeResponse({"code": 0, "data": {"list": [{"dimensions": {"item_id": "post-1", "item_group_id": "sku-1"}, "metrics": {"cost": 12.5, "orders": 2}}], "page_info": {"total_page": 1}}})
            self.fail(f"unexpected endpoint: {endpoint}")

        payload = download_creative_report(
            client=TikTokReadOnlyClient("token-123", opener=opener),
            advertiser_id="advertiser-1",
            start_date="2026-08-14",
            end_date="2026-08-20",
        )

        self.assertEqual(payload["headers"], list(CREATIVE_HEADERS))
        self.assertEqual(payload["rows"][0]["商品名称"], "")
        self.assertEqual(payload["rows"][0]["广告计划名称"], "GMV Max Plan")
        self.assertNotIn("token-123", json.dumps(payload))
        self.assertIn("/open_api/v1.3/store/product/get/", requests)
        self.assertIn("/open_api/v1.3/gmv_max/report/get/", requests)

    def test_client_retries_transient_network_errors_without_exposing_request_credentials(self):
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise URLError("temporary network failure")
            return FakeResponse({"code": 0, "data": {"store_list": []}})

        response = TikTokReadOnlyClient(
            "token-123",
            opener=opener,
            retry_delay_seconds=0,
        ).get(
            "/open_api/v1.3/gmv_max/store/list/",
            {"advertiser_id": "advertiser-1"},
        )

        self.assertEqual(calls, 2)
        self.assertEqual(response["code"], 0)

    def test_fetch_store_products_paginates_and_only_tolerates_permission_denial(self):
        class FakeClient:
            def __init__(self, responses):
                self.responses = list(responses)
                self.pages = []

            def get(self, endpoint, params):
                self.pages.append(params["page"])
                return self.responses.pop(0)

        client = FakeClient([
            {
                "code": 0,
                "data": {
                    "product_list": [{"product_id": "sku-1"}],
                    "page_info": {"total_page": 2},
                },
            },
            {
                "code": 0,
                "data": {
                    "product_list": [{"product_id": "sku-2"}],
                    "page_info": {"total_page": 2},
                },
            },
        ])
        self.assertEqual(
            [item["product_id"] for item in _fetch_store_products(client, "adv-1", "store-1")],
            ["sku-1", "sku-2"],
        )
        self.assertEqual(client.pages, [1, 2])

        denied = FakeClient([{"code": 40001, "message": "permission denied", "data": {}}])
        self.assertEqual(_fetch_store_products(denied, "adv-1", "store-1"), [])

        failed = FakeClient([{"code": 50002, "message": "temporary failure", "data": {}}])
        with self.assertRaises(TikTokApiError):
            _fetch_store_products(failed, "adv-1", "store-1")

    def test_report_filters_refuse_to_silently_truncate_api_limits(self):
        campaigns = [{"campaign_id": f"campaign-{index}"} for index in range(101)]
        details = [{"item_group_ids": ["sku-1"]}]
        with self.assertRaisesRegex(TikTokApiError, "100 campaign"):
            _report_filters(campaigns, details)

        campaigns = [{"campaign_id": "campaign-1"}]
        details = [{"item_group_ids": [f"sku-{index}" for index in range(101)]}]
        with self.assertRaisesRegex(TikTokApiError, "100 product"):
            _report_filters(campaigns, details)

    def test_build_creative_rows_maps_report_and_reference_fields(self):
        rows = build_creative_rows(
            creative_rows=[
                {
                    "dimensions": {"item_id": "post-1", "item_group_id": "sku-1"},
                    "metrics": {
                        "creative_delivery_status": "DELIVERING",
                        "cost": 12.5,
                        "orders": 2,
                        "cost_per_order": 6.25,
                        "gross_revenue": 50,
                        "product_impressions": 100,
                        "product_clicks": 10,
                        "product_click_rate": 10,
                        "ad_conversion_rate": 20,
                        "ad_video_view_rate_2s": 90,
                        "ad_video_view_rate_6s": 80,
                        "ad_video_view_rate_p25": 70,
                        "ad_video_view_rate_p50": 60,
                        "ad_video_view_rate_p75": 50,
                        "ad_video_view_rate_p100": 40,
                    },
                }
            ],
            videos=[
                {
                    "item_id": "post-1",
                    "text": "creative caption",
                    "identity_info": {
                        "display_name": "Into Beauty",
                        "identity_type": "AUTH_CODE",
                    },
                    "video_info": {"video_id": "video-1", "create_time": "2026-08-20T10:00:00Z"},
                }
            ],
            campaigns=[{"campaign_id": "campaign-1", "campaign_name": "GMV Max Plan"}],
            campaign_details=[{"campaign_id": "campaign-1", "item_group_ids": ["sku-1"]}],
            products=[{"item_group_id": "sku-1", "product_name": "Serum"}],
        )

        self.assertEqual(list(rows[0]), list(CREATIVE_HEADERS))
        self.assertEqual(rows[0]["创意素材"], "creative caption")
        self.assertEqual(rows[0]["作品 ID"], "video-1")
        self.assertEqual(rows[0]["商品名称"], "Serum")
        self.assertEqual(rows[0]["商品 ID"], "sku-1")
        self.assertEqual(rows[0]["TikTok 账号"], "Into Beauty")
        self.assertEqual(rows[0]["授权类型"], "AUTH_CODE")
        self.assertEqual(rows[0]["探索状态"], "DELIVERING")
        self.assertEqual(rows[0]["发布时间"], "2026-08-20T10:00:00Z")
        self.assertEqual(rows[0]["广告计划名称"], "GMV Max Plan")
        self.assertEqual(rows[0]["成本"], 12.5)
        self.assertEqual(rows[0]["商品广告点击率"], 0.1)
        self.assertEqual(rows[0]["广告转化率"], 0.2)
        self.assertEqual(rows[0]["广告视频完播率"], 0.4)

    def test_build_creative_rows_leaves_product_name_blank_without_product_access(self):
        rows = build_creative_rows(
            creative_rows=[
                {
                    "dimensions": {"item_id": "post-2", "item_group_id": "sku-2"},
                    "metrics": {"cost": 0},
                }
            ],
            videos=[],
            campaigns=[],
            campaign_details=[],
            products=[],
        )

        self.assertEqual(rows[0]["商品名称"], "")
        self.assertEqual(rows[0]["商品 ID"], "sku-2")
        self.assertEqual(rows[0]["成本"], 0)
        self.assertTrue(all(not isinstance(value, (dict, list)) for value in rows[0].values()))

    def test_build_creative_rows_uses_video_spu_when_report_has_only_item_id(self):
        rows = build_creative_rows(
            creative_rows=[
                {
                    "dimensions": {"item_id": "post-3"},
                    "metrics": {"cost": 1},
                }
            ],
            videos=[
                {
                    "item_id": "post-3",
                    "spu_id_list": ["sku-3"],
                    "text": "creative 3",
                    "identity_info": {"display_name": "Account 3", "identity_type": "TT_USER"},
                }
            ],
            campaigns=[{"campaign_id": "campaign-3", "campaign_name": "Plan 3"}],
            campaign_details=[{"campaign_id": "campaign-3", "item_group_ids": ["sku-3"]}],
            products=[{"item_group_id": "sku-3", "product_name": "Product 3"}],
        )

        self.assertEqual(rows[0]["商品 ID"], "sku-3")
        self.assertEqual(rows[0]["商品名称"], "Product 3")
        self.assertEqual(rows[0]["广告计划名称"], "Plan 3")

    def test_build_creative_rows_uses_campaign_detail_item_list_as_video_reference(self):
        rows = build_creative_rows(
            creative_rows=[{"dimensions": {"item_id": "post-4"}, "metrics": {"cost": 1}}],
            videos=[],
            campaigns=[{"campaign_id": "campaign-4", "campaign_name": "Plan 4"}],
            campaign_details=[
                {
                    "campaign_id": "campaign-4",
                    "item_group_ids": ["sku-4"],
                    "item_list": [
                        {
                            "item_id": "post-4",
                            "spu_id_list": ["sku-4"],
                            "text": "creative 4",
                            "identity_info": {"display_name": "Account 4", "identity_type": "BC_AUTH_TT"},
                        }
                    ],
                }
            ],
            products=[],
        )

        self.assertEqual(rows[0]["创意素材"], "creative 4")
        self.assertEqual(rows[0]["商品 ID"], "sku-4")
        self.assertEqual(rows[0]["TikTok 账号"], "Account 4")
        self.assertEqual(rows[0]["授权类型"], "BC_AUTH_TT")
        self.assertEqual(rows[0]["广告计划名称"], "Plan 4")

    def test_build_creative_rows_keeps_all_product_and_campaign_associations(self):
        rows = build_creative_rows(
            creative_rows=[{"dimensions": {"item_id": "post-5"}, "metrics": {"cost": 1}}],
            videos=[{"item_id": "post-5", "spu_id_list": ["sku-1", "sku-2"]}],
            campaigns=[
                {"campaign_id": "campaign-1", "campaign_name": "Plan 1"},
                {"campaign_id": "campaign-2", "campaign_name": "Plan 2"},
            ],
            campaign_details=[
                {"campaign_id": "campaign-1", "item_group_ids": ["sku-1"]},
                {"campaign_id": "campaign-2", "item_group_ids": ["sku-2"]},
            ],
            products=[
                {"product_id": "sku-1", "product_name": "Product 1"},
                {"product_id": "sku-2", "product_name": "Product 2"},
            ],
        )

        self.assertEqual(rows[0]["商品 ID"], "sku-1 | sku-2")
        self.assertEqual(rows[0]["商品名称"], "Product 1 | Product 2")
        self.assertEqual(rows[0]["广告计划名称"], "Plan 1 | Plan 2")


if __name__ == "__main__":
    unittest.main()
