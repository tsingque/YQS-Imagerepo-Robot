import os
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_DIR / "python"
sys.path.insert(0, str(PYTHON_DIR))

import recognition_worker
import server


class DashboardAuthTests(unittest.TestCase):
    def test_write_allowed_when_token_is_not_configured(self):
        headers = Message()
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(server.is_write_authorized(headers))

    def test_write_rejected_with_wrong_token(self):
        headers = Message()
        headers["X-YQS-Dashboard-Token"] = "wrong"
        with patch.dict(os.environ, {"YQS_DASHBOARD_TOKEN": "secret"}, clear=True):
            self.assertFalse(server.is_write_authorized(headers))

    def test_write_allowed_with_matching_token(self):
        headers = Message()
        headers["X-YQS-Dashboard-Token"] = "secret"
        with patch.dict(os.environ, {"YQS_DASHBOARD_TOKEN": "secret"}, clear=True):
            self.assertTrue(server.is_write_authorized(headers))


class RecognitionWorkerCleanupTests(unittest.TestCase):
    def test_project_prefixed_bitable_name_targets_project_folder(self):
        self.assertEqual(
            recognition_worker.split_project_and_name("客户A-Minduck图标"),
            ("客户A", "Minduck图标"),
        )
        self.assertEqual(
            recognition_worker.split_project_and_name("Minduck图标"),
            ("", "Minduck图标"),
        )

    def test_target_material_folder_uses_project_or_general_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(recognition_worker, "CASE_MATERIALS_DIR", root / "case_materials"):
                self.assertEqual(
                    recognition_worker.target_material_folder({"名字": "项目A-图标"}),
                    root / "case_materials" / "项目A",
                )
                self.assertEqual(
                    recognition_worker.target_material_folder({"名字": "图标"}),
                    root / "case_materials" / "通用素材库",
                )

    def test_record_token_usage_accumulates_runtime_monitor(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = Path(tmp) / "runtime" / "ai_token_usage.json"
            alerts_path = Path(tmp) / "runtime" / "alerts.json"
            with patch.object(recognition_worker, "TOKEN_USAGE_PATH", usage_path), patch.object(
                recognition_worker, "ALERTS_PATH", alerts_path
            ), patch.dict(os.environ, {"AI_TOKEN_WARN_TOTAL": "10"}, clear=False):
                usage = recognition_worker.record_token_usage(
                    "demo.png",
                    {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12, "model": "kimi-test"},
                    "kimi",
                )

            self.assertEqual(usage["total_tokens"], 12)
            payload = recognition_worker.read_json(usage_path, {})
            self.assertEqual(payload["totals"]["total_tokens"], 12)
            self.assertEqual(payload["events"][0]["model"], "kimi-test")
            alerts = recognition_worker.read_json(alerts_path, [])
            self.assertTrue(alerts)

    def test_cleanup_processed_compressed_images_keeps_missing_outputs_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compressed = Path(tmp) / "image_compressor" / "images_compressed"
            recognized = root / "image_compressor" / "images_recognized"
            compressed.mkdir(parents=True)
            recognized.mkdir(parents=True)
            processed_file = compressed / "done.png"
            missing_file = compressed / "missing.png"
            pending_file = compressed / "pending.png"
            recognized_file = recognized / "done-renamed.png"
            processed_file.write_bytes(b"processed")
            missing_file.write_bytes(b"missing")
            pending_file.write_bytes(b"pending")
            recognized_file.write_bytes(b"recognized")
            processed = {
                "done.png": {
                    "recognized_at": "2026-06-30 15:00:00",
                    "recognized_path": "image_compressor/images_recognized/done-renamed.png",
                },
                "missing.png": {
                    "recognized_at": "2026-06-30 15:01:00",
                    "recognized_path": "image_compressor/images_recognized/missing-renamed.png",
                },
            }

            with patch.object(recognition_worker, "PROJECT_DIR", root), patch.object(
                recognition_worker, "IMAGES_COMPRESSED_DIR", compressed
            ):
                deleted, restored = recognition_worker.cleanup_processed_compressed_images(
                    [processed_file, missing_file, pending_file],
                    processed,
                )

            self.assertEqual(deleted, ["done.png"])
            self.assertEqual(restored, ["missing.png"])
            self.assertFalse(processed_file.exists())
            self.assertTrue(missing_file.exists())
            self.assertTrue(pending_file.exists())
            self.assertNotIn("missing.png", processed)


if __name__ == "__main__":
    unittest.main()
