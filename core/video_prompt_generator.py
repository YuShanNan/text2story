from utils.file_utils import load_prompt, read_non_empty_lines, normalize_whitespace
from utils.logger import get_logger

DEFAULT_BATCH_SIZE = 10
logger = get_logger(__name__)


def _normalize_video_prompt(text: str) -> str:
    return normalize_whitespace(text)


class VideoPromptGenerator:
    def __init__(
        self,
        client,
        model: str,
        prompts_dir: str,
        fallback_model: str = None,
    ):
        self.client = client
        self.model = model
        self.prompts_dir = prompts_dir
        self.fallback_model = fallback_model

    def build_rows_from_files(
        self,
        storyboard_path: str,
        optimized_image_prompt_path: str,
    ) -> list[dict[str, str]]:
        storyboard_lines = read_non_empty_lines(storyboard_path)
        optimized_image_prompt_lines = read_non_empty_lines(
            optimized_image_prompt_path
        )

        if len(storyboard_lines) != len(optimized_image_prompt_lines):
            raise ValueError(
                "分镜段数与优化后生图提示词段数不一致: "
                f"{len(storyboard_lines)} != {len(optimized_image_prompt_lines)}"
            )

        return [
            {
                "scene_id": str(index),
                "storyboard_text": storyboard_line,
                "optimized_image_prompt": optimized_image_prompt_line,
            }
            for index, (storyboard_line, optimized_image_prompt_line) in enumerate(
                zip(storyboard_lines, optimized_image_prompt_lines), start=1
            )
        ]

    def generate_files_batch(
        self,
        storyboard_path: str | None = None,
        optimized_image_prompt_path: str | None = None,
        rows: list[dict[str, str]] | None = None,
        prompt_name: str = "default",
        rows_per_batch: int = 50,
        output_file: str | None = None,
    ):
        """批量模式：全量行一次性传入，分批次输出并自动校验。

        将全部行拼接为一个 user message，要求模型按 rows_per_batch 分批输出。
        每批完成后自动核对条数，确认后继续下一批。每批 yield 一次进度事件
        （含 batch_lines），最后 yield 最终结果字符串。
        若指定 output_file，每批完成后立即追加写入。
        """
        if rows is None:
            if storyboard_path is None or optimized_image_prompt_path is None:
                raise ValueError(
                    "必须提供 rows 参数，或同时提供 storyboard_path + optimized_image_prompt_path"
                )
            rows = self.build_rows_from_files(
                storyboard_path, optimized_image_prompt_path
            )

        system_prompt = load_prompt(
            self.prompts_dir, "video_prompt_from_image", prompt_name
        )
        total = len(rows)

        all_rows_text = "\n\n".join(
            f"[{i + 1}] 分镜原文：{row['storyboard_text']}\n"
            f"    优化后生图提示词：{row['optimized_image_prompt']}"
            for i, row in enumerate(rows)
        )

        first_batch_count = min(rows_per_batch, total)
        initial_user = (
            f"以下是 {total} 条分镜和对应的优化后生图提示词。\n\n"
            f"{all_rows_text}\n\n"
            f"请先生成前 {first_batch_count} 条的视频提示词，"
            f"每条占一行，按顺序输出。完成后不要输出其他内容。"
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": initial_user})

        all_lines: list[str] = []
        completed = 0
        batch_index = 0
        batch_total = (total + rows_per_batch - 1) // rows_per_batch

        logger.info(
            "开始批量视频提示词生成 (共 %s 条分镜, %s 批, 模型: %s)",
            total,
            batch_total,
            self.model,
        )

        zero_growth_streak = 0
        while completed < total:
            batch_index += 1
            result = self.client.chat_multi_turn(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=16000,
                fallback_model=self.fallback_model,
            )
            messages.append({"role": "assistant", "content": result})

            lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
            needed = min(rows_per_batch, total - completed)
            batch_lines = lines[:needed]
            all_lines.extend(batch_lines)
            completed += len(batch_lines)

            logger.info(
                "  第 %s/%s 批生成完成 (%s/%s 条)", batch_index, batch_total, completed, total
            )
            progress = {"completed": completed, "total": total,
                   "batch_index": batch_index, "batch_total": batch_total,
                   "batch_lines": list(batch_lines)}
            if output_file:
                import os as _os
                _os.makedirs(_os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "a", encoding="utf-8-sig") as f:
                    if batch_index == 1:
                        f.write("\n".join(batch_lines))
                    else:
                        f.write("\n" + "\n".join(batch_lines))
            yield progress

            zero_growth_streak = zero_growth_streak + 1 if len(batch_lines) == 0 else 0
            if zero_growth_streak >= 3:
                logger.warning("  连续 %s 批无有效输出，强行终止生成", zero_growth_streak)
                break

            if completed >= total:
                break

            next_count = min(rows_per_batch, total - completed)
            confirm = (
                f"已生成并确认前 {completed} 条。"
                f"请继续生成第 {completed + 1}-{completed + next_count} 条的"
                f"视频提示词，每条占一行，按顺序输出。"
            )
            messages.append({"role": "user", "content": confirm})

        final_lines = [_normalize_video_prompt(line) for line in all_lines]

        logger.info("批量视频提示词生成完成 (%s 条)", len(final_lines))
        yield "\n".join(final_lines)
