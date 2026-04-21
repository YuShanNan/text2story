import os
import tempfile
import unittest

from core.prompt_generator import PromptGenerator
from core.srt_corrector import SrtCorrector
from core.storyboard_generator import StoryboardGenerator


class FakeClient:
    def __init__(self):
        self.call_count = 0

    def chat(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
    ) -> str:
        self.call_count += 1
        return f"结果{self.call_count}"


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def chat(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        fallback_model: str = None,
    ) -> str:
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


class LongRunningProgressTest(unittest.TestCase):
    def test_srt_corrector_yields_batch_progress_events(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts", "srt_correction")
            os.makedirs(prompts_dir, exist_ok=True)
            with open(os.path.join(prompts_dir, "default.txt"), "w", encoding="utf-8") as file:
                file.write("修正提示词")

            corrector = SrtCorrector(
                client=FakeClient(),
                model="test-model",
                prompts_dir=os.path.join(tmp_dir, "prompts"),
                max_chunk_size=20,
            )

            events = list(
                corrector.iter_correct_progress(
                    "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n2\n00:00:01,000 --> 00:00:02,000\n第二句",
                    "default",
                )
            )

        self.assertEqual(2, len(events))
        self.assertEqual(1, events[0]["batch_index"])
        self.assertEqual(2, events[0]["batch_total"])
        self.assertEqual("结果1", events[0]["content"])
        self.assertGreaterEqual(events[1]["total_elapsed_seconds"], 0)

    def test_storyboard_generator_yields_chunk_progress_events(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts", "storyboard")
            os.makedirs(prompts_dir, exist_ok=True)
            with open(os.path.join(prompts_dir, "default.txt"), "w", encoding="utf-8") as file:
                file.write("分镜提示词")

            generator = StoryboardGenerator(
                client=FakeClient(),
                model="test-model",
                prompts_dir=os.path.join(tmp_dir, "prompts"),
                max_chunk_size=6,
            )

            events = list(generator.iter_generate_progress("第一段文本第二段文本", "default"))

        self.assertEqual(2, len(events))
        self.assertEqual(1, events[0]["chunk_index"])
        self.assertEqual(2, events[0]["chunk_total"])
        self.assertEqual("结果1", events[0]["content"])
        self.assertEqual("结果2", events[1]["content"])

    def test_storyboard_generator_normalizes_each_chunk_before_combining(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts", "storyboard")
            os.makedirs(prompts_dir, exist_ok=True)
            with open(os.path.join(prompts_dir, "default.txt"), "w", encoding="utf-8") as file:
                file.write("分镜提示词")

            generator = StoryboardGenerator(
                client=ScriptedClient(
                    [
                        "1. 我在老公的包里发现了半瓶润滑液",
                        "2. 可我跟他从来没有用过这个我买了两瓶502灌进去",
                    ]
                ),
                model="test-model",
                prompts_dir=os.path.join(tmp_dir, "prompts"),
                max_chunk_size=24,
            )

            result = generator.generate(
                "我在老公的包里\n发现了半瓶润滑液\n可我跟他从来没有用过这个\n我买了两瓶502灌进去",
                "default",
            )

        self.assertEqual(
            "\n".join(
                [
                    "1. 我在老公的包里发现了半瓶润滑液",
                    "2. 可我跟他从来没有用过这个我买了两瓶502灌进去",
                ]
            ),
            result,
        )

    def test_storyboard_generator_retries_when_chunk_would_fallback_to_source_lines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts", "storyboard")
            os.makedirs(prompts_dir, exist_ok=True)
            with open(os.path.join(prompts_dir, "default.txt"), "w", encoding="utf-8") as file:
                file.write("分镜提示词")

            client = ScriptedClient(
                [
                    "完全不相干的错误输出",
                    "1. 第一行第二行\n2. 第三行",
                ]
            )
            generator = StoryboardGenerator(
                client=client,
                model="test-model",
                prompts_dir=os.path.join(tmp_dir, "prompts"),
                max_chunk_size=100,
            )

            events = list(generator.iter_generate_progress("第一行\n第二行\n第三行", "default"))

        self.assertEqual(2, client.call_count)
        self.assertEqual(1, len(events))
        self.assertEqual("1. 第一行第二行\n2. 第三行", events[0]["content"])
        self.assertEqual("1. 第一行第二行\n2. 第三行", events[0]["normalized_content"])

    def test_storyboard_generator_honors_unlimited_retry_when_max_retry_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts", "storyboard")
            os.makedirs(prompts_dir, exist_ok=True)
            with open(os.path.join(prompts_dir, "default.txt"), "w", encoding="utf-8") as file:
                file.write("分镜提示词")

            client = ScriptedClient(
                [
                    "完全不相干的错误输出",
                    "完全不相干的错误输出",
                    "完全不相干的错误输出",
                    "完全不相干的错误输出",
                    "1. 第一行第二行\n2. 第三行",
                ]
            )
            client.max_retry = 0
            generator = StoryboardGenerator(
                client=client,
                model="test-model",
                prompts_dir=os.path.join(tmp_dir, "prompts"),
                max_chunk_size=100,
            )

            events = list(generator.iter_generate_progress("第一行\n第二行\n第三行", "default"))

        self.assertEqual(5, client.call_count)
        self.assertEqual(1, len(events))
        self.assertEqual("1. 第一行第二行\n2. 第三行", events[0]["normalized_content"])

    def test_storyboard_generator_returns_degraded_event_when_retries_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts", "storyboard")
            os.makedirs(prompts_dir, exist_ok=True)
            with open(os.path.join(prompts_dir, "default.txt"), "w", encoding="utf-8") as file:
                file.write("分镜提示词")

            client = ScriptedClient(
                [
                    "完全不相干的错误输出",
                    "完全不相干的错误输出",
                    "完全不相干的错误输出",
                ]
            )
            client.max_retry = 3
            generator = StoryboardGenerator(
                client=client,
                model="test-model",
                prompts_dir=os.path.join(tmp_dir, "prompts"),
                max_chunk_size=100,
            )

            events = list(generator.iter_generate_progress("第一行\n第二行\n第三行", "default"))

        self.assertEqual(3, client.call_count)
        self.assertEqual(1, len(events))
        self.assertTrue(events[0]["degraded_fallback"])
        self.assertIn("MAX_RETRY=3", events[0]["warning_message"])
        self.assertEqual("1. 第一行\n2. 第二行\n3. 第三行", events[0]["normalized_content"])

    def test_prompt_generator_yields_scene_progress_events_for_both_modes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_root = os.path.join(tmp_dir, "prompts")
            os.makedirs(os.path.join(prompts_root, "image_prompt"), exist_ok=True)
            os.makedirs(os.path.join(prompts_root, "video_prompt"), exist_ok=True)
            with open(os.path.join(prompts_root, "image_prompt", "default.txt"), "w", encoding="utf-8") as file:
                file.write("图片提示词")
            with open(os.path.join(prompts_root, "video_prompt", "default.txt"), "w", encoding="utf-8") as file:
                file.write("视频提示词")

            generator = PromptGenerator(
                client=FakeClient(),
                model="test-model",
                prompts_dir=prompts_root,
            )

            events = list(
                generator.iter_generate_progress(
                    "【分镜 1】第一幕\n---\n【分镜 2】第二幕",
                    mode="both",
                    image_prompt_name="default",
                    video_prompt_name="default",
                )
            )

        self.assertEqual(4, len(events))
        self.assertEqual(["image", "image", "video", "video"], [event["prompt_type"] for event in events])
        self.assertEqual(1, events[0]["scene_index"])
        self.assertEqual(2, events[0]["scene_total"])
        self.assertEqual("结果4", events[-1]["content"])


if __name__ == "__main__":
    unittest.main()
