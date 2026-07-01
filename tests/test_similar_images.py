import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_DIR / "python"
sys.path.insert(0, str(PYTHON_DIR))

import similar_images


def write_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 80), color).save(path)


class SimilarImagesTests(unittest.TestCase):
    def test_default_scan_checks_only_compressed_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "image_compressor" / "images_raw"
            compressed = root / "image_compressor" / "images_compressed"
            runtime = root / "runtime"
            write_image(raw / "source.png", (255, 0, 0))
            write_image(compressed / "source_copy.png", (255, 0, 0))
            write_image(compressed / "source_copy_2.png", (255, 0, 0))

            with patch.object(similar_images, "PROJECT_DIR", root), patch.object(
                similar_images, "IMAGES_COMPRESSED_DIR", compressed
            ), patch.object(
                similar_images, "RUNTIME_DIR", runtime
            ), patch.object(similar_images, "REPORT_JSON_PATH", runtime / "similar_images_report.json"), patch.object(
                similar_images, "REPORT_CSV_PATH", runtime / "similar_images_report.csv"
            ):
                summary = similar_images.scan_similar_images()

            self.assertEqual(summary["imageCount"], 2)
            self.assertEqual(summary["scanScope"], "compressed")
            self.assertEqual(summary["directory"], "image_compressor/images_compressed")
            self.assertGreaterEqual(summary["pairCount"], 1)

    def test_delete_compressed_image_rejects_other_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "image_compressor" / "images_raw"
            compressed = root / "image_compressor" / "images_compressed"
            runtime = root / "runtime"
            write_image(raw / "source.png", (255, 0, 0))

            with patch.object(similar_images, "PROJECT_DIR", root), patch.object(
                similar_images, "IMAGES_COMPRESSED_DIR", compressed
            ), patch.object(
                similar_images, "RUNTIME_DIR", runtime
            ), patch.object(similar_images, "REPORT_JSON_PATH", runtime / "similar_images_report.json"), patch.object(
                similar_images, "REPORT_CSV_PATH", runtime / "similar_images_report.csv"
            ):
                result = similar_images.delete_compressed_image("image_compressor/images_raw/source.png")

            self.assertFalse(result["ok"])
            self.assertTrue((raw / "source.png").is_file())

    def test_delete_compressed_image_deletes_and_refreshes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compressed = root / "image_compressor" / "images_compressed"
            runtime = root / "runtime"
            write_image(compressed / "source.png", (255, 0, 0))

            with patch.object(similar_images, "PROJECT_DIR", root), patch.object(
                similar_images, "IMAGES_COMPRESSED_DIR", compressed
            ), patch.object(
                similar_images, "RUNTIME_DIR", runtime
            ), patch.object(similar_images, "REPORT_JSON_PATH", runtime / "similar_images_report.json"), patch.object(
                similar_images, "REPORT_CSV_PATH", runtime / "similar_images_report.csv"
            ):
                result = similar_images.delete_compressed_image("image_compressor/images_compressed/source.png")

            self.assertTrue(result["ok"])
            self.assertFalse((compressed / "source.png").exists())
            self.assertEqual(result["similarity"]["imageCount"], 0)


if __name__ == "__main__":
    unittest.main()
