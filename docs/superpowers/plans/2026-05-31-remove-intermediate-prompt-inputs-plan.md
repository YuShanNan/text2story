# Remove Intermediate Prompt Inputs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the dependency on intermediate prompt files from both `PromptOptimizer` and `VideoPromptGenerator`, so each step only consumes storyboard text + its own system prompt.

**Architecture:** Both generators drop their second input parameter. `build_rows_from_files()` reads only storyboard text. `generate/optimize_files_batch()` builds AI input from storyboard text only. CSV table utils are simplified to remove the now-unnecessary merge functions and output columns. CLI commands lose one required parameter each. Interactive menu drops file-pairing logic.

**Tech Stack:** Python 3.x, Click, InquirerPy, unittest

---

### Task 1: Simplify VideoPromptGenerator

**Files:**
- Modify: `core/video_prompt_generator.py`

- [ ] **Step 1: Remove `optimized_image_prompt_path` from `build_rows_from_files()`**

Change the method to only read storyboard:

```python
def build_rows_from_files(
    self,
    storyboard_path: str,
) -> list[dict[str, str]]:
    storyboard_lines = read_non_empty_lines(storyboard_path)

    return [
        {
            "scene_id": str(index),
            "storyboard_text": storyboard_line,
        }
        for index, storyboard_line in enumerate(storyboard_lines, start=1)
    ]
```

- [ ] **Step 2: Remove `optimized_image_prompt_path` param from `generate_files_batch()`**

Change signature from:
```python
def generate_files_batch(
    self,
    storyboard_path: str | None = None,
    optimized_image_prompt_path: str | None = None,
    rows: list[dict[str, str]] | None = None,
    ...
)
```
To:
```python
def generate_files_batch(
    self,
    storyboard_path: str | None = None,
    rows: list[dict[str, str]] | None = None,
    ...
)
```

- [ ] **Step 3: Update row-building fallback in `generate_files_batch()`**

Change:
```python
if rows is None:
    if storyboard_path is None or optimized_image_prompt_path is None:
        raise ValueError(
            "必须提供 rows 参数，或同时提供 storyboard_path + optimized_image_prompt_path"
        )
    rows = self.build_rows_from_files(
        storyboard_path, optimized_image_prompt_path
    )
```
To:
```python
if rows is None:
    if storyboard_path is None:
        raise ValueError(
            "必须提供 rows 参数，或提供 storyboard_path"
        )
    rows = self.build_rows_from_files(storyboard_path)
```

- [ ] **Step 4: Update `all_rows_text` construction in `generate_files_batch()`**

Change:
```python
all_rows_text = "\n\n".join(
    f"[{i + 1}] 分镜原文：{row['storyboard_text']}\n"
    f"    优化后生图提示词：{row['optimized_image_prompt']}"
    for i, row in enumerate(rows)
)
```
To:
```python
all_rows_text = "\n\n".join(
    f"[{i + 1}] 分镜原文：{row['storyboard_text']}"
    for i, row in enumerate(rows)
)
```

- [ ] **Step 5: Verify the file looks correct**

Run: `python -c "from core.video_prompt_generator import VideoPromptGenerator; print('OK')"`

---

### Task 2: Update VideoPromptGenerator tests

**Files:**
- Modify: `tests/test_video_prompt_generator.py`

- [ ] **Step 1: Update `test_builds_rows_from_files`**

Remove the `optimized_image_prompt_path` parameter and the assertion for the removed field:

```python
def test_builds_rows_from_files(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        sb = os.path.join(tmp_dir, "s.txt")
        with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
        gen = VideoPromptGenerator(client=FakeVideoClient(), model="m", prompts_dir=tmp_dir)
        rows = gen.build_rows_from_files(storyboard_path=sb)
    self.assertEqual(2, len(rows))
    self.assertEqual("1. A", rows[0]["storyboard_text"])
    self.assertNotIn("optimized_image_prompt", rows[0])
```

- [ ] **Step 2: Update `test_batch_generates_all_in_one_call`**

Remove `op` file and `optimized_image_prompt_path=op`:

```python
def test_batch_generates_all_in_one_call(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)
        sb = os.path.join(tmp_dir, "s.txt")
        with open(sb, "w") as f: f.write("1. A\n\n2. B\n")

        class C(FakeVideoClient):
            def chat_multi_turn(self, model, messages, **kw):
                super().chat_multi_turn(model, messages, **kw)
                return "VA\nVB"

        client = C()
        gen = VideoPromptGenerator(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
        r = _collect_batch(gen.generate_files_batch(storyboard_path=sb, prompt_name=self.PROMPT_NAME))
    self.assertEqual("1. VA\n2. VB", r)
    self.assertEqual(1, len(client.calls))
```

- [ ] **Step 3: Update remaining tests that use `optimized_image_prompt` in rows**

`test_normalizes_multiline_output`: remove `"optimized_image_prompt": "P"` from row dict.
`test_batch_all_rows_in_one_message`: remove `"optimized_image_prompt": "PA"/"PB"` from row dicts.
`test_batch_multi_turn_for_large_input`: remove `"optimized_image_prompt": f"P{i}"` from row dicts.
`test_logs_batch_progress`: remove `"optimized_image_prompt": "P"/"Q"` from row dicts.

- [ ] **Step 4: Assert that AI input no longer contains the removed field**

In `test_batch_all_rows_in_one_message`, add assertion:
```python
self.assertNotIn("优化后生图提示词", client.calls[0]["user_content"])
```

- [ ] **Step 5: Run tests**

```bash
python -m unittest tests.test_video_prompt_generator -v
```
Expected: all 6 tests PASS

---

### Task 3: Simplify PromptOptimizer

**Files:**
- Modify: `core/prompt_optimizer.py`

- [ ] **Step 1: Remove `raw_prompt_path` from `_build_file_rows()`**

Change:
```python
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
```
To:
```python
def _build_file_rows(
    self,
    storyboard_path: str,
) -> list[dict[str, str]]:
    storyboard_lines = read_non_empty_lines(storyboard_path)

    return [
        {
            "scene_id": str(index),
            "storyboard_text": storyboard_line,
        }
        for index, storyboard_line in enumerate(storyboard_lines, start=1)
    ]
```

- [ ] **Step 2: Update `build_rows_from_files()`**

Change:
```python
def build_rows_from_files(
    self,
    storyboard_path: str,
    raw_prompt_path: str,
) -> list[dict[str, str]]:
    return self._build_file_rows(storyboard_path, raw_prompt_path)
```
To:
```python
def build_rows_from_files(
    self,
    storyboard_path: str,
) -> list[dict[str, str]]:
    return self._build_file_rows(storyboard_path)
```

- [ ] **Step 3: Update `optimize_files_batch()` signature and row-building**

