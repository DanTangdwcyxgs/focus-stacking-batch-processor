import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from focus_stack_engine import process_batch


class EngineSmokeTests(unittest.TestCase):
    def test_two_images_produce_one_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()

            y, x = np.indices((160, 220))
            pattern = (((x // 8) + (y // 8)) % 2 * 210 + 25).astype(np.uint8)
            base = cv2.cvtColor(pattern, cv2.COLOR_GRAY2BGR)
            blurred = cv2.GaussianBlur(base, (0, 0), 5)

            first = blurred.copy()
            first[:, :110] = base[:, :110]
            second = blurred.copy()
            second[:, 110:] = base[:, 110:]
            cv2.imwrite(str(source / "product_001.jpg"), first)
            cv2.imwrite(str(source / "product_002.jpg"), second)

            with patch(
                "focus_stack_engine.get_image_timestamp",
                side_effect=lambda value: 1.0 if value.endswith("001.jpg") else 1.1,
            ):
                result = process_batch(
                    str(source),
                    str(output),
                    group_size=2,
                    output_format="jpg",
                    quality=90,
                    lens_correction=False,
                    ca_correction=False,
                    max_workers=1,
                )

            self.assertEqual(result["success"], 1)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(len(result["output_files"]), 1)
            self.assertTrue((output / result["output_files"][0]["output"]).is_file())


if __name__ == "__main__":
    unittest.main()
