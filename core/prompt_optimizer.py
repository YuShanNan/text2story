import json
import os
import re

from utils.file_utils import load_prompt, read_non_empty_lines
from utils.logger import get_logger

DEFAULT_BATCH_SIZE = 50
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
        rows_per_batch: int = 50,
        output_file: str | None = None,
    ):
        """批量模式：全量原文一次性发送，chat_multi_turn 累积消息分批输出。

        全部行拼接为一个 user message 发送给模型，模型分批输出。
        每批完成后发送确认消息继续下一批。messages 累积保证模型始终
        拥有完整故事上下文，防止跨故事污染。
        每批 yield 一次进度事件（含 batch_lines），最后 yield 最终结果字符串。
        若指定 output_file，每批完成后立即追加写入。
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
        known_entities = self._extract_known_entities(rows)

        all_rows_text = "\n\n".join(
            f"[{i + 1}] 分镜原文：{row['storyboard_text']}\n"
            f"    原始画面提示词：{row['raw_image_prompt']}"
            for i, row in enumerate(rows)
        )

        first_batch_count = min(rows_per_batch, total)
        initial_user = (
            f"{summary}\n\n"
            f"以下是 {total} 条分镜和对应的原始画面提示词。\n\n"
            f"{all_rows_text}\n\n"
            f"请先生成前 {first_batch_count} 条的优化后提示词，"
            f"每条占一行，按顺序输出。完成后不要输出其他内容。"
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": initial_user})

        all_lines: list[str] = []
        completed = 0
        batch_index = 0
        batch_total = (total + rows_per_batch - 1) // rows_per_batch
        zero_growth_streak = 0

        logger.info(
            "开始批量画面提示词优化 (共 %s 条, %s 批, 每批最多 %s 条, 模型: %s)",
            total, batch_total, rows_per_batch, self.model,
        )

        while completed < total:
            batch_index += 1
            result = self.client.chat_multi_turn(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=16000,
                fallback_model=self.fallback_model,
            )
            messages.append({"role": "assistant", "content": result})

            lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
            needed = min(rows_per_batch, total - completed)
            batch_lines = lines[:needed]

            # 补齐不足行数（最多重试2次）
            retry_count = 0
            while len(batch_lines) < needed and retry_count < 2 and len(batch_lines) > 0:
                retry_count += 1
                missing = needed - len(batch_lines)
                miss_start = completed + len(batch_lines) + 1
                miss_end = completed + needed
                retry_msg = (
                    f"上一轮只输出了 {len(batch_lines)} 条，"
                    f"缺少第 {miss_start}-{miss_end} 条。"
                    f"请补充生成这 {missing} 条的优化后提示词，"
                    f"每条一行，按顺序输出。"
                )
                logger.warning(
                    "  第 %s 批缺少 %s 条，第 %s 次重试补齐 (第 %s-%s 条)",
                    batch_index, missing, retry_count, miss_start, miss_end,
                )
                messages.append({"role": "user", "content": retry_msg})
                extra_result = self.client.chat_multi_turn(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=16000,
                    fallback_model=self.fallback_model,
                )
                messages.append({"role": "assistant", "content": extra_result})
                extra_lines = [l.strip() for l in extra_result.strip().split("\n") if l.strip()]
                batch_lines.extend(extra_lines[:missing])

            # 验证输出行，对异常行逐行重试
            batch_start_idx = completed
            valid_lines, line_issues = self._validate_batch_lines(
                batch_lines, known_entities, batch_start_idx,
            )
            for line_idx, problems in line_issues:
                batch_rel_idx = line_idx - batch_start_idx
                if batch_rel_idx >= len(rows):
                    continue
                logger.warning(
                    "  第 %s 条疑似异常 (%s)，尝试单行重试",
                    line_idx + 1, "; ".join(problems),
                )
                row = rows[line_idx]
                retry_msg = (
                    f"请重新生成第{line_idx + 1}条的优化后提示词。"
                    f"注意：必须基于以下原始内容生成，不得引入其他故事的角色或场景。\n\n"
                    f"分镜原文：{row['storyboard_text']}\n"
                    f"原始画面提示词：{row['raw_image_prompt']}"
                )
                try:
                    extra_result = self.client.chat(
                        model=self.model,
                        system_prompt=system_prompt,
                        user_content=retry_msg,
                        temperature=0.7,
                        fallback_model=self.fallback_model,
                    )
                    new_line = extra_result.strip().split("\n")[0].strip()
                    new_valid, _ = self._validate_batch_lines(
                        [new_line], known_entities, line_idx,
                    )
                    if new_valid:
                        batch_lines[batch_rel_idx] = new_line
                        logger.info("  第 %s 条单行重试通过", line_idx + 1)
                    else:
                        logger.warning(
                            "  第 %s 条单行重试仍未通过验证，保留原行",
                            line_idx + 1,
                        )
                except Exception:
                    logger.warning(
                        "  第 %s 条单行重试失败，保留原行", line_idx + 1,
                    )

            all_lines.extend(batch_lines)
            completed += len(batch_lines)

            logger.info(
                "  第 %s/%s 批优化完成 (%s/%s 条)",
                batch_index, batch_total, completed, total,
            )
            progress = {
                "completed": completed, "total": total,
                "batch_index": batch_index, "batch_total": batch_total,
                "batch_lines": list(batch_lines),
            }
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, "a", encoding="utf-8-sig") as f:
                    if completed <= len(batch_lines):
                        f.write("\n".join(batch_lines))
                    else:
                        f.write("\n" + "\n".join(batch_lines))
            yield progress

            zero_growth_streak = zero_growth_streak + 1 if len(batch_lines) == 0 else 0
            if zero_growth_streak >= 3:
                logger.warning("  连续 %s 批无有效输出，强行终止优化", zero_growth_streak)
                break

            if completed >= total:
                break

            next_count = min(rows_per_batch, total - completed)
            confirm = (
                f"已生成并确认前 {completed} 条。"
                f"请继续生成第 {completed + 1}-{completed + next_count} 条的"
                f"优化后提示词，每条占一行，按顺序输出。"
            )
            messages.append({"role": "user", "content": confirm})

        logger.info("批量画面提示词优化完成 (%s 条)", len(all_lines))
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

    def _extract_known_entities(self, rows: list[dict[str, str]]) -> set[str]:
        """从所有原始画面提示词中提取已知实体（角色名+场景名）作为验证白名单。"""
        entities: set[str] = set()
        for row in rows:
            entities.update(re.findall(r"\[([^\[\]]+)\]", row["raw_image_prompt"]))
        entities.add("家用轿车车内")
        entities.add("家用轿车")
        return entities

    def _validate_batch_lines(
        self,
        lines: list[str],
        known_entities: set[str],
        batch_start_idx: int,
    ) -> tuple[list[str], list[tuple[int, list[str]]]]:
        """验证优化后的行是否存在污染和完整性问题。

        Returns:
            (valid_lines, issues):
            - valid_lines: 通过验证的行
            - issues: [(全局行号, [问题描述]), ...] 未通过验证的行
        """
        valid: list[str] = []
        issues: list[tuple[int, list[str]]] = []

        for i, line in enumerate(lines):
            problems: list[str] = []

            if re.match(r"^\[\d+\]\s*分镜原文：", line) or line.startswith(
                "原始画面提示词："
            ):
                problems.append("输入回显(非优化后提示词)")

            open_c = line.count("【")
            close_c = line.count("】")
            if open_c != close_c:
                problems.append(f"【】不配对({open_c}开{close_c}闭)")

            entities_in_line = set(re.findall(r"【([^】]+)】", line))
            foreign = entities_in_line - known_entities
            if len(foreign) >= 2:
                problems.append(
                    f"疑似污染(外来实体: {', '.join(sorted(foreign)[:5])})"
                )

            if problems:
                issues.append((batch_start_idx + i, problems))
            else:
                valid.append(line)

        return valid, issues
