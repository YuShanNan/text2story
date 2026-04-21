from api.openai_client import OpenAICompatClient
from utils.file_utils import load_prompt, split_text
from utils.logger import get_logger

logger = get_logger(__name__)


class TextCorrector:
    """使用统一模型进行文案提取和语义修正"""

    def __init__(self, client: OpenAICompatClient, model: str,
                 prompts_dir: str, max_chunk_size: int = 3000,
                 fallback_model: str = None):
        self.client = client
        self.model = model
        self.prompts_dir = prompts_dir
        self.max_chunk_size = max_chunk_size
        self.fallback_model = fallback_model

    def correct(self, text: str, prompt_name: str = "default") -> str:
        """
        对文本进行 AI 文案提取和语义修正。
        text: 从 SRT 转换来的原始文本
        prompt_name: 使用的提示词名称
        """
        system_prompt = load_prompt(self.prompts_dir, "correction", prompt_name)
        chunks = split_text(text, self.max_chunk_size)
        total = len(chunks)

        logger.info(
            f"开始语义修正 (共 {total} 段, "
            f"模型: {self.model}, 提示词: {prompt_name})"
        )

        corrected_parts = []
        for i, chunk in enumerate(chunks):
            logger.info(f"  修正第 {i + 1}/{total} 段... (Ctrl+C 可中断)")
            result = self.client.chat(
                model=self.model,
                system_prompt=system_prompt,
                user_content=chunk,
                temperature=0.3,
                fallback_model=self.fallback_model,
            )
            corrected_parts.append(result.strip())
            logger.info(f"  第 {i + 1}/{total} 段修正完成")

        full_result = "\n\n".join(corrected_parts)
        logger.info("语义修正完成")
        return full_result
