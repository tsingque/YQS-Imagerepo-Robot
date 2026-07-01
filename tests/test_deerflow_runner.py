import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_DIR / "python"
sys.path.insert(0, str(PYTHON_DIR))

import deerflow_runner


class DeerflowRunnerDirectTests(unittest.TestCase):
    def test_direct_workflow_skips_ai_when_raw_and_compressed_are_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "deerflow_agent_state.json"
            status = {
                "ok": True,
                "counts": {"raw": 0, "compressed": 0, "recognized": 0, "finished": 0},
                "feishu": {"configured": False},
            }

            with patch.object(deerflow_runner, "STATE_PATH", state_path), patch.object(
                deerflow_runner, "RUNTIME_DIR", state_path.parent
            ), patch.object(deerflow_runner.yqs_tools, "repository_status", return_value=status), patch.object(
                deerflow_runner.yqs_tools, "sync_bitable_to_raw", return_value={"ok": True, "skipped": True}
            ) as sync_mock, patch.object(
                deerflow_runner.yqs_tools, "compress_raw_images"
            ) as compress_mock, patch.object(deerflow_runner.yqs_tools, "run_glm_recognition") as recognition_mock:
                result = deerflow_runner.run_managed_workflow(force_direct=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "暂无图片，请先通过飞书发送图片。")
        self.assertIn("暂无图片", result["reply"])
        sync_mock.assert_called_once()
        compress_mock.assert_not_called()
        recognition_mock.assert_not_called()

    def test_direct_workflow_reports_failed_recognition_without_traceback_in_reply(self):
        statuses = [
            {
                "ok": True,
                "counts": {"raw": 2, "compressed": 0, "recognized": 0, "finished": 0},
                "feishu": {"configured": False},
            },
            {
                "ok": True,
                "counts": {"raw": 0, "compressed": 2, "recognized": 0, "finished": 0},
                "feishu": {"configured": False},
            },
            {
                "ok": True,
                "counts": {"raw": 0, "compressed": 2, "recognized": 0, "finished": 0},
                "feishu": {"configured": False},
            },
        ]
        recognition = {
            "ok": False,
            "provider": "kimi",
            "summary": {
                "completed": 1,
                "failed": 1,
                "errors": [{"file": "bad.png", "error": "boom"}],
            },
            "outputs": {
                "markdown": "案例素材清单_表格.md",
                "workbook": "案例素材清单.xlsx",
                "resolution_csv": "素材分辨率.csv",
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "deerflow_agent_state.json"
            with patch.object(deerflow_runner, "STATE_PATH", state_path), patch.object(
                deerflow_runner, "RUNTIME_DIR", state_path.parent
            ), patch.object(deerflow_runner.yqs_tools, "sync_bitable_to_raw", return_value={"ok": True, "downloaded": 0}), patch.object(
                deerflow_runner.yqs_tools, "repository_status", side_effect=statuses
            ), patch.object(
                deerflow_runner.yqs_tools, "compress_raw_images", return_value={"ok": True, "compressed": 2, "deleted_raw": 2}
            ), patch.object(deerflow_runner.yqs_tools, "run_glm_recognition", return_value=recognition):
                result = deerflow_runner.run_managed_workflow(force_direct=True)

        self.assertFalse(result["ok"])
        self.assertIn("识图成功 1 张，失败 1 张", result["reply"])
        self.assertIn("bad.png: boom", result["reply"])
        self.assertNotIn("Traceback", result["reply"])

    def test_direct_workflow_stops_when_bitable_sync_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "deerflow_agent_state.json"
            with patch.object(deerflow_runner, "STATE_PATH", state_path), patch.object(
                deerflow_runner, "RUNTIME_DIR", state_path.parent
            ), patch.object(
                deerflow_runner.yqs_tools, "sync_bitable_to_raw", return_value={"ok": False, "errors": [{"error": "no permission"}]}
            ), patch.object(deerflow_runner.yqs_tools, "repository_status") as status_mock:
                result = deerflow_runner.run_managed_workflow(force_direct=True)

        self.assertFalse(result["ok"])
        self.assertIn("多维表格同步失败", result["reply"])
        status_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