Change signature:
```python
def optimize_files_batch(
    self,
    storyboard_path: str | None = None,
    raw_prompt_path: str | None = None,
    rows: list[dict[str, str]] | None = None,
    ...
)
```
To:
```python
def optimize_files_batch(
    self,
    storyboard_path: str | None = None,
    rows: list[dict[str, str]] | None = None,
    ...
)
```

Change the row-building fallback:
```python
if rows is None:
    if storyboard_path is None or raw_prompt_path is None:
        raise ValueError(
            "必须提供 rows 参数，或同时提供 storyboard_path + raw_prompt_path"
        )
    rows = self._build_file_rows(storyboard_path, raw_prompt_path)
```
To:
```python
if rows is None:
    if storyboard_path is None:
        raise ValueError(
            "必须提供 rows 参数，或提供 storyboard_path"
        )
    rows = self._build_file_rows(storyboard_path)
```

- [ ] **Step 4: Update `all_rows_text` construction**

Change:
```python
all_rows_text = "\n\n".join(
    f"[{i + 1}] 分镜原文：{row['storyboard_text']}\n"
    f"    原始画面提示词：{row['raw_image_prompt']}"
    for i, row in enumerate(rows)
)
```
To:
```python
all_rows_text = "\n\n".join(
    f"[{i + 1}] 分镜原文：{row['storyboard_text']}"
    for i, row in enumerate(rows)
)
```

- [ ] **Step 5: Update initial_user message**

Since the "原始画面提示词" reference is gone, update the prompt text:
Change:
```python
initial_user = (
    f"以下是 {total} 条分镜和对应的原始画面提示词。\n\n"
    ...
)
```
To:
```python
initial_user = (
    f"以下是 {total} 条分镜。\n\n"
    ...
)
```

- [ ] **Step 6: Verify**

```bash
python -c "from core.prompt_optimizer import PromptOptimizer; print('OK')"
```

---

### Task 4: Update PromptOptimizer tests

**Files:**
- Modify: `tests/test_prompt_optimizer.py`

- [ ] **Step 1: Update `test_builds_rows_from_files`**

```python
def test_builds_rows_from_files(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        sb = os.path.join(tmp_dir, "s.txt")
        with open(sb, "w") as f: f.write("1. A\n\n2. B\n")
        opt = PromptOptimizer(client=FakeClient(), model="m", prompts_dir=tmp_dir)
        rows = opt.build_rows_from_files(storyboard_path=sb)
    self.assertEqual(2, len(rows))
    self.assertEqual("1. A", rows[0]["storyboard_text"])
    self.assertNotIn("raw_image_prompt", rows[0])
```

- [ ] **Step 2: Update `test_raises_on_mismatched_counts`**

This test is no longer relevant since there's nothing to mismatch. Delete it.

- [ ] **Step 3: Update `test_batch_mode_returns_all_lines`**

Remove `rp` file and `raw_prompt_path=rp`:
```python
def test_batch_mode_returns_all_lines(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        self._make_prompts_dir(tmp_dir)
        sb = os.path.join(tmp_dir, "s.txt")
        with open(sb, "w") as f: f.write("1. A\n\n2. B\n")

        class C(FakeClient):
            def chat_multi_turn(self, model, messages, **kw):
                super().chat_multi_turn(model, messages, **kw)
                return "OA\nOB"

        client = C()
        opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(tmp_dir, "prompts"))
        r = _collect_batch(opt.optimize_files_batch(storyboard_path=sb))
    self.assertEqual("1. OA\n2. OB", r)
    self.assertEqual(1, len(client.calls))
```

- [ ] **Step 4: Update `test_loads_default_prompt_with_back_facing_rule`**

Remove `rp` file and `raw_prompt_path=rp`:
```python
def test_loads_default_prompt_with_back_facing_rule(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        sb = os.path.join(tmp_dir, "s.txt")
        with open(sb, "w") as f: f.write("1. X\n")
        root = os.path.dirname(os.path.dirname(__file__))
        client = FakeClient()
        opt = PromptOptimizer(client=client, model="m", prompts_dir=os.path.join(root, "prompts"))
        _collect_batch(opt.optimize_files_batch(storyboard_path=sb, prompt_name="default"))
    self.assertIn("背对镜头", client.calls[0]["system_prompt"])
```

- [ ] **Step 5: Update `test_flattens_multiline_output`**

Remove `rp` file and `raw_prompt_path=rp`.

- [ ] **Step 6: Update `test_appends_negative_prompt_when_missing`**

Remove `rp` file and `raw_prompt_path=rp`.

- [ ] **Step 7: Update `test_csv_mode_returns_string`**

Remove `"raw_image_prompt": "P"` from row dict.

- [ ] **Step 8: Update `test_batch_single_turn`**

Remove `"raw_image_prompt": f"P{i}"` from row dicts.

- [ ] **Step 9: Update `test_batch_multi_turn`**

Remove `"raw_image_prompt": f"P{i}"` from row dicts.

- [ ] **Step 10: Update `test_batch_all_rows_in_one_message`**

Remove `"raw_image_prompt":` fields from row dicts. Add assertion:
```python
self.assertNotIn("原始画面提示词", client.calls[0]["user_content"])
```

- [ ] **Step 11: Run tests**

```bash
python -m unittest tests.test_prompt_optimizer -v
```
Expected: all tests PASS (11 tests → 10 after removing `test_raises_on_mismatched_counts`)

---

### Task 5: Simplify table_utils

**Files:**
- Modify: `utils/table_utils.py`

- [ ] **Step 1: Simplify `merge_prompt_tables()`**

This function merged storyboard + image_prompt tables. Since the optimizer no longer needs raw_prompt, this merge function can be replaced by a simpler one that just loads storyboard table rows:

```python
def load_storyboard_table(path: str) -> list[dict[str, str]]:
    return _load_csv_rows(path, ["scene_id", "storyboard_text"])
```

Remove the original `merge_prompt_tables()` function entirely. (Keep `_load_csv_rows` private helper.)

- [ ] **Step 2: Simplify `merge_video_prompt_tables()`**

Same simplification — video generation no longer needs optimized_image_prompt:

```python
def load_storyboard_table(path: str) -> list[dict[str, str]]:
    return _load_csv_rows(path, ["scene_id", "storyboard_text"])
```

Note: Since `load_storyboard_table` is identical for both uses, define it once and use it in both places. Remove `merge_prompt_tables()` and `merge_video_prompt_tables()`.

- [ ] **Step 3: Update `write_optimized_prompt_table()` output columns**

Change fieldnames from:
```python
fieldnames = [
    "scene_id",
    "storyboard_text",
    "raw_image_prompt",
    "optimized_image_prompt",
    "notes_cn",
]
```
To:
```python
fieldnames = [
    "scene_id",
    "storyboard_text",
    "optimized_image_prompt",
    "notes_cn",
]
```

- [ ] **Step 4: Update `write_video_prompt_table()` output columns**

