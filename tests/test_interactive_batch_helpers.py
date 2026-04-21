import csv
import unittest
import warnings
from unittest.mock import patch

from rich.console import Console

warnings.filterwarnings(
    "ignore",
    message="urllib3 .* or chardet.* doesn't match a supported version!",
)

from core.interactive import (
    write_txt_optimization_batches,
    write_csv_optimization_batches,
    write_txt_video_prompt_batches,
    write_csv_video_prompt_batches,
)


class FakeBatchOptimizer:
    def iter_optimized_file_progress(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
        prompt_name: str = "default",
        batch_size: int = 10,
    ):
        yield {
            "optimized_line": "优化后提示词1",
            "row_index": 1,
            "row_total": 2,
            "batch_index": 1,
            "batch_total": 1,
            "batch_row_index": 1,
            "batch_row_total": 2,
            "batch_elapsed_seconds": 1.5,
            "total_elapsed_seconds": 1.5,
            "batch_completed": False,
        }
        yield {
            "optimized_line": "优化后提示词2",
            "row_index": 2,
            "row_total": 2,
            "batch_index": 1,
            "batch_total": 1,
            "batch_row_index": 2,
            "batch_row_total": 2,
            "batch_elapsed_seconds": 3.0,
            "total_elapsed_seconds": 3.0,
            "batch_completed": True,
        }

    def iter_optimized_row_progress(
        self,
        rows,
        prompt_name: str = "default",
        batch_size: int = 10,
    ):
        yield {
            "optimized_row": {
                "scene_id": "1",
                "storyboard_text": "第一段分镜",
                "raw_image_prompt": "原始提示词一",
                "optimized_image_prompt": "优化后提示词1",
                "notes_cn": "",
            },
            "row_index": 1,
            "row_total": 2,
            "batch_index": 1,
            "batch_total": 1,
            "batch_row_index": 1,
            "batch_row_total": 2,
            "batch_elapsed_seconds": 1.5,
            "total_elapsed_seconds": 1.5,
            "batch_completed": False,
        }
        yield {
            "optimized_row": {
                "scene_id": "2",
                "storyboard_text": "第二段分镜",
                "raw_image_prompt": "原始提示词二",
                "optimized_image_prompt": "优化后提示词2",
                "notes_cn": "",
            },
            "row_index": 2,
            "row_total": 2,
            "batch_index": 1,
            "batch_total": 1,
            "batch_row_index": 2,
            "batch_row_total": 2,
            "batch_elapsed_seconds": 3.0,
            "total_elapsed_seconds": 3.0,
            "batch_completed": True,
        }


