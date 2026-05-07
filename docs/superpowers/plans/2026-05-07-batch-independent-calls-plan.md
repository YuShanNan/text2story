# 画面提示词优化：独立分批调用 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `PromptOptimizer.optimize_files_batch()` 从全量首轮+多轮累积改为独立分批调用+全局摘要+尾锚衔接

**Architecture:** 每 10 条一批，每批通过 `client.chat()` 独立调用（不累积 messages）。批前生成一次全局叙事摘要（轻量 AI 调用，失败降级为规则提取），每批 user message 前置摘要 + 上批尾锚。yield 接口不变，main.py / interactive.py 零改动。

**Tech Stack:** Python 3.12+, unittest, 现有 `OpenAICompatClient`

**Spec:** `docs/superpowers/specs/2026-05-07-batch-independent-calls-design.md`

---

### Task 1: 扩展 FakeClient，添加 chat_multi_turn_calls 记录

**Files:**
- Modify: `tests/test_prompt_optimizer.py:16-48`

- [ ] **Step 1: 重写 FakeClient 类**

将现有的 `FakeClient` 类替换为以下版本。关键变化：`chat()` 不再委托给 `chat_multi_turn()`，两者各自独立记录调用。

```python
class FakeClient:
    def __init__(self, return_value: str | None = None):
        self.calls = []                  # 记录所有 chat() 调用
        self.chat_multi_turn_calls = []  # 记录所有 chat_multi_turn() 调用
        self.return_value = return_value

    def chat(self, model, system_prompt, user_content, temperature=0.7,
             max_tokens=4096, fallback_model=None, thinking_enabled=None):
        self.calls.append({
            "model": model,
            "system_prompt": system_prompt,
            "user_content": user_content,
            "temperature": temperature,
            "fallback_model": fallback_model,
        })
        if self.return_value is not None:
            return self.return_value
        return f"优化后提示词{len(self.calls)}"

    def chat_multi_turn(self, model, messages, temperature=0.7,
                        max_tokens=4096, fallback_model=None, thinking_enabled=None):
        self.chat_multi_turn_calls.append({
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
            "fallback_model": fallback_model,
        })
        if self.return_value is not None:
            return self.return_value
        return f"优化后提示词{len(self.chat_multi_turn_calls)}"
```

- [ ] **Step 2: 运行现有测试确认 FakeClient 改动不破坏任何东西**

```bash
python -m unittest tests.test_prompt_optimizer -v
```

预期：部分测试 FAIL（因为旧测试内部可能依赖 `chat_multi_turn` 的旧行为），记下哪些失败，后续 Task 7 统一适配。

---

### Task 2: 新增 3 个测试

**Files:**
- Modify: `tests/test_prompt_optimizer.py`（在 `PromptOptimizerTest` 类末尾，`if __name__` 之前追加）

- [ ] **Step 1: 添加 `test_independent_calls_no_message_accumulation`**

```python
def test_independent_calls_no_message_accumulation(self):
    """验证每批调用是独立的 chat()，无 messages 累积。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)

        class C(FakeClient):
            def chat(self, model, system_prompt, user_content, **kw):
                super().chat(model, system_prompt, user_content, **kw)
                n = len(self.calls)
                return f"R{n}A\nR{n}B\nR{n}C\nR{n}D"

        client = C()
        opt = PromptOptimizer(client=client, model="m",
                              prompts_dir=os.path.join(tmp_dir, "prompts"))
        _collect_batch(opt.optimize_files_batch(rows=[
            {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"}
            for i in range(1, 9)
        ], rows_per_batch=4))

    self.assertEqual(2, len(client.calls))
    self.assertEqual(0, len(client.chat_multi_turn_calls))
```

- [ ] **Step 2: 添加 `test_continuity_anchor_passed`**

```python
def test_continuity_anchor_passed(self):
    """验证第二批的 user_content 包含上一批最后一条输出（衔接锚点）。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)

        client = FakeClient()
        opt = PromptOptimizer(client=client, model="m",
                              prompts_dir=os.path.join(tmp_dir, "prompts"))
        _collect_batch(opt.optimize_files_batch(rows=[
            {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"}
            for i in range(1, 13)
        ], rows_per_batch=5))

    self.assertEqual(3, len(client.calls))
    self.assertIn("衔接锚点", client.calls[1]["user_content"])
    self.assertNotIn("衔接锚点", client.calls[0]["user_content"])
```

- [ ] **Step 3: 添加 `test_summary_in_every_batch`**