Change fieldnames from:
```python
fieldnames = [
    "scene_id",
    "storyboard_text",
    "optimized_image_prompt",
    "video_prompt",
    "notes_cn",
]
```
To:
```python
fieldnames = [
    "scene_id",
    "storyboard_text",
    "video_prompt",
    "notes_cn",
]
```

- [ ] **Step 5: Verify**

```bash
python -c "from utils.table_utils import load_storyboard_table, write_optimized_prompt_table, write_video_prompt_table; print('OK')"
```

---

### Task 6: Update table_utils tests

**Files:**
- Modify: `tests/test_table_utils.py`

- [ ] **Step 1: Rewrite test class**

Replace `MergePromptTablesTest` with tests for `load_storyboard_table`:

```python
class LoadStoryboardTableTest(unittest.TestCase):
    def test_loads_storyboard_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "storyboard_table.csv")

            with open(path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一"})
                writer.writerow({"scene_id": "2", "storyboard_text": "分镜二"})

            rows = table_utils.load_storyboard_table(path)

        self.assertEqual(2, len(rows))
        self.assertEqual("分镜一", rows[0]["storyboard_text"])

    def test_raises_error_when_scene_id_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "storyboard_table.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file, fieldnames=["scene_id", "storyboard_text"]
                )
                writer.writeheader()
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一"})
                writer.writerow({"scene_id": "1", "storyboard_text": "分镜一-重复"})

            with self.assertRaisesRegex(ValueError, "scene_id.*1.*重复"):
                table_utils.load_storyboard_table(path)

    def test_writes_optimized_prompt_table_without_raw_prompt_column(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "optimized.csv")
            table_utils.write_optimized_prompt_table(
                output_path,
                [
                    {
                        "scene_id": "1",
                        "storyboard_text": "分镜一",
                        "optimized_image_prompt": "优化后一",
                        "notes_cn": "备注一",
                    }
                ],
            )

            with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertNotIn("raw_image_prompt", rows[0])
        self.assertEqual("优化后一", rows[0]["optimized_image_prompt"])
```

Remove `test_merges_storyboard_and_prompt_rows_by_scene_id`, `test_raises_error_when_tables_cannot_be_matched_by_scene_id`. Keep the scene_id duplication test adapted.

- [ ] **Step 2: Run tests**

```bash
python -m unittest tests.test_table_utils -v
```
Expected: all tests PASS

---

### Task 7: Update main.py CLI commands

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Update imports**

Remove `merge_prompt_tables` and `merge_video_prompt_tables` from imports. Add `load_storyboard_table`:
```python
from utils.table_utils import (
    load_storyboard_table,
    write_optimized_prompt_table,  # if used
    write_video_prompt_table,      # if used
)
```

- [ ] **Step 2: Simplify `optimize-image-prompts` command**

Replace the current command function. Remove `--raw-prompts`, `--image-prompt-table` params. Remove TXT/CSV dual-mode complexity:

```python
@cli.command()
@click.option("--storyboard", "-s", "storyboard_path", default=None,
              help="输入分镜 TXT 文件路径")
@click.option("--storyboard-table", "storyboard_table_path", default=None,
              help="输入分镜表 CSV 文件路径")
@click.option("--prompt", "-p", "prompt_name", default="default",
              help="提示词文件名（不含 .txt）")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, type=int,
              help="每批处理的分镜数量")
@click.option("--output", "-o", "output_path", default=None,
              help="输出优化后提示词文件路径")
def optimize_image_prompts(
    storyboard_path, storyboard_table_path,
    prompt_name, batch_size, output_path
):
    """优化画面提示词"""
    text_mode = bool(storyboard_path)
    csv_mode = bool(storyboard_table_path)

    if not text_mode and not csv_mode:
        _abort_cli("请提供 --storyboard 或 --storyboard-table。")

    if text_mode and csv_mode:
        _abort_cli("TXT 模式和 CSV 模式参数不能混用，请二选一。")

    path = storyboard_path or storyboard_table_path
    if not os.path.exists(path):
        _abort_cli(f"文件不存在: {_format_cli_path(path)}")

    bundle = get_client_bundle()
    optimizer = PromptOptimizer(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        thinking_enabled=Config.OPTIMIZE_THINKING,
        reasoning_effort=Config.OPTIMIZE_REASONING_EFFORT,
    )

    if text_mode:
        if output_path is None:
            stem = get_stem(storyboard_path)
            output_path = os.path.join(
                get_output_dir_for_file(stem), f"{stem}_optimized_image_prompts.txt"
            )
        write_txt_optimization_batches(
            optimizer=optimizer,
            storyboard_path=storyboard_path,
            prompt_name=prompt_name,
            output_path=output_path,
            batch_size=batch_size,
            console_obj=console,
        )
        console.print(f"[green][OK] 优化后提示词: {output_path}[/]")
        return

    # CSV mode
    if output_path is None:
        stem = get_stem(storyboard_table_path)
        output_path = os.path.join(
            get_output_dir_for_file(stem), f"{stem}_optimized_image_prompts.csv"
        )
    rows = load_storyboard_table(storyboard_table_path)
    write_csv_optimization_batches(
        optimizer=optimizer,
        rows=rows,
        prompt_name=prompt_name,
        output_path=output_path,
        batch_size=batch_size,
        console_obj=console,
    )
    console.print(f"[green][OK] 优化后提示词表: {output_path}[/]")
```

- [ ] **Step 3: Simplify `generate-video-prompts` command**

Similar simplification — remove `--optimized-image-prompts` and `--image-prompt-table` params:

```python
@cli.command()
@click.option("--storyboard", "-s", "storyboard_path", default=None,
              help="输入分镜 TXT 文件路径")
@click.option("--storyboard-table", "storyboard_table_path", default=None,
              help="输入分镜表 CSV 文件路径")
@click.option("--prompt", "-p", "prompt_name", default="default",
              help="提示词文件名（不含 .txt）")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, type=int,
              help="每批处理的分镜数量")
@click.option("--output", "-o", "output_path", default=None,
              help="输出视频提示词文件路径")
def generate_video_prompts(
    storyboard_path, storyboard_table_path,
    prompt_name, batch_size, output_path
):
    """根据分镜原文生成视频提示词"""
    text_mode = bool(storyboard_path)
    csv_mode = bool(storyboard_table_path)

    if not text_mode and not csv_mode:
        _abort_cli("请提供 --storyboard 或 --storyboard-table。")

    if text_mode and csv_mode:
        _abort_cli("TXT 模式和 CSV 模式参数不能混用，请二选一。")

    path = storyboard_path or storyboard_table_path
    if not os.path.exists(path):
        _abort_cli(f"文件不存在: {_format_cli_path(path)}")

    bundle = get_client_bundle()
    generator = VideoPromptGenerator(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        thinking_enabled=Config.VIDEO_THINKING,
        reasoning_effort=Config.VIDEO_REASONING_EFFORT,
    )

    if text_mode:
        if output_path is None:
            stem = get_stem(storyboard_path)
            output_path = os.path.join(
                get_output_dir_for_file(stem), f"{stem}_video_prompts.txt"
            )
        write_txt_video_prompt_batches(
            generator=generator,
            storyboard_path=storyboard_path,
            prompt_name=prompt_name,
            output_path=output_path,
            batch_size=batch_size,
            console_obj=console,
        )
        console.print(f"[green][OK] 视频提示词: {output_path}[/]")
        return

    # CSV mode
    if output_path is None:
        stem = get_stem(storyboard_table_path)
        output_path = os.path.join(
            get_output_dir_for_file(stem), f"{stem}_video_prompts.csv"
        )
    rows = load_storyboard_table(storyboard_table_path)
    write_csv_video_prompt_batches(
        generator=generator,
        rows=rows,
        prompt_name=prompt_name,
        output_path=output_path,
        batch_size=batch_size,
        console_obj=console,
    )
    console.print(f"[green][OK] 视频提示词表: {output_path}[/]")
```

