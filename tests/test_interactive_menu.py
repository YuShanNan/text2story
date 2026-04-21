import os
import tempfile
import unittest
import warnings
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message="urllib3 .* or chardet.* doesn't match a supported version!",
)

from core.interactive import (
    _compact_path,
    _create_step_progress,
    _run_postprocess_pipeline,
    ENV_CONFIG_ITEMS,
    get_main_menu_choices,
    get_single_step_choices,
    run_interactive,
    run_single_step,
    scan_input_txt_files,
    select_input_file,
    select_optimization_input_mode,
    select_prompt,
    select_storyboard_input_mode,
    scan_storyboard_optimized_image_prompt_files,
    scan_storyboard_prompt_files,
)
from core.storyboard_generator import StoryboardGenerationUnstableError
from rich.console import Console


class InteractiveMenuTest(unittest.TestCase):
    def test_main_menu_exposes_two_stage_pipeline_entries(self):
        choices = [choice for choice in get_main_menu_choices() if isinstance(choice, dict)]
        choice_values = [choice["value"] for choice in choices]
        choice_names = [choice["name"] for choice in choices]

        self.assertIn("pipeline_stage_one", choice_values)
        self.assertIn("pipeline_stage_two", choice_values)
        self.assertTrue(any("阶段一完整流水线" in name for name in choice_names))
        self.assertTrue(any("阶段二完整流水线" in name for name in choice_names))

    def test_single_step_choices_use_one_unified_optimization_entry(self):
        choices = get_single_step_choices()
        mapped_choices = [choice for choice in choices if isinstance(choice, dict)]
        choice_values = [choice["value"] for choice in mapped_choices]
        choice_names = [choice["name"] for choice in mapped_choices]

        self.assertEqual([1, 2, 3, 4, 5], choice_values)
        self.assertTrue(any("画面提示词优化" in name for name in choice_names))
        self.assertFalse(any("TXT 画面提示词优化" in name for name in choice_names))
        self.assertFalse(any("CSV 画面提示词优化" in name for name in choice_names))

    def test_step_4_label_does_not_have_extra_leading_space(self):
        choices = get_single_step_choices()
        step_4 = next(choice for choice in choices if choice["value"] == 4)

        self.assertTrue(step_4["name"].startswith("✨ 步骤 4"))
        self.assertIn("TXT / CSV", step_4["name"])

    def test_step_5_label_exists_for_video_prompt_generation(self):
        choices = get_single_step_choices()
        step_5 = next(choice for choice in choices if choice["value"] == 5)

        self.assertTrue(step_5["name"].startswith("🎥 步骤 5"))
        self.assertIn("视频提示词生成", step_5["name"])

    def test_select_optimization_input_mode_returns_selected_mode(self):
        select_prompt = patch("core.interactive.inquirer.select").start()
        clear_console = patch("core.interactive.console.clear").start()
        self.addCleanup(patch.stopall)

        select_prompt.return_value.execute.return_value = "csv"

        self.assertEqual("csv", select_optimization_input_mode())
        clear_console.assert_called_once()

    def test_select_storyboard_input_mode_returns_selected_mode(self):
        select_prompt = patch("core.interactive.inquirer.select").start()
        clear_console = patch("core.interactive.console.clear").start()
        self.addCleanup(patch.stopall)

        select_prompt.return_value.execute.return_value = "any_txt"

        self.assertEqual("any_txt", select_storyboard_input_mode())
        clear_console.assert_called_once()

    def test_select_input_file_clears_previous_screen_after_choice(self):
        typed_input = patch("core.interactive.inquirer.text").start()
        clear_console = patch("core.interactive.console.clear").start()
        self.addCleanup(patch.stopall)

        typed_input.return_value.execute.return_value = "2"

        selected = select_input_file(
            [r"E:\text2story\output\a.txt", r"E:\text2story\output\b.txt"],
            r"E:\text2story\output",
            "测试",
        )

        self.assertEqual(r"E:\text2story\output\b.txt", selected)
        clear_console.assert_called_once()

    def test_run_interactive_clears_console_before_rendering_welcome_screen(self):
        clear_console = patch("core.interactive.console.clear").start()
        execute_prompt = patch("core.interactive._execute_prompt", side_effect=KeyboardInterrupt).start()
        self.addCleanup(patch.stopall)

        run_interactive()

        clear_console.assert_called_once()
        execute_prompt.assert_called_once()

    def test_run_interactive_clears_console_before_returning_to_main_menu(self):
        clear_console = patch("core.interactive.console.clear").start()
        execute_prompt = patch(
            "core.interactive._execute_prompt",
            side_effect=["single", KeyboardInterrupt],
        ).start()
        run_single_step = patch("core.interactive.run_single_step").start()
        self.addCleanup(patch.stopall)

        run_interactive()

        self.assertEqual(2, clear_console.call_count)
        run_single_step.assert_called_once()
        self.assertEqual(2, execute_prompt.call_count)

    def test_run_single_step_prints_user_friendly_storyboard_error(self):
        run_inner = patch(
            "core.interactive._run_single_step_inner",
            side_effect=StoryboardGenerationUnstableError("分镜生成失败"),
        ).start()
        print_error = patch("core.interactive._print_error").start()
        self.addCleanup(patch.stopall)

        run_single_step()

        run_inner.assert_called_once()
        print_error.assert_called_once()
        self.assertEqual("❌ 分镜生成失败", print_error.call_args.args[1])
        self.assertEqual("分镜生成失败", print_error.call_args.args[2])
        self.assertIn("MAX_RETRY", print_error.call_args.args[3])

    def test_run_postprocess_pipeline_prints_runtime_error_panel(self):
        run_inner = patch(
            "core.interactive._run_postprocess_pipeline_inner",
            side_effect=RuntimeError("阶段二失败"),
        ).start()
        print_error = patch("core.interactive._print_error").start()
        self.addCleanup(patch.stopall)

        _run_postprocess_pipeline()

        run_inner.assert_called_once()
        print_error.assert_called_once()
        self.assertEqual("❌ 阶段二执行失败", print_error.call_args.args[1])
        self.assertEqual("阶段二失败", print_error.call_args.args[2])

    def test_scan_storyboard_prompt_files_only_returns_same_directory_qingfeng_txt_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_dir = os.path.join(tmp_dir, "示例剧集")
            other_dir = os.path.join(tmp_dir, "其他剧集")
            os.makedirs(target_dir)
            os.makedirs(other_dir)

            storyboard_path = os.path.join(target_dir, "示例_storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 分镜")

            expected_prompt = os.path.join(target_dir, "画面提示词.txt")
            another_expected_prompt = os.path.join(target_dir, "画面提示词_2026-4-14.txt")
            ignored_same_dir = os.path.join(target_dir, "别的提示词.txt")
            ignored_other_dir = os.path.join(other_dir, "画面提示词.txt")

            for path in [
                expected_prompt,
                another_expected_prompt,
                ignored_same_dir,
                ignored_other_dir,
            ]:
                with open(path, "w", encoding="utf-8") as file:
                    file.write("提示词")

            self.assertEqual(
                [expected_prompt, another_expected_prompt],
                scan_storyboard_prompt_files(storyboard_path),
            )

    def test_scan_storyboard_optimized_prompt_files_only_returns_same_directory_optimized_txt_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_dir = os.path.join(tmp_dir, "示例剧集")
            other_dir = os.path.join(tmp_dir, "其他剧集")
            os.makedirs(target_dir)
            os.makedirs(other_dir)

            storyboard_path = os.path.join(target_dir, "示例_storyboard.txt")
            with open(storyboard_path, "w", encoding="utf-8") as file:
                file.write("1. 分镜")

            expected_prompt = os.path.join(target_dir, "示例_optimized_image_prompts.txt")
            another_expected_prompt = os.path.join(target_dir, "别名_optimized_image_prompts.txt")
            ignored_same_dir = os.path.join(target_dir, "画面提示词.txt")
            ignored_other_dir = os.path.join(other_dir, "示例_optimized_image_prompts.txt")

            for path in [
                expected_prompt,
                another_expected_prompt,
                ignored_same_dir,
                ignored_other_dir,
            ]:
                with open(path, "w", encoding="utf-8") as file:
                    file.write("提示词")

            self.assertEqual(
                [another_expected_prompt, expected_prompt],
                scan_storyboard_optimized_image_prompt_files(storyboard_path),
            )

    def test_scan_input_txt_files_recursively_returns_only_txt_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            nested_dir = os.path.join(tmp_dir, "剧集", "子目录")
            os.makedirs(nested_dir)

            expected_paths = [
                os.path.join(tmp_dir, "a.txt"),
                os.path.join(nested_dir, "b.txt"),
            ]
            ignored_paths = [
                os.path.join(tmp_dir, "a.srt"),
                os.path.join(nested_dir, "b.csv"),
            ]

            for path in expected_paths + ignored_paths:
                with open(path, "w", encoding="utf-8") as file:
                    file.write("content")

            self.assertEqual(expected_paths, scan_input_txt_files(tmp_dir))

    def test_env_config_items_only_keep_single_generic_model_entry(self):
        keys = [item[0] for item in ENV_CONFIG_ITEMS]

        self.assertIn("MODEL_API_KEY", keys)
        self.assertIn("MODEL_BASE_URL", keys)
        self.assertIn("MODEL_NAME", keys)
        self.assertFalse(any(key.startswith("DEEPSEEK_") for key in keys))
        self.assertFalse(any(key.startswith("VOLCENGINE_") for key in keys))

    def test_runtime_facing_source_files_do_not_keep_old_provider_wording(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        target_files = [
            os.path.join(project_root, "core", "text_corrector.py"),
            os.path.join(project_root, "core", "storyboard_generator.py"),
            os.path.join(project_root, "core", "prompt_generator.py"),
            os.path.join(project_root, "start.bat"),
        ]

        for path in target_files:
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()

            self.assertNotIn("DeepSeek", content)
            self.assertNotIn("火山方舟", content)
            self.assertNotIn("豆包", content)

    def test_start_bat_error_hint_does_not_use_unescaped_pipe(self):
        project_root = os.path.dirname(os.path.dirname(__file__))
        start_bat_path = os.path.join(project_root, "start.bat")

        with open(start_bat_path, "r", encoding="utf-8") as file:
            content = file.read()

        self.assertIn("ImportError 或 RuntimeError", content)
        self.assertNotIn("ImportError|RuntimeError", content)

    def test_create_step_progress_compacts_columns_on_narrow_console(self):
        progress = _create_step_progress(Console(width=60, record=True))
        self.assertEqual(4, len(progress.columns))

        progress = _create_step_progress(Console(width=90, record=True))
        self.assertEqual(5, len(progress.columns))

        progress = _create_step_progress(Console(width=120, record=True))
        self.assertEqual(5, len(progress.columns))

    def test_compact_path_shortens_long_paths_on_narrow_console(self):
        console = Console(width=40, record=True)
        path = r"E:\text2story\output\一个很长很长的目录\一个很长很长的文件名_storyboard.txt"

        compacted = _compact_path(path, console_obj=console)

        self.assertLessEqual(len(compacted), 24)
        self.assertTrue(compacted.endswith("txt"))
        self.assertIn("...", compacted)


if __name__ == "__main__":
    unittest.main()
