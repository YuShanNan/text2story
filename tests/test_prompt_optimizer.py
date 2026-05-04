import os
import tempfile
import unittest

from core.prompt_optimizer import PromptOptimizer, FIXED_NEGATIVE_PROMPT


class FakeClient:
    def __init__(self, return_value: str | None = None):
        self.calls = []
        self.return_value = return_value

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
        if self.return_value is not None:
            return self.return_value
        return f"优化后提示词{len(self.calls)}"

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


class PromptOptimizerTest(unittest.TestCase):
    def test_optimizes_non_empty_storyboard_lines_and_outputs_txt_lines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            with open(
                os.path.join(prompt_category_dir, "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是提示词优化器")

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n原始提示词二\n")

            class TwoLineClient(FakeClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    super().chat_multi_turn(model, messages, **kwargs)
                    return f"优化后提示词1\n优化后提示词2"

            client = TwoLineClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                storyboard_path=storyboard_path,
                raw_prompt_path=raw_prompt_path,
            )

        self.assertEqual(
            f"优化后提示词1 {FIXED_NEGATIVE_PROMPT}\n优化后提示词2 {FIXED_NEGATIVE_PROMPT}",
            result,
        )
        self.assertEqual(1, len(client.calls))
        self.assertIn("第一段分镜", client.calls[0]["user_content"])
        self.assertIn("原始提示词一", client.calls[0]["user_content"])
        self.assertEqual("你是提示词优化器", client.calls[0]["system_prompt"])

    def test_default_project_prompt_includes_back_facing_expression_rule_when_loaded(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 前景男人背对镜头站在窗前\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("男人背对镜头站立，窗外夜景\n")

            project_root = os.path.dirname(os.path.dirname(__file__))
            prompts_dir = os.path.join(project_root, "prompts")

            client = FakeClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            optimizer.optimize_files_batch(
                storyboard_path=storyboard_path,
                raw_prompt_path=raw_prompt_path,
                prompt_name="default",
            )

        self.assertEqual(1, len(client.calls))
        self.assertIn("背对镜头、侧背对镜头、背拍、越肩且该人物面部不可见", client.calls[0]["system_prompt"])
        self.assertIn("禁止描写该人物的任何面部表情或面部细节", client.calls[0]["system_prompt"])

    def test_flattens_multiline_model_output_into_single_prompt_line(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            prompt_path = os.path.join(prompt_category_dir, "default.txt")
            with open(prompt_path, "w", encoding="utf-8") as file:
                file.write("你是提示词优化器")

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n")

            optimizer = PromptOptimizer(
                client=FakeClient(return_value="主体画面描述 负面提示词：无衣物穿透、无多余人物"),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                storyboard_path=storyboard_path,
                raw_prompt_path=raw_prompt_path,
            )

        self.assertEqual(
            "主体画面描述 负面提示词：无衣物穿透、无多余人物",
            result,
        )

    def test_appends_fixed_negative_prompt_tail_when_model_omits_it(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            prompt_path = os.path.join(prompt_category_dir, "default.txt")
            with open(prompt_path, "w", encoding="utf-8") as file:
                file.write("你是提示词优化器")

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n")

            optimizer = PromptOptimizer(
                client=FakeClient(return_value="主体画面描述"),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                storyboard_path=storyboard_path,
                raw_prompt_path=raw_prompt_path,
            )

        self.assertEqual(
            f"主体画面描述 {FIXED_NEGATIVE_PROMPT}",
            result,
        )

    def test_sanitizes_phone_interface_and_body_part_layer_details_not_in_storyboard(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            prompt_path = os.path.join(prompt_category_dir, "default.txt")
            with open(prompt_path, "w", encoding="utf-8") as file:
                file.write("你是提示词优化器")

            optimizer = PromptOptimizer(
                client=FakeClient(return_value="[我]右手拇指按在手机拨号键上，左手托着手机底部，前景是正在拨出的号码界面，后景是[我]紧绷的下颌线条。"),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "我迅速拨通了我爸的电话。",
                        "raw_image_prompt": "原始提示词",
                    }
                ]
            )

        self.assertNotIn("拨号键", result)
        self.assertNotIn("号码界面", result)
        self.assertNotIn("下颌线条", result)
        self.assertIn("手持旧手机", result)

    def test_drops_calendar_visualization_when_storyboard_only_contains_date_info(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            prompt_path = os.path.join(prompt_category_dir, "default.txt")
            with open(prompt_path, "w", encoding="utf-8") as file:
                file.write("你是提示词优化器")

            optimizer = PromptOptimizer(
                client=FakeClient(return_value="墙上挂着一本老式日历，光线落在日历翻页边缘形成细碎阴影。"),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "二零零五年八月十三日。",
                        "raw_image_prompt": "原始提示词",
                    }
                ]
            )

        self.assertNotIn("日历", result)
        self.assertNotIn("翻页", result)
        self.assertEqual(FIXED_NEGATIVE_PROMPT, result)

    def test_builds_table_rows_from_same_txt_inputs_as_txt_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n原始提示词二\n")

            optimizer = PromptOptimizer(
                client=FakeClient(),
                model="test-model",
                prompts_dir=tmp_dir,
            )

            rows = optimizer.build_rows_from_files(
                storyboard_path=storyboard_path,
                raw_prompt_path=raw_prompt_path,
            )

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "1. 第一段分镜",
                    "raw_image_prompt": "原始提示词一",
                },
                {
                    "scene_id": "2",
                    "storyboard_text": "2. 第二段分镜",
                    "raw_image_prompt": "原始提示词二",
                },
            ],
            rows,
        )

    def test_raises_error_when_non_empty_segment_counts_do_not_match(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            prompt_path = os.path.join(prompt_category_dir, "default.txt")
            with open(prompt_path, "w", encoding="utf-8") as file:
                file.write("你是提示词优化器")

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n")

            optimizer = PromptOptimizer(
                client=FakeClient(),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            with self.assertRaisesRegex(ValueError, "段数.*不一致"):
                optimizer.optimize_files_batch(
                    storyboard_path=storyboard_path,
                    raw_prompt_path=raw_prompt_path,
                )

    def test_optimizes_merged_rows_for_csv_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            prompt_path = os.path.join(prompt_category_dir, "default.txt")
            with open(prompt_path, "w", encoding="utf-8") as file:
                file.write("你是提示词优化器")

            optimizer = PromptOptimizer(
                client=FakeClient(),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "第一段分镜",
                        "raw_image_prompt": "原始提示词一",
                    }
                ],
            )

        self.assertEqual(
            f"优化后提示词1 {FIXED_NEGATIVE_PROMPT}",
            result,
        )

    def test_batch_mode_single_turn_covers_all_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            with open(
                os.path.join(prompt_category_dir, "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是提示词优化器")

            class MultiLineClient(FakeClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    super().chat_multi_turn(model, messages, **kwargs)
                    return "优化A\n优化B\n优化C"

            client = MultiLineClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                rows=[
                    {"scene_id": "1", "storyboard_text": "第一段", "raw_image_prompt": "提示词一"},
                    {"scene_id": "2", "storyboard_text": "第二段", "raw_image_prompt": "提示词二"},
                    {"scene_id": "3", "storyboard_text": "第三段", "raw_image_prompt": "提示词三"},
                ],
                prompt_name="default",
                rows_per_batch=50,
            )

        self.assertEqual(1, len(client.calls))
        msgs = client.calls[0]["messages"]
        self.assertEqual(2, len(msgs))
        self.assertIn("第一段", msgs[1]["content"])
        self.assertIn("第三段", msgs[1]["content"])
        lines = result.strip().split("\n")
        self.assertEqual(3, len(lines))

    def test_batch_mode_multi_turn_splits_large_input(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            with open(
                os.path.join(prompt_category_dir, "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是提示词优化器")

            class CountingFakeClient(FakeClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    result = super().chat_multi_turn(model, messages, **kwargs)
                    return f"结果{len(self.calls)}A\n结果{len(self.calls)}B\n结果{len(self.calls)}C"

            client = CountingFakeClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files_batch(
                rows=[
                    {"scene_id": str(i), "storyboard_text": f"分镜{i}", "raw_image_prompt": f"提示词{i}"}
                    for i in range(1, 8)
                ],
                prompt_name="default",
                rows_per_batch=3,
            )

        self.assertEqual(3, len(client.calls))
        msgs_r1 = client.calls[0]["messages"]
        self.assertEqual(2, len(msgs_r1))
        self.assertIn("分镜1", msgs_r1[1]["content"])
        self.assertIn("分镜7", msgs_r1[1]["content"])

        msgs_r2 = client.calls[1]["messages"]
        self.assertEqual(4, len(msgs_r2))
        self.assertEqual("assistant", msgs_r2[2]["role"])
        self.assertIn("已生成并确认前 3 条", msgs_r2[3]["content"])

        msgs_r3 = client.calls[2]["messages"]
        self.assertEqual(6, len(msgs_r3))

        lines = result.strip().split("\n")
        self.assertEqual(7, len(lines))

    def test_batch_mode_passes_all_rows_in_one_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompts_dir = os.path.join(tmp_dir, "prompts")
            prompt_category_dir = os.path.join(prompts_dir, "image_prompt_optimize")
            os.makedirs(prompt_category_dir, exist_ok=True)

            with open(
                os.path.join(prompt_category_dir, "default.txt"),
                "w",
                encoding="utf-8",
            ) as file:
                file.write("你是提示词优化器")

            class TwoLineClient(FakeClient):
                def chat_multi_turn(self, model, messages, **kwargs):
                    super().chat_multi_turn(model, messages, **kwargs)
                    return "优化A\n优化B"

            client = TwoLineClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            optimizer.optimize_files_batch(
                rows=[
                    {"scene_id": "1", "storyboard_text": "人物A进房间", "raw_image_prompt": "男人进门"},
                    {"scene_id": "2", "storyboard_text": "人物A到窗前", "raw_image_prompt": "男人走向窗户"},
                ],
                rows_per_batch=50,
            )

        self.assertEqual(1, len(client.calls))
        msgs = client.calls[0]["messages"]
        self.assertEqual(2, len(msgs))
        self.assertIn("人物A进房间", msgs[1]["content"])
        self.assertIn("人物A到窗前", msgs[1]["content"])


if __name__ == "__main__":
    unittest.main()
