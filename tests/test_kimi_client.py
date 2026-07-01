import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_DIR / "python"
sys.path.insert(0, str(PYTHON_DIR))

import kimi_client
import recognition_worker


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "category": "测试",
                            "suggested_filename": "测试图片.png",
                        }, ensure_ascii=False)
                    }
                }
            ]
        }).encode("utf-8")


class KimiClientTests(unittest.TestCase):
    def test_kimi_client_uses_openai_compatible_vision_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "sample.png"
            Image.new("RGB", (16, 16), (255, 0, 0)).save(image_path)
            captured = {}

            def fake_urlopen(request, timeout):
                captured["url"] = request.full_url
                captured["timeout"] = timeout
                captured["headers"] = dict(request.header_items())
                captured["payload"] = json.loads(request.data.decode("utf-8"))
                return FakeResponse()

            env = {
                "KIMI_API_KEY": "kimi-test-key",
                "KIMI_MODEL": "kimi-k2.6",
                "KIMI_API_BASE": "https://api.moonshot.cn/v1/chat/completions",
                "KIMI_TIMEOUT_SECONDS": "33",
            }
            with patch.dict(os.environ, env, clear=True), patch("urllib.request.urlopen", fake_urlopen):
                result = kimi_client.recognize_image(
                    image_path,
                    "只返回 JSON",
                    {"source_path": "image_compressor/images_compressed/sample.png", "resolution": "16x16"},
                )

            self.assertEqual(result["suggested_filename"], "测试图片.png")
            self.assertEqual(captured["url"], "https://api.moonshot.cn/v1/chat/completions")
            self.assertEqual(captured["timeout"], 33)
            self.assertEqual(captured["headers"]["Authorization"], "Bearer kimi-test-key")
            self.assertEqual(captured["payload"]["model"], "kimi-k2.6")
            self.assertNotIn("temperature", captured["payload"])
            self.assertNotIn("response_format", captured["payload"])
            content = captured["payload"]["messages"][0]["content"]
            self.assertEqual(content[0]["type"], "text")
            self.assertEqual(content[1]["type"], "image_url")
            self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_recognition_worker_routes_kimi_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "sample.png"
            Image.new("RGB", (16, 16), (255, 0, 0)).save(image_path)
            with patch.dict(os.environ, {"AI_PROVIDER": "kimi"}, clear=True), patch.object(
                kimi_client, "recognize_image", return_value={"suggested_filename": "kimi.png"}
            ) as kimi_recognize, patch.object(
                recognition_worker.glm_client, "recognize_image", return_value={"suggested_filename": "glm.png"}
            ) as glm_recognize:
                result = recognition_worker.recognize_with_provider(image_path, "rules", {})

            self.assertEqual(result["suggested_filename"], "kimi.png")
            kimi_recognize.assert_called_once()
            glm_recognize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