class InteractiveBatchHelpersTest(unittest.TestCase):
    def test_write_txt_optimization_batches_rewrites_after_each_row_and_prints_timing(self):
        console = Console(record=True)
        with patch("core.interactive.write_file") as write_file_mock:
            final_text = write_txt_optimization_batches(
                optimizer=FakeBatchOptimizer(),
                storyboard_path="storyboard.txt",
                raw_prompt_path="raw.txt",
                prompt_name="default",
                output_path="optimized.txt",
                batch_size=1,
                console_obj=console,
            )

        self.assertEqual("优化后提示词1\n优化后提示词2", final_text)
        self.assertEqual(2, write_file_mock.call_count)
        self.assertEqual("优化后提示词1", write_file_mock.call_args_list[0].args[1])
        self.assertEqual("优化后提示词1\n优化后提示词2", write_file_mock.call_args_list[1].args[1])
        self.assertEqual(False, write_file_mock.call_args_list[0].kwargs.get("log_saved"))
        self.assertEqual(False, write_file_mock.call_args_list[1].kwargs.get("log_saved"))
        output = console.export_text()
        self.assertNotIn("第 1/1 批完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)

    def test_write_csv_optimization_batches_rewrites_after_each_row_and_prints_timing(self):
        console = Console(record=True)
        snapshot_lengths = []

        def capture_rows(_output_path, rows):
            snapshot_lengths.append(len(list(rows)))

        with patch(
            "core.interactive.write_optimized_prompt_table",
            side_effect=capture_rows,
        ) as write_table_mock:
            final_rows = write_csv_optimization_batches(
                optimizer=FakeBatchOptimizer(),
                rows=[
                    {"scene_id": "1", "storyboard_text": "第一段分镜", "raw_image_prompt": "原始提示词一"},
                    {"scene_id": "2", "storyboard_text": "第二段分镜", "raw_image_prompt": "原始提示词二"},
                ],
                prompt_name="default",
                output_path="optimized.csv",
                batch_size=1,
                console_obj=console,
            )

        self.assertEqual(2, len(final_rows))
        self.assertEqual(2, write_table_mock.call_count)
        self.assertEqual([1, 2], snapshot_lengths)
        output = console.export_text()
        self.assertNotIn("第 1/1 批完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)

    def test_write_txt_video_prompt_batches_rewrites_after_each_row_and_prints_timing(self):
        class FakeBatchGenerator:
            def iter_generate_file_progress(
                self,
                storyboard_path: str,
                optimized_image_prompt_path: str,
                prompt_name: str = "default",
                batch_size: int = 10,
            ):
                yield {
                    "video_line": "视频提示词1",
                    "row_index": 1,
                    "row_total": 2,
                    "batch_index": 1,
                    "batch_total": 1,
                    "batch_row_index": 1,
                    "batch_row_total": 2,
                    "batch_elapsed_seconds": 1.5,
                    "total_elapsed_seconds": 1.5,
                    "batch_completed": False,
                }
                yield {
                    "video_line": "视频提示词2",
                    "row_index": 2,
                    "row_total": 2,
                    "batch_index": 1,
                    "batch_total": 1,
                    "batch_row_index": 2,
                    "batch_row_total": 2,
                    "batch_elapsed_seconds": 3.0,
                    "total_elapsed_seconds": 3.0,
                    "batch_completed": True,
                }

        console = Console(record=True)
        with patch("core.interactive.write_file") as write_file_mock:
            final_text = write_txt_video_prompt_batches(
                generator=FakeBatchGenerator(),
                storyboard_path="storyboard.txt",
                optimized_image_prompt_path="optimized_image_prompts.txt",
                prompt_name="default",
                output_path="video_prompts.txt",
                batch_size=1,
                console_obj=console,
            )

        self.assertEqual("视频提示词1\n视频提示词2", final_text)
        self.assertEqual(2, write_file_mock.call_count)
        self.assertEqual("视频提示词1", write_file_mock.call_args_list[0].args[1])
        self.assertEqual("视频提示词1\n视频提示词2", write_file_mock.call_args_list[1].args[1])
        self.assertEqual(False, write_file_mock.call_args_list[0].kwargs.get("log_saved"))
        self.assertEqual(False, write_file_mock.call_args_list[1].kwargs.get("log_saved"))
        output = console.export_text()
        self.assertNotIn("第 1/1 批完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)

    def test_write_csv_video_prompt_batches_rewrites_after_each_row_and_prints_timing(self):
        class FakeBatchGenerator:
            def iter_generate_row_progress(
                self,
                rows,
                prompt_name: str = "default",
                batch_size: int = 10,
            ):
                yield {
                    "generated_row": {
                        "scene_id": "1",
                        "storyboard_text": "第一段分镜",
                        "optimized_image_prompt": "优化后生图提示词一",
                        "video_prompt": "视频提示词1",
                        "notes_cn": "",
                    },
                    "row_index": 1,
                    "row_total": 2,
                    "batch_index": 1,
                    "batch_total": 1,
                    "batch_row_index": 1,
                    "batch_row_total": 2,
                    "batch_elapsed_seconds": 1.5,
                    "total_elapsed_seconds": 1.5,
                    "batch_completed": False,
                }
                yield {
                    "generated_row": {
                        "scene_id": "2",
                        "storyboard_text": "第二段分镜",
                        "optimized_image_prompt": "优化后生图提示词二",
                        "video_prompt": "视频提示词2",
                        "notes_cn": "",
                    },
                    "row_index": 2,
                    "row_total": 2,
                    "batch_index": 1,
                    "batch_total": 1,
                    "batch_row_index": 2,
                    "batch_row_total": 2,
                    "batch_elapsed_seconds": 3.0,
                    "total_elapsed_seconds": 3.0,
                    "batch_completed": True,
                }

        console = Console(record=True)
        snapshot_lengths = []

        def capture_rows(_output_path, rows):
            snapshot_lengths.append(len(list(rows)))

        with patch(
            "core.interactive.write_video_prompt_table",
            side_effect=capture_rows,
        ) as write_table_mock:
            final_rows = write_csv_video_prompt_batches(
                generator=FakeBatchGenerator(),
                rows=[
                    {"scene_id": "1", "storyboard_text": "第一段分镜", "optimized_image_prompt": "优化后生图提示词一"},
                    {"scene_id": "2", "storyboard_text": "第二段分镜", "optimized_image_prompt": "优化后生图提示词二"},
                ],
                prompt_name="default",
                output_path="video_prompts.csv",
                batch_size=1,
                console_obj=console,
            )

        self.assertEqual(2, len(final_rows))
        self.assertEqual(2, write_table_mock.call_count)
        self.assertEqual([1, 2], snapshot_lengths)
        output = console.export_text()
        self.assertNotIn("第 1/1 批完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)


if __name__ == "__main__":
    unittest.main()
