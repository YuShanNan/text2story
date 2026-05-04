import re

from utils.file_utils import load_prompt, read_file, read_non_empty_lines, normalize_whitespace
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
    ) -> str:
        """批量模式：全量行一次性传入，分批次输出并自动校验。

        将全部行拼接为一个 user message，要求模型按 rows_per_batch 分批输出。
        每批完成后自动核对条数，确认后继续下一批，直到全部完成。
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

        logger.info(
            "开始批量画面提示词优化 (共 %s 条分镜, 每批 %s 条, 模型: %s)",
            total,
            rows_per_batch,
            self.model,
        )

        while completed < total:
            result = self.client.chat_multi_turn(
                model=self.model,
                messages=messages,
                temperature=0.7,
                fallback_model=self.fallback_model,
            )
            messages.append({"role": "assistant", "content": result})

            lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
            needed = min(rows_per_batch, total - completed)
            batch_lines = lines[:needed]
            all_lines.extend(batch_lines)
            completed += len(batch_lines)

            logger.info(
                "  批量优化: 已获取 %s/%s 条", completed, total
            )

            if completed >= total:
                break

            next_count = min(rows_per_batch, total - completed)
            confirm = (
                f"已生成并确认前 {completed} 条。"
                f"请继续生成第 {completed + 1}-{completed + next_count} 条的"
                f"优化后提示词，每条占一行，按顺序输出。"
            )
            messages.append({"role": "user", "content": confirm})

        final_lines = []
        for i, line in enumerate(all_lines):
            sanitized = _sanitize_optimized_prompt(line, rows[i]["storyboard_text"])
            normalized = _normalize_optimized_prompt(sanitized)
            final_lines.append(normalized)

        logger.info("批量画面提示词优化完成 (%s 条)", len(final_lines))
        return "\n".join(final_lines)

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
