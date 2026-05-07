# 画面提示词优化：多轮累积改独立分批调用

## 概述

将 `PromptOptimizer.optimize_files_batch()` 从"全量原文首轮一次性传入 + 多轮对话累积输出"模式改为"独立分批调用 + 全局叙事摘要 + 尾锚衔接"模式。

**动机：** 当前模式在处理 100+ 条分镜时，全部原文挤在首轮 user message 中，模型注意力被稀释，中间位置的条目容易产生空间占位矛盾、背对镜头+面部表情冲突等问题。改为每批独立调用后，每批 10 条获得完整注意力窗口，通过全局摘要和尾锚保证跨批连续性。

## 当前行为（需要替换的代码）

文件：`core/prompt_optimizer.py`，方法：`optimize_files_batch()`

```
1. 将所有 rows 拼接为一个 all_rows_text
2. 构建 initial_user = "以下是 N 条分镜..." + all_rows_text + "先生成前 K 条"
3. messages = [system, user(initial_user)]
4. while completed < total:
     result = client.chat_multi_turn(messages)  ← messages 累积
     messages.append(assistant, result)
     解析 result 中的行
     messages.append(user, "继续生成第 X-Y 条")
5. yield 最终结果
```

核心问题：
- 全部原文一次性传入，对于 100+ 条场景，模型注意力在首轮就被稀释
- `chat_multi_turn()` 的 messages 列表不断膨胀（system + user1 + assistant1 + user2 + assistant2 + ...）
- 后期轮次的上下文窗口被历史输出挤占

## 目标行为

```
1. 生成全局叙事摘要（一次轻量 AI 调用，仅传原文不含原始画面提示词）
2. 将 rows 按 rows_per_batch=10 切分为 batches
3. prev_tail = None
4. for each batch:
     user_msg = 全局摘要
     if prev_tail:
         user_msg += 上一批最后一条输出（衔接锚点）
     user_msg += 本批的完整原文（分镜原文 + 原始画面提示词）
     result = client.chat(system_prompt, user_msg)  ← 独立单轮调用
     解析 result 中的行
     prev_tail = 本批最后一条输出
     yield 进度事件
5. yield 最终结果
```

关键变化：
- `chat_multi_turn()` → `chat()`，每批独立调用，无消息历史累积
- 首轮不再一次传全部原文，每批只传当前批次的 10 条原文
- 全局摘要每批发一次，给模型提供叙事全局视野
- 上一批尾部作为衔接锚点，保证批次边界的连续性

## 详细设计

### 1. 全局叙事摘要生成

新增方法：`_build_global_summary(self, rows: list[dict]) -> str`

在所有批次开始前，做一次轻量 AI 预调用，输入全部原文（仅分镜原文，不含原始画面提示词），让模型提取叙事骨架。

**API 调用参数：**

```python
summary_system = "你是一个叙事结构分析助手。只输出JSON，不输出其他内容。"

summary_user = f"""请从以下 {len(rows)} 条分镜原文中提取叙事摘要，严格按照以下JSON格式输出：

{{
  "total_scenes": {len(rows)},
  "characters": [{{"name": "角色名", "emotional_arc": "情绪变化简述"}}],
  "location_changes": ["场景A → 场景B → ..."],
  "lighting_timeline": ["时间点或光线变化描述"],
  "spatial_main_axis": "主要空间关系演变概述",
  "scene_groups": [
    {{"location": "场景名", "scene_range": "第X-Y条", "key_event": "核心事件"}}
  ]
}}

原文如下：
{所有分镜原文，每条一行，带编号}
"""

result = self.client.chat(
    model=self.model,
    system_prompt=summary_system,
    user_content=summary_user,
    temperature=0.3,
    max_tokens=800,
    fallback_model=self.fallback_model,
)
```

**JSON 解析与容错：**

```python
try:
    # 尝试从 result 中提取 JSON（可能被 markdown 代码块包裹）
    json_str = result.strip()
    if json_str.startswith("```"):
        json_str = json_str.split("\n", 1)[1]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
    summary_data = json.loads(json_str)
    summary = self._format_summary(summary_data)
