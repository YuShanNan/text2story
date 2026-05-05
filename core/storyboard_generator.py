import time

from api.openai_client import OpenAICompatClient
from utils.file_utils import load_prompt, split_text
from utils.logger import get_logger

logger = get_logger(__name__)


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
        results = []
        for event in self.iter_generate_progress(text, prompt_name):
            results.append(event["content"])
        return "\n".join(results)

    def iter_generate_progress(self, text: str, prompt_name: str = "default"):
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

            result = self.client.chat(
                model=self.model,
                system_prompt=system_prompt,
                user_content=user_msg,
                temperature=0.7,
                fallback_model=self.fallback_model,
            )

            context_source = result.strip()
            context = context_source[-200:] if len(context_source) > 200 else context_source
            logger.info(f"  第 {i}/{total} 段分镜生成完成")
            yield {
                "content": result.strip(),
                "normalized_content": result.strip(),
                "chunk_index": i,
                "chunk_total": total,
                "chunk_elapsed_seconds": time.perf_counter() - chunk_start,
                "total_elapsed_seconds": time.perf_counter() - total_start,
            }

        logger.info("分镜生成完成")