- [ ] **Step 4: Simplify `continue-run` command**

Remove `--raw-prompts` parameter and auto-pairing logic. The command now only needs `--storyboard`:

```python
@cli.command(name="continue-run")
@click.option("--storyboard", "-s", "storyboard_paths", multiple=True, required=True,
              help="输入分镜 TXT 文件路径（可多次指定）")
@click.option("--optimize-prompt", default="default",
              help="画面提示词优化模板名称")
@click.option("--video-prompt", "video_prompt_name", default="default",
              help="视频提示词模板名称")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, type=int,
              help="每批处理的分镜数量")
@click.option("--output-dir", "-o", "output_dir", default=None,
              help="输出目录（仅单文件模式生效）")
def continue_run(storyboard_paths, optimize_prompt, video_prompt_name,
                 batch_size, output_dir):
    """阶段二完整流水线: 画面提示词优化 → 视频提示词生成"""
    for path in storyboard_paths:
        if not os.path.exists(path):
            _abort_cli(f"文件不存在: {_format_cli_path(path)}")

    multi_file = len(storyboard_paths) > 1
    bundle = get_client_bundle()

    failed_files = []
    for i, storyboard_path in enumerate(storyboard_paths, start=1):
        stem = os.path.basename(os.path.dirname(os.path.abspath(storyboard_path)))
        if multi_file:
            console.print(
                f"\n[bold cyan]━━━ [{i}/{len(storyboard_paths)}] {stem} ━━━[/]"
            )

        try:
            run_postprocess_pipeline_for_storyboard(
                bundle=bundle,
                storyboard_path=storyboard_path,
                optimize_prompt_name=optimize_prompt,
                video_prompt_name=video_prompt_name,
                batch_size=batch_size,
                unattended=True,
                output_dir=output_dir if not multi_file else None,
            )
        except Exception as e:
            console.print(f"[red]✗ {stem} 处理失败: {e}[/]")
            failed_files.append(stem)
            continue

    if multi_file:
        if failed_files:
            console.print(
                f"\n[yellow][OK] 完成 {len(storyboard_paths) - len(failed_files)}/{len(storyboard_paths)} 个文件，"
                f"失败: {', '.join(failed_files)}[/]"
            )
        else:
            console.print(f"\n[bold green][OK] 全部完成！共处理 {len(storyboard_paths)} 个文件[/]")
```

- [ ] **Step 5: Verify main.py imports**

```bash
python -c "import main; print('OK')"
```

---

### Task 8: Update CLI tests

**Files:**
- Modify: `tests/test_main_optimize_cli.py`

- [ ] **Step 1: Update `test_txt_mode_writes_optimized_prompt_txt`**

Remove `raw_prompt_path` file creation and `--raw-prompts` argument. Change expected output (1-based numbering removed in AI output? No — numbering is added by `all_lines.extend(numbered_batch_lines)` in PromptOptimizer. Let me re-check...).

Actually, the test checks output format `"1. 优化后提示词2\n2. 优化后提示词3"`. The numbering is added by `PromptOptimizer.optimize_files_batch()` (lines like `f"{completed + j + 1}. {line}"`). The FakeClient returns `f"优化后提示词{self.call_count}"` — call_count starts at 1 for connect test, so first real call is 2, second is 3.

But wait — with the simplified flow, will there still be 2 calls for 2 lines with batch_size=1? Yes, because batch_size=1 means one row per batch, so the first batch triggers the connect check + one API call, then the confirm + one API call for the second batch. Let me verify: `_check_model_connectivity` makes one call, then the first batch makes one call producing output. The second batch makes the confirm call producing more output. So call_count would be 2 (connect) + 3 (first batch) and 4 (second batch)? Actually, FakePromptClient's call_count starts at 0, so:
- Connect check: call_count=1, returns "优化后提示词1"
- First batch: call_count=2, returns "优化后提示词2"
- Second batch: call_count=3, returns "优化后提示词3"

Expected: "1. 优化后提示词2\n2. 优化后提示词3" — this should still work.

```python
def test_txt_mode_writes_optimized_prompt_txt(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompts_dir = os.path.join(tmp_dir, "prompts")
        os.makedirs(os.path.join(prompts_dir, "image_prompt_optimize"), exist_ok=True)
        with open(
            os.path.join(prompts_dir, "image_prompt_optimize", "default.txt"),
            "w", encoding="utf-8",
        ) as file:
            file.write("你是提示词优化器")

        storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
        output_path = os.path.join(tmp_dir, "optimized.txt")

        with open(storyboard_path, "w", encoding="utf-8") as file:
            file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

        runner = CliRunner()
        fake_bundle = SimpleNamespace(
            client=FakePromptClient(),
            model="test-model",
        )

        with (
            patch("main.get_client_bundle", return_value=fake_bundle),
            patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
        ):
            result = runner.invoke(
                main.cli,
                [
                    "optimize-image-prompts",
                    "--storyboard",
                    storyboard_path,
                    "--batch-size",
                    "1",
                    "--output",
                    output_path,
                ],
            )

        self.assertEqual(0, result.exit_code, result.output)

        with open(output_path, "r", encoding="utf-8-sig") as file:
            output_text = file.read().strip()

    self.assertEqual(
        "1. 优化后提示词2\n2. 优化后提示词3",
        output_text,
    )
```

- [ ] **Step 2: Update `test_csv_mode_writes_optimized_prompt_csv`**

Remove `image_prompt_table_path`. Change to use `load_storyboard_table`. The expected output rows no longer have `raw_image_prompt`:

