import csv
import os
import tempfile
import unittest

import utils.table_utils as table_utils


class MergePromptTablesTest(unittest.TestCase):
    def test_merges_storyboard_and_prompt_rows_by_scene_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storyboard_path = os.path.join(tmp_dir, "storyboard_table.csv")
            image_prompt_path = os.path.join(tmp_dir, "image_prompt_table.csv")

            with open(storyboard_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一"})
                writer.writerow({"scene_id": "2", "storyboard_text": "分镜二"})

            with open(image_prompt_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "raw_image_prompt"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "raw_image_prompt": "提示词一"})
                writer.writerow({"scene_id": "2", "raw_image_prompt": "提示词二"})

            merged_rows = table_utils.merge_prompt_tables(
                storyboard_path, image_prompt_path
            )

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "分镜一",
                    "raw_image_prompt": "提示词一",
                },
                {
                    "scene_id": "2",
                    "storyboard_text": "分镜二",
                    "raw_image_prompt": "提示词二",
                },
            ],
            merged_rows,
        )

    def test_raises_error_when_scene_id_is_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storyboard_path = os.path.join(tmp_dir, "storyboard_table.csv")
            image_prompt_path = os.path.join(tmp_dir, "image_prompt_table.csv")

            with open(storyboard_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一"})

            with open(image_prompt_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "raw_image_prompt"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "raw_image_prompt": "提示词一"})
                writer.writerow({"scene_id": "1", "raw_image_prompt": "提示词一-重复"})

            with self.assertRaisesRegex(ValueError, "scene_id.*1.*重复"):
                table_utils.merge_prompt_tables(storyboard_path, image_prompt_path)

    def test_raises_error_when_tables_cannot_be_matched_by_scene_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storyboard_path = os.path.join(tmp_dir, "storyboard_table.csv")
            image_prompt_path = os.path.join(tmp_dir, "image_prompt_table.csv")

            with open(storyboard_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一"})
                writer.writerow({"scene_id": "2", "storyboard_text": "分镜二"})

            with open(image_prompt_path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "raw_image_prompt"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "raw_image_prompt": "提示词一"})

            with self.assertRaisesRegex(ValueError, "scene_id.*2.*缺失"):
                table_utils.merge_prompt_tables(storyboard_path, image_prompt_path)

    def test_writes_optimized_prompt_table_as_csv(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "optimized_image_prompt_table.csv")

            table_utils.write_optimized_prompt_table(
                output_path,
                [
                    {
                        "scene_id": "1",
                        "storyboard_text": "分镜一",
                        "raw_image_prompt": "提示词一",
                        "optimized_image_prompt": "优化后一",
                        "notes_cn": "备注一",
                    }
                ],
            )

            with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "分镜一",
                    "raw_image_prompt": "提示词一",
                    "optimized_image_prompt": "优化后一",
                    "notes_cn": "备注一",
                }
            ],
            rows,
        )


if __name__ == "__main__":
    unittest.main()
