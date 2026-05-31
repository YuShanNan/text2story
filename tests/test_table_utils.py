import csv
import os
import tempfile
import unittest

import utils.table_utils as table_utils


class LoadStoryboardTableTest(unittest.TestCase):
    def test_loads_storyboard_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "storyboard_table.csv")

            with open(path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一"})
                writer.writerow({"scene_id": "2", "storyboard_text": "分镜二"})

            rows = table_utils.load_storyboard_table(path)

        self.assertEqual(2, len(rows))
        self.assertEqual("分镜一", rows[0]["storyboard_text"])

    def test_raises_error_when_scene_id_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "storyboard_table.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一"})
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一-重复"})

            with self.assertRaisesRegex(ValueError, "scene_id.*1.*重复"):
                table_utils.load_storyboard_table(path)

    def test_writes_optimized_prompt_table_without_raw_prompt_column(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "optimized.csv")
            table_utils.write_optimized_prompt_table(
                output_path,
                [
                    {
                        "scene_id": "1",
                        "storyboard_text": "分镜一",
                        "optimized_image_prompt": "优化后一",
                        "notes_cn": "备注一",
                    }
                ],
            )

            with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertNotIn("raw_image_prompt", rows[0])
        self.assertEqual("优化后一", rows[0]["optimized_image_prompt"])


if __name__ == "__main__":
    unittest.main()
