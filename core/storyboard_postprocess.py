import re

from utils.logger import get_logger

logger = get_logger(__name__)


def postprocess_storyboard(text: str, max_chars: int = 30) -> str:
    """后处理分镜输出：在断句处拆分超过字数限制的长条目。

    拆分优先级：句号/问号/感叹号 → 逗号/分号 → 字符级硬拆分。
    """
    entries = _parse_entries(text)
    if not entries:
        return text
    split_entries = _split_long_entries(entries, max_chars)
    return _format_output(split_entries)


def _parse_entries(text: str) -> list[str]:
    """解析带编号的分镜文本为内容字符串列表。"""
    lines = text.strip().splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^\d+[\.\、\s]\s*', line)
        if match:
            content = line[match.end():].strip()
        else:
            content = line.strip()
        if content:
            entries.append(content)
    return entries


def _char_count(text: str) -> int:
    """统计字符数（不含空白和标点，按提示词规则）。"""
    # 1个汉字/数字/字母为1个字符，标点符号不计入
    cleaned = re.sub(r'[，。！？、；：""''「」『』【】《》（）\s]', '', text)
    return len(cleaned)


def _split_long_entries(entries: list[str], max_chars: int) -> list[str]:
    """将超过 max_chars 的条目在自然断句处拆分。"""
    result = []
    for entry in entries:
        if _char_count(entry) <= max_chars:
            result.append(entry)
            continue

        parts = _split_at_natural_boundary(entry, max_chars)
        result.extend(parts)
    return result


def _split_at_natural_boundary(text: str, max_chars: int) -> list[str]:
    """在自然断句处拆分长文本。返回拆分后的多个片段。

    拆分策略：
    1. 找到所有断句点（。！？）
    2. 贪心：尽量让每个片段 ≤ max_chars，但只在断句点拆分
    3. 无断句点时，依次尝试逗号/分号拆分、字符级硬拆分
    """
    # 找出所有断句位置
    breaks = []
    for m in re.finditer(r'[。！？]', text):
        breaks.append(m.end())

    if not breaks:
        # 没有自然断句点，尝试次要边界或字符级拆分
        sub = _split_at_secondary_boundary(text, max_chars)
        if len(sub) == 1 and _char_count(sub[0]) > max_chars:
            sub = _split_at_character_boundary(sub[0], max_chars)
        return sub if sub else [text]

    parts = []
    start = 0

    for i, pos in enumerate(breaks):
        segment = text[start:pos]
        # 看接下来到下一个断句点（或结尾）的内容
        if i + 1 < len(breaks):
            next_pos = breaks[i + 1]
        else:
            next_pos = len(text)

        combined = text[start:next_pos]

        if _char_count(combined) > max_chars:
            # 当前到下一个断句点会超长，在当前断句点拆分
            parts.append(segment)
            start = pos
        elif i == len(breaks) - 1:
            # 最后一个断句点，把剩余内容作为一个片段
            parts.append(text[start:])

    # 去空白检查
    cleaned = []
    for p in parts:
        p = p.strip()
        if p:
            cleaned.append(p)

    if not cleaned:
        return [text]

    # 检查是否有片段仍然超长（单句超长的情况）
    final = []
    for part in cleaned:
        if _char_count(part) > max_chars:
            sub_parts = _split_at_secondary_boundary(part, max_chars)
            # 如果次要边界也无法拆分，使用字符级硬拆分作为最后手段
            if len(sub_parts) == 1 and _char_count(sub_parts[0]) > max_chars:
                sub_parts = _split_at_character_boundary(sub_parts[0], max_chars)
            final.extend(sub_parts)
        else:
            final.append(part)

    return final if final else [text]


def _split_at_secondary_boundary(text: str, max_chars: int) -> list[str]:
    """在次要边界拆分：逗号、分号位置。仅用于单句超过 max_chars 的情况。

    要求拆分后两边至少各有 10 字，避免产生悬空短句。
    """
    breaks = []
    for m in re.finditer(r'[，；]', text):
        breaks.append(m.end())

    if not breaks:
        return [text]

    min_chars = 10  # 拆分后每边至少 10 字，避免悬空

    for pos in breaks:
        left = text[:pos]
        right = text[pos:]
        left_cnt = _char_count(left)
        right_cnt = _char_count(right)
        if (left_cnt >= min_chars and right_cnt >= min_chars
                and left_cnt <= max_chars and right_cnt <= max_chars):
            return [left.strip(), right.strip()]

    return [text]


def _split_at_character_boundary(text: str, max_chars: int) -> list[str]:
    """在字符级别拆分超长文本（无任何标点时的最后手段）。

    尽量等分，在中间位置拆分，避免产生过短的碎片。
    """
    if _char_count(text) <= max_chars:
        return [text]

    # 贪心按字符数均匀切分
    parts = []
    remaining = text
    while remaining:
        if _char_count(remaining) <= max_chars:
            parts.append(remaining)
            break
        # 找到 max_chars 字符处作为拆分点
        pos = _find_split_pos(remaining, max_chars)
        if pos == 0:
            pos = max_chars  # 极端情况，直接按字数截断
        parts.append(remaining[:pos])
        remaining = remaining[pos:]
    return [p for p in parts if p.strip()]


