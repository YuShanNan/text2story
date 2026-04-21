import unittest

from rich.console import Console

from core.interactive import (
    run_prompt_generation_with_progress,
    run_srt_correction_with_progress,
    run_storyboard_generation_with_progress,
)


class FakeCorrector:
    def iter_correct_progress(self, srt_content: str, prompt_name: str = "default"):
        yield {
            "content": "修正结果1",
            "batch_index": 1,
            "batch_total": 2,
            "batch_elapsed_seconds": 1.2,
            "total_elapsed_seconds": 1.2,
        }
        yield {
            "content": "修正结果2",
            "batch_index": 2,
            "batch_total": 2,
            "batch_elapsed_seconds": 2.4,
            "total_elapsed_seconds": 3.6,
        }


class FakeStoryboardGenerator:
    def iter_generate_progress(self, text: str, prompt_name: str = "default"):
        yield {
            "content": "分镜结果1",
            "chunk_index": 1,
            "chunk_total": 2,
            "chunk_elapsed_seconds": 1.1,
            "total_elapsed_seconds": 1.1,
        }
        yield {
            "content": "分镜结果2",
            "chunk_index": 2,
            "chunk_total": 2,
            "chunk_elapsed_seconds": 2.2,
            "total_elapsed_seconds": 3.3,
        }


class FakeNormalizedStoryboardGenerator:
    def iter_generate_progress(self, text: str, prompt_name: str = "default"):
        yield {
            "content": "原始结果1",
            "normalized_content": "1. 第一镜\n2. 第二镜",
            "source_chunk": "片段一",
            "chunk_index": 1,
            "chunk_total": 2,
            "chunk_elapsed_seconds": 1.1,
            "total_elapsed_seconds": 1.1,
        }
        yield {
            "content": "原始结果2",
            "normalized_content": "1. 第三镜",
            "source_chunk": "片段二",
            "chunk_index": 2,
            "chunk_total": 2,
            "chunk_elapsed_seconds": 2.2,
            "total_elapsed_seconds": 3.3,
        }


class FakeDegradedStoryboardGenerator:
    def iter_generate_progress(self, text: str, prompt_name: str = "default"):
        yield {
            "content": "原始结果1",
            "normalized_content": "1. 第一镜\n2. 第二镜",
            "source_chunk": "片段一",
            "chunk_index": 1,
            "chunk_total": 1,
            "chunk_elapsed_seconds": 1.1,
            "total_elapsed_seconds": 1.1,
            "degraded_fallback": True,
            "warning_message": "第 1/1 段分镜未生成出稳定结果，已在达到 MAX_RETRY=5 后自动降级为保守分镜输出。",
        }


class FakePromptGenerator:
    def iter_generate_progress(
        self,
        storyboard_text: str,
        mode: str = "both",
        image_prompt_name: str = "default",
        video_prompt_name: str = "default",
    ):
        yield {
            "prompt_type": "image",
            "prompt_label": "图片",
            "stage_index": 1,
            "stage_total": 2,
            "scene_index": 1,
            "scene_total": 2,
            "content": "图片结果1",
            "formatted_prompt": "图片格式1",
            "stage_elapsed_seconds": 1.5,
            "total_elapsed_seconds": 1.5,
        }
        yield {
            "prompt_type": "image",
            "prompt_label": "图片",
            "stage_index": 1,
            "stage_total": 2,
            "scene_index": 2,
            "scene_total": 2,
            "content": "图片结果2",
            "formatted_prompt": "图片格式2",
            "stage_elapsed_seconds": 2.8,
            "total_elapsed_seconds": 2.8,
        }
        yield {
            "prompt_type": "video",
            "prompt_label": "视频",
            "stage_index": 2,
            "stage_total": 2,
            "scene_index": 1,
            "scene_total": 1,
            "content": "视频结果1",
            "formatted_prompt": "视频格式1",
            "stage_elapsed_seconds": 1.0,
            "total_elapsed_seconds": 3.8,
        }


class GlobalProgressHelpersTest(unittest.TestCase):
    def test_run_srt_correction_with_progress_prints_timing_summary(self):
        console = Console(record=True)

        result = run_srt_correction_with_progress(
            corrector=FakeCorrector(),
            srt_content="test",
            prompt_name="default",
            console_obj=console,
        )

        self.assertEqual("修正结果1\n\n修正结果2", result)
        output = console.export_text()
        self.assertNotIn("第 2/2 批修正完成", output)
        self.assertNotIn("本批用时", output)
        self.assertNotIn("累计用时", output)

    def test_run_storyboard_generation_with_progress_prints_timing_summary(self):
        console = Console(record=True)

        result = run_storyboard_generation_with_progress(
            generator=FakeStoryboardGenerator(),
            text="test",
            prompt_name="default",
            console_obj=console,
        )

        self.assertEqual("1. test", result)
        output = console.export_text()
        self.assertNotIn("第 2/2 段分镜生成完成", output)
        self.assertNotIn("本段用时", output)
        self.assertNotIn("累计用时", output)

    def test_run_storyboard_generation_with_progress_uses_normalized_chunks(self):
        console = Console(record=True)

        result = run_storyboard_generation_with_progress(
            generator=FakeNormalizedStoryboardGenerator(),
            text="test",
            prompt_name="default",
            console_obj=console,
        )

        self.assertEqual("1. 第一镜\n2. 第二镜\n3. 第三镜", result)

    def test_run_storyboard_generation_with_progress_prints_degradation_warning(self):
        console = Console(record=True)

        result = run_storyboard_generation_with_progress(
            generator=FakeDegradedStoryboardGenerator(),
            text="test",
            prompt_name="default",
            console_obj=console,
        )

        self.assertEqual("1. 第一镜\n2. 第二镜", result)
        output = console.export_text()
        self.assertIn("分镜已降级输出", output)
        self.assertIn("MAX_RETRY=5", output)

    def test_run_prompt_generation_with_progress_prints_stage_timing_summary(self):
        console = Console(record=True)

        result = run_prompt_generation_with_progress(
            generator=FakePromptGenerator(),
            storyboard_text="test",
            mode="both",
            image_prompt_name="default",
            video_prompt_name="default",
            console_obj=console,
        )

        self.assertEqual("图片格式1\n\n图片格式2", result["image_prompts"])
        self.assertEqual("视频格式1", result["video_prompts"])
        output = console.export_text()
        self.assertNotIn("图片提示词 2/2 完成", output)
        self.assertNotIn("视频提示词 1/1 完成", output)
        self.assertNotIn("本阶段用时", output)
        self.assertNotIn("累计用时", output)


if __name__ == "__main__":
    unittest.main()
