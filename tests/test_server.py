import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_homepage_is_available(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("焦点堆叠批量处理工具".encode("utf-8"), response.data)
        response.close()

    def test_scan_rejects_invalid_group_size(self):
        response = self.client.post(
            "/api/scan", json={"folder": "missing", "group_size": 0}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("group_size", response.get_json()["error"])

    def test_scan_groups_local_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(2):
                Image.fromarray(np.full((8, 8, 3), index * 50, dtype=np.uint8)).save(
                    root / f"image_{index}.jpg"
                )
            with patch("server.group_images_by_sequence", return_value=[
                [str(root / "image_0.jpg"), str(root / "image_1.jpg")]
            ]):
                response = self.client.post(
                    "/api/scan", json={"folder": str(root), "group_size": 10}
                )
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertEqual(body["total_images"], 2)
            self.assertEqual(body["total_groups"], 1)

    def test_process_rejects_unknown_output_format(self):
        with tempfile.TemporaryDirectory() as directory:
            response = self.client.post(
                "/api/process",
                json={"input_folder": directory, "output_format": "exe"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("输出格式", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
