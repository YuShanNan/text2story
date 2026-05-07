from utils.file_utils import load_prompt, read_non_empty_lines
from utils.logger import get_logger
import json
import re

DEFAULT_BATCH_SIZE = 10
logger = get_logger(__name__)


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
        rows_per_batch: int = 10,
    ):
        """批量模式：独立分批调用，每批通过独立 chat() 处理。

        先生成全局叙事摘要，再将全部行按 rows_per_batch 切分为多批，
        每批独立调用 chat()（不累积 messages），通过全局摘要和尾锚保证跨批连续性。
        每批 yield 一次进度事件，最后 yield 最终结果字符串。
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

        if total == 0:
            yield ""
            return

        summary = self._build_global_summary(rows)

        batches = [
            rows[i:i + rows_per_batch]
            for i in range(0, total, rows_per_batch)
        ]
        batch_total = len(batches)

        logger.info(
            "开始独立分批画面提示词优化 (共 %s 条, %s 批, 每批 %s 条, 模型: %s)",
            total, batch_total, rows_per_batch, self.model,
        )

        all_lines: list[str] = []
        prev_tail: str | None = None
        completed = 0
        zero_growth_streak = 0

        for batch_idx, batch in enumerate(batches):
            batch_start_idx = batch_idx * rows_per_batch

            user_msg = summary

            if prev_tail and batch_idx > 0:
                user_msg += (
                    f"\n\n[衔接锚点] 上一批最后一条（第{batch_start_idx}条）"
                    f"优化结果：\n{prev_tail}"
                )

            batch_text = "\n\n".join(
                f"[{batch_start_idx + j + 1}] 分镜原文：{row['storyboard_text']}\n"
                f"    原始画面提示词：{row['raw_image_prompt']}"
                for j, row in enumerate(batch)
            )
            user_msg += (
                f"\n\n[本批] 以下是第 {batch_start_idx + 1}-"
                f"{min(batch_start_idx + rows_per_batch, total)} 条"
                f"的分镜原文和原始画面提示词，请逐条优化：\n\n{batch_text}"
            )

            result = self.client.chat(
                model=self.model,
                system_prompt=system_prompt,
                user_content=user_msg,
                temperature=0.7,
                fallback_model=self.fallback_model,
            )

            lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
            needed = min(rows_per_batch, total - completed)
            batch_lines = lines[:needed]
            all_lines.extend(batch_lines)
            completed += len(batch_lines)

            if batch_lines:
                prev_tail = batch_lines[-1]

            logger.info(
                "  第 %s/%s 批优化完成 (%s/%s 条)",
                batch_idx + 1, batch_total, completed, total,
            )
            yield {
                "completed": completed, "total": total,
                "batch_index": batch_idx + 1, "batch_total": batch_total,
            }

            if len(batch_lines) == 0:
                zero_growth_streak += 1
                if zero_growth_streak >= 3:
                    logger.warning("  连续 %s 批无有效输出，强行终止优化", zero_growth_streak)
                    break
            else:
                zero_growth_streak = 0

        logger.info("独立分批画面提示词优化完成 (%s 条)", len(all_lines))
        yield "\n".join(all_lines)

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

    def _build_global_summary(self, rows: list[dict[str, str]]) -> str:
        """生成全局叙事摘要，用于每批 user message 的前缀。"""
        summary_system = "你是一个叙事结构分析助手。只输出JSON，不输出其他内容。"

        scenes_text = "\n".join(
            f"[{i + 1}] {row['storyboard_text']}"
            for i, row in enumerate(rows)
        )

        summary_user = (
            f"请从以下 {len(rows)} 条分镜原文中提取叙事摘要，"
            f"严格按照JSON格式输出：\n\n"
            f"{{\n"
            f'  "total_scenes": {len(rows)},\n'
            f'  "characters": [{{"name": "角色名", "emotional_arc": "情绪变化简述"}}],\n'
            f'  "location_changes": ["场景变化顺序"],\n'
            f'  "lighting_timeline": ["光线/时间变化"],\n'
            f'  "spatial_main_axis": "主要空间关系演变",\n'
            f'  "scene_groups": [{{"location": "场景名", "scene_range": "第X-Y条", "key_event": "核心事件"}}]\n'
            f"}}\n\n"
            f"原文如下：\n{scenes_text}"
        )

        try:
            result = self.client.chat(
                model=self.model,
                system_prompt=summary_system,
                user_content=summary_user,
                temperature=0.3,
                max_tokens=800,
                fallback_model=self.fallback_model,
            )
            return self._format_summary(result)
        except Exception:
            logger.warning("全局摘要生成失败，降级为规则提取")
            return self._fallback_summary(rows)

    def _format_summary(self, raw_json: str) -> str:
        """将 AI 返回的 JSON 格式化为可嵌入 user message 的文本。"""
        json_str = raw_json.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError(f"全局摘要JSON解析失败: {json_str[:200]}")

        parts = [f"【全局叙事摘要】\n总镜数：{data.get('total_scenes', '?')}"]

        chars = data.get("characters", [])
        if chars:
            char_lines = []
            for c in chars:
                name = c.get("name", "?")
                arc = c.get("emotional_arc", "")
                char_lines.append(f"  - {name}：{arc}")
            parts.append("角色与情绪弧线：\n" + "\n".join(char_lines))

        locs = data.get("location_changes", [])
        if locs:
            parts.append("场景变化：" + " → ".join(locs))

        lighting = data.get("lighting_timeline", [])
        if lighting:
            parts.append("光线时间线：" + " → ".join(lighting))

        spatial = data.get("spatial_main_axis", "")
        if spatial:
            parts.append(f"空间主轴：{spatial}")

        groups = data.get("scene_groups", [])
        if groups:
            group_lines = []
            for g in groups:
                loc = g.get("location", "?")
                rng = g.get("scene_range", "?")
                evt = g.get("key_event", "")
                group_lines.append(f"  - {loc}（{rng}）：{evt}")
            parts.append("场景分组：\n" + "\n".join(group_lines))

        return "\n".join(parts)

    def _fallback_summary(self, rows: list[dict[str, str]]) -> str:
        """规则提取叙事摘要（AI 预调用失败时的降级方案）。"""
        all_text = " ".join(row["storyboard_text"] for row in rows)

        characters = list(set(re.findall(r"【([^】]+)】", all_text)))

        time_light_keywords = [
            "清晨", "午后", "傍晚", "夕阳", "夜色", "阳光",
            "余晖", "黄昏", "黎明", "灯光", "白天", "黑夜",
            "日出", "日落", "夜色彻底", "天色渐暗", "天色渐亮",
        ]
        found_times = [w for w in time_light_keywords if w in all_text]
        found_times.sort(key=lambda w: all_text.index(w))

        parts = [
            f"【全局叙事摘要】\n总镜数：{len(rows)}",
        ]
        if characters:
            parts.append(f"角色列表：{', '.join(characters)}")
        if found_times:
            parts.append("光线时间线：" + " → ".join(found_times))

        return "\n".join(parts)