```python
def test_csv_mode_writes_optimized_prompt_csv(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompts_dir = os.path.join(tmp_dir, "prompts")
        os.makedirs(os.path.join(prompts_dir, "image_prompt_optimize"), exist_ok=True)
        with open(
            os.path.join(prompts_dir, "image_prompt_optimize", "default.txt"),
            "w", encoding="utf-8",
        ) as file:
            file.write("你是提示词优化器")

        storyboard_table_path = os.path.join(tmp_dir, "storyboard_table.csv")
        output_path = os.path.join(tmp_dir, "optimized.csv")

        with open(storyboard_table_path, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=["scene_id", "storyboard_text"]
            )
            writer.writeheader()
            writer.writerow({"scene_id": "1", "storyboard_text": "第一段分镜"})

        runner = CliRunner()
        fake_bundle = SimpleNamespace(
            client=FakePromptClient(),
            model="test-model",
        )

        with (
            patch("main.get_client_bundle", return_value=fake_bundle),
            patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
        ):
            result = runner.invoke(
                main.cli,
                [
                    "optimize-image-prompts",
                    "--storyboard-table",
                    storyboard_table_path,
                    "--batch-size",
                    "1",
                    "--output",
                    output_path,
                ],
            )

        self.assertEqual(0, result.exit_code, result.output)

        with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))

    self.assertEqual(
        [
            {
                "scene_id": "1",
                "storyboard_text": "第一段分镜",
                "optimized_image_prompt": "1. 优化后提示词2",
                "notes_cn": "",
            }
        ],
        rows,
    )
```

- [ ] **Step 3: Update `test_txt_mode_writes_video_prompt_txt_from_optimized_image_prompts`**

Remove `optimized_image_prompt_path`. Change to only `--storyboard`:

```python
def test_txt_mode_writes_video_prompt_txt_from_optimized_image_prompts(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompts_dir = os.path.join(tmp_dir, "prompts")
        os.makedirs(
            os.path.join(prompts_dir, "video_prompt_from_image"), exist_ok=True
        )
        with open(
            os.path.join(prompts_dir, "video_prompt_from_image",
                         "2026.4.13-带商业运镜测试简化版2(1).txt"),
            "w", encoding="utf-8",
        ) as file:
            file.write("你是视频提示词生成器")

        storyboard_path = os.path.join(tmp_dir, "storyboard.txt")
        output_path = os.path.join(tmp_dir, "video_prompts.txt")

        with open(storyboard_path, "w", encoding="utf-8") as file:
            file.write("1. 第一段分镜\n\n2. 第二段分镜\n")

        runner = CliRunner()
        fake_bundle = SimpleNamespace(
            client=FakeVideoPromptClient(),
            model="test-model",
        )

        with (
            patch("main.get_client_bundle", return_value=fake_bundle),
            patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
        ):
            result = runner.invoke(
                main.cli,
                [
                    "generate-video-prompts",
                    "--storyboard",
                    storyboard_path,
                    "--prompt",
                    "2026.4.13-带商业运镜测试简化版2(1)",
                    "--batch-size",
                    "1",
                    "--output",
                    output_path,
                ],
            )

        self.assertEqual(0, result.exit_code, result.output)

        with open(output_path, "r", encoding="utf-8-sig") as file:
            output_text = file.read().strip()

    self.assertEqual("1. 视频提示词2\n2. 视频提示词3", output_text)
```

- [ ] **Step 4: Update `test_csv_mode_writes_video_prompt_csv_from_optimized_image_prompts`**

Remove `image_prompt_table_path`. Only use `--storyboard-table`:

```python
def test_csv_mode_writes_video_prompt_csv_from_optimized_image_prompts(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        prompts_dir = os.path.join(tmp_dir, "prompts")
        os.makedirs(
            os.path.join(prompts_dir, "video_prompt_from_image"), exist_ok=True
        )
        with open(
            os.path.join(prompts_dir, "video_prompt_from_image",
                         "2026.4.13-带商业运镜测试简化版2(1).txt"),
            "w", encoding="utf-8",
        ) as file:
            file.write("你是视频提示词生成器")

        storyboard_table_path = os.path.join(tmp_dir, "storyboard_table.csv")
        output_path = os.path.join(tmp_dir, "video_prompts.csv")

        with open(storyboard_table_path, "w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=["scene_id", "storyboard_text"]
            )
            writer.writeheader()
            writer.writerow({"scene_id": "1", "storyboard_text": "第一段分镜"})

        runner = CliRunner()
        fake_bundle = SimpleNamespace(
            client=FakeVideoPromptClient(),
            model="test-model",
        )

        with (
            patch("main.get_client_bundle", return_value=fake_bundle),
            patch.object(main.Config, "PROMPTS_DIR", prompts_dir),
        ):
            result = runner.invoke(
                main.cli,
                [
                    "generate-video-prompts",
                    "--storyboard-table",
                    storyboard_table_path,
                    "--prompt",
                    "2026.4.13-带商业运镜测试简化版2(1)",
                    "--batch-size",
                    "1",
                    "--output",
                    output_path,
                ],
            )

        self.assertEqual(0, result.exit_code, result.output)

        with open(output_path, "r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))

    self.assertEqual(
        [
            {
                "scene_id": "1",
                "storyboard_text": "第一段分镜",
                "video_prompt": "1. 视频提示词2",
                "notes_cn": "",
            }
        ],
        rows,
    )
```

- [ ] **Step 5: Run CLI tests**

```bash
python -m unittest tests.test_main_optimize_cli -v
```
Expected: all tests PASS

---

### Task 9: Update interactive.py helper functions

**Files:**
- Modify: `core/interactive.py`

- [ ] **Step 1: Update `write_txt_optimization_batches()`**

Remove `raw_prompt_path` parameter:

```python
def write_txt_optimization_batches(
    optimizer: PromptOptimizer,
    storyboard_path: str,
    prompt_name: str,
    output_path: str,
    batch_size: int,
    console_obj: Console | None = None,
) -> str:
    console_obj = console_obj or console
    _check_model_connectivity(optimizer.client, optimizer.model, console_obj)

    row_total = len(read_non_empty_lines(storyboard_path))

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = progress.add_task(
            "优化进度",
            total=row_total,
            completed=0,
            step_label="第 0/? 批",
            current_label=f"共 {row_total} 行，等待模型处理...",
            total_elapsed="0.0s",
            unit_elapsed="0.0s",
        )
        result = ""
        for step in optimizer.optimize_files_batch(
            storyboard_path=storyboard_path,
            prompt_name=prompt_name,
            rows_per_batch=batch_size,
            output_file=output_path,
        ):
            if isinstance(step, str):
                result = step
                progress.update(task_id, completed=row_total,
                                step_label="优化完成",
                                current_label=f"共 {row_total} 行")
            else:
                progress.update(task_id, completed=step["completed"],
                                step_label=f"第 {step['batch_index']}/{step['batch_total']} 批",
                                current_label=f"已获取 {step['completed']}/{step['total']} 行")

    write_file(output_path, result, log_saved=False)
    return result
```