except (json.JSONDecodeError, KeyError):
    # 降级：规则提取
    summary = self._fallback_summary(rows)
```

**`_format_summary()` 输出格式（拼入每批 user message 的前缀）：**

```
【全局叙事摘要】
总镜数：100
角色与情绪弧线：
  - 姜春秋：真诚 → 沉稳 → 错愕 → 示好 → 疑惑 → 不安 → 被指责 → 愤怒 → 被包围 → 压抑不甘
  - 村中大婶：不满 → 沉默 → 指责 → 冷视 → 逼视 → 嘲讽
场景变化：白羽村鸡舍 → 邻村养殖场 → 白羽村姜春秋家门口
光线时间线：午后阳光 → 清晨 → 傍晚橘光 → 夕阳余晖 → 夕阳下沉 → 天色渐暗 → 夜色初降 → 灯泡亮起 → 夜色彻底
空间主轴：姜春秋从前景中央逐渐被挤压包围，与村中大婶对峙升级
```

**降级方案 `_fallback_summary()`：** 用正则从原文中提取：
- `【([^】]+)】` 匹配角色名和场景名
- `清晨|午后|傍晚|夕阳|夜色|阳光|灯光` 等关键词匹配时间光线
- 场景名按照首次出现顺序排列

### 2. 批次迭代主循环

重写 `optimize_files_batch()` 方法：

```python
def optimize_files_batch(
    self,
    storyboard_path: str | None = None,
    raw_prompt_path: str | None = None,
    rows: list[dict[str, str]] | None = None,
    prompt_name: str = "default",
    rows_per_batch: int = 10,  # 默认值从 50 改为 10
):
    # --- 输入解析（不变） ---
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

    # --- 步骤1：生成全局叙事摘要 ---
    summary = self._build_global_summary(rows)

    # --- 步骤2：分批 ---
    batches = [
        rows[i:i + rows_per_batch]
        for i in range(0, total, rows_per_batch)
    ]
    batch_total = len(batches)

    logger.info(
        "开始独立分批画面提示词优化 (共 %s 条, %s 批, 每批 %s 条, 模型: %s)",
        total, batch_total, rows_per_batch, self.model,
    )

    # --- 步骤3：逐批独立调用 ---
    all_lines: list[str] = []
    prev_tail: str | None = None
    completed = 0

    for batch_idx, batch in enumerate(batches):
        batch_start_idx = batch_idx * rows_per_batch

        # 构建本批 user message
        user_msg = summary

        # 衔接锚点（第二批开始）
        if prev_tail and batch_idx > 0:
            user_msg += (
                f"\n\n[衔接锚点] 上一批最后一条（第{batch_start_idx}条）"
                f"优化结果：\n{prev_tail}"
            )

        # 本批完整原文
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

        # 独立单轮调用（非 chat_multi_turn）
        result = self.client.chat(
            model=self.model,
            system_prompt=system_prompt,
            user_content=user_msg,
            temperature=0.7,
            fallback_model=self.fallback_model,
        )

        # 解析输出行
        lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
        needed = min(rows_per_batch, total - completed)
        batch_lines = lines[:needed]
        all_lines.extend(batch_lines)
        completed += len(batch_lines)

        # 更新尾锚
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

        # 死循环保护（复用现有逻辑）
        if len(batch_lines) == 0:
            zero_growth_streak += 1
            if zero_growth_streak >= 3:
                logger.warning("  连续 3 批无有效输出，强行终止优化")
                break
        else:
            zero_growth_streak = 0

    logger.info("独立分批画面提示词优化完成 (%s 条)", len(all_lines))
    yield "\n".join(all_lines)
```

**注意：** `zero_growth_streak` 变量需要在循环前初始化为 `0`。现有代码中是在 `while` 循环内初始化，改为 `for` 循环后需要在循环外初始化。

### 3. 辅助方法

#### `_build_global_summary()`

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
```

#### `_format_summary()`

