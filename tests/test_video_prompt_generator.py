import os
import tempfile
import unittest

from core.video_prompt_generator import VideoPromptGenerator


def _collect_batch(generator):
    for step in generator:
        if isinstance(step, str):
            return step
    return ""


class FakeVideoClient:
    def __init__(self):
        self.calls = []

    def chat_multi_turn(self, model, messages, temperature=0.7,
                        max_tokens=4096, fallback_model=None, thinking_enabled=None):
        system_prompt = ""
        user_content = ""
        if messages and messages[0]["role"] == "system":
            system_prompt = messages[0]["content"]
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_content = msg["content"]
                break
        self.calls.append({
            "model": model, "system_prompt": system_prompt,
            "user_content": user_content, "messages": list(messages),
            "temperature": temperature, "fallback_model": fallback_model,
        })
        return f"视频提示词{len(self.calls)}"

    def chat(self, **kwargs):
        return self.chat_multi_turn(**kwargs)


class VideoPromptGeneratorTest(unittest.TestCase):
    PROMPT_NAME = "2026.4.13-带商业运镜测试简化版2(1)"

    def _make_prompts_dir(self, tmp_dir):
        d = os.path.join(tmp_dir, "prompts", "video_prompt_from_image")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{self.PROMPT_NAME}.txt"), "w", encoding="utf-8") as f:
            f.write("你是视频提示词生成器")
        return os.path.join(tmp_dir, "prompts")

    def test_batch_generates_all_in_one_call(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)
            sb = os.path.join(tmp_dir, "s.txt")
            op = os.path.join(tmp_dir, "o.txt")
            with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
            with open(op, "w") as f: f.write("PA\nPB\n")

            class C(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "VA\nVB"

            client = C()
            gen = VideoPromptGenerator(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(gen.generate_files_batch(storyboard_path=sb, optimized_image_prompt_path=op, prompt_name=self.PROMPT_NAME))
        self.assertEqual("1. VA\n2. VB", r)
        self.assertEqual(1, len(client.calls))

    def test_builds_rows_from_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sb = os.path.join(tmp_dir, "s.txt")
            op = os.path.join(tmp_dir, "o.txt")
            with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
            with open(op, "w") as f: f.write("PA\nPB\n")
            gen = VideoPromptGenerator(client=FakeVideoClient(), model="m", prompts_dir=tmp_dir)
            rows = gen.build_rows_from_files(storyboard_path=sb, optimized_image_prompt_path=op)
        self.assertEqual(2, len(rows))
        self.assertEqual("1. A", rows[0]["storyboard_text"])

    def test_normalizes_multiline_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "视频主体描述 镜头继续推进"

            gen = VideoPromptGenerator(client=C(), model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(gen.generate_files_batch(rows=[
                {"s": "1", "storyboard_text": "A", "optimized_image_prompt": "P"}
            ], prompt_name=self.PROMPT_NAME))
        self.assertEqual("1. 视频主体描述 镜头继续推进", r)

    def test_batch_all_rows_in_one_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "VA\nVB"

            client = C()
            gen = VideoPromptGenerator(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            _collect_batch(gen.generate_files_batch(rows=[
                {"s": "1", "storyboard_text": "SA", "optimized_image_prompt": "PA"},
                {"s": "2", "storyboard_text": "SB", "optimized_image_prompt": "PB"},
            ], prompt_name=self.PROMPT_NAME, rows_per_batch=50))
        self.assertEqual(1, len(client.calls))
        self.assertIn("SA", client.calls[0]["user_content"])
        self.assertIn("SB", client.calls[0]["user_content"])

    def test_batch_multi_turn_for_large_input(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    n = len(self.calls)
                    return f"V{n}A\nV{n}B\nV{n}C"

            client = C()
            gen = VideoPromptGenerator(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(gen.generate_files_batch(rows=[
                {"s": str(i), "storyboard_text": f"S{i}", "optimized_image_prompt": f"P{i}"} for i in range(1, 8)
            ], prompt_name=self.PROMPT_NAME, rows_per_batch=3))
        self.assertEqual(3, len(client.calls))
        self.assertEqual(7, len(r.strip().split("\n")))

    def test_logs_batch_progress(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeVideoClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "VA\nVB"

            gen = VideoPromptGenerator(client=C(), model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            with self.assertLogs("core.video_prompt_generator", level="INFO") as captured:
                _collect_batch(gen.generate_files_batch(rows=[
                    {"s": "1", "storyboard_text": "A", "optimized_image_prompt": "P"},
                    {"s": "2", "storyboard_text": "B", "optimized_image_prompt": "Q"},
                ], prompt_name=self.PROMPT_NAME, rows_per_batch=50))
        log = "\n".join(captured.output)
        self.assertIn("开始批量视频提示词生成", log)
        self.assertIn("批量视频提示词生成完成 (2 条)", log)


if __name__ == "__main__":
    unittest.main()
