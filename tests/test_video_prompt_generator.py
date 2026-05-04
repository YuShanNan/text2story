import os
import tempfile
import unittest

from core.video_prompt_generator import VideoPromptGenerator


class FakeVideoClient:
    def __init__(self):
        self.calls = []

    def chat_multi_turn(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
        thinking_enabled: bool = None,
    ) -> str:
        system_prompt = ""
        user_content = ""
        if messages and messages[0]["role"] == "system":
            system_prompt = messages[0]["content"]
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_content = msg["content"]
                break
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "messages": list(messages),
                "temperature": temperature,
                "fallback_model": fallback_model,
            }
        )
        return f"视频提示词{len(self.calls)}"

    def chat(self, **kwargs):
        return self.chat_multi_turn(**kwargs)


class VideoPromptGeneratorTest(unittest.TestCase):
    def _make_prompts_dir(self, tmp_dir: str) -> str:
        prompts_dir = os.path.join(tmp_dir, "prompts")
        prompt_category_dir = os.path.join(prompts_dir, "video_prompt_from_image")
        os.makedirs(prompt_category_dir, exist_ok=True)
        prompt_name = "2026.4.13-带商业运镜测试简化版2(1)"
        with open(
            os.path.join(prompt_category_dir, f"{prompt_name}.txt"),
            "w",
            encoding="utf-8",
        ) as file:
            file.write("你是视频提示词生成器")
        return prompts_dir

    def test_batch_mode_generates_all_rows_in_one_call(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            optimized_path = os.path.join(tmp_dir, "optimized_image_prompts.txt")
            with open(optimized_path, "w", encoding="utf-8") as file:
                file.write("优化后生图提示词一\n优化后生图提示词二\n")

            class TwoLineClient(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    super().chat_multi_turn(model, messages, **kwargs)
                    return "视频A\n视频B"

            client = TwoLineClient()
            generator = VideoPromptGenerator(
                client=client, model="test-model", prompts_dir=prompts_dir,
            )

            result = generator.generate_files_batch(
                storyboard_path=storyboard_path,
                optimized_image_prompt_path=optimized_path,
                prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
            )

        self.assertEqual("视频A\n视频B", result)
        self.assertEqual(1, len(client.calls))
        self.assertIn("第一段分镜", client.calls[0]["user_content"])
        self.assertIn("第二段分镜", client.calls[0]["user_content"])

    def test_builds_rows_from_same_txt_inputs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            optimized_path = os.path.join(tmp_dir, "optimized_image_prompts.txt")
            with open(optimized_path, "w", encoding="utf-8") as file:
                file.write("优化后生图提示词一\n优化后生图提示词二\n")

            generator = VideoPromptGenerator(
                client=FakeVideoClient(), model="test-model", prompts_dir=tmp_dir,
            )

            rows = generator.build_rows_from_files(
                storyboard_path=storyboard_path,
                optimized_image_prompt_path=optimized_path,
            )

        self.assertEqual(2, len(rows))
        self.assertEqual("1. 第一段分镜", rows[0]["storyboard_text"])
        self.assertEqual("优化后生图提示词一", rows[0]["optimized_image_prompt"])

    def test_normalizes_multiline_video_prompt_output_into_single_line(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            class MultiLineClient(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    super().chat_multi_turn(model, messages, **kwargs)
                    return "视频主体描述 镜头继续推进"

            generator = VideoPromptGenerator(
                client=MultiLineClient(), model="test-model", prompts_dir=prompts_dir,
            )

            result = generator.generate_files_batch(
                rows=[
                    {"scene_id": "1", "storyboard_text": "第一段分镜", "optimized_image_prompt": "优化后生图提示词一"}
                ],
                prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
            )

        self.assertEqual("视频主体描述 镜头继续推进", result)

    def test_batch_mode_passes_all_rows_in_first_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            class TwoLineClient(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    super().chat_multi_turn(model, messages, **kwargs)
                    return "视频A\n视频B"

            client = TwoLineClient()
            generator = VideoPromptGenerator(
                client=client, model="test-model", prompts_dir=prompts_dir,
            )

            generator.generate_files_batch(
                rows=[
                    {"scene_id": "1", "storyboard_text": "分镜A", "optimized_image_prompt": "提示词A"},
                    {"scene_id": "2", "storyboard_text": "分镜B", "optimized_image_prompt": "提示词B"},
                ],
                prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
            )

        self.assertEqual(1, len(client.calls))
        msgs = client.calls[0]["messages"]
        self.assertEqual(2, len(msgs))
        self.assertIn("分镜A", msgs[1]["content"])
        self.assertIn("分镜B", msgs[1]["content"])

    def test_batch_mode_multi_turn_for_large_input(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            class CountingClient(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    result = super().chat_multi_turn(model, messages, **kwargs)
                    n = len(self.calls)
                    return f"V{n}A\nV{n}B\nV{n}C"

            client = CountingClient()
            generator = VideoPromptGenerator(
                client=client, model="test-model", prompts_dir=prompts_dir,
            )

            result = generator.generate_files_batch(
                rows=[
                    {"scene_id": str(i), "storyboard_text": f"分镜{i}", "optimized_image_prompt": f"提示词{i}"}
                    for i in range(1, 8)
                ],
                prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
                rows_per_batch=3,
            )

        self.assertEqual(3, len(client.calls))
        lines = result.strip().split("\n")
        self.assertEqual(7, len(lines))

    def test_logs_batch_progress(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            class TwoLineClient(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    super().chat_multi_turn(model, messages, **kwargs)
                    return "VA\nVB"

            generator = VideoPromptGenerator(
                client=TwoLineClient(), model="test-model", prompts_dir=prompts_dir,
            )

            with self.assertLogs("core.video_prompt_generator", level="INFO") as captured:
                generator.generate_files_batch(
                    rows=[
                        {"scene_id": "1", "storyboard_text": "第一段", "optimized_image_prompt": "提示词一"},
                        {"scene_id": "2", "storyboard_text": "第二段", "optimized_image_prompt": "提示词二"},
                    ],
                    prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
                    rows_per_batch=50,
                )

        log_output = "\n".join(captured.output)
        self.assertIn("开始批量视频提示词生成", log_output)
        self.assertIn("批量视频提示词生成完成 (2 条)", log_output)


if __name__ == "__main__":
    unittest.main()
