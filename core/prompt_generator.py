import re
import time

from api.openai_client import OpenAICompatClient
from utils.file_utils import load_prompt
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_storyboard(storyboard_text: str) -> list[str]:
    """将分镜脚本文本拆分为独立分镜"""
    scenes = re.split(r"\n---\n", storyboard_text)
    result = [s.strip() for s in scenes if s.strip() and "分镜" in s]
    if not result:
        # 如果按 --- 分割不到，尝试按【分镜 开头分割
        scenes = re.split(r"(?=【分镜)", storyboard_text)
        result = [s.strip() for s in scenes if s.strip() and "分镜" in s]
    if not result:
        # 兜底：整段作为一个分镜
        result = [storyboard_text.strip()]
    return result


class PromptGenerator:
    """使用统一模型生成图片/视频提示词"""

    def __init__(self, client: OpenAICompatClient, model: str,
                 prompts_dir: str, fallback_model: str = None):
        self.client = client
        self.model = model
        self.prompts_dir = prompts_dir
        self.fallback_model = fallback_model

    def generate(self, storyboard_text: str, mode: str = "both",
                 image_prompt_name: str = "default",
                 video_prompt_name: str = "default") -> dict:
        result = {"image_prompts": [], "video_prompts": []}
        for event in self.iter_generate_progress(
            storyboard_text,
            mode=mode,
            image_prompt_name=image_prompt_name,
            video_prompt_name=video_prompt_name,
        ):
            result[f"{event['prompt_type']}_prompts"].append(event["formatted_prompt"])
        return {
            "image_prompts": "\n\n".join(result["image_prompts"]),
            "video_prompts": "\n\n".join(result["video_prompts"]),
        }

    def iter_generate_progress(
        self,
        storyboard_text: str,
        mode: str = "both",
        image_prompt_name: str = "default",
        video_prompt_name: str = "default",
    ):
        """
        将分镜脚本生成提示词。
        storyboard_text: 分镜脚本全文
        mode: image / video / both
        返回: {"image_prompts": str, "video_prompts": str}
        """
        scenes = parse_storyboard(storyboard_text)
        logger.info(f"解析到 {len(scenes)} 个分镜")

        stages = []
        if mode in ("image", "both"):
            stages.append(("image", "图片", "image_prompt", image_prompt_name))
        if mode in ("video", "both"):
            stages.append(("video", "视频", "video_prompt", video_prompt_name))

        total_start = time.perf_counter()
        for stage_index, (prompt_type, label, category, prompt_name) in enumerate(
            stages, start=1
        ):
            system_prompt = load_prompt(self.prompts_dir, category, prompt_name)
            scene_total = len(scenes)
            stage_start = time.perf_counter()

            logger.info(
                f"开始生成{label}提示词 (共 {scene_total} 个分镜, "
                f"模型: {self.model}, 提示词: {prompt_name})"
            )

            for scene_index, scene in enumerate(scenes, start=1):
                logger.info(
                    f"  生成第 {scene_index}/{scene_total} 个分镜的{label}提示词... (Ctrl+C 可中断)"
                )
                result = self.client.chat(
                    model=self.model,
                    system_prompt=system_prompt,
                    user_content=scene,
                    temperature=0.7,
                    fallback_model=self.fallback_model,
                )
                logger.info(
                    f"  第 {scene_index}/{scene_total} 个分镜的{label}提示词生成完成"
                )
                formatted_prompt = (
                    f"{'=' * 50}\n"
                    f"分镜 {scene_index}\n"
                    f"{'=' * 50}\n\n"
                    f"{result.strip()}\n"
                )
                yield {
                    "prompt_type": prompt_type,
                    "prompt_label": label,
                    "stage_index": stage_index,
                    "stage_total": len(stages),
                    "scene_index": scene_index,
                    "scene_total": scene_total,
                    "content": result.strip(),
                    "formatted_prompt": formatted_prompt,
                    "stage_elapsed_seconds": time.perf_counter() - stage_start,
                    "total_elapsed_seconds": time.perf_counter() - total_start,
                }

            logger.info(f"{label}提示词生成完成")
