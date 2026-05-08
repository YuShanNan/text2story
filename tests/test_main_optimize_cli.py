import os
import csv
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


class FakePromptClient:
    def __init__(self):
        self.call_count = 0

    def chat_multi_turn(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
        thinking_enabled: bool = None,
    ) -> str:
        self.call_count += 1
        return f"优化后提示词{self.call_count}"

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


class FakeVideoPromptClient:
    def __init__(self):
        self.call_count = 0

    def chat_multi_turn(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
        thinking_enabled: bool = None,
    ) -> str:
        self.call_count += 1
        return f"视频提示词{self.call_count}"

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


class OptimizeCliTest(unittest.TestCase):
    def test_txt_mode_writes_optimized_prompt_txt(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            os.makedirs(os.path.join(prompts_dir, "image_prompt_optimize"), exist_ok=True)
            with open(
                os.path.join(prompts_dir, "image_prompt_optimize", "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是提示词优化器")

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            output_path = os.path.join(tmp_dir, "optimized.txt")

            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n原始提示词二\n")

            runner = CliRunner()
            fake_bundle = SimpleNamespace(
                client=FakePromptClient(),
                model="test-model",
            )

            with (
                patch("main.get_client_bundle", return_value=fake_bundle),
                patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
            ):
                result = runner.invoke(
                    main.cli,
                    [
                        "optimize-image-prompts",
                        "--storyboard",
                        storyboard_path,
                        "--raw-prompts",
                        raw_prompt_path,
                        "--batch-size",
                        "1",
                        "--output",
                        output_path,
                    ],
                )

            self.assertEqual(0, result.exit_code, result.output)

            with open(output_path, "r", encoding="utf-8-sig") as file:
                output_text = file.read().strip()

        self.assertEqual(
            "优化后提示词3\n优化后提示词4",
            output_text,
        )

    def test_csv_mode_writes_optimized_prompt_csv(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            os.makedirs(os.path.join(prompts_dir, "image_prompt_optimize"), exist_ok=True)
            with open(
                os.path.join(prompts_dir, "image_prompt_optimize", "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是提示词优化器")

            storyboard_table_path = os.path.join(tmp_dir, "storyboard_table.csv")
            image_prompt_table_path = os.path.join(tmp_dir, "image_prompt_table.csv")
            output_path = os.path.join(tmp_dir, "optimized.csv")

            with open(
                storyboard_table_path, "w", encoding="utf-8-sig", newline=""
            ) as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "第一段分镜"})

            with open(
                image_prompt_table_path, "w", encoding="utf-8-sig", newline=""
            ) as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "raw_image_prompt"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "raw_image_prompt": "原始提示词一"})

            runner = CliRunner()
            fake_bundle = SimpleNamespace(
                client=FakePromptClient(),
                model="test-model",
            )

            with (
                patch("main.get_client_bundle", return_value=fake_bundle),
                patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
            ):
                result = runner.invoke(
                    main.cli,
                    [
                        "optimize-image-prompts",
                        "--storyboard-table",
                        storyboard_table_path,
                        "--image-prompt-table",
                        image_prompt_table_path,
                        "--batch-size",
                        "1",
                        "--output",
                        output_path,
                    ],
                )

            self.assertEqual(0, result.exit_code, result.output)

            with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "第一段分镜",
                    "raw_image_prompt": "原始提示词一",
                    "optimized_image_prompt": "优化后提示词3",
                    "notes_cn": "",
                }
            ],
            rows,
        )

    def test_txt_mode_writes_video_prompt_txt_from_optimized_image_prompts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            os.makedirs(
                os.path.join(prompts_dir, "video_prompt_from_image"), exist_ok=True
            )
            with open(
                os.path.join(
                    prompts_dir,
                    "video_prompt_from_image",
                    "2026.4.13-带商业运镜测试简化版2(1).txt",
                ),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是视频提示词生成器")

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            optimized_image_prompt_path = os.path.join(
                tmp_dir, "optimized_image_prompts.txt"
            )
            output_path = os.path.join(tmp_dir, "video_prompts.txt")

            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            with open(optimized_image_prompt_path, "w", encoding="utf-8") as file:
                file.write("优化后生图提示词一\n优化后生图提示词二\n")

            runner = CliRunner()
            fake_bundle = SimpleNamespace(
                client=FakeVideoPromptClient(),
                model="test-model",
            )

            with (
                patch("main.get_client_bundle", return_value=fake_bundle),
                patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
            ):
                result = runner.invoke(
                    main.cli,
                    [
                        "generate-video-prompts",
                        "--storyboard",
                        storyboard_path,
                        "--optimized-image-prompts",
                        optimized_image_prompt_path,
                        "--prompt",
                        "2026.4.13-带商业运镜测试简化版2(1)",
                        "--batch-size",
                        "1",
                        "--output",
                        output_path,
                    ],
                )

            self.assertEqual(0, result.exit_code, result.output)

            with open(output_path, "r", encoding="utf-8-sig") as file:
                output_text = file.read().strip()

        self.assertEqual("视频提示词2\n视频提示词3", output_text)

    def test_csv_mode_writes_video_prompt_csv_from_optimized_image_prompts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            os.makedirs(
                os.path.join(prompts_dir, "video_prompt_from_image"), exist_ok=True
            )
            with open(
                os.path.join(
                    prompts_dir,
                    "video_prompt_from_image",
                    "2026.4.13-带商业运镜测试简化版2(1).txt",
                ),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是视频提示词生成器")

            storyboard_table_path = os.path.join(tmp_dir, "storyboard_table.csv")
            image_prompt_table_path = os.path.join(tmp_dir, "image_prompt_table.csv")
            output_path = os.path.join(tmp_dir, "video_prompts.csv")

            with open(
                storyboard_table_path, "w", encoding="utf-8-sig", newline=""
            ) as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "第一段分镜"})

            with open(
                image_prompt_table_path, "w", encoding="utf-8-sig", newline=""
            ) as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "optimized_image_prompt"]
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "scene_id": "1",
                        "optimized_image_prompt": "优化后生图提示词一",
                    }
                )

            runner = CliRunner()
            fake_bundle = SimpleNamespace(
                client=FakeVideoPromptClient(),
                model="test-model",
            )

            with (
                patch("main.get_client_bundle", return_value=fake_bundle),
                patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
            ):
                result = runner.invoke(
                    main.cli,
                    [
                        "generate-video-prompts",
                        "--storyboard-table",
                        storyboard_table_path,
                        "--image-prompt-table",
                        image_prompt_table_path,
                        "--prompt",
                        "2026.4.13-带商业运镜测试简化版2(1)",
                        "--batch-size",
                        "1",
                        "--output",
                        output_path,
                    ],
                )

            self.assertEqual(0, result.exit_code, result.output)

            with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "第一段分镜",
                    "optimized_image_prompt": "优化后生图提示词一",
                    "video_prompt": "视频提示词2",
                    "notes_cn": "",
                }
            ],
            rows,
        )


if __name__ == "__main__":
    unittest.main()
