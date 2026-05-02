import re
import time

from utils.file_utils import load_prompt, read_file, read_non_empty_lines, batched, normalize_whitespace
from utils.logger import get_logger

DEFAULT_BATCH_SIZE = 10
NEGATIVE_PROMPT_PREFIX = "负面提示词："
FIXED_NEGATIVE_PROMPT = (
    "负面提示词：无衣物穿透、无多余人物、无杂乱元素、无面部混淆、无版权争议。"
)
logger = get_logger(__name__)

# 预编译正则，避免每次调用 _sanitize_optimized_prompt 时重复编译
_FOREGROUND_BACKGROUND_PATTERNS = (
    re.compile(r"(?:前景|后景)(?:是|为)?[^，。；;]*(?:手部|肩颈|下颌线|嘴唇|眼部|手机|按键|界面)[^，。；;]*[，。；;]?"),
    re.compile(r"(?:前景|后景)[^，。；;]*(?:日历|床铺|墙面纹理|地板纹理)[^，。；;]*[，。；;]?"),
)

_DISALLOWED_WHEN_NOT_IN_STORYBOARD = {
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

_DETAIL_REMOVAL_TPL = r"[^，。；;]*<TOKEN>[^，。；;]*[，。；;]?"

_SOUND_DETAIL_TOKENS = ("风声", "水声", "回声", "铃声", "脚步声", "布料摩擦声", "扬声器", "声音从")

_PRECOMPILED_DETAIL_PATTERNS: dict[str, re.Pattern] = {}


def _get_detail_pattern(token: str) -> re.Pattern:
    pattern = _PRECOMPILED_DETAIL_PATTERNS.get(token)
    if pattern is None:
        pattern = re.compile(_DETAIL_REMOVAL_TPL.replace("<TOKEN>", re.escape(token)))
        _PRECOMPILED_DETAIL_PATTERNS[token] = pattern
    return pattern


# 用于快速退出的关键字集合：如果 prompt 文本中不包含任何这些 token，则跳过 sanitize
_SANITIZE_GUARD_TOKENS = frozenset(
    ("前景", "后景", "按键", "拨号键", "界面", "日历", "翻页",
     "风声", "水声", "回声", "铃声", "脚步声", "布料摩擦声", "扬声器", "声音从",
     "手部", "肩颈", "下颌线", "嘴唇", "眼部", "手机",
     "床铺", "墙面纹理", "地板纹理")
)

_COLLAPSE_RE_1 = re.compile(r"[，,]{2,}")
_COLLAPSE_RE_2 = re.compile(r"[。；;]{2,}")
_COLLAPSE_RE_3 = re.compile(r"[，,](?=[。；;])")
_COLLAPSE_RE_4 = re.compile(r"^[，,。；;\s]+|[，,。；;\s]+$")


def _normalize_optimized_prompt(text: str) -> str:
    normalized = normalize_whitespace(text)
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
    collapsed = _COLLAPSE_RE_1.sub("，", text)
    collapsed = _COLLAPSE_RE_2.sub("。", collapsed)
    collapsed = _COLLAPSE_RE_3.sub("", collapsed)
    collapsed = _COLLAPSE_RE_4.sub("", collapsed)
    return collapsed.strip()


def _sanitize_optimized_prompt(text: str, storyboard_text: str) -> str:
    prompt_text, negative_prompt = _split_prompt_and_negative(text)
    if not prompt_text:
        return text

    # 快速退出：如果文本中不包含任何需要处理的关键字，直接跳过清理
    if not any(token in prompt_text for token in _SANITIZE_GUARD_TOKENS):
        sanitized = _collapse_prompt_text(prompt_text)
        if negative_prompt:
            return f"{sanitized} {negative_prompt}".strip()
        return sanitized

    sanitized = prompt_text

    for pattern in _FOREGROUND_BACKGROUND_PATTERNS:
        sanitized = pattern.sub("", sanitized)

    replacement_insertions: list[str] = []
    for rule in _DISALLOWED_WHEN_NOT_IN_STORYBOARD.values():
        has_context = any(token in storyboard_text for token in rule["storyboard_tokens"])
        for detail_token in rule["detail_tokens"]:
            if detail_token in storyboard_text:
                continue
            sanitized, replacements = _get_detail_pattern(detail_token).subn("", sanitized)
            if replacements and has_context and rule["replacement"]:
                replacement_insertions.append(rule["replacement"])

    for token in _SOUND_DETAIL_TOKENS:
        sanitized = _get_detail_pattern(token).sub("", sanitized)

    sanitized = _collapse_prompt_text(sanitized)

    if replacement_insertions:
        deduped = [r for r in dict.fromkeys(replacement_insertions) if r and r not in sanitized]
        if deduped:
            sanitized = _collapse_prompt_text(
                "，".join(part for part in [sanitized, *deduped] if part)
            )

    if negative_prompt:
        return f"{sanitized} {negative_prompt}".strip()
    return sanitized


def _build_optimize_user_content(row: dict[str, str]) -> str:
    parts = [
        f"[分镜原文]\n{row['storyboard_text']}",
        f"[原始画面提示词]\n{row['raw_image_prompt']}",
    ]
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
        batches = list(batched(rows, batch_size))
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

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        completed_rows = 0
        for index, row_batch in enumerate(batches, start=1):
            batch_start = time.perf_counter()
            batch_row_total = len(row_batch)
            logger.info("  优化第 %s/%s 批... (Ctrl+C 可中断)", index, total)
            for batch_row_index, row in enumerate(row_batch, start=1):
                user_content = _build_optimize_user_content(row)
                messages.append({"role": "user", "content": user_content})
                optimized_line = self.client.chat_multi_turn(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    fallback_model=self.fallback_model,
                )
                messages.append({"role": "assistant", "content": optimized_line})
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
