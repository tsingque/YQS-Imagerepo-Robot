import unittest
from pathlib import Path


import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import setup_bitable


class FakeBitableClient:
    def __init__(self) -> None:
        self.app_token = "app"
        self.table_id = "table"
        self.view_id = "view"
        self.calls: list[str] = []

    def configured(self) -> bool:
        return True

    def list_fields(self) -> list[dict]:
        self.calls.append("list_fields")
        return [
            {"field_name": "名字", "field_id": "fld_name", "is_primary": True},
            {"field_name": "描述", "field_id": "fld_desc"},
            {"field_name": "文件", "field_id": "fld_file"},
            {"field_name": "来源", "field_id": "fld_source"},
            {"field_name": "是否可商用", "field_id": "fld_commercial"},
        ]

    def list_views(self) -> list[dict]:
        self.calls.append("list_views")
        return [{"view_id": "form", "view_name": "图片上传表单视图", "view_type": "form"}]

    def create_app(self) -> dict:
        self.calls.append("create_app")
        return {}

    def create_table(self) -> dict:
        self.calls.append("create_table")
        return {}

    def ensure_schema(self, fields: dict) -> dict:
        self.calls.append("ensure_schema")
        return {"created": []}

    def grant_tenant_editable(self) -> dict:
        self.calls.append("grant_tenant_editable")
        return {"ok": True}

    def create_form_view(self) -> dict:
        self.calls.append("create_form_view")
        return {"ok": True, "view": {"view_id": "form", "view_type": "form"}}


class SetupBitableTests(unittest.TestCase):
    def test_validate_bitable_is_read_only(self):
        client = FakeBitableClient()

        result = setup_bitable.validate_bitable(client)

        self.assertEqual(result["mode"], "validate")
        self.assertIn("项目", result["missing_fields"])
        self.assertIn("来源二级分类", result["missing_fields"])
        self.assertEqual(client.calls, ["list_fields", "list_views"])

    def test_apply_without_prune_does_not_delete_extra_fields(self):
        with patch.object(setup_bitable, "FeishuBitableClient", return_value=FakeBitableClient()):
            result = setup_bitable.setup_bitable(apply_changes=True, prune_extra=False)

        self.assertEqual(result["mode"], "apply")
        self.assertTrue(result["cleanup"]["skipped"])


if __name__ == "__main__":
    unittest.main()
