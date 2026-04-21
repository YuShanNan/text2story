import re
import time
import unicodedata
from functools import lru_cache
from difflib import SequenceMatcher

from api.openai_client import OpenAICompatClient
from utils.file_utils import load_prompt, split_text
from utils.logger import get_logger
from utils.retry_utils import format_retry_limit, should_retry_attempt

logger = get_logger(__name__)


_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\.\s*")
_MAX_LINES_PER_GROUP = 8
_MIN_SOURCE_LINES_FOR_OVERSPLIT_CHECK = 8
_MECHANICAL_COPY_RATIO_THRESHOLD = 0.8
_FALLBACK_TARGET_RATIO = 0.7
_MAX_FALLBACK_GROUP_LINES = 4
_FLEXIBLE_STORYBOARD_PROMPT_NAMES = {"自由拆句分镜"}
_DEPENDENT_FRAGMENT_PREFIXES = (
    "和",
    "在",
    "就",
    "也",
    "还",
    "但",
    "却",
    "而",
    "可",
    "只",
    "又",
    "再",
    "才",
    "被",
    "把",
    "给",
    "对",
    "向",
    "从",
    "到",
    "等",
    "当",
    "要",
    "让",
    "将",
    "并",
    "并且",
    "而且",
    "如果",
    "因为",
    "所以",
    "但是",
    "不过",
    "哪怕",
    "甚至",
    "随后",
    "于是",
    "然后",
)
_DEPENDENT_FRAGMENT_EXACTS = {
    "第一时间",
    "作为佐证",
    "甚至",
    "证明",
    "结果",
    "到时候",
    "听到这话",
    "呵笑死",
}
_DEPENDENT_FRAGMENT_SUFFIXES = (
    "后",
    "时",
    "的时候",
    "之后",
    "之前",
    "的话",
)
_TRANSITION_FRAGMENT_EXACTS = {
    "我那时问过他",
    "我懂他的意思",
    "我答得很干脆",
    "我点点头",
    "我点了点头",
    "我不由想起上一世",
    "再然后",
    "说完",
}
_TRANSITION_FRAGMENT_PREFIXES = (
    "她说着",
    "她笑着",
    "她说完",
    "他说着",
    "他说完",
    "我答得很",
    "我不由想起",
    "我一边应着",
    "我一边说着",
    "我点点头",
    "我点了点头",
)
_DIRECT_RESPONSE_EXACTS = {
    "啊",
    "嗯",
    "没印象",
    "不喜欢",
    "可没有",
    "我没抛错",
    "我答应了",
    "我真的很害怕",
    "我终于死了心",
    "但我愿意啊",
    "骗子",
}
_PRIMARY_SPLIT_PUNCTUATION = "。！？?!；;"
_SECONDARY_SPLIT_PUNCTUATION = "，、,:："
_SCENE_SHIFT_PREFIXES = (
    "再睁眼",
    "一睁眼",
    "转眼",
    "下一刻",
    "下一秒",
    "下一瞬",
    "这时",
    "此时",
    "等到",
    "直到",
    "随后",
    "紧接着",
    "很快",
    "回到",
)
_NARRATION_FOLLOWUP_PREFIXES = (
    "她",
    "他",
    "聂",
    "崔",
    "当",
    "我真的",
    "我终于",
    "我这才",
    "我一把",
    "我心里",
    "马车里",
    "上了",
    "时间太久",
    "听到",
    "面对",
    "对上",
    "等到",
    "说完",
    "说罢",
)
_SPEECH_ACTION_PREFIXES = (
    "她说",
    "他说",
    "她笑",
    "他说着",
    "她说着",
    "她说完",
    "他说完",
    "她笑着",
    "他说罢",
    "她说罢",
)


def _source_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_storyboard_items(raw_output: str) -> list[str]:
    numbered_items = []
    plain_items = []
    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_numbered = bool(_NUMBERED_ITEM_RE.match(stripped))
        item = _NUMBERED_ITEM_RE.sub("", stripped)
        if item:
            plain_items.append(item)
            if is_numbered:
                numbered_items.append(item)
    return numbered_items or plain_items


