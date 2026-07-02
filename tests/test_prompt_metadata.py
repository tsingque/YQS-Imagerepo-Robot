import unittest
from pathlib import Path

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_DIR / "python"
sys.path.insert(0, str(PYTHON_DIR))

import glm_client


class PromptMetadataTests(unittest.TestCase):
    def test_build_user_prompt_includes_bitable_metadata_and_ppt_usage_rule(self):
        prompt = glm_client.build_user_prompt(
            "规则正文",
            Path("demo.png"),
            {
                "source_path": "image_compressor/images_compressed/demo.png",
                "resolution": "100x100",
                "file_size": "10 KB",
                "record_id": "rec1",
                "名字": "minduck图标",
                "项目": "Minduck",
                "描述": "2026-minduck图标",
                "来源": "AI",
                "来源二级分类": "计划",
                "是否可商用": "有",
                "原始附件名": "logo.png",
            },
        )

        self.assertIn("适合用于", prompt)
        self.assertIn("AI 不负责判断、改变或审核商用权限", prompt)
        self.assertIn("bitable_record_id: rec1", prompt)
        self.assertIn("bitable_name: minduck图标", prompt)
        self.assertIn("bitable_project: Minduck", prompt)
        self.assertIn("bitable_description: 2026-minduck图标", prompt)
        self.assertIn("bitable_source_subcategory: 计划", prompt)
        self.assertIn("bitable_commercial: 有", prompt)


if __name__ == "__main__":
    unittest.main()
