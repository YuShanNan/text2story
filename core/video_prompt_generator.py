import time

from utils.file_utils import load_prompt, read_file
from utils.logger import get_logger

DEFAULT_BATCH_SIZE = 10
logger = get_logger(__name__)


def _read_non_empty_lines(path: str) -> list[str]:
    content = read_file(path)
    return [line.strip() for line in content.splitlines() if line.strip()]


def _normalize_video_prompt(text: str) -> str:
    return " ".join(text.split())


def _build_video_user_content(
    row: dict[str, str],
    previous_generated_row: dict[str, str] | None = None,
) -> str:
    parts = [
        f"[Current storyboard / 分镜原文]\n{row['storyboard_text']}",
        f"[Current optimized image prompt / 优化后生图提示词]\n{row['optimized_image_prompt']}",
    ]

    if previous_generated_row is not None:
        parts.extend(
            [
                (
                    "[Continuity reference only - previous storyboard / 连续性参考-上一条分镜]\n"
                    f"{previous_generated_row['storyboard_text']}"
                ),
                (
                    "[Continuity reference only - previous optimized image prompt / 连续性参考-上一条优化后生图提示词]\n"
                    f"{previous_generated_row['optimized_image_prompt']}"
                ),
                (
                    "[Continuity reference only - previous video prompt / 连续性参考-上一条视频提示词]\n"
                    f"{previous_generated_row['video_prompt']}"
                ),
            ]
        )

    return "\n\n".join(parts)


def _batched(items: list, batch_size: int):
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


class VideoPromptGenerator:
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

    def generate_files(
        self,
        storyboard_path: str,
        optimized_image_prompt_path: str,
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> str:
        video_lines = []
        for generated_batch in self.iter_generate_file_batches(
            storyboard_path=storyboard_path,
            optimized_image_prompt_path=optimized_image_prompt_path,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            video_lines.extend(generated_batch)
        return "\n".join(video_lines)

    def iter_generate_file_batches(
        self,
        storyboard_path: str,
        optimized_image_prompt_path: str,
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        generated_batch = []
        for event in self.iter_generate_file_progress(
            storyboard_path=storyboard_path,
            optimized_image_prompt_path=optimized_image_prompt_path,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            generated_batch.append(event["video_line"])
            if event["batch_completed"]:
                yield generated_batch
                generated_batch = []

    def iter_generate_file_progress(
        self,
        storyboard_path: str,
        optimized_image_prompt_path: str,
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        rows = self.build_rows_from_files(
            storyboard_path=storyboard_path,
            optimized_image_prompt_path=optimized_image_prompt_path,
        )
        for event in self.iter_generate_row_progress(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            yield {**event, "video_line": event["generated_row"]["video_prompt"]}

    def build_rows_from_files(
        self,
        storyboard_path: str,
        optimized_image_prompt_path: str,
    ) -> list[dict[str, str]]:
        storyboard_lines = _read_non_empty_lines(storyboard_path)
        optimized_image_prompt_lines = _read_non_empty_lines(
            optimized_image_prompt_path
        )

        if len(storyboard_lines) != len(optimized_image_prompt_lines):
            raise ValueError(
                "分镜段数与优化后生图提示词段数不一致: "
                f"{len(storyboard_lines)} != {len(optimized_image_prompt_lines)}"
            )

        return [
            {
                "scene_id": str(index),
                "storyboard_text": storyboard_line,
                "optimized_image_prompt": optimized_image_prompt_line,
            }
            for index, (storyboard_line, optimized_image_prompt_line) in enumerate(
                zip(storyboard_lines, optimized_image_prompt_lines), start=1
            )
        ]

    def generate_rows(
        self,
        rows: list[dict[str, str]],
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> list[dict[str, str]]:
        generated_rows = []
        for generated_batch in self.iter_generate_row_batches(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            generated_rows.extend(generated_batch)
        return generated_rows

    def iter_generate_row_batches(
        self,
        rows: list[dict[str, str]],
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        generated_batch = []
        for event in self.iter_generate_row_progress(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            generated_batch.append(event["generated_row"])
            if event["batch_completed"]:
                yield generated_batch
                generated_batch = []

    def iter_generate_row_progress(
        self,
        rows: list[dict[str, str]],
        prompt_name: str = "default",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        system_prompt = load_prompt(
            self.prompts_dir, "video_prompt_from_image", prompt_name
        )
        batches = list(_batched(rows, batch_size))
        total = len(batches)
        total_rows = len(rows)
        total_start = time.perf_counter()

        logger.info(
            "开始视频提示词生成 (共 %s 条分镜, %s 批, 模型: %s, 提示词: %s)",
            total_rows,
            total,
            self.model,
            prompt_name,
        )

        completed_rows = 0
        previous_generated_row = None
        for index, row_batch in enumerate(batches, start=1):
            batch_start = time.perf_counter()
            batch_row_total = len(row_batch)
            logger.info("  生成第 %s/%s 批... (Ctrl+C 可中断)", index, total)
            for batch_row_index, row in enumerate(row_batch, start=1):
                user_content = _build_video_user_content(
                    row=row,
                    previous_generated_row=previous_generated_row,
                )
                video_prompt = self.client.chat(
                    model=self.model,
                    system_prompt=system_prompt,
                    user_content=user_content,
                    temperature=0.7,
                    fallback_model=self.fallback_model,
                )
                generated_row = {
                    "scene_id": row["scene_id"],
                    "storyboard_text": row["storyboard_text"],
                    "optimized_image_prompt": row["optimized_image_prompt"],
                    "video_prompt": _normalize_video_prompt(video_prompt),
                    "notes_cn": "",
                }
                previous_generated_row = generated_row
                completed_rows += 1
                batch_completed = batch_row_index == batch_row_total
                if batch_completed:
                    logger.info("  第 %s/%s 批生成完成", index, total)

                yield {
                    "generated_row": generated_row,
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

        logger.info("视频提示词生成完成")
