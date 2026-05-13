import os
import time

from api.openai_client import OpenAICompatClient
from utils.file_utils import load_prompt, split_text
from utils.logger import get_logger

logger = get_logger(__name__)


class StoryboardGenerator:
    """使用统一模型生成分镜脚本"""

    def __init__(self, client: OpenAICompatClient, model: str,
                 prompts_dir: str, max_chunk_size: int = 15000,
                 fallback_model: str = None,
                 thinking_enabled: bool | None = None,
                 reasoning_effort: str | None = None):
        self.client = client
        self.model = model
        self.prompts_dir = prompts_dir
        self.max_chunk_size = max_chunk_size
        self.fallback_model = fallback_model
        self.thinking_enabled = thinking_enabled
        self.reasoning_effort = reasoning_effort

    def generate(self, text: str, prompt_name: str = "default") -> str:
        results = []
        for event in self.iter_generate_progress(text, prompt_name):
            results.append(event["content"])
        return "\n".join(results)

    def iter_generate_progress(self, text: str, prompt_name: str = "default",
                              output_file: str | None = None):
        system_prompt = load_prompt(self.prompts_dir, "storyboard", prompt_name)

        # max_chunk_size=0 → 一次性全量发送
        if self.max_chunk_size == 0:
            total = 1
            logger.info(
                f"开始生成分镜 (一次性全量发送, "
                f"模型: {self.model}, 提示词: {prompt_name})"
            )
        else:
            chunks = split_text(text, self.max_chunk_size)
            total = len(chunks)
            logger.info(
                f"开始生成分镜 (共 {total} 段, "
                f"模型: {self.model}, 提示词: {prompt_name})"
            )

        context = ""
        total_start = time.perf_counter()

        for i, chunk in enumerate(([text.strip()] if self.max_chunk_size == 0
                                   else split_text(text, self.max_chunk_size)),
                                   start=1):
            chunk_start = time.perf_counter()
            logger.info(f"  第 {i}/{total} 段 等待模型响应... (Ctrl+C 可中断)")

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
                max_tokens=16000,
                fallback_model=self.fallback_model,
                thinking_enabled=self.thinking_enabled,
                reasoning_effort=self.reasoning_effort,
            )

            context_source = result.strip()
            if len(context_source) > 200:
                context = context_source[-200:]
                # 退到上一个换行处，避免从半行截断
                nl = context_source[:-200].rfind("\n")
                if nl > 0:
                    context = context_source[nl + 1:]
            else:
                context = context_source
            logger.info(f"  第 {i}/{total} 段分镜生成完成")
            content = result.strip()
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "a", encoding="utf-8-sig") as f:
                    if i == 1:
                        f.write(content)
                    else:
                        f.write("\n" + content)
            yield {
                "content": content,
                "chunk_index": i,
                "chunk_total": total,
                "chunk_elapsed_seconds": time.perf_counter() - chunk_start,
                "total_elapsed_seconds": time.perf_counter() - total_start,
            }

        logger.info("分镜生成完成")
