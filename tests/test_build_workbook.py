import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
HEADERS = [
    "日期", "创意素材", "作品 ID", "商品名称", "商品 ID", "TikTok 账号", "授权类型", "探索状态", "发布时间", "广告计划名称",
    "成本", "SKU 订单数", "平均下单成本", "总收入", "商品广告曝光数", "商品广告点击数", "商品广告点击率", "广告转化率",
    "广告视频播放达 2 秒播放率", "广告视频播放达 6 秒播放率", "广告视频播放达 25% 播放率", "广告视频播放达 50% 播放率", "广告视频播放达 75% 播放率", "广告视频完播率",
]


class WorkbookBuildTests(unittest.TestCase):
    def test_builder_creates_creative_detail_workbook(self):
        node = os.environ["ARTIFACT_TOOL_NODE"]
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            payload_path = temporary_path / "payload.json"
            workbook_path = temporary_path / "TikTok_创意明细.xlsx"
            payload_path.write_text(
                json.dumps(
                    {
                        "headers": HEADERS,
                        "rows": [
                            {
                                "日期": "2026-08-14",
                                "创意素材": "fixture creative",
                                "作品 ID": "video-1",
                                "成本": 12.5,
                                "商品广告点击率": 0.1,
                                "广告视频完播率": 0.4,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [node, str(ROOT / "scripts" / "build_creative_workbook.mjs"), str(payload_path), str(workbook_path)],
                check=True,
                cwd=ROOT,
            )

            self.assertTrue(workbook_path.exists())
            with ZipFile(workbook_path) as workbook:
                names = set(workbook.namelist())
            self.assertIn("xl/workbook.xml", names)
            self.assertIn("xl/worksheets/sheet1.xml", names)
            probe_path = temporary_path / "probe.mjs"
            probe_path.write_text(
                f"""
import {{ FileBlob, SpreadsheetFile }} from "{(ROOT / 'node_modules' / '@oai' / 'artifact-tool' / 'dist' / 'artifact_tool.mjs').as_uri()}";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(process.argv[2]));
const sheet = workbook.worksheets.getItem("11_creative_daily_report");
console.log(JSON.stringify({{
  dateFormat: sheet.getRange("A2").format.numberFormat,
  workIdFormat: sheet.getRange("C2").format.numberFormat,
  productIdFormat: sheet.getRange("E2").format.numberFormat,
}}));
""",
                encoding="utf-8",
            )
            probe = subprocess.run(
                [node, str(probe_path), str(workbook_path)],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            formats = json.loads(probe.stdout)
            self.assertEqual(formats.get("dateFormat"), "yyyy-mm-dd")
            self.assertEqual(formats.get("workIdFormat"), "@")
            self.assertEqual(formats.get("productIdFormat"), "@")

    def test_builder_reuses_existing_metadata_when_new_api_row_is_blank(self):
        node = os.environ["ARTIFACT_TOOL_NODE"]
        headers = HEADERS
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            cached_payload = temporary_path / "cached.json"
            fresh_payload = temporary_path / "fresh.json"
            cached_workbook = temporary_path / "cached.xlsx"
            result_workbook = temporary_path / "result.xlsx"
            cached_payload.write_text(
                json.dumps({
                    "headers": headers,
                    "rows": [{
                        "作品 ID": "post-1",
                        "创意素材": "cached creative",
                        "商品 ID": "sku-1",
                        "TikTok 账号": "cached account",
                        "发布时间": "2026-08-10 12:00:00",
                        "广告计划名称": "cached plan",
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            fresh_payload.write_text(
                json.dumps({"headers": headers, "rows": [{"作品 ID": "post-1", "成本": 5}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            subprocess.run(
                [node, str(ROOT / "scripts" / "build_creative_workbook.mjs"), str(cached_payload), str(cached_workbook)],
                check=True,
                cwd=ROOT,
            )
            subprocess.run(
                [
                    node,
                    str(ROOT / "scripts" / "build_creative_workbook.mjs"),
                    str(fresh_payload),
                    str(cached_workbook),
                    "",
                    str(result_workbook),
                ],
                check=True,
                cwd=ROOT,
            )

            with ZipFile(result_workbook) as workbook:
                xml = "\n".join(
                    workbook.read(name).decode("utf-8", errors="ignore")
                    for name in workbook.namelist()
                    if name.endswith(".xml")
                )
            self.assertIn("cached creative", xml)
            self.assertIn("cached account", xml)
            self.assertIn("cached plan", xml)

    def test_builder_preserves_other_sheets_in_existing_workbook(self):
        node = os.environ["ARTIFACT_TOOL_NODE"]
        headers = HEADERS
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            existing_workbook = temporary_path / "existing.xlsx"
            result_workbook = temporary_path / "result.xlsx"
            payload_path = temporary_path / "payload.json"
            fixture_script = temporary_path / "fixture.mjs"
            fixture_script.write_text(
                f"""
import {{ SpreadsheetFile, Workbook }} from "{(ROOT / 'node_modules' / '@oai' / 'artifact-tool' / 'dist' / 'artifact_tool.mjs').as_uri()}";
const workbook = Workbook.create();
workbook.worksheets.add("Summary").getRange("A1").values = [["keep me"]];
workbook.worksheets.add("11_creative_daily_report").getRange("A1").values = [["old report"]];
await SpreadsheetFile.exportXlsx(workbook).then((blob) => blob.save(process.argv[2]));
""",
                encoding="utf-8",
            )
            payload_path.write_text(
                json.dumps({"headers": headers, "rows": [{"作品 ID": "post-1", "成本": 5}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            subprocess.run([node, str(fixture_script), str(existing_workbook)], check=True, cwd=ROOT)
            subprocess.run(
                [
                    node,
                    str(ROOT / "scripts" / "build_creative_workbook.mjs"),
                    str(payload_path),
                    str(existing_workbook),
                    "",
                    str(result_workbook),
                ],
                check=True,
                cwd=ROOT,
            )

            with ZipFile(result_workbook) as workbook:
                xml = "\n".join(
                    workbook.read(name).decode("utf-8", errors="ignore")
                    for name in workbook.namelist()
                    if name.endswith(".xml")
                )
            self.assertIn("Summary", xml)
            self.assertIn("11_creative_daily_report", xml)
            self.assertIn("keep me", xml)

    def test_builder_unhides_report_data_rows_from_existing_workbook(self):
        node = os.environ["ARTIFACT_TOOL_NODE"]
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            source_payload = temporary_path / "source.json"
            fresh_payload = temporary_path / "fresh.json"
            source_workbook = temporary_path / "source.xlsx"
            hidden_workbook = temporary_path / "hidden.xlsx"
            result_workbook = temporary_path / "result.xlsx"
            source_payload.write_text(
                json.dumps({"headers": HEADERS, "rows": [{"日期": "2026-08-14", "作品 ID": "post-1"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            fresh_payload.write_text(
                json.dumps({"headers": HEADERS, "rows": [{"日期": "2026-08-15", "作品 ID": "post-2"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            subprocess.run(
                [node, str(ROOT / "scripts" / "build_creative_workbook.mjs"), str(source_payload), str(source_workbook)],
                check=True,
                cwd=ROOT,
            )
            with ZipFile(source_workbook) as source, ZipFile(hidden_workbook, "w") as hidden:
                for entry in source.infolist():
                    content = source.read(entry.filename)
                    if entry.filename == "xl/worksheets/sheet1.xml":
                        content = content.replace(b'<x:row r="2">', b'<x:row r="2" hidden="1">')
                    hidden.writestr(entry, content)
            subprocess.run(
                [
                    node,
                    str(ROOT / "scripts" / "build_creative_workbook.mjs"),
                    str(fresh_payload),
                    str(hidden_workbook),
                    "",
                    str(result_workbook),
                ],
                check=True,
                cwd=ROOT,
            )
            with ZipFile(result_workbook) as workbook:
                sheet_xml = workbook.read("xl/worksheets/sheet1.xml")
            self.assertIn(b'<x:row r="2"', sheet_xml)
            self.assertNotIn(b'<x:row r="2" hidden="1"', sheet_xml)


if __name__ == "__main__":
    unittest.main()