```python
def _format_summary(self, raw_json: str) -> str:
    """将 AI 返回的 JSON 格式化为可嵌入 user message 的文本。"""
    json_str = raw_json.strip()
    # 处理可能的 markdown 代码块包裹
    if json_str.startswith("```"):
        lines = json_str.split("\n")
        json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(json_str)

    parts = [f"【全局叙事摘要】\n总镜数：{data.get('total_scenes', '?')}"]

    chars = data.get("characters", [])
    if chars:
        lines = []
        for c in chars:
            name = c.get("name", "?")
            arc = c.get("emotional_arc", "")
            lines.append(f"  - {name}：{arc}")
        parts.append("角色与情绪弧线：\n" + "\n".join(lines))

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
        lines = []
        for g in groups:
            loc = g.get("location", "?")
            rng = g.get("scene_range", "?")
            evt = g.get("key_event", "")
            lines.append(f"  - {loc}（{rng}）：{evt}")
        parts.append("场景分组：\n" + "\n".join(lines))

    return "\n".join(parts)
```

#### `_fallback_summary()`

```python
import re

def _fallback_summary(self, rows: list[dict[str, str]]) -> str:
    """规则提取叙事摘要（AI 预调用失败时的降级方案）。"""
    all_text = " ".join(row["storyboard_text"] for row in rows)

    # 提取角色名
    characters = list(set(re.findall(r"【([^】]+)】", all_text)))

    # 提取时间光线关键词
    time_light_keywords = [
        "清晨", "午后", "傍晚", "夕阳", "夜色", "阳光",
        "余晖", "黄昏", "黎明", "灯光", "白天", "黑夜",
        "日出", "日落", "夜色彻底", "天色渐暗", "天色渐亮",
    ]
    found_times = [w for w in time_light_keywords if w in all_text]
    # 按首次出现位置排序
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

### 4. DEFAULT_BATCH_SIZE 常量

`core/prompt_optimizer.py` 第 3 行：

```python
# 改前
DEFAULT_BATCH_SIZE = 10  # 原来是 50
```

### 5. 调用方兼容性

`main.py` 和 `interactive.py` 调用 `optimize_files_batch()` 的方式**完全不变**：

- 仍然传入 `rows_per_batch` 参数
- 仍然通过 `yield` 的进度事件和最终 string 消费结果
- `interactive.py` 中的 `write_txt_optimization_batches()` 和 `write_csv_optimization_batches()` 不改

唯一的语义变化：`rows_per_batch` 从"多轮对话每轮输出行数"变为"每批独立调用的输入/输出行数"。

## 测试适配

文件：`tests/test_prompt_optimizer.py`

### FakeClient 适配

现有 `FakeClient.chat_multi_turn()` 方法保留，但新流程不再调用它。需要确保 `FakeClient.chat()` 方法正确工作（现有代码第 40-48 行已有实现，委托给 `chat_multi_turn`）。

关键变化：测试需要验证调用走的是 `chat()` 而非 `chat_multi_turn()`，且每次 `chat()` 的 messages 只有 system + user（无历史累积）。

为支持此验证，可扩展 `FakeClient`：

```python
class FakeClient:
    def __init__(self, return_value: str | None = None):
        self.calls = []           # 记录所有 chat() 调用
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
            "messages": messages,
            "temperature": temperature,
            "fallback_model": fallback_model,
        })
        if self.return_value is not None:
            return self.return_value
        return f"优化后提示词{len(self.chat_multi_turn_calls)}"
```

### 现有测试修改

