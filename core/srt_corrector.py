import re
import time

from api.openai_client import OpenAICompatClient
from utils.file_utils import load_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


def split_srt_blocks(srt_content: str) -> list[str]:
    """
    将 SRT 内容按字幕块分割。
    每个字幕块包含：序号、时间轴、文案内容，以空行分隔。
    返回字幕块列表，每个元素是一个完整的字幕块字符串。
    """
    blocks = re.split(r"\n\s*\n", srt_content.strip())
    return [b.strip() for b in blocks if b.strip()]


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
        for i, batch in enumerate(batches, start=1):
            batch_start = time.perf_counter()
            logger.info(f"  修正第 {i}/{total} 批... (Ctrl+C 可中断)")
            result = self.client.chat(
                model=self.model,
                system_prompt=system_prompt,
                user_content=batch,
                temperature=0.3,
                fallback_model=self.fallback_model,
            )
            logger.info(f"  第 {i}/{total} 批修正完成")
            yield {
                "content": result.strip(),
                "batch_index": i,
                "batch_total": total,
                "batch_elapsed_seconds": time.perf_counter() - batch_start,
                "total_elapsed_seconds": time.perf_counter() - total_start,
            }

        logger.info("SRT 修正完成")
