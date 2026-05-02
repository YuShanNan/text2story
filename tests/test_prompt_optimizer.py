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

            prompt_path = os.path.join(prompt_category_dir, "default.txt")
            with open(prompt_path, "w", encoding="utf-8") as file:
                file.write("你是提示词优化器")

            storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n原始提示词二\n")

            client = FakeClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files(
                storyboard_path=storyboard_path,
                raw_prompt_path=raw_prompt_path,
            )

        self.assertEqual(
            f"优化后提示词1 {FIXED_NEGATIVE_PROMPT}\n优化后提示词2 {FIXED_NEGATIVE_PROMPT}",
            result,
        )
        self.assertEqual(2, len(client.calls))
        self.assertIn("第一段分镜", client.calls[0]["user_content"])
        self.assertIn("原始提示词一", client.calls[0]["user_content"])
        self.assertEqual("你是提示词优化器", client.calls[0]["system_prompt"])
        self.assertNotIn("[优化要求]", client.calls[0]["user_content"])

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

            optimizer.optimize_files(
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
                client=FakeClient(return_value="主体画面描述\n负面提示词：无衣物穿透、无多余人物"),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_files(
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

            result = optimizer.optimize_files(
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

            result = optimizer.optimize_rows(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "我迅速拨通了我爸的电话。",
                        "raw_image_prompt": "原始提示词",
                    }
                ]
            )

        optimized = result[0]["optimized_image_prompt"]
        self.assertNotIn("拨号键", optimized)
        self.assertNotIn("号码界面", optimized)
        self.assertNotIn("下颌线条", optimized)
        self.assertIn("手持旧手机", optimized)

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

            result = optimizer.optimize_rows(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "二零零五年八月十三日。",
                        "raw_image_prompt": "原始提示词",
                    }
                ]
            )

        optimized = result[0]["optimized_image_prompt"]
        self.assertNotIn("日历", optimized)
        self.assertNotIn("翻页", optimized)
        self.assertEqual(FIXED_NEGATIVE_PROMPT, optimized)

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
                optimizer.optimize_files(
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

            client = FakeClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            result = optimizer.optimize_rows(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "第一段分镜",
                        "raw_image_prompt": "原始提示词一",
                    }
                ],
            )

        self.assertEqual(
            [
                {
                    "scene_id": "1",
                    "storyboard_text": "第一段分镜",
                    "raw_image_prompt": "原始提示词一",
                    "optimized_image_prompt": f"优化后提示词1 {FIXED_NEGATIVE_PROMPT}",
                    "notes_cn": "",
                }
            ],
            result,
        )

    def test_yields_txt_optimization_results_in_batches(self):
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
                file.write("1. 第一段分镜\n\n2. 第二段分镜\n\n3. 第三段分镜\n")

            raw_prompt_path = os.path.join(tmp_dir, "raw_prompts.txt")
            with open(raw_prompt_path, "w", encoding="utf-8") as file:
                file.write("原始提示词一\n原始提示词二\n原始提示词三\n")

            optimizer = PromptOptimizer(
                client=FakeClient(),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            batches = list(
                optimizer.iter_optimized_file_batches(
                    storyboard_path=storyboard_path,
                    raw_prompt_path=raw_prompt_path,
                    batch_size=2,
                )
            )

        self.assertEqual(
            [
                [
                    f"优化后提示词1 {FIXED_NEGATIVE_PROMPT}",
                    f"优化后提示词2 {FIXED_NEGATIVE_PROMPT}",
                ],
                [f"优化后提示词3 {FIXED_NEGATIVE_PROMPT}"],
            ],
            batches,
        )

    def test_logs_batch_progress_in_existing_project_style(self):
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

            optimizer = PromptOptimizer(
                client=FakeClient(),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            with self.assertLogs("core.prompt_optimizer", level="INFO") as captured:
                list(
                    optimizer.iter_optimized_row_batches(
                        rows=[
                            {
                                "scene_id": "1",
                                "storyboard_text": "第一段分镜",
                                "raw_image_prompt": "原始提示词一",
                            },
                            {
                                "scene_id": "2",
                                "storyboard_text": "第二段分镜",
                                "raw_image_prompt": "原始提示词二",
                            },
                        {
                            "scene_id": "3",
                            "storyboard_text": "第三段分镜",
                            "raw_image_prompt": "原始提示词三",
                        },
                    ],
                    prompt_name="default",
                    batch_size=2,
                )
            )

        log_output = "\n".join(captured.output)
        self.assertIn("开始画面提示词优化 (共 3 条分镜, 2 批, 模型: test-model, 提示词: default)", log_output)
        self.assertIn("优化第 1/2 批... (Ctrl+C 可中断)", log_output)
        self.assertIn("第 1/2 批优化完成", log_output)
        self.assertIn("第 2/2 批优化完成", log_output)
        self.assertIn("画面提示词优化完成", log_output)

    def test_yields_row_level_progress_events_inside_each_batch(self):
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

            optimizer = PromptOptimizer(
                client=FakeClient(),
                model="test-model",
                prompts_dir=prompts_dir,
            )

            events = list(
                optimizer.iter_optimized_row_progress(
                    rows=[
                        {
                            "scene_id": "1",
                            "storyboard_text": "第一段分镜",
                            "raw_image_prompt": "原始提示词一",
                        },
                        {
                            "scene_id": "2",
                            "storyboard_text": "第二段分镜",
                            "raw_image_prompt": "原始提示词二",
                        },
                        {
                            "scene_id": "3",
                            "storyboard_text": "第三段分镜",
                            "raw_image_prompt": "原始提示词三",
                        },
                    ],
                    prompt_name="default",
                    batch_size=2,
                )
            )

        self.assertEqual(3, len(events))
        self.assertEqual(
            f"优化后提示词1 {FIXED_NEGATIVE_PROMPT}",
            events[0]["optimized_row"]["optimized_image_prompt"],
        )
        self.assertEqual(1, events[0]["batch_index"])
        self.assertEqual(2, events[0]["batch_total"])
        self.assertEqual(1, events[0]["batch_row_index"])
        self.assertEqual(2, events[0]["batch_row_total"])
        self.assertFalse(events[0]["batch_completed"])
        self.assertTrue(events[1]["batch_completed"])
        self.assertEqual(2, events[2]["batch_index"])
        self.assertGreaterEqual(events[2]["total_elapsed_seconds"], 0)

    def test_optimize_rows_passes_continuity_context(self):
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

            client = FakeClient()
            optimizer = PromptOptimizer(
                client=client,
                model="test-model",
                prompts_dir=prompts_dir,
            )

            optimizer.optimize_rows(
                rows=[
                    {
                        "scene_id": "1",
                        "storyboard_text": "人物A走进房间",
                        "raw_image_prompt": "男人进门",
                    },
                    {
                        "scene_id": "2",
                        "storyboard_text": "人物A走到窗前",
                        "raw_image_prompt": "男人走向窗户",
                    },
                ],
            )

        self.assertEqual(2, len(client.calls))

        # 第一条：messages 只有 system + user (2条)
        msgs0 = client.calls[0]["messages"]
        self.assertEqual(2, len(msgs0))
        self.assertIn("人物A走进房间", msgs0[1]["content"])
        self.assertIn("男人进门", msgs0[1]["content"])

        # 第二条：messages 包含完整历史 (4条: system + user1 + assistant1 + user2)
        msgs1 = client.calls[1]["messages"]
        self.assertEqual(4, len(msgs1))
        self.assertEqual("system", msgs1[0]["role"])
        self.assertEqual("user", msgs1[1]["role"])
        self.assertIn("人物A走进房间", msgs1[1]["content"])
        self.assertEqual("assistant", msgs1[2]["role"])
        self.assertIn("优化后提示词1", msgs1[2]["content"])
        self.assertEqual("user", msgs1[3]["role"])
        self.assertIn("人物A走到窗前", msgs1[3]["content"])


if __name__ == "__main__":
    unittest.main()
