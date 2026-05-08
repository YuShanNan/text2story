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
        self.calls = []                  # records all chat() calls
        self.chat_multi_turn_calls = []  # records all chat_multi_turn() calls
        self.return_value = return_value

    def chat(self, model, system_prompt, user_content, temperature=0.7,
             max_tokens=4096, fallback_model=None, thinking_enabled=None):
        self.calls.append({
            "model": model,
            "system_prompt": system_prompt,
            "user_content": user_content,
            "temperature": temperature,
            "fallback_model": fallback_model,
        })
        if self.return_value is not None:
            return self.return_value
        return f"优化后提示词{len(self.calls)}"

    def chat_multi_turn(self, model, messages, temperature=0.7,
                        max_tokens=4096, fallback_model=None, thinking_enabled=None):
        self.chat_multi_turn_calls.append({
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
            "fallback_model": fallback_model,
        })
        if self.return_value is not None:
            return self.return_value
        return f"优化后提示词{len(self.chat_multi_turn_calls)}"


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
        self.assertEqual("OA\nOB", r)
        self.assertEqual(1, len(client.calls))  # 1 summary (chat)
        self.assertEqual(1, len(client.chat_multi_turn_calls))  # 1 batch (chat_multi_turn)

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
        self.assertIn("背对镜头", client.chat_multi_turn_calls[0]["messages"][0]["content"])

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
        self.assertEqual("主体画面描述 负面提示词：无衣物穿透、无多余人物", r)

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
        self.assertEqual("主体", r)

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
        self.assertEqual("优化后提示词1", r)  # chat_multi_turn call 1

    def test_all_rows_in_first_message(self):
        """verify all rows are in the first user message (single multi-turn session)"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return "A\nB\nC"

            client = C()
            opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            _collect_batch(opt.optimize_files_batch(rows=[
                {"s": "1", "storyboard_text": "SA", "raw_image_prompt": "PA"},
                {"s": "2", "storyboard_text": "SB", "raw_image_prompt": "PB"},
                {"s": "3", "storyboard_text": "SC", "raw_image_prompt": "PC"},
            ], rows_per_batch=50))
        self.assertEqual(1, len(client.chat_multi_turn_calls))  # single batch call
        first_user = client.chat_multi_turn_calls[0]["messages"][1]["content"]
        self.assertIn("SA", first_user)
        self.assertIn("SB", first_user)
        self.assertIn("SC", first_user)
        self.assertIn("PA", first_user)
        self.assertIn("PB", first_user)
        self.assertIn("PC", first_user)

    def test_multi_batch_uses_confirm_messages(self):
        """verify confirm messages between batches in multi-turn session"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    n = len(self.chat_multi_turn_calls)
                    return f"R{n}A\nR{n}B\nR{n}C"

            client = C()
            opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
            r = _collect_batch(opt.optimize_files_batch(rows=[
                {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"} for i in range(1, 8)
            ], rows_per_batch=3))
        # 7 rows, 3 per batch → 3 batches (3+3+1)
        self.assertEqual(3, len(client.chat_multi_turn_calls))
        # Check confirm messages in batch 2 and 3
        msgs2 = client.chat_multi_turn_calls[1]["messages"]
        msgs3 = client.chat_multi_turn_calls[2]["messages"]
        self.assertIn("已生成并确认前 3 条", msgs2[-1]["content"])
        self.assertIn("已生成并确认前 6 条", msgs3[-1]["content"])
        self.assertEqual(7, len(r.strip().split("\n")))

    def test_messages_accumulate_across_batches(self):
        """verify messages list grows across batches (not independent calls)"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    n = len(self.chat_multi_turn_calls)
                    return f"R{n}A\nR{n}B\nR{n}C\nR{n}D"

            client = C()
            opt = PromptOptimizer(client=client, model="m",
                                  prompts_dir=os.path.join(tmp_dir, "prompts"))
            _collect_batch(opt.optimize_files_batch(rows=[
                {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"}
                for i in range(1, 9)
            ], rows_per_batch=4))

        # 8 rows, 4 per batch → 2 batches
        self.assertEqual(2, len(client.chat_multi_turn_calls))
        # Batch 1: [system, user] = 2 messages
        self.assertEqual(2, len(client.chat_multi_turn_calls[0]["messages"]))
        # Batch 2: [system, user, assistant, user] = 4 messages (accumulated)
        self.assertEqual(4, len(client.chat_multi_turn_calls[1]["messages"]))

    def test_summary_in_first_message(self):
        """verify global summary is in the initial user message"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._make_prompts_dir(tmp_dir)

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    if "缺少第" in (messages[-1].get("content", "") if messages else ""):
                        return "R\n"
                    return "L1\nL2\nL3\nL4\nL5"

            client = C()
            opt = PromptOptimizer(client=client, model="m",
                                  prompts_dir=os.path.join(tmp_dir, "prompts"))
            _collect_batch(opt.optimize_files_batch(rows=[
                {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"}
                for i in range(1, 13)
            ], rows_per_batch=5))

        first_user = client.chat_multi_turn_calls[0]["messages"][1]["content"]
        self.assertIn("全局叙事摘要", first_user)


class ValidationTest(unittest.TestCase):
    """Tests for _extract_known_entities and _validate_batch_lines."""

    def setUp(self):
        self.opt = PromptOptimizer(
            client=FakeClient(), model="m", prompts_dir="/tmp",
        )

    def test_extract_known_entities_from_raw_prompts(self):
        rows = [
            {"storyboard_text": "S1", "raw_image_prompt": "[画风:写实][姜春秋][白羽村村口]"},
            {"storyboard_text": "S2", "raw_image_prompt": "[黄兴祖][村中大婶][王叔]"},
        ]
        entities = self.opt._extract_known_entities(rows)
        self.assertIn("姜春秋", entities)
        self.assertIn("白羽村村口", entities)
        self.assertIn("黄兴祖", entities)
        self.assertIn("村中大婶", entities)
        self.assertIn("王叔", entities)
        self.assertIn("画风:写实", entities)

    def test_validate_clean_lines_pass(self):
        entities = {"姜春秋", "白羽村村口", "黄兴祖"}
        lines = [
            "【姜春秋】站在【白羽村村口】，【黄兴祖】在一旁。",
        ]
        valid, issues = self.opt._validate_batch_lines(lines, entities, 0)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(issues), 0)

    def test_validate_foreign_characters_flagged(self):
        entities = {"姜春秋", "白羽村村口"}
        lines = [
            "【宋栖晚】在【家用轿车车内】开车，【苏世衍】坐副驾。",
        ]
        valid, issues = self.opt._validate_batch_lines(lines, entities, 0)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(issues), 1)
        self.assertIn("宋栖晚", issues[0][1][0])
        self.assertIn("苏世衍", issues[0][1][0])

    def test_validate_single_foreign_entity_not_flagged(self):
        """单个外来实体不触发污染标记（可能是依法规添加的场景名）。"""
        entities = {"姜春秋"}
        lines = [
            "【姜春秋】在【家用轿车车内】开车。",
        ]
        valid, issues = self.opt._validate_batch_lines(lines, entities, 0)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(issues), 0)

    def test_validate_unbalanced_brackets_flagged(self):
        entities = {"姜春秋"}
        lines = [
            "【姜春秋】站在村口，【王叔指着他。",  # 】缺失
        ]
        valid, issues = self.opt._validate_batch_lines(lines, entities, 0)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(issues), 1)
        self.assertIn("不配对", issues[0][1][0])

    def test_validate_input_echo_flagged(self):
        entities = {"姜春秋"}
        lines = [
            "[1] 分镜原文：姜春秋站在村口",
        ]
        valid, issues = self.opt._validate_batch_lines(lines, entities, 0)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(issues), 1)
        self.assertIn("输入回显", issues[0][1][0])

    def test_validate_raw_prompt_echo_flagged(self):
        entities = {"姜春秋"}
        lines = [
            "原始画面提示词：[画风:写实]姜春秋站在村口",
        ]
        valid, issues = self.opt._validate_batch_lines(lines, entities, 0)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(issues), 1)
        self.assertIn("输入回显", issues[0][1][0])

    def test_validate_empty_line_handled(self):
        entities: set[str] = set()
        lines = [""]
        valid, issues = self.opt._validate_batch_lines(lines, entities, 0)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(issues), 0)

    def test_contamination_triggers_single_line_retry(self):
        """集成测试：首轮返回污染行，验证触发单行重试且最终干净。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_root = os.path.join(tmp_dir, "prompts")
            d = os.path.join(prompts_root, "image_prompt_optimize")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "default.txt"), "w", encoding="utf-8") as f:
                f.write("你是提示词优化器")

            class C(FakeClient):
                def chat_multi_turn(self, model, messages, **kw):
                    super().chat_multi_turn(model, messages, **kw)
                    return (
                        "【宋栖晚】在【家用轿车车内】开车，【苏世衍】坐副驾。\n"
                        "【姜春秋】站在【白羽村村口】，【黄兴祖】指着他。"
                    )

                def chat(self, model, system_prompt, user_content, **kw):
                    super().chat(model, system_prompt, user_content, **kw)
                    if "重新生成第" in user_content:
                        return "【姜春秋】站在【白羽村村口】。"
                    return "OK"

            client = C()
            opt = PromptOptimizer(
                client=client, model="m",
                prompts_dir=prompts_root,
            )
            r = _collect_batch(opt.optimize_files_batch(rows=[
                {"s": "1", "storyboard_text": "S1", "raw_image_prompt": "[姜春秋][白羽村村口][黄兴祖]"},
                {"s": "2", "storyboard_text": "S2", "raw_image_prompt": "[姜春秋][白羽村村口][黄兴祖]"},
            ], rows_per_batch=50))

        lines = r.strip().split("\n")
        self.assertEqual(2, len(lines))
        self.assertNotIn("宋栖晚", r)
        self.assertNotIn("苏世衍", r)
        self.assertIn("姜春秋", lines[1])


if __name__ == "__main__":
    unittest.main()
