import os
import tempfile
import unittest

try:
    from core.video_prompt_generator import VideoPromptGenerator
except ImportError:
    VideoPromptGenerator = None


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
            thinking_enabled=thinking_enabled,
        )


class MultilineVideoClient(FakeVideoClient):
    def chat_multi_turn(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
        thinking_enabled: bool = None,
    ) -> str:
        super().chat_multi_turn(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback_model=fallback_model,
            thinking_enabled=thinking_enabled,
        )
        return "视频主体描述\n镜头继续推进"


class VideoPromptGeneratorTest(unittest.TestCase):
    def _make_prompts_dir(self, tmp_dir: str) -> str:
        prompts_dir = os.path.join(tmp_dir, "prompts")
        prompt_category_dir = os.path.join(prompts_dir, "video_prompt_from_image")
        os.makedirs(prompt_category_dir, exist_ok=True)

        with open(
            os.path.join(
                prompt_category_dir, "2026.4.13-带商业运镜测试简化版2(1).txt"
            ),
            "w",
            encoding="utf-8",
        ) as file:
            file.write("你是视频提示词生成器")
        return prompts_dir

    def test_generates_video_prompts_from_storyboard_and_optimized_image_prompt_txt(self):
        self.assertIsNotNone(VideoPromptGenerator, "VideoPromptGenerator 尚未实现")

        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            optimized_image_prompt_path = os.path.join(
                tmp_dir, "optimized_image_prompts.txt"
            )
            with open(optimized_image_prompt_path, "w", encoding="utf-8") as file:
                file.write("优化后生图提示词一\n优化后生图提示词二\n")

            client = FakeVideoClient()
            generator = VideoPromptGenerator(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = generator.generate_files(
                storyboard_path=storyboard_path,
                optimized_image_prompt_path=optimized_image_prompt_path,
                prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
            )

        self.assertEqual("视频提示词1\n视频提示词2", result)
        self.assertEqual(2, len(client.calls))
        self.assertIn("第一段分镜", client.calls[0]["user_content"])
        self.assertIn("优化后生图提示词一", client.calls[0]["user_content"])

    def test_builds_rows_from_same_txt_inputs(self):
        self.assertIsNotNone(VideoPromptGenerator, "VideoPromptGenerator 尚未实现")

        with tempfile.TemporaryDirectory() as tmp_dir:
            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            optimized_image_prompt_path = os.path.join(
                tmp_dir, "optimized_image_prompts.txt"
            )
            with open(optimized_image_prompt_path, "w", encoding="utf-8") as file:
                file.write("优化后生图提示词一\n优化后生图提示词二\n")

            generator = VideoPromptGenerator(
                client=FakeVideoClient(),
                model="test-model",
                prompts_dir=tmp_dir,
            )

            rows = generator.build_rows_from_files(
                storyboard_path=storyboard_path,
                optimized_image_prompt_path=optimized_image_prompt_path,
            )

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "1. 第一段分镜",
                    "optimized_image_prompt": "优化后生图提示词一",
                },
                {
                    "scene_id": "2",
                    "storyboard_text": "2. 第二段分镜",
                    "optimized_image_prompt": "优化后生图提示词二",
                },
            ],
            rows,
        )

    def test_normalizes_multiline_video_prompt_output_into_single_line(self):
        self.assertIsNotNone(VideoPromptGenerator, "VideoPromptGenerator 尚未实现")

        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            generator = VideoPromptGenerator(
                client=MultilineVideoClient(),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = generator.generate_rows(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "第一段分镜",
                        "optimized_image_prompt": "优化后生图提示词一",
                    }
                ],
                prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
            )

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "第一段分镜",
                    "optimized_image_prompt": "优化后生图提示词一",
                    "video_prompt": "视频主体描述 镜头继续推进",
                    "notes_cn": "",
                }
            ],
            result,
        )

    def test_includes_previous_scene_continuity_reference_from_second_row_onward(self):
        self.assertIsNotNone(VideoPromptGenerator, "VideoPromptGenerator 尚未实现")

        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)

            client = FakeVideoClient()
            generator = VideoPromptGenerator(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = generator.generate_rows(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "第一段分镜",
                        "optimized_image_prompt": "优化后生图提示词一",
                    },
                    {
                        "scene_id": "2",
                        "storyboard_text": "第二段分镜",
                        "optimized_image_prompt": "优化后生图提示词二",
                    },
                ],
                prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
            )

        self.assertEqual(2, len(result))

        # 第一条：messages 只有 system + user (2条)
        msgs0 = client.calls[0]["messages"]
        self.assertEqual(2, len(msgs0))

        # 第二条：messages 包含完整历史 (4条: system + user1 + assistant1 + user2)
        msgs1 = client.calls[1]["messages"]
        self.assertEqual(4, len(msgs1))
        self.assertEqual("system", msgs1[0]["role"])
        self.assertEqual("user", msgs1[1]["role"])
        self.assertIn("第一段分镜", msgs1[1]["content"])
        self.assertEqual("assistant", msgs1[2]["role"])
        self.assertIn("视频提示词1", msgs1[2]["content"])
        self.assertEqual("user", msgs1[3]["role"])
        self.assertIn("第二段分镜", msgs1[3]["content"])

    def test_logs_batch_progress_in_existing_project_style(self):
        self.assertIsNotNone(VideoPromptGenerator, "VideoPromptGenerator 尚未实现")

        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = self._make_prompts_dir(tmp_dir)
            generator = VideoPromptGenerator(
                client=FakeVideoClient(),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            with self.assertLogs("core.video_prompt_generator", level="INFO") as captured:
                list(
                    generator.iter_generate_row_batches(
                        rows=[
                            {
                                "scene_id": "1",
                                "storyboard_text": "第一段分镜",
                                "optimized_image_prompt": "优化后生图提示词一",
                            },
                            {
                                "scene_id": "2",
                                "storyboard_text": "第二段分镜",
                                "optimized_image_prompt": "优化后生图提示词二",
                            },
                            {
                                "scene_id": "3",
                                "storyboard_text": "第三段分镜",
                                "optimized_image_prompt": "优化后生图提示词三",
                            },
                        ],
                        prompt_name="2026.4.13-带商业运镜测试简化版2(1)",
                        batch_size=2,
                    )
                )

        log_output = "\n".join(captured.output)
        self.assertIn("开始视频提示词生成 (共 3 条分镜, 2 批, 模型: test-model, 提示词: 2026.4.13-带商业运镜测试简化版2(1))", log_output)
        self.assertIn("生成第 1/2 批... (Ctrl+C 可中断)", log_output)
        self.assertIn("第 1/2 批生成完成", log_output)
        self.assertIn("第 2/2 批生成完成", log_output)
        self.assertIn("视频提示词生成完成", log_output)


if __name__ == "__main__":
    unittest.main()