- [ ] **Step 2: Update `write_csv_optimization_batches()`**

Remove `raw_image_prompt` from output row construction:

Change:
```python
optimized_rows = [
    {
        "scene_id": rows[i]["scene_id"],
        "storyboard_text": rows[i]["storyboard_text"],
        "raw_image_prompt": rows[i]["raw_image_prompt"],
        "optimized_image_prompt": line,
        "notes_cn": "",
    }
    for i, line in enumerate(optimized_lines)
]
```
To:
```python
optimized_rows = [
    {
        "scene_id": rows[i]["scene_id"],
        "storyboard_text": rows[i]["storyboard_text"],
        "optimized_image_prompt": line,
        "notes_cn": "",
    }
    for i, line in enumerate(optimized_lines)
]
```

- [ ] **Step 3: Update `write_txt_video_prompt_batches()`**

Remove `optimized_image_prompt_path` parameter:

```python
def write_txt_video_prompt_batches(
    generator: VideoPromptGenerator,
    storyboard_path: str,
    prompt_name: str,
    output_path: str,
    batch_size: int,
    console_obj: Console | None = None,
) -> str:
    console_obj = console_obj or console
    _check_model_connectivity(generator.client, generator.model, console_obj)

    row_total = len(read_non_empty_lines(storyboard_path))

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = progress.add_task(
            "生成进度",
            total=row_total,
            completed=0,
            step_label="第 0/? 批",
            current_label=f"共 {row_total} 行，等待模型处理...",
            total_elapsed="0.0s",
            unit_elapsed="0.0s",
        )
        result = ""
        for step in generator.generate_files_batch(
            storyboard_path=storyboard_path,
            prompt_name=prompt_name,
            rows_per_batch=batch_size,
            output_file=output_path,
        ):
            if isinstance(step, str):
                result = step
                progress.update(task_id, completed=row_total,
                                step_label="生成完成",
                                current_label=f"共 {row_total} 行")
            else:
                progress.update(task_id, completed=step["completed"],
                                step_label=f"第 {step['batch_index']}/{step['batch_total']} 批",
                                current_label=f"已获取 {step['completed']}/{step['total']} 行")

    write_file(output_path, result, log_saved=False)
    return result
```

- [ ] **Step 4: Update `write_csv_video_prompt_batches()`**

Remove `optimized_image_prompt` from output rows:

Change:
```python
video_rows = [
    {
        "scene_id": rows[i]["scene_id"],
        "storyboard_text": rows[i]["storyboard_text"],
        "optimized_image_prompt": rows[i]["optimized_image_prompt"],
        "video_prompt": line,
        "notes_cn": "",
    }
    for i, line in enumerate(video_lines)
]
```
To:
```python
video_rows = [
    {
        "scene_id": rows[i]["scene_id"],
        "storyboard_text": rows[i]["storyboard_text"],
        "video_prompt": line,
        "notes_cn": "",
    }
    for i, line in enumerate(video_lines)
]
```

- [ ] **Step 5: Remove `select_storyboard_and_optimized_prompt_files()` function**

This function is no longer needed (it scanned for `*_optimized_image_prompts.txt` files). Delete it.

- [ ] **Step 6: Remove `scan_storyboard_optimized_image_prompt_files()` function**

This function is no longer needed. Delete it.

- [ ] **Step 7: Simplify `select_storyboard_and_raw_prompt_files()`**

This function was used for the optimize step (to pair storyboard with raw prompts). Now the optimize step only needs storyboard files. Rename it to `select_storyboard_files_for_postprocess()` and simplify:

```python
def select_storyboard_files_for_postprocess() -> list[str]:
    """Multi-select storyboard files for postprocess pipeline."""
    storyboard_files = scan_output_files("_storyboard")
    if not storyboard_files:
        console.print("[red]未找到分镜 TXT 文件，请先执行步骤 3[/]")
        return []

    selected = select_storyboard_files(storyboard_files)
    return selected
```

- [ ] **Step 8: Update `select_optimization_input_mode()` calls**

The function `select_optimization_input_mode()` takes labels that mention file pairs. Update the default labels or remove the function since it's now simpler. Actually, both steps now have the same single-input TXT/CSV choice, so keep it but update the defaults:

Actually, looking at the code, `select_optimization_input_mode()` is called in two places:
1. Step 4 (optimize): `select_optimization_input_mode()` with defaults
2. Step 5 (video): `select_optimization_input_mode(workflow_label=..., txt_label=..., csv_label=...)`

Since both now just select storyboard input, we could simplify. But the function still works as-is with updated labels. Let's just keep it.

- [ ] **Step 9: Verify**

```bash
python -c "from core.interactive import write_txt_optimization_batches, write_txt_video_prompt_batches; print('OK')"
```

---

### Task 10: Update interactive.py pipeline functions

**Files:**
- Modify: `core/interactive.py:1160-1277` and `core/interactive.py:1516-1644` and `core/interactive.py:1955-2061`

- [ ] **Step 1: Update `run_postprocess_pipeline_for_storyboard()`**

Remove `raw_prompt_path` parameter. Update both optimization and video generation calls:

