import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


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
                        "headers": [
                            "创意素材", "作品 ID", "商品名称", "商品 ID", "TikTok 账号", "授权类型", "探索状态", "发布时间", "广告计划名称",
                            "成本", "SKU 订单数", "平均下单成本", "总收入", "商品广告曝光数", "商品广告点击数", "商品广告点击率", "广告转化率",
                            "广告视频播放达 2 秒播放率", "广告视频播放达 6 秒播放率", "广告视频播放达 25% 播放率", "广告视频播放达 50% 播放率", "广告视频播放达 75% 播放率", "广告视频完播率",
                        ],
                        "rows": [
                            {
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


if __name__ == "__main__":
    unittest.main()