```python
def test_summary_in_every_batch(self):
    """验证每批 user_content 都包含全局摘要。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)

        client = FakeClient()
        opt = PromptOptimizer(client=client, model="m",
                              prompts_dir=os.path.join(tmp_dir, "prompts"))
        _collect_batch(opt.optimize_files_batch(rows=[
            {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"}
            for i in range(1, 13)
        ], rows_per_batch=5))

    for call in client.calls:
        self.assertIn("全局叙事摘要", call["user_content"])
```

- [ ] **Step 4: 运行新测试确认它们全部 FAIL**

```bash
python -m unittest tests.test_prompt_optimizer.PromptOptimizerTest.test_independent_calls_no_message_accumulation tests.test_prompt_optimizer.PromptOptimizerTest.test_continuity_anchor_passed tests.test_prompt_optimizer.PromptOptimizerTest.test_summary_in_every_batch -v
```

预期：3 个新测试全部 FAIL，因为实现还没改。

---

### Task 3: 在 prompt_optimizer.py 中新增辅助方法

**Files:**
- Modify: `core/prompt_optimizer.py`

- [ ] **Step 1: 在文件顶部添加 import**

在第 1 行之后（`from utils.logger import get_logger` 之后）添加：

```python
import json
import re
```

- [ ] **Step 2: 在 `PromptOptimizer` 类末尾（`_build_file_rows` 方法之后）添加三个新方法**

在 `_build_file_rows` 方法结束后（第 147 行后，类结束前）插入：

```python
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

        data = json.loads(json_str)

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
```

- [ ] **Step 3: 验证语法正确**

```bash
python -m py_compile core/prompt_optimizer.py
```

预期：无输出（编译通过）。

---

### Task 4: 重写 optimize_files_batch 方法

**Files:**
- Modify: `core/prompt_optimizer.py:28-123`

- [ ] **Step 1: 将 `rows_per_batch` 默认值从 50 改为 10**

第 34 行：

```python
# 改前
rows_per_batch: int = 50,
# 改后
rows_per_batch: int = 10,
```

- [ ] **Step 2: 替换整个 `optimize_files_batch` 方法体**

将第 36-123 行（方法体从 docstring 到 `yield "\n".join(all_lines)`）替换为：

```python
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
```

- [ ] **Step 3: 验证语法正确**

```bash
python -m py_compile core/prompt_optimizer.py
```

预期：无输出。

---

### Task 5: 运行新测试，确认通过

- [ ] **Step 1: 运行 3 个新测试**

```bash
python -m unittest tests.test_prompt_optimizer.PromptOptimizerTest.test_independent_calls_no_message_accumulation tests.test_prompt_optimizer.PromptOptimizerTest.test_continuity_anchor_passed tests.test_prompt_optimizer.PromptOptimizerTest.test_summary_in_every_batch -v
```

预期：3 个全部 PASS。

---

### Task 6: 适配现有测试

**Files:**
- Modify: `tests/test_prompt_optimizer.py`

- [ ] **Step 1: 适配 `test_batch_mode_returns_all_lines`**

旧代码（第 59-76 行）中内部类 C 重写了 `chat_multi_turn`，新流程走 `chat()`。修改：

```python
def test_batch_mode_returns_all_lines(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)
        sb = os.path.join(tmp_dir, "s.txt")
        rp = os.path.join(tmp_dir, "r.txt")
        with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
        with open(rp, "w") as f: f.write("PA\nPB\n")

        class C(FakeClient):
            def chat(self, model, system_prompt, user_content, **kw):
                super().chat(model, system_prompt, user_content, **kw)
                return "OA\nOB"

        client = C()
        opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
        r = _collect_batch(opt.optimize_files_batch(storyboard_path=sb, raw_prompt_path=rp))
    self.assertEqual("OA\nOB", r)
    self.assertEqual(1, len(client.calls))
```

- [ ] **Step 2: 适配 `test_loads_default_prompt_with_back_facing_rule`**

旧代码从 `client.calls[0]["system_prompt"]` 读取——FakeClient 新 `chat()` 已经有这个字段，无需改动。但旧代码中 `FakeClient.chat()` 委托给了 `chat_multi_turn()`，现在不委托了。验证：

当前第 78-88 行的测试代码不变，确认它仍通过：

```bash
python -m unittest tests.test_prompt_optimizer.PromptOptimizerTest.test_loads_default_prompt_with_back_facing_rule -v
```

- [ ] **Step 3: 适配 `test_csv_mode_returns_string`**