```python
def run_postprocess_pipeline_for_storyboard(
    bundle: ClientBundle,
    storyboard_path: str,
    optimize_prompt_name: str,
    video_prompt_name: str,
    batch_size: int,
    unattended: bool = True,
    output_dir: str | None = None,
) -> list[tuple[str, str]]:
    """对单个 storyboard.txt 执行阶段二流水线，返回 (标签, 路径) 列表"""
    stem = os.path.basename(os.path.dirname(storyboard_path))
    rel_name = _safe_relpath(storyboard_path, Config.OUTPUT_DIR)
    out_dir = output_dir or get_output_dir_for_file(stem)

    console.print(Panel(
        f"[bold]分镜文件: {rel_name}[/]\n"
        "阶段: 2/2（画面提示词优化 → 视频提示词生成）\n"
        f"模型: {bundle.model}",
        title="✨ 开始后处理",
        border_style="magenta",
        padding=_panel_padding(console),
    ))

    saved_files = []

    # 步骤 4: 画面提示词优化
    console.print("\n[bold cyan]━━━ 步骤 4/5: 画面提示词优化 ━━━[/]")
    optimizer = PromptOptimizer(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        thinking_enabled=Config.OPTIMIZE_THINKING,
        reasoning_effort=Config.OPTIMIZE_REASONING_EFFORT,
    )
    optimized_path = os.path.join(out_dir, f"{stem}_optimized_image_prompts.txt")
    write_txt_optimization_batches(
        optimizer=optimizer,
        storyboard_path=storyboard_path,
        prompt_name=optimize_prompt_name,
        output_path=optimized_path,
        batch_size=batch_size,
        console_obj=console,
    )
    console.print(f"[green]✓ 优化后提示词: {optimized_path}[/]")
    saved_files.append(("优化后提示词", optimized_path))

    if not unattended:
        review = step_review(optimized_path, "画面提示词优化")
        if review == "skip":
            return saved_files
        while review == "retry":
            write_txt_optimization_batches(
                optimizer=optimizer,
                storyboard_path=storyboard_path,
                prompt_name=optimize_prompt_name,
                output_path=optimized_path,
                batch_size=batch_size,
                console_obj=console,
            )
            console.print(f"[green]✓ 重新生成完成: {optimized_path}[/]")
            review = step_review(optimized_path, "画面提示词优化")
            if review == "skip":
                return saved_files

    # 步骤 5: 视频提示词生成
    console.print("\n[bold cyan]━━━ 步骤 5/5: 视频提示词生成 ━━━[/]")
    generator = VideoPromptGenerator(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        thinking_enabled=Config.VIDEO_THINKING,
        reasoning_effort=Config.VIDEO_REASONING_EFFORT,
    )
    video_prompt_path = os.path.join(out_dir, f"{stem}_video_prompts.txt")
    write_txt_video_prompt_batches(
        generator=generator,
        storyboard_path=storyboard_path,
        prompt_name=video_prompt_name,
        output_path=video_prompt_path,
        batch_size=batch_size,
        console_obj=console,
    )
    console.print(f"[green]✓ 视频提示词: {video_prompt_path}[/]")
    saved_files.append(("视频提示词", video_prompt_path))

    if not unattended:
        review = step_review(video_prompt_path, "视频提示词生成")
        if review == "skip":
            return saved_files
        while review == "retry":
            write_txt_video_prompt_batches(
                generator=generator,
                storyboard_path=storyboard_path,
                prompt_name=video_prompt_name,
                output_path=video_prompt_path,
                batch_size=batch_size,
                console_obj=console,
            )
            console.print(f"[green]✓ 重新生成完成: {video_prompt_path}[/]")
            review = step_review(video_prompt_path, "视频提示词生成")
            if review == "skip":
                return saved_files

    console.print()
    _print_saved_files_summary(
        f"✅ {rel_name} 阶段二完成",
        saved_files,
        base_dir=Config.OUTPUT_DIR,
        border_style="green",
        console_obj=console,
    )
    console.print()

    return saved_files
```

- [ ] **Step 2: Update `_run_postprocess_pipeline_inner()`**

Remove the file-pairing logic and `raw_prompt_path`:

```python
def _run_postprocess_pipeline_inner():
    console.print("[bold cyan]🔍 环境检查[/]")
    bundle = get_client()

    console.print("[bold cyan]📂 选择分镜文件[/]")
    storyboard_paths = select_storyboard_files_for_postprocess()
    if not storyboard_paths:
        return

    console.print("[bold cyan]📝 选择系统提示词模板[/]")
    console.print("[dim]画面提示词优化模板[/]")
    optimize_prompt_name = select_prompt("image_prompt_optimize", "画面提示词优化模板")
    console.print("[dim]视频提示词生成模板[/]")
    video_prompt_name = select_prompt("video_prompt_from_image", "视频提示词生成模板")

    unattended = _execute_prompt(inquirer.confirm(
        message="是否开启无人值守模式？（开启后将自动执行阶段二，不会中途暂停）",
        default=True,
    ))

    if unattended:
        console.print("[green]✓ 无人值守模式已开启，将全自动执行阶段二[/]\n")
    else:
        console.print("[yellow]✓ 交互模式，每步完成后可预览/编辑/重新生成[/]\n")

    total = len(storyboard_paths)
    console.print(Panel(
        f"[bold]共 {total} 个分镜文件待处理[/]",
        title="✨ 开始后处理",
        border_style="magenta",
        padding=_panel_padding(console),
    ))

    all_results: list[tuple[str, list[tuple[str, str]]]] = []

    for i, storyboard_path in enumerate(storyboard_paths, start=1):
        stem = os.path.basename(os.path.dirname(storyboard_path))
        try:
            results = run_postprocess_pipeline_for_storyboard(
                bundle=bundle,
                storyboard_path=storyboard_path,
                optimize_prompt_name=optimize_prompt_name,
                video_prompt_name=video_prompt_name,
                batch_size=10,
                unattended=unattended,
            )
            all_results.append((storyboard_path, results))
        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠️ 用户中断操作，正在返回主菜单...[/]")
            return
        except Exception as e:
            _print_error(
                console,
                f"❌ 处理失败: {stem}",
                str(e),
                "已跳过此文件，继续处理下一个。",
            )
            console.print()
            all_results.append((storyboard_path, [("错误", str(e))]))

    # 最终汇总 (unchanged from current code)
    ...
```

- [ ] **Step 3: Update `_run_single_step_inner()` step 4 (TXT mode)**

Remove the raw_prompt file selection. Change to only select storyboard:

```python
elif step == 4:
    optimization_mode = select_optimization_input_mode()

    if optimization_mode == "txt":
        storyboard_files = scan_output_files("_storyboard")
        if not storyboard_files:
            console.print("[red]未找到分镜 TXT 文件，请先执行步骤 3[/]")
            return
        selected_storyboard = select_input_file(storyboard_files, Config.OUTPUT_DIR, "分镜 TXT")
        if not selected_storyboard:
            return

        bundle = get_client()
        prompt_name = select_prompt("image_prompt_optimize", "画面提示词优化模板")
        optimizer = PromptOptimizer(
            client=bundle.client,
            model=bundle.model,
            prompts_dir=Config.PROMPTS_DIR,
            thinking_enabled=Config.OPTIMIZE_THINKING,
            reasoning_effort=Config.OPTIMIZE_REASONING_EFFORT,
        )
        stem = os.path.basename(os.path.dirname(selected_storyboard))
        out_dir = get_output_dir_for_file(stem)
        out_path = os.path.join(out_dir, f"{stem}_optimized_image_prompts.txt")
        result = write_txt_optimization_batches(
            optimizer=optimizer,
            storyboard_path=selected_storyboard,
            prompt_name=prompt_name,
            output_path=out_path,
            batch_size=10,
            console_obj=console,
        )
        console.print(f"[green]✓ 优化后提示词: {out_path}[/]")
        preview_file_content(out_path)
    else:
        # CSV mode - similar simplification
        ...
```

- [ ] **Step 4: Update `_run_single_step_inner()` step 4 (CSV mode)**