| 测试方法 | 修改 |
|---------|------|
| `test_batch_mode_returns_all_lines` | 2 条数据，1 批完成，验证走 `chat()` |
| `test_loads_default_prompt_with_back_facing_rule` | 改为从 `client.calls[0]["system_prompt"]` 读取 |
| `test_flattens_multiline_output` | 不变 |
| `test_appends_negative_prompt_when_missing` | 不变 |
| `test_builds_rows_from_files` | 不变（不涉及 API 调用） |
| `test_raises_on_mismatched_counts` | 不变（不涉及 API 调用） |
| `test_csv_mode_returns_string` | 1 条数据，走 `chat()` |
| `test_batch_single_turn` | 3 条数据，1 批完成，验证只有 1 次 `chat()` 调用 |
| `test_batch_multi_turn` | 7 条数据，rows_per_batch=3，验证 3 次 `chat()` 调用，每次 messages 只有 system+user |
| `test_batch_all_rows_in_one_message` | **修改语义**：验证 2 条数据分 2 批时，不在同一 message，而是在两次独立调用中 |

### 新增测试

#### `test_independent_calls_no_message_accumulation`

```python
def test_independent_calls_no_message_accumulation(self):
    """验证每批调用是独立的 chat()，无 messages 累积。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)

        class C(FakeClient):
            def chat(self, model, system_prompt, user_content, **kw):
                super().chat(model, system_prompt, user_content, **kw)
                # 返回足够行数
                n = len(self.calls)
                return f"R{n}A\nR{n}B\nR{n}C\nR{n}D"

        client = C()
        opt = PromptOptimizer(client=client, model="m",
                             prompts_dir=os.path.join(tmp_dir, "prompts"))
        _collect_batch(opt.optimize_files_batch(rows=[
            {"s": str(i), "storyboard_text": f"S{i}", "raw_image_prompt": f"P{i}"}
            for i in range(1, 9)
        ], rows_per_batch=4))

    # 应该有 2 批独立 chat() 调用
    self.assertEqual(2, len(client.calls))
    # 不应该走 chat_multi_turn
    self.assertEqual(0, len(client.chat_multi_turn_calls))
```

#### `test_continuity_anchor_passed`

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

    # 12 条，每批 5 条 = 3 批
    self.assertEqual(3, len(client.calls))
    # 第二批的 user_content 应包含 "衔接锚点"
    self.assertIn("衔接锚点", client.calls[1]["user_content"])
    # 第一批不应该有衔接锚点
    self.assertNotIn("衔接锚点", client.calls[0]["user_content"])
```

#### `test_summary_in_every_batch`

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

    # 每批都应该包含全局摘要
    for call in client.calls:
        self.assertIn("全局叙事摘要", call["user_content"])
```

## 边界情况处理

| 情况 | 处理方式 |
|------|----------|
| total = 0 | 直接 yield "" 返回 |
| total ≤ rows_per_batch | 1 批完成，无衔接锚点 |
| 摘要 AI 调用失败 | 降级为规则提取，不阻塞主流程 |
| 某批 API 调用失败 | 复用 `OpenAICompatClient.chat()` 内置重试（指数退避 + fallback_model），最终失败抛 `RuntimeError` |
| 某批返回行数不足 | 缺几条就空几条；连续 3 批零输出则终止（`zero_growth_streak` 保护） |
| 某批返回行数超出 | 按 `len(batch)` 截断 |
| 单条原文为空 | `read_non_empty_lines` 已在输入阶段过滤 |

## 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/prompt_optimizer.py` | **重写** | `optimize_files_batch` 循环体 + 新增 3 个辅助方法；`DEFAULT_BATCH_SIZE` 改值 |
| `tests/test_prompt_optimizer.py` | **适配+新增** | `FakeClient` 扩展；9 个现有测试适配；3 个新测试 |

**不改的文件：** `main.py`、`core/interactive.py`、`config.py`、`api/openai_client.py`、`prompts/image_prompt_optimize/default.txt`

## 实现顺序

1. 扩展 `FakeClient`，添加 `chat_multi_turn_calls` 记录
2. 在 `prompt_optimizer.py` 中新增 `_build_global_summary()`、`_format_summary()`、`_fallback_summary()` 三个方法
3. 修改 `DEFAULT_BATCH_SIZE = 10`
4. 重写 `optimize_files_batch()` 的循环体（while → for，chat_multi_turn → chat）
5. 运行现有测试，逐个适配
6. 新增 3 个测试
7. 全量测试验证 `python -m unittest discover -s tests`