def _normalize_for_alignment(text: str) -> str:
    chars = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch.isspace() or category.startswith("P") or category.startswith("Z"):
            continue
        chars.append(ch)
    return "".join(chars)


def _render_numbered_storyboards(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def _normalized_length(text: str) -> int:
    return len(_normalize_for_alignment(text))


def _is_flexible_storyboard_prompt(prompt_name: str | None) -> bool:
    if not prompt_name:
        return False
    if prompt_name in _FLEXIBLE_STORYBOARD_PROMPT_NAMES:
        return True
    return "自由拆句" in prompt_name


def _is_alignment_close_enough(source_total: str, item_total: str) -> bool:
    if source_total == item_total:
        return True
    if not source_total or not item_total:
        return False

    max_length_diff = max(4, len(source_total) // 200)
    if abs(len(source_total) - len(item_total)) > max_length_diff:
        return False

    return SequenceMatcher(None, source_total, item_total).ratio() >= 0.98


def _is_dependent_fragment(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True

    normalized = _normalize_for_alignment(stripped)
    if not normalized:
        return True

    if len(normalized) <= 4:
        return True

    return (
        _attaches_backward(stripped)
        or _attaches_forward(stripped)
    )


def _attaches_backward(text: str) -> bool:
    if text in _DEPENDENT_FRAGMENT_EXACTS:
        return True
    return any(text.startswith(prefix) for prefix in _DEPENDENT_FRAGMENT_PREFIXES)


def _attaches_forward(text: str) -> bool:
    return any(text.endswith(suffix) for suffix in _DEPENDENT_FRAGMENT_SUFFIXES)


def _is_strong_standalone_line(text: str) -> bool:
    normalized = _normalize_for_alignment(text)
    return len(normalized) >= 7 and not _is_dependent_fragment(text)


def _looks_like_transition_fragment(text: str) -> bool:
    normalized = _normalize_for_alignment(text)
    if not normalized:
        return True

    if normalized in _TRANSITION_FRAGMENT_EXACTS:
        return True

    if len(normalized) <= 12 and any(
        normalized.startswith(prefix) for prefix in _TRANSITION_FRAGMENT_PREFIXES
    ):
        return True

    return False


def _is_direct_response_fragment(text: str) -> bool:
    normalized = _normalize_for_alignment(text)
    if not normalized:
        return False

    if normalized in _DIRECT_RESPONSE_EXACTS:
        return True

    stripped = text.strip()
    if any(mark in stripped for mark in ("？", "?", "！", "!")):
        return True

    return False


def _starts_with_narration_followup(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(prefix) for prefix in _NARRATION_FOLLOWUP_PREFIXES)


def _starts_with_scene_shift(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(prefix) for prefix in _SCENE_SHIFT_PREFIXES)


def _looks_like_speech_action_fragment(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(prefix) for prefix in _SPEECH_ACTION_PREFIXES)


def _exact_line_match_ratio(source_lines: list[str], raw_items: list[str]) -> float:
    if len(source_lines) != len(raw_items) or not source_lines:
        return 0.0

    matches = 0
    for source_line, raw_item in zip(source_lines, raw_items):
        if _normalize_for_alignment(source_line) == _normalize_for_alignment(raw_item):
            matches += 1
    return matches / len(source_lines)


def _looks_like_mechanical_line_copy(source_lines: list[str], raw_items: list[str]) -> bool:
    source_count = len(source_lines)
    item_count = len(raw_items)
    if source_count < _MIN_SOURCE_LINES_FOR_OVERSPLIT_CHECK or not item_count:
        return False

    ratio = item_count / source_count
    if ratio < _MECHANICAL_COPY_RATIO_THRESHOLD:
        return False

    exact_match_ratio = _exact_line_match_ratio(source_lines, raw_items)
    if exact_match_ratio < 0.85:
        return False

    dependent_count = sum(1 for line in raw_items if _is_dependent_fragment(line))
    short_count = sum(1 for line in raw_items if _normalized_length(line) <= 8)
    suspicious_count = max(dependent_count, short_count)
    if suspicious_count < max(3, source_count // 10):
        return False

    return len(raw_items) >= max(2, int(source_count * _FALLBACK_TARGET_RATIO))


def _should_merge_into_fallback_group(current_lines: list[str], next_line: str) -> bool:
    if len(current_lines) >= _MAX_FALLBACK_GROUP_LINES:
        return False

    current_text = "".join(current_lines)
    current_length = _normalized_length(current_text)
    last_line = current_lines[-1]

    if _attaches_backward(next_line.strip()):
        return True

    if _attaches_forward(last_line.strip()) and current_length < 20:
        return True

    return False


def _regroup_oversplit_source_lines(source_lines: list[str]) -> list[str]:
    if not source_lines:
        return []

    regrouped = []
    current_group = [source_lines[0]]

    for next_line in source_lines[1:]:
        if _should_merge_into_fallback_group(current_group, next_line):
            current_group.append(next_line)
            continue

        regrouped.append("".join(current_group))
        current_group = [next_line]

    regrouped.append("".join(current_group))
    return regrouped


def _project_raw_items_onto_source_text(
    source_text: str,
    item_norms: list[str],
) -> list[str] | None:
    retained_positions = []
    for index, ch in enumerate(source_text):
        category = unicodedata.category(ch)
        if ch.isspace() or category.startswith("P") or category.startswith("Z"):
            continue
        retained_positions.append(index)

    expected_length = sum(len(item) for item in item_norms)
    if expected_length != len(retained_positions):
        return None

    projected_items = []
    cursor = 0
    for item_norm in item_norms:
        if not item_norm:
            return None

        start_index = retained_positions[cursor]
        next_cursor = cursor + len(item_norm)
        end_index = retained_positions[next_cursor] if next_cursor < len(retained_positions) else len(source_text)
        fragment = source_text[start_index:end_index].replace("\r", "").replace("\n", "").strip()
        if not fragment:
            return None

        projected_items.append(fragment)
        cursor = next_cursor

    return projected_items


def _should_merge_short_fragment_with_next(current_item: str, next_item: str) -> bool:
    if not next_item:
        return False

    if _is_direct_response_fragment(current_item):
        return False

    normalized_length = _normalized_length(current_item)
    stripped = current_item.strip()
    if (
        normalized_length >= 3
        and stripped
        and stripped[-1] in _PRIMARY_SPLIT_PUNCTUATION
        and not _looks_like_transition_fragment(current_item)
    ):
        return False

    if normalized_length > 12:
        return False

    return _is_dependent_fragment(current_item) or _looks_like_transition_fragment(current_item)


def _merge_short_dependent_items(items: list[str]) -> list[str]:
    if not items:
        return []

    merged_items = []
    current_item = items[0]
    for next_item in items[1:]:
        if _should_merge_short_fragment_with_next(current_item, next_item):
            current_item = f"{current_item}{next_item}"
            continue

        merged_items.append(current_item)
        current_item = next_item

    merged_items.append(current_item)
    return merged_items


def _split_dialogue_narration_item_once(item: str) -> list[str] | None:
    for index, ch in enumerate(item):
        if ch not in _PRIMARY_SPLIT_PUNCTUATION:
            continue

        left = item[: index + 1].strip()
        right = item[index + 1 :].strip()
        if not left or not right:
            continue

        left_length = _normalized_length(left)
        right_length = _normalized_length(right)
        if right_length < 4:
            continue

        if _looks_like_transition_fragment(left):
            continue

        is_direct_response = _is_direct_response_fragment(left)
        if left_length < 4 and not is_direct_response:
            continue

        if _fragment_is_too_dependent_for_split(right):
            continue

        if not (
            is_direct_response
            or _looks_like_speech_action_fragment(left)
            or (
                left_length <= 18
                and _starts_with_narration_followup(right)
            )
        ):
            continue

        return [left, right]

    return None


def _split_dialogue_narration_items(items: list[str]) -> list[str]:
    stabilized_items = []
    for item in items:
        pending = [item]
        while pending:
            current_item = pending.pop(0)
            split_items = _split_dialogue_narration_item_once(current_item)
            if split_items is None:
                stabilized_items.append(current_item)
                continue

            pending = split_items + pending

    return stabilized_items


def _split_independent_sentence_item_once(item: str) -> list[str] | None:
    for index, ch in enumerate(item):
        if ch not in _PRIMARY_SPLIT_PUNCTUATION:
            continue

        left = item[: index + 1].strip()
        right = item[index + 1 :].strip()
        if not left or not right:
            continue

        left_length = _normalized_length(left)
        right_length = _normalized_length(right)
        if left_length < 3 or right_length < 3:
            continue

        if _looks_like_transition_fragment(left):
            continue

        if _fragment_is_too_dependent_for_split(right) and not _starts_with_scene_shift(right):
            continue

        if _looks_like_transition_fragment(right):
            continue

        return [left, right]

    return None


def _split_independent_sentence_items(items: list[str]) -> list[str]:
    stabilized_items = []
    for item in items:
        pending = [item]
        while pending:
            current_item = pending.pop(0)
            split_items = _split_independent_sentence_item_once(current_item)
            if split_items is None:
                stabilized_items.append(current_item)
                continue

            pending = split_items + pending

    return stabilized_items


def _split_candidate_is_acceptable(
    left: str,
    right: str,
    priority: int,
) -> bool:
    left_length = _normalized_length(left)
    right_length = _normalized_length(right)
    min_length = 6 if priority == 0 else 10
    if left_length < min_length or right_length < min_length:
        return False

    if _fragment_is_too_dependent_for_split(left) or _fragment_is_too_dependent_for_split(right):
        return False

    if _looks_like_transition_fragment(left) or _looks_like_transition_fragment(right):
        return False

    return True


def _fragment_is_too_dependent_for_split(text: str) -> bool:
    normalized = _normalize_for_alignment(text)
    if not normalized:
        return True

    if len(normalized) <= 10:
        return _is_dependent_fragment(text)

    return False


def _split_overlong_item_once(item: str) -> list[str] | None:
    if _normalized_length(item) <= 40:
        return None

    primary_candidates = []
    secondary_candidates = []
    for index, ch in enumerate(item):
        if ch in _PRIMARY_SPLIT_PUNCTUATION:
            priority = 0
        elif ch in _SECONDARY_SPLIT_PUNCTUATION:
            priority = 1
        else:
            continue

        left = item[: index + 1].strip()
        right = item[index + 1 :].strip()
        if not left or not right:
            continue

        if not _split_candidate_is_acceptable(left, right, priority):
            continue

        max_side_length = max(_normalized_length(left), _normalized_length(right))
        if priority == 1 and max_side_length > 40:
            continue

        score = (
            max_side_length,
            abs(_normalized_length(left) - _normalized_length(right)),
        )
        candidate = (score, [left, right])
        if priority == 0:
            primary_candidates.append(candidate)
        else:
            secondary_candidates.append(candidate)

    if primary_candidates:
        return min(primary_candidates, key=lambda item: item[0])[1]
    if secondary_candidates:
        return min(secondary_candidates, key=lambda item: item[0])[1]
    return None


def _split_overlong_items(items: list[str]) -> list[str]:
    stabilized_items = []
    for item in items:
        pending = [item]
        while pending:
            current_item = pending.pop(0)
            split_items = _split_overlong_item_once(current_item)
            if split_items is None:
                stabilized_items.append(current_item)
                continue

            pending = split_items + pending

    return stabilized_items


def _stabilize_flexible_storyboard_items(items: list[str]) -> list[str]:
    stabilized_items = _merge_short_dependent_items(items)
    stabilized_items = _split_independent_sentence_items(stabilized_items)
    stabilized_items = _split_dialogue_narration_items(stabilized_items)
    stabilized_items = _split_overlong_items(stabilized_items)
    stabilized_items = _split_independent_sentence_items(stabilized_items)
    stabilized_items = _split_dialogue_narration_items(stabilized_items)
    return _merge_short_dependent_items(stabilized_items)


def _build_flexible_source_fallback(source_lines: list[str]) -> list[str]:
    return _stabilize_flexible_storyboard_items(source_lines)


def _normalize_storyboard_output_result(
    source_text: str,
    raw_output: str,
    prompt_name: str = "default",
) -> dict[str, object]:
    source_lines = _source_lines(source_text)
    if not source_lines:
        return {
            "text": raw_output.strip(),
            "used_source_fallback": False,
        }

    raw_items = _parse_storyboard_items(raw_output)
    if not raw_items:
        return {
            "text": _render_numbered_storyboards(source_lines),
            "used_source_fallback": True,
        }

    source_norms = [_normalize_for_alignment(line) for line in source_lines]
    item_norms = [_normalize_for_alignment(item) for item in raw_items]

    source_total = "".join(source_norms)
    item_total = "".join(item_norms)

    if _is_flexible_storyboard_prompt(prompt_name) and source_total != item_total:
        return {
            "text": _render_numbered_storyboards(_build_flexible_source_fallback(source_lines)),
            "used_source_fallback": False,
        }

    if not _is_alignment_close_enough(source_total, item_total):
        return {
            "text": _render_numbered_storyboards(source_lines),
            "used_source_fallback": True,
        }

    if _is_flexible_storyboard_prompt(prompt_name):
        projected_items = _project_raw_items_onto_source_text(source_text, item_norms)
        if projected_items is not None:
            stabilized_items = _stabilize_flexible_storyboard_items(projected_items)
            return {
                "text": _render_numbered_storyboards(stabilized_items),
                "used_source_fallback": False,
            }

    if _looks_like_mechanical_line_copy(source_lines, raw_items):
        regrouped_items = _regroup_oversplit_source_lines(source_lines)
        if len(regrouped_items) < len(source_lines):
            return {
                "text": _render_numbered_storyboards(regrouped_items),
                "used_source_fallback": False,
            }

    grouped_items = _group_source_lines_by_raw_items(source_lines, source_norms, item_norms)
    if grouped_items is None:
        return {
            "text": _render_numbered_storyboards(raw_items),
            "used_source_fallback": False,
        }

    return {
        "text": _render_numbered_storyboards(grouped_items),
        "used_source_fallback": False,
    }


def _group_similarity_score(source_chunk: str, item_chunk: str) -> float:
    if source_chunk == item_chunk:
        return 1.0

    score = SequenceMatcher(None, source_chunk, item_chunk).ratio()
    if source_chunk in item_chunk or item_chunk in source_chunk:
        score = min(1.0, score + 0.01)
    return score


def _is_group_match_acceptable(source_chunk: str, item_chunk: str) -> bool:
    if not source_chunk or not item_chunk:
        return False

    length_diff = abs(len(source_chunk) - len(item_chunk))
    max_length_diff = max(2, len(source_chunk) // 15)
    if length_diff > max_length_diff:
        return False

    return _group_similarity_score(source_chunk, item_chunk) >= 0.94


def _group_source_lines_by_raw_items(
    source_lines: list[str],
    source_norms: list[str],
    item_norms: list[str],
) -> list[str] | None:
    source_count = len(source_lines)
    item_count = len(item_norms)

    if item_count > source_count:
        return None

    @lru_cache(maxsize=None)
    def solve(source_index: int, item_index: int) -> tuple[float, tuple[int, ...]] | None:
        if item_index == item_count:
            if source_index == source_count:
                return 0.0, ()
            return None

        remaining_items = item_count - item_index
        remaining_lines = source_count - source_index
        if remaining_lines < remaining_items:
            return None

        max_end = source_count - (remaining_items - 1)
        if remaining_items > 1:
            max_end = min(max_end, source_index + _MAX_LINES_PER_GROUP)

        best_result = None
        best_score = float("-inf")
        combined = ""

        for end_index in range(source_index + 1, max_end + 1):
            combined += source_norms[end_index - 1]
            if not _is_group_match_acceptable(combined, item_norms[item_index]):
                continue

            tail_result = solve(end_index, item_index + 1)
            if tail_result is None:
                continue

            total_score = _group_similarity_score(combined, item_norms[item_index]) + tail_result[0]
            if total_score > best_score:
                best_score = total_score
                best_result = (total_score, (end_index,) + tail_result[1])

        return best_result

    result = solve(0, 0)
    if result is None:
        return None

    grouped_items = []
    start_index = 0
    for end_index in result[1]:
        grouped_items.append("".join(source_lines[start_index:end_index]))
        start_index = end_index

    return grouped_items


def normalize_storyboard_output(
    source_text: str,
    raw_output: str,
    prompt_name: str = "default",
) -> str:
    return _normalize_storyboard_output_result(source_text, raw_output, prompt_name)["text"]


class StoryboardGenerationUnstableError(RuntimeError):
    """Raised when storyboard generation keeps falling back to source text."""


class StoryboardGenerator:
    """使用统一模型生成分镜脚本"""

    def __init__(self, client: OpenAICompatClient, model: str,
                 prompts_dir: str, max_chunk_size: int = 3000,
                 fallback_model: str = None):
        self.client = client
        self.model = model
        self.prompts_dir = prompts_dir
        self.max_chunk_size = max_chunk_size
        self.fallback_model = fallback_model

    def generate(self, text: str, prompt_name: str = "default") -> str:
        storyboard_items = []
        for event in self.iter_generate_progress(text, prompt_name):
            normalized_chunk = event.get("normalized_content") or normalize_storyboard_output(
                event["source_chunk"],
                event["content"],
                prompt_name=prompt_name,
            )
            storyboard_items.extend(_parse_storyboard_items(normalized_chunk))

        if not storyboard_items:
            return normalize_storyboard_output(text, "", prompt_name=prompt_name)

        return _render_numbered_storyboards(storyboard_items)

    def iter_generate_progress(self, text: str, prompt_name: str = "default"):
        """
        将修正后的文案生成分镜脚本。
        text: 修正后的文案
        prompt_name: 使用的提示词名称
        """
        system_prompt = load_prompt(self.prompts_dir, "storyboard", prompt_name)
        chunks = split_text(text, self.max_chunk_size)
        total = len(chunks)

        logger.info(
            f"开始生成分镜 (共 {total} 段, "
            f"模型: {self.model}, 提示词: {prompt_name})"
        )

        context = ""
        total_start = time.perf_counter()

        for i, chunk in enumerate(chunks, start=1):
            chunk_start = time.perf_counter()
            logger.info(f"  生成第 {i}/{total} 段分镜... (Ctrl+C 可中断)")

            user_msg = chunk
            if context:
                user_msg = (
                    f"[上文分镜摘要]\n{context}\n\n"
                    f"[请继续为以下文案生成分镜，编号接续上文]\n{chunk}"
                )

            source_line_count = len(_source_lines(chunk))
            retry_limit_label = format_retry_limit(getattr(self.client, "max_retry", None))
            attempt = 0
            degraded_fallback = False
            fallback_warning = None
            while True:
                attempt += 1
                result = self.client.chat(
                    model=self.model,
                    system_prompt=system_prompt,
                    user_content=user_msg,
                    temperature=0.7,
                    fallback_model=self.fallback_model,
                )
                normalized_result = _normalize_storyboard_output_result(
                    chunk,
                    result,
                    prompt_name=prompt_name,
                )
                if (
                    normalized_result["used_source_fallback"]
                    and source_line_count >= 3
                ):
                    if should_retry_attempt(attempt, getattr(self.client, "max_retry", None)):
                        logger.warning(
                            "  第 %s/%s 段分镜结果退回原文，正在重试 (%s/%s)",
                            i,
                            total,
                            attempt + 1,
                            retry_limit_label,
                        )
                        continue
                    degraded_fallback = True
                    fallback_warning = (
                        f"第 {i}/{total} 段分镜未生成出稳定结果，"
                        f"已在达到 MAX_RETRY={retry_limit_label} 后自动降级为保守分镜输出。"
                    )
                    logger.warning("  %s", fallback_warning)
                break

            context_source = normalized_result["text"]
            context = context_source[-200:] if len(context_source) > 200 else context_source
            logger.info(f"  第 {i}/{total} 段分镜生成完成")
            yield {
                "content": result.strip(),
                "normalized_content": normalized_result["text"],
                "source_chunk": chunk,
                "chunk_index": i,
                "chunk_total": total,
                "chunk_elapsed_seconds": time.perf_counter() - chunk_start,
                "total_elapsed_seconds": time.perf_counter() - total_start,
                "degraded_fallback": degraded_fallback,
                "warning_message": fallback_warning,
            }

        logger.info("分镜生成完成")