```python
    else:
        # CSV mode for optimization
        csv_files = scan_project_files(".csv")
        storyboard_csv_files = [f for f in csv_files if "storyboard_table" in os.path.basename(f)]
        if not storyboard_csv_files:
            console.print("[red]未找到 storyboard_table.csv 文件[/]")
            return
        selected_csv = select_input_file(storyboard_csv_files, os.path.dirname(os.path.dirname(__file__)), "分镜表 CSV")
        if not selected_csv:
            return

        bundle = get_client()
        prompt_name = select_prompt("image_prompt_optimize", "画面提示词优化模板")
        optimizer = PromptOptimizer(
            client=bundle.client,
            model=bundle.model,
            prompts_dir=Config.PROMPTS_DIR,
            thinking_enabled=Config.OPTIMIZE_THINKING,
            reasoning_effort=Config.OPTIMIZE_REASONING_EFFORT,
        )
        out_path = selected_csv.replace("storyboard_table", "optimized_image_prompts").replace(".csv", ".csv")
        # ensure output is in output/ directory
        rows = load_storyboard_table(selected_csv)
        result = write_csv_optimization_batches(
            optimizer=optimizer,
            rows=rows,
            prompt_name=prompt_name,
            output_path=out_path,
            batch_size=10,
            console_obj=console,
        )
        console.print(f"[green]✓ 优化后提示词表: {out_path}[/]")
        preview_file_content(out_path)
```

Actually wait, the CSV mode in the interactive single step needs more thought. Let me look at how it currently works...

Currently, CSV mode for step 4 (optimize) uses `select_storyboard_and_raw_prompt_files()` which returns TXT file pairs, then reads them and converts to CSV. That seems incorrect — it says CSV mode but reads TXT files. Let me just simplify both branches to only need storyboard.

Actually, looking at the current code more carefully:

For step 4 CSV mode (lines 1547-1577):
```python
else:
    selected_storyboard, selected_raw_prompt = select_storyboard_and_raw_prompt_files()
    ...
    merged_rows = optimizer.build_rows_from_files(
        storyboard_path=selected_storyboard,
        raw_prompt_path=selected_raw_prompt,
    )
```

It actually still uses TXT files even in "CSV" mode... that's the existing behavior. The CSV mode label is misleading. Since we're removing `raw_prompt_path`, we just need to remove the raw_prompt part. The CSV mode stays the same pattern — it reads storyboard TXT and produces CSV output.

Wait, actually what the "CSV mode" does in steps 4 and 5 is that it produces CSV output format, not that it reads CSV input. The input is still storyboard TXT files. The mode just determines output format. OK, I'll keep the same pattern but remove the raw_prompt dependency.

Let me simplify this part of the plan. The CSV mode in the interactive step 4 reads storyboard TXT files and produces CSV output. I'll keep this pattern.

Let me finalize:

For steps 4 and 5 in `_run_single_step_inner()`, simplify to only select storyboard files (no pairing needed):

**Step 4 TXT mode**: Select storyboard → optimize → output TXT
**Step 4 CSV mode**: Select storyboard → optimize → output CSV
**Step 5 TXT mode**: Select storyboard → video generate → output TXT
**Step 5 CSV mode**: Select storyboard → video generate → output CSV

All four branches just need a storyboard file, no pairing needed.

- [ ] **Step 5: Update `_run_single_step_inner()` step 5 (TXT mode)**

```python
elif step == 5:
    generation_mode = select_optimization_input_mode(
        workflow_label="视频提示词生成",
        txt_label="storyboard.txt → video_prompts.txt",
        csv_label="storyboard.txt → video_prompts.csv",
    )

    if generation_mode == "txt":
        storyboard_files = scan_output_files("_storyboard")
        if not storyboard_files:
            console.print("[red]未找到分镜 TXT 文件，请先执行步骤 3[/]")
            return
        selected_storyboard = select_input_file(storyboard_files, Config.OUTPUT_DIR, "分镜 TXT")
        if not selected_storyboard:
            return

        bundle = get_client()
        prompt_name = select_prompt("video_prompt_from_image", "视频提示词生成模板")
        generator = VideoPromptGenerator(
            client=bundle.client,
            model=bundle.model,
            prompts_dir=Config.PROMPTS_DIR,
            thinking_enabled=Config.VIDEO_THINKING,
            reasoning_effort=Config.VIDEO_REASONING_EFFORT,
        )
        stem = os.path.basename(os.path.dirname(selected_storyboard))
        out_dir = get_output_dir_for_file(stem)
        out_path = os.path.join(out_dir, f"{stem}_video_prompts.txt")
        result = write_txt_video_prompt_batches(
            generator=generator,
            storyboard_path=selected_storyboard,
            prompt_name=prompt_name,
            output_path=out_path,
            batch_size=10,
            console_obj=console,
        )
        console.print(f"[green]✓ 视频提示词: {out_path}[/]")
        preview_file_content(out_path)
    else:
        # CSV mode - same pattern but outputs CSV
        storyboard_files = scan_output_files("_storyboard")
        if not storyboard_files:
            console.print("[red]未找到分镜 TXT 文件，请先执行步骤 3[/]")
            return
        selected_storyboard = select_input_file(storyboard_files, Config.OUTPUT_DIR, "分镜 TXT")
        if not selected_storyboard:
            return

        bundle = get_client()
        prompt_name = select_prompt("video_prompt_from_image", "视频提示词生成模板")
        generator = VideoPromptGenerator(
            client=bundle.client,
            model=bundle.model,
            prompts_dir=Config.PROMPTS_DIR,
            thinking_enabled=Config.VIDEO_THINKING,
            reasoning_effort=Config.VIDEO_REASONING_EFFORT,
        )
        stem = os.path.basename(os.path.dirname(selected_storyboard))
        out_dir = get_output_dir_for_file(stem)
        out_path = os.path.join(out_dir, f"{stem}_video_prompts.csv")
        rows = generator.build_rows_from_files(storyboard_path=selected_storyboard)
        result = write_csv_video_prompt_batches(
            generator=generator,
            rows=rows,
            prompt_name=prompt_name,
            output_path=out_path,
            batch_size=10,
            console_obj=console,
        )
        console.print(f"[green]✓ 视频提示词表: {out_path}[/]")
        preview_file_content(out_path)
```

- [ ] **Step 6: Update `_run_single_step_inner()` step 4 CSV mode similarly**

Same pattern — select storyboard, optimize, output CSV.

---

### Task 11: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
python -m unittest discover -s tests -v
```

- [ ] **Step 2: Fix any failing tests**

Address any unexpected failures from the refactoring.

- [ ] **Step 3: Run tests again to confirm all pass**

```bash
python -m unittest discover -s tests -v
```
Expected: all tests PASS

---

### Task 12: Cleanup — Remove unused imports and functions

- [ ] **Step 1: Check for unused imports in all modified files**

After all changes, verify no unused imports remain in:
- `main.py` (remove `merge_prompt_tables`, `merge_video_prompt_tables`, `scan_storyboard_prompt_files`)
- `core/interactive.py` (remove `merge_prompt_tables`, `merge_video_prompt_tables` if unused)

- [ ] **Step 2: Final code check**

```bash
python -c "import main; import core.interactive; import core.prompt_optimizer; import core.video_prompt_generator; import utils.table_utils; print('All imports OK')"
```
