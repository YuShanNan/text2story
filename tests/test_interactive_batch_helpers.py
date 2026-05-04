import csv
import unittest
import warnings
from unittest.mock import patch

from rich.console import Console

warnings.filterwarnings(
    "ignore",
    message="urllib3 .* doesn't match a supported version!",
)

from core.interactive import (
    write_txt_optimization_batches,
    write_csv_optimization_batches,
    write_txt_video_prompt_batches,
    write_csv_video_prompt_batches,
)


class FakeClient:
    def chat(self, **kwargs):
        return "ok"

class FakeBatchOptimizer:
    def __init__(self):
        self.client = FakeClient()
        self.model = "test-model"

    def optimize_files_batch(
        self,
        storyboard_path=None,
        raw_prompt_path=None,
        rows=None,
        prompt_name="default",
        rows_per_batch=50,
    ):
        total = len(rows) if rows else 2
        yield {"completed": total, "total": total, "batch_index": 1, "batch_total": 1}
        yield "优化后提示词1\n优化后提示词2"


class InteractiveBatchHelpersTest(unittest.TestCase):
    def test_write_txt_optimization_batches_rewrites_after_each_row_and_prints_timing(self):
        console = Console(record=True)
        with patch("core.interactive.write_file") as write_file_mock, \
             patch("core.interactive.read_non_empty_lines", return_value=["line1", "line2"]):
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
        self.assertEqual(1, write_file_mock.call_count)
        self.assertEqual("优化后提示词1\n优化后提示词2", write_file_mock.call_args_list[0].args[1])
        self.assertEqual(False, write_file_mock.call_args_list[0].kwargs.get("log_saved"))
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
        self.assertEqual(1, write_table_mock.call_count)
        self.assertEqual([2], snapshot_lengths)
        output = console.export_text()
        self.assertNotIn("第 1/1 批完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)

    def test_write_txt_video_prompt_batches_rewrites_after_each_row_and_prints_timing(self):
        class FakeBatchGenerator:
            client = FakeClient()
            model = "test-model"

            def generate_files_batch(self, **kwargs):
                yield {"completed": 2, "total": 2, "batch_index": 1, "batch_total": 1}
                yield "视频提示词1\n视频提示词2"

        console = Console(record=True)
        with patch("core.interactive.write_file") as write_file_mock, \
             patch("core.interactive.read_non_empty_lines", return_value=["line1", "line2"]):
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
        self.assertEqual(1, write_file_mock.call_count)
        self.assertEqual("视频提示词1\n视频提示词2", write_file_mock.call_args_list[0].args[1])
        self.assertEqual(False, write_file_mock.call_args_list[0].kwargs.get("log_saved"))
        output = console.export_text()
        self.assertNotIn("第 1/1 批完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)

    def test_write_csv_video_prompt_batches_rewrites_after_each_row_and_prints_timing(self):
        class FakeBatchGenerator:
            client = FakeClient()
            model = "test-model"

            def generate_files_batch(self, **kwargs):
                yield {"completed": 2, "total": 2, "batch_index": 1, "batch_total": 1}
                yield "视频提示词1\n视频提示词2"

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
        self.assertEqual(1, write_table_mock.call_count)
        self.assertEqual([2], snapshot_lengths)
        output = console.export_text()
        self.assertNotIn("第 1/1 批完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)


if __name__ == "__main__":
    unittest.main()
