import re
import time

from utils.file_utils import load_prompt, read_file
from utils.logger import get_logger

DEFAULT_BATCH_SIZE = 10
NEGATIVE_PROMPT_PREFIX = "负面提示词："
FIXED_NEGATIVE_PROMPT = (
    "负面提示词：无衣物穿透、无多余人物、无杂乱元素、无面部混淆、无版权争议。"
)
logger = get_logger(__name__)


def _read_non_empty_lines(path: str) -> list[str]:
    content = read_file(path)
    return [line.strip() for line in content.splitlines() if line.strip()]


def _normalize_optimized_prompt(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return FIXED_NEGATIVE_PROMPT
    if NEGATIVE_PROMPT_PREFIX in normalized:
        return normalized
    return f"{normalized} {FIXED_NEGATIVE_PROMPT}"


def _split_prompt_and_negative(text: str) -> tuple[str, str]:
    if NEGATIVE_PROMPT_PREFIX not in text:
        return text, ""
    prompt_text, negative_prompt = text.split(NEGATIVE_PROMPT_PREFIX, 1)
    return prompt_text.strip(), f"{NEGATIVE_PROMPT_PREFIX}{negative_prompt.strip()}"


def _collapse_prompt_text(text: str) -> str:
    collapsed = re.sub(r"[，,]{2,}", "，", text)
    collapsed = re.sub(r"[。；;]{2,}", "。", collapsed)
    collapsed = re.sub(r"[，,](?=[。；;])", "", collapsed)
    collapsed = re.sub(r"^[，,。；;\s]+", "", collapsed)
    collapsed = re.sub(r"[，,。；;\s]+$", "", collapsed)
    return collapsed.strip()


def _sanitize_optimized_prompt(text: str, storyboard_text: str) -> str:
    prompt_text, negative_prompt = _split_prompt_and_negative(text)
    if not prompt_text:
        return text

    sanitized = prompt_text

    foreground_background_detail_patterns = [
        r"(?:前景|后景)(?:是|为)?[^，。；;]*(?:手部|肩颈|下颌线|嘴唇|眼部|手机|按键|界面)[^，。；;]*[，。；;]?",
        r"(?:前景|后景)[^，。；;]*(?:日历|床铺|墙面纹理|地板纹理)[^，。；;]*[，。；;]?",
    ]
    for pattern in foreground_background_detail_patterns:
        sanitized = re.sub(pattern, "", sanitized)

    disallowed_when_not_in_storyboard = {
        "phone_interface": {
            "storyboard_tokens": ("电话", "手机", "来电", "拨通", "拨打", "停机", "空号"),
            "detail_tokens": ("按键", "拨号键", "拨号界面", "号码界面", "空号提示", "屏幕显示", "界面", "磨损", "掉漆"),
            "replacement": "手持旧手机，目光看向手中旧手机",
        },
        "calendar_visualization": {
            "storyboard_tokens": ("日期", "年月日", "年", "月", "日"),
            "detail_tokens": ("日历", "翻页"),
            "replacement": "",
        },
    }

    replacement_insertions: list[str] = []
    for rule in disallowed_when_not_in_storyboard.values():
        has_context = any(token in storyboard_text for token in rule["storyboard_tokens"])
        for detail_token in rule["detail_tokens"]:
            if detail_token in storyboard_text:
                continue
            sanitized, replacements = re.subn(
                rf"[^，。；;]*{re.escape(detail_token)}[^，。；;]*[，。；;]?",
                "",
                sanitized,
            )
            if replacements and has_context and rule["replacement"]:
                replacement_insertions.append(rule["replacement"])

    sound_detail_tokens = ("风声", "水声", "回声", "铃声", "脚步声", "布料摩擦声", "扬声器", "声音从")
    for token in sound_detail_tokens:
        sanitized = re.sub(
            rf"[^，。；;]*{re.escape(token)}[^，。；;]*[，。；;]?",
            "",
            sanitized,
        )

    sanitized = _collapse_prompt_text(sanitized)

    if replacement_insertions:
        deduped_replacements = []
        for replacement in replacement_insertions:
            if replacement and replacement not in sanitized and replacement not in deduped_replacements:
                deduped_replacements.append(replacement)
        if deduped_replacements:
            sanitized = _collapse_prompt_text(
                "，".join(part for part in [sanitized, *deduped_replacements] if part)
            )

    if negative_prompt:
        return f"{sanitized} {negative_prompt}".strip()
    return sanitized


def _batched(items: list, batch_size: int):
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


def _build_optimize_user_content(
    row: dict[str, str],
    previous_row: dict[str, str] | None = None,
) -> str:
    parts = [
        f"[分镜原文]\n{row['storyboard_text']}",
        f"[原始画面提示词]\n{row['raw_image_prompt']}",
    ]

    if previous_row is not None:
        parts.extend(
            [
                (
                    "[Continuity reference only - previous storyboard / 连续性参考-上一条分镜]\n"
                    f"{previous_row['storyboard_text']}"
                ),
                (
                    "[Continuity reference only - previous raw image prompt / "
                    "连续性参考-上一条原始画面提示词]\n"
                    f"{previous_row['raw_image_prompt']}"
                ),
                (
                    "[Continuity reference only - previous optimized image prompt / "
                    "连续性参考-上一条优化后生图提示词]\n"
                    f"{previous_row['optimized_image_prompt']}"
                ),
            ]
        )

    return "\n\n".join(parts)


class PromptOptimizer:
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

    def optimize_files(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> str:
        optimized_lines = []
        for optimized_batch in self.iter_optimized_file_batches(
            storyboard_path=storyboard_path,
            raw_prompt_path=raw_prompt_path,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            optimized_lines.extend(optimized_batch)
        return "\n".join(optimized_lines)

    def iter_optimized_file_batches(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        optimized_batch = []
        for event in self.iter_optimized_file_progress(
            storyboard_path=storyboard_path,
            raw_prompt_path=raw_prompt_path,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            optimized_batch.append(event["optimized_line"])
            if event["batch_completed"]:
                yield optimized_batch
                optimized_batch = []

    def iter_optimized_file_progress(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        rows = self.build_rows_from_files(storyboard_path, raw_prompt_path)
        for event in self.iter_optimized_row_progress(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            yield {
                **event,
                "optimized_line": event["optimized_row"]["optimized_image_prompt"],
            }

    def build_rows_from_files(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
    ) -> list[dict[str, str]]:
        return self._build_file_rows(storyboard_path, raw_prompt_path)

    def optimize_rows(
        self,
        rows: list[dict[str, str]],
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> list[dict[str, str]]:
        optimized_rows = []
        for optimized_batch in self.iter_optimized_row_batches(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            optimized_rows.extend(optimized_batch)
        return optimized_rows

    def iter_optimized_row_batches(
        self,
        rows: list[dict[str, str]],
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        optimized_batch = []
        for event in self.iter_optimized_row_progress(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            optimized_batch.append(event["optimized_row"])
            if event["batch_completed"]:
                yield optimized_batch
                optimized_batch = []

    def iter_optimized_row_progress(
        self,
        rows: list[dict[str, str]],
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        system_prompt = load_prompt(
            self.prompts_dir, "image_prompt_optimize", prompt_name
        )
        batches = list(_batched(rows, batch_size))
        total = len(batches)
        total_rows = len(rows)
        total_start = time.perf_counter()

        logger.info(
            "开始画面提示词优化 (共 %s 条分镜, %s 批, 模型: %s, 提示词: %s)",
            total_rows,
            total,
            self.model,
            prompt_name,
        )

        completed_rows = 0
        previous_row = None
        for index, row_batch in enumerate(batches, start=1):
            batch_start = time.perf_counter()
            batch_row_total = len(row_batch)
            logger.info("  优化第 %s/%s 批... (Ctrl+C 可中断)", index, total)
            for batch_row_index, row in enumerate(row_batch, start=1):
                user_content = _build_optimize_user_content(
                    row=row,
                    previous_row=previous_row,
                )
                optimized_line = self.client.chat(
                    model=self.model,
                    system_prompt=system_prompt,
                    user_content=user_content,
                    temperature=0.7,
                    fallback_model=self.fallback_model,
                )
                optimized_row = {
                    "scene_id": row["scene_id"],
                    "storyboard_text": row["storyboard_text"],
                    "raw_image_prompt": row["raw_image_prompt"],
                    "optimized_image_prompt": _normalize_optimized_prompt(
                        _sanitize_optimized_prompt(
                            optimized_line,
                            row["storyboard_text"],
                        )
                    ),
                    "notes_cn": "",
                }
                previous_row = optimized_row
                completed_rows += 1
                batch_completed = batch_row_index == batch_row_total
                if batch_completed:
                    logger.info("  第 %s/%s 批优化完成", index, total)

                yield {
                    "optimized_row": optimized_row,
                    "row_index": completed_rows,
                    "row_total": total_rows,
                    "batch_index": index,
                    "batch_total": total,
                    "batch_row_index": batch_row_index,
                    "batch_row_total": batch_row_total,
                    "batch_elapsed_seconds": time.perf_counter() - batch_start,
                    "total_elapsed_seconds": time.perf_counter() - total_start,
                    "batch_completed": batch_completed,
                }

        logger.info("画面提示词优化完成")

    def _build_file_rows(
        self,
        storyboard_path: str,
        raw_prompt_path: str,
    ) -> list[dict[str, str]]:
        storyboard_lines = _read_non_empty_lines(storyboard_path)
        raw_prompt_lines = _read_non_empty_lines(raw_prompt_path)

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
