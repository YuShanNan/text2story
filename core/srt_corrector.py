import re
import time
from difflib import SequenceMatcher

from api.openai_client import OpenAICompatClient
from utils.file_utils import load_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


_SRT_TS_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,、\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,、\.]\d{3}"
)


def _is_srt_header(lines: list[str], i: int) -> bool:
    """检查 lines[i] 是否为 SRT 块序号行（紧接着时间戳行）。"""
    return (
        lines[i].strip().isdigit()
        and i + 1 < len(lines)
        and bool(_SRT_TS_RE.search(lines[i + 1]))
    )


def _split_by_block_header(content: str) -> list[str]:
    """按 SRT 块头（序号 + 时间戳）拆分无空行格式的字幕文件。"""
    lines = content.strip().split("\n")
    blocks: list[str] = []
    start = None
    for i, line in enumerate(lines):
        if _is_srt_header(lines, i):
            if start is not None:
                blocks.append("\n".join(lines[start:i]))
            start = i
    if start is not None:
        blocks.append("\n".join(lines[start:]))
    return [b.strip() for b in blocks if b.strip()]


def split_srt_blocks(srt_content: str) -> list[str]:
    """
    将 SRT 内容按字幕块分割。
    优先按空行分隔；若只有一块且内容明显含多个条目，则退回到
    按「序号 + 时间戳」头部分割，兼容无空行格式。
    """
    blocks = re.split(r"\n\s*\n", srt_content.strip())
    result = [b.strip() for b in blocks if b.strip()]
    if len(result) == 1 and result[0].count("\n") > 5:
        result = _split_by_block_header(result[0])
    return result


def batch_srt_blocks(blocks: list[str], max_chars: int = 3000) -> list[str]:
    """
    将字幕块按大小分批，每批不超过 max_chars 字符。
    以完整字幕块为单位分批，不会在字幕块中间截断。
    """
    batches = []
    current_batch = []
    current_size = 0

    for block in blocks:
        block_size = len(block) + 2  # +2 for \n\n separator
        if current_batch and current_size + block_size > max_chars:
            batches.append("\n\n".join(current_batch))
            current_batch = [block]
            current_size = len(block)
        else:
            current_batch.append(block)
            current_size += block_size

    if current_batch:
        batches.append("\n\n".join(current_batch))

    return batches


def _extract_correction_summary(input_batch: str, output_batch: str) -> str:
    """
    Compare input vs output SRT batches and produce a short correction diary.
    Only reports changed text fragments — never full block text — so it does
    not violate rules 9/10 (no borrowing of adjacent block text).
    """
    in_blocks = split_srt_blocks(input_batch)
    out_blocks = split_srt_blocks(output_batch)

    if len(in_blocks) != len(out_blocks):
        return ""

    corrections = []
    for idx, (in_blk, out_blk) in enumerate(zip(in_blocks, out_blocks)):
        in_lines = in_blk.split("\n")
        out_lines = out_blk.split("\n")
        if len(in_lines) < 3 or len(out_lines) < 3:
            continue
        in_text = " ".join(in_lines[2:])
        out_text = " ".join(out_lines[2:])
        if in_text == out_text:
            continue

        matcher = SequenceMatcher(None, in_text, out_text)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                before = in_text[i1:i2].strip()
                after = out_text[j1:j2].strip()
                if before and after and before != after:
                    corrections.append(f"第{idx+1}条: '{before}'→'{after}'")
            elif tag == "delete":
                deleted = in_text[i1:i2].strip()
                if deleted:
                    corrections.append(f"第{idx+1}条: 删除'{deleted}'")
            elif tag == "insert":
                inserted = out_text[j1:j2].strip()
                if inserted:
                    corrections.append(f"第{idx+1}条: 插入'{inserted}'")

    if not corrections:
        return ""

    MAX_ITEMS = 5
    summary = corrections[:MAX_ITEMS]
    remaining = len(corrections) - MAX_ITEMS
    if remaining > 0:
        summary.append(f"及另{remaining}处修正")
    return "；".join(summary)


class SrtCorrector:
    """直接修正 SRT 字幕文件，保留时间戳仅修改文案"""

    def __init__(self, client: OpenAICompatClient, model: str,
                 prompts_dir: str, max_chunk_size: int = 3000,
                 fallback_model: str = None):
        self.client = client
        self.model = model
        self.prompts_dir = prompts_dir
        self.max_chunk_size = max_chunk_size
        self.fallback_model = fallback_model

    def correct(self, srt_content: str, prompt_name: str = "default") -> str:
        corrected_parts = []
        for event in self.iter_correct_progress(srt_content, prompt_name):
            corrected_parts.append(event["content"])
        return "\n\n".join(corrected_parts)

    def iter_correct_progress(self, srt_content: str, prompt_name: str = "default"):
        """
        对 SRT 字幕文件进行 AI 修正，保留时间戳仅修改文案。
        srt_content: 完整的 SRT 文件内容
        prompt_name: 使用的提示词名称
        返回: 修正后的完整 SRT 内容
        """
        system_prompt = load_prompt(self.prompts_dir, "srt_correction", prompt_name)
        blocks = split_srt_blocks(srt_content)
        batches = batch_srt_blocks(blocks, self.max_chunk_size)
        total = len(batches)

        logger.info(
            f"开始 SRT 修正 (共 {len(blocks)} 条字幕, {total} 批, "
            f"模型: {self.model}, 提示词: {prompt_name})"
        )

        total_start = time.perf_counter()
        previous_correction_summary = None
        for i, batch in enumerate(batches, start=1):
            batch_start = time.perf_counter()
            logger.info(f"  修正第 {i}/{total} 批... (Ctrl+C 可中断)")

            if previous_correction_summary:
                user_content = (
                    f"[上一批修正摘要]\n{previous_correction_summary}\n\n"
                    f"[请继续修正以下SRT]\n{batch}"
                )
            else:
                user_content = batch

            expected_count = len(split_srt_blocks(batch))
            _BLOCK_RETRY = 3

            for block_attempt in range(_BLOCK_RETRY + 1):
                result = self.client.chat(
                    model=self.model,
                    system_prompt=system_prompt,
                    user_content=user_content,
                    temperature=0.3,
                    fallback_model=self.fallback_model,
                )
                output_blocks = split_srt_blocks(result.strip())
                if len(output_blocks) == expected_count:
                    break
                if block_attempt < _BLOCK_RETRY:
                    logger.warning(
                        f"  块数不匹配: 期望 {expected_count}，实际 {len(output_blocks)}，"
                        f"重试 {block_attempt + 1}/{_BLOCK_RETRY}"
                    )
                else:
                    logger.warning(
                        f"  块数仍不匹配: 期望 {expected_count}，实际 {len(output_blocks)}，使用当前输出"
                    )

            try:
                previous_correction_summary = _extract_correction_summary(
                    batch, result.strip()
                )
            except (ValueError, IndexError):
                previous_correction_summary = None
                logger.warning("  提取修正摘要失败，下一批将不传递上下文")

            logger.info(f"  第 {i}/{total} 批修正完成")
            yield {
                "content": result.strip(),
                "batch_index": i,
                "batch_total": total,
                "batch_elapsed_seconds": time.perf_counter() - batch_start,
                "total_elapsed_seconds": time.perf_counter() - total_start,
            }

        logger.info("SRT 修正完成")