def _find_split_pos(text: str, max_chars: int) -> int:
    """在 text 中找到不超过 max_chars 的最远拆分位置。"""
    count = 0
    last_pos = 0
    for i, ch in enumerate(text):
        if re.match(r'[，。！？、；：""''「」『』【】《》（）\s]', ch):
            # 标点不计入字符数但可以作为拆分点
            continue
        count += 1
        if count <= max_chars:
            last_pos = i + 1
        else:
            break
    return last_pos if last_pos > 0 else max_chars


def _format_output(entries: list[str]) -> str:
    """格式化为带编号的分镜输出。"""
    lines = []
    for i, entry in enumerate(entries, start=1):
        lines.append(f"{i}. {entry}")
    return "\n".join(lines)


def audit_coverage(source_text: str, storyboard_text: str,
                   threshold: float = 0.9) -> dict:
    """检查原文内容在分镜输出中的覆盖率。

    将 source_text 每一非空行作为原子内容单元，
    在清洗后的 storyboard 中做子串匹配。

    Returns:
        {
            "covered": int,       # 已覆盖行数
            "total": int,          # 总行数
            "ratio": float,        # 覆盖率 (0.0~1.0)
            "uncovered": list[str], # 未覆盖的原文行
            "passed": bool,        # 是否达到阈值
        }
    """
    source_lines = [l.strip() for l in source_text.strip().split("\n")
                    if l.strip()]
    if not source_lines:
        return {"covered": 0, "total": 0, "ratio": 1.0,
                "uncovered": [], "passed": True}

    storyboard_clean = _strip_punctuation(storyboard_text)

    covered = 0
    uncovered = []
    for line in source_lines:
        clean = _strip_punctuation(line)
        if not clean:
            covered += 1
            continue
        if clean in storyboard_clean:
            covered += 1
        else:
            # 尝试滑动窗口匹配（允许轻微拼接偏差）
            if _fuzzy_match(clean, storyboard_clean):
                covered += 1
            else:
                uncovered.append(line)

    total = len(source_lines)
    ratio = covered / total if total > 0 else 1.0
    return {
        "covered": covered,
        "total": total,
        "ratio": ratio,
        "uncovered": uncovered,
        "passed": ratio >= threshold,
    }


def _strip_punctuation(text: str) -> str:
    """去除标点和空白，返回纯字符序列（用于子串匹配）。"""
    return re.sub(r'[，。！？、；：""''「」『』【】《》（）\s]', '', text)


def _fuzzy_match(source: str, target: str, min_sub_len: int = 4) -> bool:
    """滑动窗口模糊匹配：将 source 按 min_sub_len 切分，全部窗口都在 target 中则匹配。"""
    if len(source) < min_sub_len:
        return source in target
    step = max(1, len(source) // 3)
    for start in range(0, len(source) - min_sub_len + 1, step):
        sub = source[start:start + min_sub_len]
        if sub not in target:
            extended = source[start:start + min_sub_len + 2] if start + min_sub_len + 2 <= len(source) else None
            if extended is None or extended not in target:
                return False
    return True


def generate_with_audit(
    generate_fn,
    source_text: str,
    max_retries: int = 3,
    threshold: float = 0.9,
) -> tuple[str, dict, int]:
    """带覆盖率审计的分镜生成，自动重试直到达标或耗尽重试次数。

    Args:
        generate_fn: 无参回调，返回原始分镜文本 (str)
        source_text: 原文内容（用于审计对比）
        max_retries: 最大重试次数
        threshold: 覆盖率阈值

    Returns:
        (storyboard_text, audit_result, attempt_count)
    """
    storyboard_text = ""
    audit = {}
    for attempt in range(1, max_retries + 1):
        raw = generate_fn()
        if not raw.strip():
            logger.warning("分镜生成产出空结果，重试 %d/%d", attempt, max_retries)
            continue
        storyboard_text = postprocess_storyboard(raw)
        audit = audit_coverage(source_text, storyboard_text, threshold)
        if audit["passed"]:
            logger.info(
                "覆盖率达标: %.1f%% (%d/%d)，第 %d 次尝试",
                audit["ratio"] * 100, audit["covered"], audit["total"], attempt,
            )
            return storyboard_text, audit, attempt
        logger.warning(
            "覆盖率不足: %.1f%% (%d/%d)，阈值 %.0f%%，第 %d/%d 次",
            audit["ratio"] * 100, audit["covered"], audit["total"],
            threshold * 100, attempt, max_retries,
        )
    if not storyboard_text.strip():
        raise RuntimeError("分镜生成多次尝试均产出空结果")
    logger.warning(
        "覆盖率审计 %d 次后仍未达标，保留最后一次结果 (%.1f%%)",
        max_retries, audit["ratio"] * 100 if audit else 0,
    )
    return storyboard_text, audit, max_retries
