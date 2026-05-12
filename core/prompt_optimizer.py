import os

from utils.file_utils import load_prompt, read_non_empty_lines
from utils.logger import get_logger

DEFAULT_BATCH_SIZE = 10
logger = get_logger(__name__)


class PromptOptimizer:
    def __init__(
        self,
        client,
        model: str,
        prompts_dir: str,
        fallback_model: str = None,
        thinking_enabled: bool | None = None,
    ):
        self.client = client
        self.model = model
        self.prompts_dir = prompts_dir
        self.fallback_model = fallback_model
        self.thinking_enabled = thinking_enabled

    def build_rows_from_files(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
    ) -> list[dict[str, str]]:
        return self._build_file_rows(storyboard_path, raw_prompt_path)

    def optimize_files_batch(
        self,
        storyboard_path: str | None = None,
        raw_prompt_path: str | None = None,
        rows: list[dict[str, str]] | None = None,
        prompt_name: str = "default",
        rows_per_batch: int = 50,
        output_file: str | None = None,
    ):
        """批量模式：全量原文一次性发送，chat_multi_turn 累积消息分批输出。

        全部行拼接为一个 user message 发送给模型，模型分批输出。
        每批完成后发送确认消息继续下一批。messages 累积保证模型始终
        拥有完整故事上下文，防止跨故事污染。
        每批 yield 一次进度事件（含 batch_lines），最后 yield 最终结果字符串。
        若指定 output_file，每批完成后立即追加写入。
        """
        if rows is None:
            if storyboard_path is None or raw_prompt_path is None:
                raise ValueError(
                    "必须提供 rows 参数，或同时提供 storyboard_path + raw_prompt_path"
                )
            rows = self._build_file_rows(storyboard_path, raw_prompt_path)

        system_prompt = load_prompt(
            self.prompts_dir, "image_prompt_optimize", prompt_name
        )
        total = len(rows)

        if total == 0:
            yield ""
            return

        all_rows_text = "\n\n".join(
            f"[{i + 1}] 分镜原文：{row['storyboard_text']}\n"
            f"    原始画面提示词：{row['raw_image_prompt']}"
            for i, row in enumerate(rows)
        )

        first_batch_count = min(rows_per_batch, total)
        initial_user = (
            f"以下是 {total} 条分镜和对应的原始画面提示词。\n\n"
            f"{all_rows_text}\n\n"
            f"请先生成前 {first_batch_count} 条的优化后提示词，"
            f"每条占一行，按顺序输出。完成后不要输出其他内容。"
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": initial_user})

        all_lines: list[str] = []
        completed = 0
        batch_index = 0
        batch_total = (total + rows_per_batch - 1) // rows_per_batch
        zero_growth_streak = 0

        logger.info(
            "开始批量画面提示词优化 (共 %s 条, %s 批, 每批最多 %s 条, 模型: %s)",
            total, batch_total, rows_per_batch, self.model,
        )

        while completed < total:
            batch_index += 1
            result = self.client.chat_multi_turn(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=16000,
                fallback_model=self.fallback_model,
                thinking_enabled=self.thinking_enabled,
            )
            messages.append({"role": "assistant", "content": result})

            lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
            needed = min(rows_per_batch, total - completed)
            batch_lines = lines[:needed]

            # 补齐不足行数（最多重试2次）
            retry_count = 0
            while len(batch_lines) < needed and retry_count < 2 and len(batch_lines) > 0:
                retry_count += 1
                missing = needed - len(batch_lines)
                miss_start = completed + len(batch_lines) + 1
                miss_end = completed + needed
                retry_msg = (
                    f"上一轮只输出了 {len(batch_lines)} 条，"
                    f"缺少第 {miss_start}-{miss_end} 条。"
                    f"请补充生成这 {missing} 条的优化后提示词，"
                    f"每条一行，按顺序输出。"
                )
                logger.warning(
                    "  第 %s 批缺少 %s 条，第 %s 次重试补齐 (第 %s-%s 条)",
                    batch_index, missing, retry_count, miss_start, miss_end,
                )
                messages.append({"role": "user", "content": retry_msg})
                extra_result = self.client.chat_multi_turn(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=16000,
                    fallback_model=self.fallback_model,
                    thinking_enabled=self.thinking_enabled,
                )
                messages.append({"role": "assistant", "content": extra_result})
                extra_lines = [l.strip() for l in extra_result.strip().split("\n") if l.strip()]
                batch_lines.extend(extra_lines[:missing])

            numbered_batch_lines = [
                f"{completed + j + 1}. {line}"
                for j, line in enumerate(batch_lines)
            ]

            all_lines.extend(numbered_batch_lines)
            completed += len(batch_lines)

            logger.info(
                "  第 %s/%s 批优化完成 (%s/%s 条)",
                batch_index, batch_total, completed, total,
            )
            progress = {
                "completed": completed, "total": total,
                "batch_index": batch_index, "batch_total": batch_total,
                "batch_lines": list(numbered_batch_lines),
            }
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "a", encoding="utf-8-sig") as f:
                    if batch_index == 1:
                        f.write("\n".join(numbered_batch_lines))
                    else:
                        f.write("\n" + "\n".join(numbered_batch_lines))
            yield progress

            zero_growth_streak = zero_growth_streak + 1 if len(batch_lines) == 0 else 0
            if zero_growth_streak >= 3:
                logger.warning("  连续 %s 批无有效输出，强行终止优化", zero_growth_streak)
                break

            if completed >= total:
                break

            next_count = min(rows_per_batch, total - completed)
            confirm = (
                f"已生成并确认前 {completed} 条。"
                f"请继续生成第 {completed + 1}-{completed + next_count} 条的"
                f"优化后提示词，每条占一行，按顺序输出。"
            )
            messages.append({"role": "user", "content": confirm})

        logger.info("批量画面提示词优化完成 (%s 条)", len(all_lines))
        yield "\n".join(all_lines)

    def _build_file_rows(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
    ) -> list[dict[str, str]]:
        storyboard_lines = read_non_empty_lines(storyboard_path)
        raw_prompt_lines = read_non_empty_lines(raw_prompt_path)

        if len(storyboard_lines) != len(raw_prompt_lines):
            raise ValueError(
                f"分镜段数与提示词段数不一致: {len(storyboard_lines)} != {len(raw_prompt_lines)}"
            )

        return [
            {
                "scene_id": str(index),
                "storyboard_text": storyboard_line,
                "raw_image_prompt": raw_prompt_line,
            }
            for index, (storyboard_line, raw_prompt_line) in enumerate(
                zip(storyboard_lines, raw_prompt_lines), start=1
            )
        ]

