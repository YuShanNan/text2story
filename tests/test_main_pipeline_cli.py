import os
import tempfile
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

warnings.filterwarnings(
    "ignore",
    message="urllib3 .* doesn't match a supported version!",
)

import main



class StageAwareFakeClient:
    def __init__(self):
        self.optimize_count = 0
        self.video_count = 0

    def chat_multi_turn(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
        thinking_enabled: bool = None,
    ) -> str:
        system_prompt = messages[0]["content"] if messages else ""
        if not system_prompt.strip():
            return "pong"
        if system_prompt == "SRT":
            return messages[-1]["content"] if messages[-1]["role"] == "user" else ""
        if system_prompt == "STORYBOARD":
            return "1. 测试分镜"
        if system_prompt == "OPTIMIZE":
            self.optimize_count += 1
            return f"优化结果{self.optimize_count}"
        if system_prompt == "VIDEO":
            self.video_count += 1
            return f"视频结果{self.video_count}"
        raise AssertionError(f"unexpected system prompt: {system_prompt}")

    def chat(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
        thinking_enabled: bool = None,
    ) -> str:
        return self.chat_multi_turn(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            fallback_model=fallback_model,
        )


class MainPipelineCliTest(unittest.TestCase):
    def test_run_command_stops_after_stage_one_storyboard(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            input_dir = os.path.join(tmp_dir, "input")
            output_dir = os.path.join(tmp_dir, "stage_one_output")
            os.makedirs(os.path.join(prompts_dir, "srt_correction"), exist_ok=True)
            os.makedirs(os.path.join(prompts_dir, "storyboard"), exist_ok=True)
            os.makedirs(input_dir, exist_ok=True)

            with open(
                os.path.join(prompts_dir, "srt_correction", "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("SRT")
            with open(
                os.path.join(prompts_dir, "storyboard", "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("STORYBOARD")

            input_path = os.path.join(input_dir, "demo.srt")
            with open(input_path, "w", encoding="utf-8") as file:
                file.write(
                    "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n"
                    "2\n00:00:01,000 --> 00:00:02,000\n第二句\n"
                )

            runner = CliRunner()
            fake_bundle = SimpleNamespace(
                client=StageAwareFakeClient(),
                model="test-model",
            )

            with (
                patch("main.get_client_bundle", return_value=fake_bundle),
                patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
                patch.object(main.Config, "INPUT_DIR", input_dir),
            ):
                result = runner.invoke(
                    main.cli,
                    [
                        "run",
                        "--input",
                        input_path,
                        "--output-dir",
                        output_dir,
                    ],
                )

            self.assertEqual(0, result.exit_code, result.output)
            self.assertTrue(os.path.exists(os.path.join(output_dir, "demo_corrected.srt")))
            self.assertTrue(os.path.exists(os.path.join(output_dir, "demo_corrected.txt")))
            self.assertTrue(os.path.exists(os.path.join(output_dir, "demo_storyboard.txt")))
            self.assertFalse(os.path.exists(os.path.join(output_dir, "demo_image_prompts.txt")))
            self.assertFalse(os.path.exists(os.path.join(output_dir, "demo_video_prompts.txt")))

    def test_continue_run_executes_stage_two_outputs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            output_dir = os.path.join(tmp_dir, "stage_two_output")
            storyboard_dir = os.path.join(tmp_dir, "demo")
            os.makedirs(os.path.join(prompts_dir, "image_prompt_optimize"), exist_ok=True)
            os.makedirs(os.path.join(prompts_dir, "video_prompt_from_image"), exist_ok=True)
            os.makedirs(storyboard_dir, exist_ok=True)

            with open(
                os.path.join(prompts_dir, "image_prompt_optimize", "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("OPTIMIZE")
            with open(
                os.path.join(prompts_dir, "video_prompt_from_image", "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("VIDEO")

            storyboard_path = os.path.join(storyboard_dir, "demo_storyboard.txt")
            raw_prompt_path = os.path.join(storyboard_dir, "画面提示词_2026-4-17.txt")

            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n2. 第二段分镜\n")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n原始提示词二\n")

            runner = CliRunner()
            fake_bundle = SimpleNamespace(
                client=StageAwareFakeClient(),
                model="test-model",
            )

            with (
                patch("main.get_client_bundle", return_value=fake_bundle),
                patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
            ):
                result = runner.invoke(
                    main.cli,
                    [
                        "continue-run",
                        "--storyboard",
                        storyboard_path,
                        "--raw-prompts",
                        raw_prompt_path,
                        "--output-dir",
                        output_dir,
                        "--batch-size",
                        "1",
                    ],
                )

            self.assertEqual(0, result.exit_code, result.output)

            optimized_path = os.path.join(output_dir, "demo_optimized_image_prompts.txt")
            video_path = os.path.join(output_dir, "demo_video_prompts.txt")
            self.assertTrue(os.path.exists(optimized_path))
            self.assertTrue(os.path.exists(video_path))

            with open(optimized_path, "r", encoding="utf-8-sig") as file:
                optimized_text = file.read().strip()
            with open(video_path, "r", encoding="utf-8-sig") as file:
                video_text = file.read().strip()

            self.assertEqual(
                "优化结果1\n优化结果2",
                optimized_text,
            )
            self.assertEqual("视频结果1\n视频结果2", video_text)

    def test_storyboard_command_propagates_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "demo.txt")
            with open(input_path, "w", encoding="utf-8") as file:
                file.write("第一行\n第二行\n第三行\n")

            runner = CliRunner()
            fake_bundle = SimpleNamespace(
                client=StageAwareFakeClient(),
                model="test-model",
            )

            with (
                patch("main.get_client_bundle", return_value=fake_bundle),
                patch(
                    "main.run_storyboard_generation_with_progress",
                    side_effect=RuntimeError("分镜生成失败"),
                ),
            ):
                result = runner.invoke(
                    main.cli,
                    [
                        "storyboard",
                        "--input",
                        input_path,
                    ],
                )

            self.assertNotEqual(0, result.exit_code)


if __name__ == "__main__":
    unittest.main()
