import os
import tempfile
import unittest

from core.prompt_optimizer import PromptOptimizer


def _collect_batch(generator):
    """消费生成器的进度事件，返回最终结果字符串"""
    for step in generator:
        if isinstance(step, str):
            return step
    return ""


class FakeClient:
    def __init__(self, return_value: str | None = None):
        self.calls = []
        self.return_value = return_value

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
        if self.return_value is not None:
            return self.return_value
        return f"优化后提示词{len(self.calls)}"

    def chat(self, model, system_prompt, user_content, temperature=0.7,
             max_tokens=4096, fallback_model=None, thinking_enabled=None):
        return self.chat_multi_turn(
            model=model,
            messages=[{"role": "system", "content": system_prompt},
                       {"role": "user", "content": user_content}],
            temperature=temperature, max_tokens=max_tokens,
            fallback_model=fallback_model, thinking_enabled=thinking_enabled,
        )


class PromptOptimizerTest(unittest.TestCase):
    def _make_prompts_dir(self, tmp_dir):
        d = os.path.join(tmp_dir, "prompts", "image_prompt_optimize")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "default.txt"), "w", encoding="utf-8") as f:
            f.write("你是提示词优化器")
        return os.path.join(tmp_dir, "prompts")

    def test_batch_mode_returns_all_lines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)
            sb = os.path.join(tmp_dir, "s.txt")
            rp = os.path.join(tmp_dir, "r.txt")
            with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
            with open(rp, "w") as f: f.write("PA\nPB\n")

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "OA\nOB"

            client = C()
            opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(opt.optimize_files_batch(storyboard_path=sb, raw_prompt_path=rp))
        self.assertEqual("1. OA\n2. OB", r)
        self.assertEqual(1, len(client.calls))

    def test_loads_default_prompt_with_back_facing_rule(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sb = os.path.join(tmp_dir, "s.txt")
            rp = os.path.join(tmp_dir, "r.txt")
            with open(sb, "w") as f: f.write("1. X\n")
            with open(rp, "w") as f: f.write("P\n")
            root = os.path.dirname(os.path.dirname(__file__))
            client = FakeClient()
            opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(root, "prompts"))
            _collect_batch(opt.optimize_files_batch(storyboard_path=sb, raw_prompt_path=rp, prompt_name="default"))
        self.assertIn("背对镜头", client.calls[0]["system_prompt"])

    def test_flattens_multiline_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)
            sb = os.path.join(tmp_dir, "s.txt")
            rp = os.path.join(tmp_dir, "r.txt")
            with open(sb, "w") as f: f.write("1. X\n")
            with open(rp, "w") as f: f.write("P\n")
            opt = PromptOptimizer(client=FakeClient(return_value="主体画面描述 负面提示词：无衣物穿透、无多余人物"),
                                   model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(opt.optimize_files_batch(storyboard_path=sb, raw_prompt_path=rp))
        self.assertEqual("1. 主体画面描述 负面提示词：无衣物穿透、无多余人物", r)

    def test_appends_negative_prompt_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)
            sb = os.path.join(tmp_dir, "s.txt")
            rp = os.path.join(tmp_dir, "r.txt")
            with open(sb, "w") as f: f.write("1. X\n")
            with open(rp, "w") as f: f.write("P\n")
            opt = PromptOptimizer(client=FakeClient(return_value="主体"),
                                   model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(opt.optimize_files_batch(storyboard_path=sb, raw_prompt_path=rp))
        self.assertEqual("1. 主体", r)

    def test_builds_rows_from_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sb = os.path.join(tmp_dir, "s.txt")
            rp = os.path.join(tmp_dir, "r.txt")
            with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
            with open(rp, "w") as f: f.write("PA\nPB\n")
            opt = PromptOptimizer(client=FakeClient(), model="m", prompts_dir=tmp_dir)
            rows = opt.build_rows_from_files(storyboard_path=sb, raw_prompt_path=rp)
        self.assertEqual(2, len(rows))
        self.assertEqual("1. A", rows[0]["storyboard_text"])

    def test_raises_on_mismatched_counts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)
            sb = os.path.join(tmp_dir, "s.txt")
            rp = os.path.join(tmp_dir, "r.txt")
            with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
            with open(rp, "w") as f: f.write("PA\n")
            opt = PromptOptimizer(client=FakeClient(), model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            with self.assertRaisesRegex(ValueError, "段数.*不一致"):
                _collect_batch(opt.optimize_files_batch(storyboard_path=sb, raw_prompt_path=rp))

    def test_csv_mode_returns_string(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)
            opt = PromptOptimizer(client=FakeClient(), model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(opt.optimize_files_batch(rows=[
                {"scene_id": "1", "storyboard_text": "A", "raw_image_prompt": "P"}]))
        self.assertEqual("1. 优化后提示词1", r)

    def test_batch_single_turn(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "A\nB\nC"

            client = C()
            opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(opt.optimize_files_batch(rows=[
                {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"} for i in range(1, 4)
            ], rows_per_batch=50))
        self.assertEqual(1, len(client.calls))
        self.assertEqual(3, len(r.strip().split("\n")))

    def test_batch_multi_turn(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    n = len(self.calls)
                    return f"R{n}A\nR{n}B\nR{n}C"

            client = C()
            opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(opt.optimize_files_batch(rows=[
                {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"} for i in range(1, 8)
            ], rows_per_batch=3))
        self.assertEqual(3, len(client.calls))
        self.assertEqual(7, len(r.strip().split("\n")))

    def test_batch_all_rows_in_one_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "A\nB"

            client = C()
            opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            _collect_batch(opt.optimize_files_batch(rows=[
                {"s": "1", "storyboard_text": "SA", "raw_image_prompt": "PA"},
                {"s": "2", "storyboard_text": "SB", "raw_image_prompt": "PB"},
            ], rows_per_batch=50))
        self.assertEqual(1, len(client.calls))
        self.assertIn("SA", client.calls[0]["user_content"])
        self.assertIn("SB", client.calls[0]["user_content"])


if __name__ == "__main__":
    unittest.main()
