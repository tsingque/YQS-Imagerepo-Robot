import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import feishu_knowledge_base as kb


class FakeKnowledgeClient:
    def __init__(self) -> None:
        self.space_name = "YQS Test Space"
        self.space_id = "space_1"
        self.ensure_space_calls = 0
        self.folder_calls: list[tuple[str, ...]] = []
        self.upload_calls: list[tuple[str, Path]] = []

    def ensure_space(self) -> dict:
        self.ensure_space_calls += 1
        return {"space_id": self.space_id, "name": self.space_name, "created": True}

    def ensure_folder_path(self, space_id: str, folder_parts: tuple[str, ...]) -> dict:
        self.folder_calls.append(folder_parts)
        return {
            "node_token": "node_" + "_".join(folder_parts),
            "nodes": [{"title": part, "node_token": f"node_{part}", "created": True} for part in folder_parts],
        }

    def upload_file(self, parent_node_token: str, image_path: Path) -> dict:
        self.upload_calls.append((parent_node_token, image_path))
        return {"file_token": "file_" + image_path.stem}


class FeishuKnowledgeBaseTests(unittest.TestCase):
    def test_iter_case_material_images_preserves_folder_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "项目A" / "二级分类" / "湖面.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"jpg")
            (root / "项目A" / ".DS_Store").write_bytes(b"ignored")

            images = kb.iter_case_material_images(root)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].relative_path, "项目A/二级分类/湖面.jpg")
        self.assertEqual(images[0].folder_parts, ("项目A", "二级分类"))

    def test_sync_uploads_images_to_matching_knowledge_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case_materials"
            state = Path(tmp) / "state.json"
            first = root / "项目A" / "图1.png"
            second = root / "项目B" / "图2.jpg"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            client = FakeKnowledgeClient()

            summary = kb.sync_case_materials_to_knowledge_base(root=root, state_path=state, client=client, force_upload=False)

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["uploaded"], 2)
            self.assertEqual(summary["skipped"], 0)
            self.assertEqual(client.ensure_space_calls, 1)
            self.assertEqual(client.folder_calls, [("项目A",), ("项目B",)])
            self.assertEqual([path.name for _, path in client.upload_calls], ["图1.png", "图2.jpg"])
            self.assertTrue(state.exists())

    def test_sync_skips_unchanged_files_from_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case_materials"
            state = Path(tmp) / "state.json"
            image = root / "项目A" / "图1.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"same")
            client = FakeKnowledgeClient()

            first = kb.sync_case_materials_to_knowledge_base(root=root, state_path=state, client=client, force_upload=False)
            second = kb.sync_case_materials_to_knowledge_base(root=root, state_path=state, client=client, force_upload=False)

            self.assertEqual(first["uploaded"], 1)
            self.assertEqual(second["uploaded"], 0)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(len(client.upload_calls), 1)

    def test_ensure_space_creates_missing_space_with_user_token(self):
        responses = [
            {"code": 0, "data": {"items": [], "has_more": False}},
            {"code": 0, "data": {"space": {"space_id": "space_new", "name": "YQS Test Space"}}},
        ]

        with patch.object(kb, "_env", return_value=""):
            client = kb.FeishuKnowledgeBaseClient(
                space_name="YQS Test Space",
                user_access_token="user-token",
            )
        with patch.object(client, "request", side_effect=responses) as request:
            space = client.ensure_space()

        self.assertEqual(space["space_id"], "space_new")
        self.assertTrue(space["created"])
        self.assertEqual(request.call_args_list[0].args[:2], ("GET", "/wiki/v2/spaces"))
        self.assertEqual(request.call_args_list[1].args[:2], ("POST", "/wiki/v2/spaces"))
        self.assertTrue(request.call_args_list[1].kwargs["require_user"])


if __name__ == "__main__":
    unittest.main()
