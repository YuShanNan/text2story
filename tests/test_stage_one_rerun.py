import os
import tempfile
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="urllib3 .* doesn't match a supported version!",
)

from core.interactive import run_pipeline_for_file


class StageOneRerunTest(unittest.TestCase):
    def _make_srt(self, path: str) -> str:
        content = (
            "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n第二句\n"
        )
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
        return content

    def test_run_pipeline_for_file_single_pass_produces_all_outputs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = os.path.join(tmp_dir, "input")
            output_dir = os.path.join(tmp_dir, "output")
            os.makedirs(input_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            input_path = os.path.join(input_dir, "demo.srt")
            srt_content = self._make_srt(input_path)

            bundle = SimpleNamespace(client=object(), model="test-model")

            with (
                patch("core.interactive.Config.INPUT_DIR", input_dir),
                patch("core.interactive.run_srt_correction_with_progress", return_value=srt_content) as correct,
                patch(
                    "core.interactive.run_storyboard_generation_with_progress",
                    return_value="1. 分镜结果",
                ) as storyboard,
            ):
                results = run_pipeline_for_file(
                    bundle=bundle,
                    srt_path=input_path,
                    correction_prompt="default",
                    storyboard_prompt="default",
                    file_index=1,
                    total_files=1,
                    unattended=True,
                    output_dir=output_dir,
                )

            self.assertEqual(1, correct.call_count)
            self.assertEqual(1, storyboard.call_count)
            storyboard_path = os.path.join(output_dir, "demo_storyboard.txt")
            with open(storyboard_path, "r", encoding="utf-8-sig") as file:
                self.assertEqual("1. 分镜结果", file.read().strip())
            self.assertEqual(
                [
                    ("SRT 修正", os.path.join(output_dir, "demo_corrected.srt")),
                    ("文案提取", os.path.join(output_dir, "demo_corrected.txt")),
                    ("分镜脚本", storyboard_path),
                ],
                results,
            )

    def test_run_pipeline_for_file_propagates_storyboard_error_immediately(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_dir = os.path.join(tmp_dir, "input")
            output_dir = os.path.join(tmp_dir, "output")
            os.makedirs(input_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            input_path = os.path.join(input_dir, "demo.srt")
            srt_content = self._make_srt(input_path)

            bundle = SimpleNamespace(client=object(), model="test-model")

            with (
                patch("core.interactive.Config.INPUT_DIR", input_dir),
                patch("core.interactive.run_srt_correction_with_progress", return_value=srt_content) as correct,
                patch(
                    "core.interactive.run_storyboard_generation_with_progress",
                    side_effect=RuntimeError("分镜生成失败"),
                ) as storyboard,
            ):
                with self.assertRaisesRegex(RuntimeError, "分镜生成失败"):
                    run_pipeline_for_file(
                        bundle=bundle,
                        srt_path=input_path,
                        correction_prompt="default",
                        storyboard_prompt="default",
                        file_index=1,
                        total_files=1,
                        unattended=True,
                        output_dir=output_dir,
                    )

            self.assertEqual(1, correct.call_count)
            self.assertEqual(1, storyboard.call_count)


if __name__ == "__main__":
    unittest.main()