旧代码第 136-142 行使用 `FakeClient()` 无 `return_value`，新 `FakeClient.chat()` 返回 `f"优化后提示词{len(self.calls)}"` → `"优化后提示词1"`，断言匹配。无需修改。

- [ ] **Step 4: 适配 `test_batch_single_turn`**

旧代码第 144-159 行内部类 C 重写了 `chat_multi_turn`，需改为重写 `chat()`：

```python
def test_batch_single_turn(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)

        class C(FakeClient):
            def chat(self, model, system_prompt, user_content, **kw):
                super().chat(model, system_prompt, user_content, **kw)
                return "A\nB\nC"

        client = C()
        opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
        r = _collect_batch(opt.optimize_files_batch(rows=[
            {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"} for i in range(1, 4)
        ], rows_per_batch=50))
    self.assertEqual(1, len(client.calls))
    self.assertEqual(3, len(r.strip().split("\n")))
```

- [ ] **Step 5: 适配 `test_batch_multi_turn`**

旧代码第 161-177 行内部类 C 重写了 `chat_multi_turn`，需改为重写 `chat()`，并验证独立调用：

```python
def test_batch_multi_turn(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)

        class C(FakeClient):
            def chat(self, model, system_prompt, user_content, **kw):
                super().chat(model, system_prompt, user_content, **kw)
                n = len(self.calls)
                return f"R{n}A\nR{n}B\nR{n}C"

        client = C()
        opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
        r = _collect_batch(opt.optimize_files_batch(rows=[
            {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"} for i in range(1, 8)
        ], rows_per_batch=3))
    self.assertEqual(3, len(client.calls))
    self.assertEqual(0, len(client.chat_multi_turn_calls))
    self.assertEqual(7, len(r.strip().split("\n")))
```

- [ ] **Step 6: 适配 `test_batch_all_rows_in_one_message`**

旧测试验证所有 row 在同一 message。新语义下分批独立调用，改为验证不在同一 message：

```python
def test_batch_all_rows_in_one_message(self):
    """验证分批模式下，不同批的数据不在同一次调用中。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)

        class C(FakeClient):
            def chat(self, model, system_prompt, user_content, **kw):
                super().chat(model, system_prompt, user_content, **kw)
                return "A\nB"

        client = C()
        opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
        _collect_batch(opt.optimize_files_batch(rows=[
            {"s": "1", "storyboard_text": "SA", "raw_image_prompt": "PA"},
            {"s": "2", "storyboard_text": "SB", "raw_image_prompt": "PB"},
            {"s": "3", "storyboard_text": "SC", "raw_image_prompt": "PC"},
            {"s": "4", "storyboard_text": "SD", "raw_image_prompt": "PD"},
        ], rows_per_batch=2))
    # 4 条 ÷ 2 条/批 = 2 次独立调用
    self.assertEqual(2, len(client.calls))
    # SA 和 SB 在第一批，SC 和 SD 在第二批
    self.assertIn("SA", client.calls[0]["user_content"])
    self.assertIn("SB", client.calls[0]["user_content"])
    self.assertNotIn("SC", client.calls[0]["user_content"])
    self.assertNotIn("SD", client.calls[0]["user_content"])
```

- [ ] **Step 7: 无需修改的测试确认**

以下测试不涉及 API 调用方式，无需改动：
- `test_flattens_multiline_output` (第 90-100 行)
- `test_appends_negative_prompt_when_missing` (第 102-112 行)
- `test_builds_rows_from_files` (第 114-122 行)
- `test_raises_on_mismatched_counts` (第 125-134 行)

---

### Task 7: 运行全部测试

- [ ] **Step 1: 运行完整测试套件**

```bash
python -m unittest discover -s tests -v
```

预期：全部 PASS，包括 9 个现有测试 + 3 个新增测试 = 12 个测试通过。

如果有关联测试失败（如 `test_interactive_batch_helpers` 或 `test_prompt_templates`），逐个排查修复。

---

### Task 8: 提交

- [ ] **Step 1: 检查改动**

```bash
git diff --stat
```

预期：只改动 2 个文件 — `core/prompt_optimizer.py` 和 `tests/test_prompt_optimizer.py`。

- [ ] **Step 2: 提交**

```bash
git add core/prompt_optimizer.py tests/test_prompt_optimizer.py
git commit -m "$(cat <<'EOF'
refactor: 画面提示词优化改为独立分批调用

将 optimize_files_batch 从全量首轮+chat_multi_turn 多轮累积
改为独立 chat() 分批调用+全局叙事摘要+尾锚衔接。
每批 10 条，消除多轮 messages 累积导致的注意力稀释。
EOF
)"
```
