import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_DIR / "python"
sys.path.insert(0, str(PYTHON_DIR))

import bitable_sync


class BitableSyncTests(unittest.TestCase):
    def test_parse_record_extracts_configured_fields_and_attachment(self):
        record = {
            "record_id": "rec1",
            "fields": {
                "名字": [{"text": "minduck图标"}],
                "描述": "2026-minduck图标",
                "文件": [{"file_token": "tok1", "name": "logo.png", "size": 100}],
                "来源": "下载",
                "是否可用": "是",
            },
        }

        parsed = bitable_sync.parse_record(record, bitable_sync.BitableFieldConfig())

        self.assertEqual(parsed.record_id, "rec1")
        self.assertEqual(parsed.name, "minduck图标")
        self.assertEqual(parsed.description, "2026-minduck图标")
        self.assertEqual(parsed.source, "下载")
        self.assertEqual(parsed.usable, "是")
        self.assertEqual(parsed.attachments[0]["file_token"], "tok1")

    def test_sync_downloads_usable_records_and_skips_unusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "image_compressor" / "images_raw"
            runtime_dir = root / "runtime"
            client = MagicMock()
            client.configured.return_value = True
            client.list_records.return_value = [
                {
                    "record_id": "rec-y",
                    "fields": {
                        "名字": "可用图",
                        "描述": "用于产品页",
                        "文件": [{"file_token": "tok-y", "name": "demo.png"}],
                        "来源": "截图",
                        "是否可用": "是",
                    },
                },
                {
                    "record_id": "rec-n",
                    "fields": {
                        "名字": "不可用图",
                        "描述": "不进入素材库",
                        "文件": [{"file_token": "tok-n", "name": "skip.png"}],
                        "来源": "下载",
                        "是否可用": "否",
                    },
                },
            ]
            client.download_attachment.side_effect = lambda attachment, target: target.write_bytes(b"image")

            with patch.object(bitable_sync, "PROJECT_DIR", root), patch.object(
                bitable_sync, "IMAGES_RAW_DIR", raw_dir
            ), patch.object(bitable_sync, "RUNTIME_DIR", runtime_dir), patch.object(
                bitable_sync, "BITABLE_FILE_MAP_PATH", runtime_dir / "bitable_file_map.json"
            ), patch.object(
                bitable_sync, "BITABLE_RECORDS_PATH", runtime_dir / "bitable_records.json"
            ):
                result = bitable_sync.sync_bitable_to_raw(client=client)

            self.assertTrue(result["ok"])
            self.assertEqual(result["downloaded"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertTrue((raw_dir / "rec-y_demo.png").is_file())
            client.update_record.assert_not_called()

            file_map = json.loads((runtime_dir / "bitable_file_map.json").read_text(encoding="utf-8"))
            self.assertEqual(file_map["rec-y_demo.png"]["record_id"], "rec-y")
            self.assertEqual(file_map["rec-y_demo.png"]["名字"], "可用图")
            self.assertEqual(file_map["rec-y_demo.png"]["是否可用"], "是")

    def test_sync_is_noop_when_client_not_configured(self):
        client = MagicMock()
        client.configured.return_value = False
        result = bitable_sync.sync_bitable_to_raw(client=client)
        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["message"], "未配置飞书多维表格，跳过同步。")

    def test_build_write_back_fields_is_empty_for_input_only_table(self):
        fields = bitable_sync.build_write_back_fields(
            bitable_sync.BitableFieldConfig(),
            status="已完成",
            record={
                "图片内容": "Minduck 图标",
                "想放在哪（章节/论点）": "品牌介绍页 / 产品能力页",
                "分类": "概念",
                "关键数据": "Minduck",
            },
            recognized_path="image_compressor/images_recognized/minduck.png",
        )

        self.assertEqual(fields, {})


if __name__ == "__main__":
    unittest.main()
