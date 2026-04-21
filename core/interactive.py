"""
交互式 CLI 向导模块
用户直接运行 python main.py 时进入此向导，全程菜单选择，无需手动输入命令。
"""
import os
import sys
import glob as glob_mod
import subprocess

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.syntax import Syntax
from dotenv import load_dotenv, set_key, dotenv_values

from config import Config
from api.client_factory import create_clients, ClientBundle
from core.srt_converter import convert_srt_to_txt
from core.srt_corrector import SrtCorrector
from core.storyboard_generator import (
    StoryboardGenerator,
    StoryboardGenerationUnstableError,
    normalize_storyboard_output,
)
from core.prompt_generator import PromptGenerator
from core.prompt_optimizer import PromptOptimizer
from core.video_prompt_generator import VideoPromptGenerator
from utils.file_utils import read_file, write_file, get_stem, get_safe_stem, get_output_dir_for_file
from utils.logger import suppress_console_logs
from utils.table_utils import write_optimized_prompt_table, write_video_prompt_table

console = Console()
_NARROW_CONSOLE_WIDTH = 100
_VERY_NARROW_CONSOLE_WIDTH = 72


# ─── 工具函数 ───────────────────────────────────────────

def _execute_prompt(prompt):
    """执行 Inquirer 提示，并在完成后刷新界面。"""
    result = prompt.execute()
    console.clear()
    return result


def _safe_relpath(path: str, start: str) -> str:
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return os.path.basename(path)


def _console_width(console_obj: Console | None = None) -> int:
    console_obj = console_obj or console
    return max(40, getattr(console_obj, "width", 80) or 80)


def _is_narrow_console(console_obj: Console | None = None) -> bool:
    return _console_width(console_obj) <= _NARROW_CONSOLE_WIDTH


def _is_very_narrow_console(console_obj: Console | None = None) -> bool:
    return _console_width(console_obj) <= _VERY_NARROW_CONSOLE_WIDTH


def _shorten_middle(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    if max_length <= 10:
        return text[:max_length]
    head = (max_length - 3) // 2
    tail = max_length - 3 - head
    return f"{text[:head]}...{text[-tail:]}"


def _compact_path(path: str, base_dir: str | None = None, console_obj: Console | None = None) -> str:
    display = _safe_relpath(path, base_dir) if base_dir else path
    if not _is_narrow_console(console_obj):
        return display

    max_length = max(24, _console_width(console_obj) - 18)
    basename = os.path.basename(display)
    if len(basename) <= max_length:
        return basename
    return _shorten_middle(display, max_length)


def _panel_padding(console_obj: Console | None = None) -> tuple[int, int]:
    return (0, 1) if _is_narrow_console(console_obj) else (1, 2)


def _print_error(console_obj: Console | None, title: str, message: str, hint: str | None = None):
    console_obj = console_obj or console
    body = message
    if hint:
        body = f"{body}\n[dim]{hint}[/]"
    console_obj.print(
        Panel(
            body,
            title=title,
            border_style="red",
            padding=_panel_padding(console_obj),
        )
    )


def _storyboard_failure_hint() -> str:
    return "请检查 .env 中的 MAX_RETRY、模型配置或分镜提示词模板后重试。"


def _print_runtime_failure(title: str, error: RuntimeError, hint: str | None = None):
    _print_error(console, title, str(error), hint or "已返回主菜单，请修正配置、输入文件或提示词后重试。")


def _print_storyboard_degradation_summary(
    console_obj: Console | None,
    warnings: list[str],
):
    if not warnings:
        return

    console_obj = console_obj or console
    body = "\n".join(f"- {message}" for message in warnings)
    body += "\n[dim]已输出保守分镜结果；如需更强的合并效果，可调整提示词模板或 MAX_RETRY 后重试。[/]"
    console_obj.print(
        Panel(
            body,
            title="⚠ 分镜已降级输出",
            border_style="yellow",
            padding=_panel_padding(console_obj),
        )
    )


class StageOneStoryboardPassError(RuntimeError):
    """Raised when the storyboard step fails during a stage-one pipeline pass."""


def _print_key_value_summary(
    title: str,
    rows: list[tuple[str, str]],
    border_style: str = "cyan",
    console_obj: Console | None = None,
):
    console_obj = console_obj or console
    if _is_narrow_console(console_obj):
        body = "\n".join(f"[cyan]{label}[/]: {value}" for label, value in rows)
        console_obj.print(
            Panel(
                body,
                title=title,
                border_style=border_style,
                padding=_panel_padding(console_obj),
            )
        )
        return

    table = Table(title=title, border_style=border_style, show_lines=True, box=box.SIMPLE_HEAVY)
    table.add_column("配置项", style="bold cyan", width=20)
    table.add_column("值", style="white")
    for label, value in rows:
        table.add_row(label, value)
    console_obj.print(table)


def _print_saved_files_summary(
    title: str,
    saved_files: list[tuple[str, str]],
    base_dir: str | None = None,
    border_style: str = "green",
    console_obj: Console | None = None,
):
    rows = [
        (label, _compact_path(path, base_dir=base_dir, console_obj=console_obj))
        for label, path in saved_files
    ]
    _print_key_value_summary(title, rows, border_style=border_style, console_obj=console_obj)


def get_main_menu_choices() -> list:
    return [
        {"name": "🚀 阶段一完整流水线（SRT → 修正 → 提取 → 分镜）", "value": "pipeline_stage_one"},
        {"name": "✨ 阶段二完整流水线（分镜 → 画面提示词优化 → 视频提示词生成）", "value": "pipeline_stage_two"},
        {"name": "🔧 单步执行（从任意步骤开始）", "value": "single"},
        {"name": "⚙️ 配置管理（查看/修改 .env 配置）", "value": "config"},
        Separator(),
        {"name": "❌ 退出", "value": "exit"},
    ]

def scan_srt_files(input_dir: str) -> list[str]:
    """扫描 input/ 目录下所有 .srt 文件，返回文件路径列表"""
    pattern = os.path.join(input_dir, "**", "*.srt")
    files = glob_mod.glob(pattern, recursive=True)
    files.sort()
    return files


def scan_input_txt_files(input_dir: str) -> list[str]:
    """扫描 input/ 目录下所有 .txt 文件，返回文件路径列表"""
    pattern = os.path.join(input_dir, "**", "*.txt")
    files = glob_mod.glob(pattern, recursive=True)
    files.sort()
    return files


def scan_prompts(prompts_dir: str, category: str) -> list[str]:
    """扫描指定类别目录下所有 .txt 提示词模板，返回名称列表（不含扩展名）"""
    category_dir = os.path.join(prompts_dir, category)
    if not os.path.isdir(category_dir):
        return []
    names = []
    for f in sorted(os.listdir(category_dir)):
        if f.endswith(".txt"):
            names.append(os.path.splitext(f)[0])
    return names


def scan_output_files(suffix: str, ext: str = ".txt") -> list[str]:
    """扫描 output 目录下所有子文件夹中匹配后缀的文件"""
    target_dir = Config.OUTPUT_DIR
    if not os.path.isdir(target_dir):
        return []
    files = []
    for stem_dir in sorted(os.listdir(target_dir)):
        stem_path = os.path.join(target_dir, stem_dir)
        if not os.path.isdir(stem_path):
            continue
        for f in sorted(os.listdir(stem_path)):
            if f.endswith(ext) and f.endswith(f"{suffix}{ext}"):
                files.append(os.path.join(stem_path, f))
    return files


def scan_storyboard_prompt_files(storyboard_path: str) -> list[str]:
    """扫描与 storyboard.txt 同目录下的青风画面提示词 TXT 文件"""
    storyboard_dir = os.path.dirname(storyboard_path)
    if not os.path.isdir(storyboard_dir):
        return []

    files = []
    for name in sorted(os.listdir(storyboard_dir)):
        if not name.endswith(".txt"):
            continue
        if not name.startswith("画面提示词"):
            continue
        files.append(os.path.join(storyboard_dir, name))
    return files


def scan_storyboard_optimized_image_prompt_files(storyboard_path: str) -> list[str]:
    """扫描与 storyboard.txt 同目录下的优化后生图提示词 TXT 文件"""
    storyboard_dir = os.path.dirname(storyboard_path)
    if not os.path.isdir(storyboard_dir):
        return []

    files = []
    for name in sorted(os.listdir(storyboard_dir)):
        if not name.endswith(".txt"):
            continue
        if not name.endswith("_optimized_image_prompts.txt"):
            continue
        files.append(os.path.join(storyboard_dir, name))
    return files


def scan_project_files(ext: str, exclude_dirs: set[str] | None = None) -> list[str]:
    """扫描项目内指定扩展名文件，排除虚拟环境等目录"""
    root_dir = os.path.dirname(os.path.dirname(__file__))
    exclude_dirs = exclude_dirs or {"venv", "__pycache__"}
    pattern = os.path.join(root_dir, "**", f"*{ext}")
    files = []
    for path in glob_mod.glob(pattern, recursive=True):
        rel_parts = os.path.relpath(path, root_dir).split(os.sep)
        if any(part in exclude_dirs for part in rel_parts):
            continue
        files.append(path)
    files.sort()
    return files


def preview_file_content(filepath: str, max_chars: int = 500):
    """预览文件内容（前 max_chars 个字符）"""
    try:
        content = read_file(filepath)
        preview = content[:max_chars]
        if len(content) > max_chars:
            preview += f"\n\n... (共 {len(content)} 字符，已截断)"
        console.print(Panel(
            preview,
            title=f"📄 预览: {os.path.basename(filepath)}",
            border_style="dim",
            padding=_panel_padding(console),
        ))
    except Exception as e:
        _print_error(console, "❌ 预览失败", str(e))


def open_in_editor(filepath: str):
    """用系统默认编辑器打开文件"""
    try:
        if sys.platform == "win32":
            os.startfile(filepath)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", filepath])
        else:
            subprocess.Popen(["xdg-open", filepath])
        console.print(f"[dim]已在编辑器中打开: {_compact_path(filepath, console_obj=console)}[/]")
    except Exception as e:
        _print_error(console, "⚠ 无法打开编辑器", str(e), "请手动编辑该文件。")


def step_review(filepath: str, step_name: str) -> str:
    """
    步间预览交互，返回用户选择:
    - 'continue': 继续下一步
    - 'retry': 重新生成本步骤
    - 'skip': 跳过后续步骤
    """
    preview_file_content(filepath)
    console.print()

    choice = _execute_prompt(inquirer.select(
        message=f"【{step_name}】生成完毕，请选择操作：",
        choices=[
            {"name": "✅ 满意，继续下一步", "value": "continue"},
            {"name": "✏️ 打开文件编辑，编辑后继续", "value": "edit"},
            {"name": "🔄 不满意，重新生成本步骤", "value": "retry"},
            {"name": "⏭️ 跳过后续步骤", "value": "skip"},
        ],
        default="continue",
    ))

    if choice == "edit":
        open_in_editor(filepath)
        _execute_prompt(inquirer.confirm(
            message="编辑完成后按回车继续...",
            default=True,
        ))
        return "continue"

    return choice


def get_client() -> ClientBundle:
    """创建 API 客户端"""
    try:
        bundle = create_clients()
    except ValueError as e:
        _print_error(console, "❌ 配置错误", str(e))
        sys.exit(1)

    console.print(
        f"[dim]当前模型: {Config.MODEL_NAME} ({Config.MODEL_BASE_URL})[/]"
    )
    console.print("[green]✓ API 配置已加载[/]\n")

    return bundle


# ─── 交互选择 ───────────────────────────────────────────

def select_files(srt_files: list[str]) -> list[str]:
    """交互式选择 SRT 文件，返回选中的文件路径列表"""
    console.print("[bold cyan]📂 扫描到以下 SRT 文件：[/]\n")
    console.print("  [yellow]0[/] — 全部文件（依次处理）")
    for i, f in enumerate(srt_files, start=1):
        rel = os.path.relpath(f, Config.INPUT_DIR)
        console.print(f"  [yellow]{i}[/] — {rel}")
    console.print()

    while True:
        answer = _execute_prompt(inquirer.text(
            message="请输入文件编号（多选用逗号分隔，如 1,3,5；输入 0 选择全部）：",
        ))

        answer = answer.strip()
        if not answer:
            console.print("[red]请输入至少一个编号[/]")
            continue

        if answer == "0":
            console.print("[green]已选择全部文件[/]\n")
            return list(srt_files)

        try:
            indices = [int(x.strip()) for x in answer.split(",")]
        except ValueError:
            console.print("[red]输入格式有误，请输入数字编号[/]")
            continue

        invalid = [x for x in indices if x < 1 or x > len(srt_files)]
        if invalid:
            console.print(f"[red]无效编号: {invalid}，有效范围 1~{len(srt_files)}[/]")
            continue

        selected = [srt_files[i - 1] for i in indices]
        names = [os.path.relpath(f, Config.INPUT_DIR) for f in selected]
        console.print(f"[green]已选择: {', '.join(names)}[/]\n")
        return selected


def select_mode() -> str:
    """交互式选择生成模式"""
    choice = _execute_prompt(inquirer.select(
        message="请选择生成模式：",
        choices=[
            {"name": "🖼️ 仅生成图片分镜提示词", "value": "image"},
            {"name": "🎬 仅生成视频分镜提示词", "value": "video"},
            {"name": "🖼️🎬 同时生成图片和视频提示词", "value": "both"},
        ],
        default="both",
    ))
    mode_labels = {"image": "图片", "video": "视频", "both": "图片+视频"}
    console.print(f"[green]已选择: {mode_labels[choice]}[/]\n")
    return choice


def select_optimization_input_mode(
    workflow_label: str = "画面提示词优化",
    txt_label: str = "storyboard.txt + 原始提示词.txt",
    csv_label: str = "storyboard_table.csv + image_prompt_table.csv",
) -> str:
    """交互式选择双输入流程的 TXT/CSV 模式"""
    choice = _execute_prompt(inquirer.select(
        message=f"请选择{workflow_label}输入模式：",
        choices=[
            {"name": f"📝 TXT 模式（{txt_label}）", "value": "txt"},
            {"name": f"📊 CSV 表格模式（{csv_label}）", "value": "csv"},
        ],
        default="txt",
    ))
    mode_labels = {"txt": "TXT 模式", "csv": "CSV 表格模式"}
    console.print(f"[green]已选择: {mode_labels[choice]}[/]\n")
    return choice


def select_prompt(category: str, label: str) -> str:
    """交互式选择指定类别的系统提示词模板"""
    names = scan_prompts(Config.PROMPTS_DIR, category)
    if not names:
        console.print(f"[yellow]⚠ {label}提示词目录为空，将使用 default[/]")
        return "default"

    if len(names) == 1:
        console.print(f"[dim]{label}提示词只有一个模板: {names[0]}，自动选择[/]")
        return names[0]

    choices = []
    for name in names:
        display = f"⭐ {name}" if name == "default" else f"   {name}"
        choices.append({"name": display, "value": name})

    choice = _execute_prompt(inquirer.select(
        message=f"请选择【{label}】系统提示词模板：",
        choices=choices,
        default="default" if "default" in names else names[0],
    ))

    console.print(f"[green]已选择{label}提示词: {choice}[/]\n")
    return choice


def get_single_step_choices() -> list:
    return [
        {"name": "📝 步骤 1: SRT AI 修正（输入: .srt 文件，输出: 修正后 .srt）", "value": 1},
        {"name": "📄 步骤 2: 修正后 SRT → TXT 提取（输入: 修正后 .srt）", "value": 2},
        {"name": "🎬 步骤 3: AI 分镜生成（输入: 修正后 .txt 文件）", "value": 3},
        {"name": "✨ 步骤 4: 画面提示词优化（进入后选择 TXT / CSV）", "value": 4},
        {"name": "🎥 步骤 5: 视频提示词生成（进入后选择 TXT / CSV）", "value": 5},
    ]


def write_txt_optimization_batches(
    optimizer: PromptOptimizer,
    storyboard_path: str,
    raw_prompt_path: str,
    prompt_name: str,
    output_path: str,
    batch_size: int,
    console_obj: Console | None = None,
) -> str:
    console_obj = console_obj or console
    optimized_lines = []

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = _add_pending_step_task(
            progress,
            "优化进度",
            "正在请求模型...",
            include_unit_elapsed=True,
        )
        task_initialized = False
        for event in optimizer.iter_optimized_file_progress(
            storyboard_path=storyboard_path,
            raw_prompt_path=raw_prompt_path,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            if not task_initialized:
                progress.update(task_id, total=event["row_total"])
                task_initialized = True
            optimized_lines.append(event["optimized_line"])
            write_file(output_path, "\n".join(optimized_lines), log_saved=False)
            progress.update(
                task_id,
                completed=event["row_index"],
                step_label=f"第 {event['batch_index']}/{event['batch_total']} 批",
                current_label=f"批内 {event['batch_row_index']}/{event['batch_row_total']}",
                unit_elapsed=_format_elapsed_seconds(event["batch_elapsed_seconds"]),
                total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
            )

    return "\n".join(optimized_lines)


def write_csv_optimization_batches(
    optimizer: PromptOptimizer,
    rows: list[dict[str, str]],
    prompt_name: str,
    output_path: str,
    batch_size: int,
    console_obj: Console | None = None,
) -> list[dict[str, str]]:
    console_obj = console_obj or console
    optimized_rows = []

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = _add_pending_step_task(
            progress,
            "优化进度",
            "正在请求模型...",
            include_unit_elapsed=True,
        )
        task_initialized = False
        for event in optimizer.iter_optimized_row_progress(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            if not task_initialized:
                progress.update(task_id, total=event["row_total"])
                task_initialized = True
            optimized_rows.append(event["optimized_row"])
            write_optimized_prompt_table(output_path, optimized_rows)
            progress.update(
                task_id,
                completed=event["row_index"],
                step_label=f"第 {event['batch_index']}/{event['batch_total']} 批",
                current_label=f"批内 {event['batch_row_index']}/{event['batch_row_total']}",
                unit_elapsed=_format_elapsed_seconds(event["batch_elapsed_seconds"]),
                total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
            )

    return optimized_rows


def write_txt_video_prompt_batches(
    generator: VideoPromptGenerator,
    storyboard_path: str,
    optimized_image_prompt_path: str,
    prompt_name: str,
    output_path: str,
    batch_size: int,
    console_obj: Console | None = None,
) -> str:
    console_obj = console_obj or console
    video_lines = []

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = _add_pending_step_task(
            progress,
            "生成进度",
            "正在请求模型...",
            include_unit_elapsed=True,
        )
        task_initialized = False
        for event in generator.iter_generate_file_progress(
            storyboard_path=storyboard_path,
            optimized_image_prompt_path=optimized_image_prompt_path,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            if not task_initialized:
                progress.update(task_id, total=event["row_total"])
                task_initialized = True
            video_lines.append(event["video_line"])
            write_file(output_path, "\n".join(video_lines), log_saved=False)
            progress.update(
                task_id,
                completed=event["row_index"],
                step_label=f"第 {event['batch_index']}/{event['batch_total']} 批",
                current_label=f"批内 {event['batch_row_index']}/{event['batch_row_total']}",
                unit_elapsed=_format_elapsed_seconds(event["batch_elapsed_seconds"]),
                total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
            )

    return "\n".join(video_lines)


def write_csv_video_prompt_batches(
    generator: VideoPromptGenerator,
    rows: list[dict[str, str]],
    prompt_name: str,
    output_path: str,
    batch_size: int,
    console_obj: Console | None = None,
) -> list[dict[str, str]]:
    console_obj = console_obj or console
    video_rows = []

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = _add_pending_step_task(
            progress,
            "生成进度",
            "正在请求模型...",
            include_unit_elapsed=True,
        )
        task_initialized = False
        for event in generator.iter_generate_row_progress(
            rows=rows,
            prompt_name=prompt_name,
            batch_size=batch_size,
        ):
            if not task_initialized:
                progress.update(task_id, total=event["row_total"])
                task_initialized = True
            video_rows.append(event["generated_row"])
            write_video_prompt_table(output_path, video_rows)
            progress.update(
                task_id,
                completed=event["row_index"],
                step_label=f"第 {event['batch_index']}/{event['batch_total']} 批",
                current_label=f"批内 {event['batch_row_index']}/{event['batch_row_total']}",
                unit_elapsed=_format_elapsed_seconds(event["batch_elapsed_seconds"]),
                total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
            )

    return video_rows


def _create_step_progress(console_obj: Console) -> Progress:
    if _is_very_narrow_console(console_obj):
        return Progress(
            TextColumn("[cyan]{task.fields[step_label]}[/]"),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("[dim]{task.fields[current_label]}[/]"),
            TextColumn("[dim]{task.fields[total_elapsed]}[/]"),
            console=console_obj,
            transient=True,
            expand=True,
        )
    return Progress(
        TextColumn("[cyan]{task.fields[step_label]}[/]"),
        BarColumn(bar_width=None if _is_narrow_console(console_obj) else 40),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("[dim]{task.fields[current_label]}[/]"),
        TextColumn("[dim]{task.fields[total_elapsed]}[/]"),
        console=console_obj,
        transient=True,
        expand=True,
    )


def _format_elapsed_seconds(seconds: float) -> str:
    return f"{seconds:.1f}s"


def _add_pending_step_task(
    progress: Progress,
    description: str,
    waiting_label: str,
    include_unit_elapsed: bool = False,
):
    fields = {
        "step_label": description,
        "current_label": waiting_label,
        "total_elapsed": "0.0s",
    }
    if include_unit_elapsed:
        fields["unit_elapsed"] = "0.0s"
    return progress.add_task(description, total=1, completed=0, **fields)


def run_srt_correction_with_progress(
    corrector: SrtCorrector,
    srt_content: str,
    prompt_name: str,
    console_obj: Console | None = None,
) -> str:
    console_obj = console_obj or console
    corrected_parts = []

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = _add_pending_step_task(progress, "SRT 修正", "正在请求模型...")
        task_initialized = False
        for event in corrector.iter_correct_progress(srt_content, prompt_name):
            if not task_initialized:
                progress.update(task_id, total=event["batch_total"])
                task_initialized = True
            corrected_parts.append(event["content"])
            progress.update(
                task_id,
                completed=event["batch_index"],
                step_label="SRT 修正",
                current_label=f"第 {event['batch_index']}/{event['batch_total']} 批",
                total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
            )

    return "\n\n".join(corrected_parts)


def run_storyboard_generation_with_progress(
    generator: StoryboardGenerator,
    text: str,
    prompt_name: str,
    console_obj: Console | None = None,
    return_diagnostics: bool = False,
) -> str | dict[str, object]:
    console_obj = console_obj or console
    storyboards = []
    storyboard_items = []
    uses_normalized_chunks = False
    degraded_warnings = []

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = _add_pending_step_task(progress, "分镜生成", "正在请求模型...")
        task_initialized = False
        for event in generator.iter_generate_progress(text, prompt_name):
            if not task_initialized:
                progress.update(task_id, total=event["chunk_total"])
                task_initialized = True
            if "normalized_content" in event:
                uses_normalized_chunks = True
                for line in event["normalized_content"].splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped[0].isdigit() and ". " in stripped:
                        storyboard_items.append(stripped.split(". ", 1)[1])
                    else:
                        storyboard_items.append(stripped)
            else:
                storyboards.append(event["content"])
            if event.get("degraded_fallback") and event.get("warning_message"):
                degraded_warnings.append(event["warning_message"])
            progress.update(
                task_id,
                completed=event["chunk_index"],
                step_label="分镜生成",
                current_label=f"第 {event['chunk_index']}/{event['chunk_total']} 段",
                total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
            )

    if uses_normalized_chunks:
        result_text = "\n".join(
            f"{index}. {item}" for index, item in enumerate(storyboard_items, start=1)
        )
        _print_storyboard_degradation_summary(console_obj, degraded_warnings)
        if return_diagnostics:
            return {
                "text": result_text,
                "degraded_warnings": degraded_warnings,
            }
        return result_text

    result_text = normalize_storyboard_output(text, "\n".join(storyboards), prompt_name=prompt_name)
    _print_storyboard_degradation_summary(console_obj, degraded_warnings)
    if return_diagnostics:
        return {
            "text": result_text,
            "degraded_warnings": degraded_warnings,
        }
    return result_text


def run_prompt_generation_with_progress(
    generator: PromptGenerator,
    storyboard_text: str,
    mode: str,
    image_prompt_name: str,
    video_prompt_name: str,
    console_obj: Console | None = None,
) -> dict:
    console_obj = console_obj or console
    result = {"image_prompts": [], "video_prompts": []}

    with suppress_console_logs(), _create_step_progress(console_obj) as progress:
        task_id = _add_pending_step_task(progress, "提示词生成", "正在请求模型...")
        task_initialized = False
        current_stage = None
        for event in generator.iter_generate_progress(
            storyboard_text,
            mode=mode,
            image_prompt_name=image_prompt_name,
            video_prompt_name=video_prompt_name,
        ):
            stage_key = (event["prompt_type"], event["stage_index"])
            if not task_initialized:
                progress.update(task_id, total=event["scene_total"])
                task_initialized = True
            if current_stage != stage_key:
                progress.update(
                    task_id,
                    completed=0,
                    total=event["scene_total"],
                    step_label=f"{event['prompt_label']}提示词",
                    current_label=f"{event['scene_index']}/{event['scene_total']}",
                    total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
                )
            current_stage = stage_key

            result[f"{event['prompt_type']}_prompts"].append(event["formatted_prompt"])
            progress.update(
                task_id,
                completed=event["scene_index"],
                total=event["scene_total"],
                step_label=f"{event['prompt_label']}提示词",
                current_label=f"{event['scene_index']}/{event['scene_total']}",
                total_elapsed=_format_elapsed_seconds(event["total_elapsed_seconds"]),
            )

    return {
        "image_prompts": "\n\n".join(result["image_prompts"]),
        "video_prompts": "\n\n".join(result["video_prompts"]),
    }


def show_summary_and_confirm(
    selected_files: list[str],
    mode: str,
    correction_prompt: str,
    storyboard_prompt: str,
    image_prompt: str | None,
    video_prompt: str | None,
    bundle: ClientBundle = None,
) -> bool:
    """显示配置汇总并请求确认"""
    mode_labels = {
        "image": "仅图片",
        "video": "仅视频",
        "both": "图片+视频",
        "stage_one": "阶段一（修正→提取→分镜）",
    }

    rows = [
        (
            "选中文件",
            "\n".join(
                _compact_path(f, base_dir=Config.INPUT_DIR, console_obj=console)
                for f in selected_files
            ),
        ),
        ("文件数量", str(len(selected_files))),
        ("生成模式", mode_labels.get(mode, mode)),
        ("当前模型", bundle.model if bundle else Config.MODEL_NAME),
        ("SRT 修正提示词", correction_prompt),
        ("分镜生成提示词", storyboard_prompt),
    ]
    if image_prompt:
        rows.append(("图片提示词模板", image_prompt))
    if video_prompt:
        rows.append(("视频提示词模板", video_prompt))

    console.print()
    _print_key_value_summary("📋 配置汇总", rows, border_style="cyan", console_obj=console)
    console.print()

    confirm = _execute_prompt(inquirer.confirm(
        message="确认以上配置并开始执行？",
        default=True,
    ))

    return confirm


# ─── 流水线执行 ─────────────────────────────────────────

def run_pipeline_for_file(
    bundle: ClientBundle,
    srt_path: str,
    correction_prompt: str,
    storyboard_prompt: str,
    file_index: int,
    total_files: int,
    unattended: bool = True,
    output_dir: str | None = None,
) -> list[tuple[str, str]]:
    """对单个 SRT 文件执行阶段一流水线，返回 (标签, 路径) 列表"""
    stem = get_safe_stem(srt_path, Config.INPUT_DIR)
    rel_name = _safe_relpath(srt_path, Config.INPUT_DIR)
    out_dir = output_dir or get_output_dir_for_file(stem)

    console.print(Panel(
        f"[bold]文件 {file_index}/{total_files}: {rel_name}[/]\n"
        "阶段: 1/2（修正 → 提取 → 分镜）\n"
        f"模型: {bundle.model}",
        title=f"🎬 开始处理 [{file_index}/{total_files}]",
        border_style="cyan",
        padding=_panel_padding(console),
    ))

    saved_files = []
    rerun_reason = None
    rerun_attempted = False
    final_pass = None

    for pass_index in range(1, 3):
        if pass_index > 1:
            rerun_attempted = True
            body = (
                f"[bold]检测到首轮阶段一分镜不稳定，正在从原始 SRT 重新修正并重跑一遍。[/]\n"
                f"文件: {rel_name}"
            )
            if rerun_reason:
                body += f"\n[dim]触发原因: {rerun_reason}[/]"
            console.print(
                Panel(
                    body,
                    title="🔄 自动重跑阶段一",
                    border_style="yellow",
                    padding=_panel_padding(console),
                )
            )

        try:
            pass_result = _run_stage_one_pass(
                bundle=bundle,
                srt_path=srt_path,
                stem=stem,
                out_dir=out_dir,
                correction_prompt=correction_prompt,
                storyboard_prompt=storyboard_prompt,
                unattended=unattended,
            )
        except StageOneStoryboardPassError as e:
            rerun_reason = str(e)
            if pass_index < 2:
                continue
            raise RuntimeError(
                f"已从原始 SRT 重新修正并重跑一遍，但分镜仍失败：{e}"
            ) from e.__cause__

        if pass_result["should_stop"]:
            return pass_result["saved_files"]

        if pass_result["storyboard_warnings"] and pass_index < 2:
            rerun_reason = pass_result["storyboard_warnings"][0]
            continue

        final_pass = pass_result
        break

    if final_pass is None:
        raise RuntimeError("阶段一重跑后未获得可用结果。")

    saved_files = final_pass["saved_files"]

    if rerun_attempted:
        if final_pass["storyboard_warnings"]:
            console.print(
                Panel(
                    "[bold yellow]已从原始 SRT 重新修正并重跑一遍，但分镜仍不稳定。[/]\n"
                    "[dim]已保留最后一轮生成的修正文件和保守分镜结果。[/]",
                    title="⚠ 自动重跑后仍不稳定",
                    border_style="yellow",
                    padding=_panel_padding(console),
                )
            )
        else:
            console.print(
                Panel(
                    "[bold green]已从原始 SRT 重新修正并重跑一遍，第二轮成功产出分镜。[/]",
                    title="✅ 自动重跑恢复成功",
                    border_style="green",
                    padding=_panel_padding(console),
                )
            )

    console.print(
        "\n[bold green]✓ 阶段一完成：已产出分镜。[/]\n"
        "[dim]请在准备好原始画面提示词文件后，再通过阶段二完整流水线或单步执行继续。[/]"
    )

    # 单文件完成汇总
    console.print()
    _print_saved_files_summary(
        f"✅ {rel_name} 阶段一完成",
        saved_files,
        base_dir=Config.OUTPUT_DIR,
        border_style="green",
        console_obj=console,
    )
    console.print()

    return saved_files


def _run_stage_one_pass(
    bundle: ClientBundle,
    srt_path: str,
    stem: str,
    out_dir: str,
    correction_prompt: str,
    storyboard_prompt: str,
    unattended: bool,
) -> dict[str, object]:
    saved_files = []

    # 步骤 1: SRT AI 修正（保留时间戳，仅修改文案）
    console.print("\n[bold cyan]━━━ 步骤 1/3: SRT AI 修正 ━━━[/]")
    srt_content = read_file(srt_path)
    corrector = SrtCorrector(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        max_chunk_size=Config.MAX_CHUNK_SIZE,
    )
    corrected_srt = run_srt_correction_with_progress(
        corrector=corrector,
        srt_content=srt_content,
        prompt_name=correction_prompt,
        console_obj=console,
    )
    corrected_srt_path = os.path.join(out_dir, f"{stem}_corrected.srt")
    write_file(corrected_srt_path, corrected_srt)
    console.print(f"[green]✓ 完成: {corrected_srt_path}[/]")
    saved_files.append(("SRT 修正", corrected_srt_path))

    if not unattended:
        review = step_review(corrected_srt_path, "SRT AI 修正")
        if review == "skip":
            return {
                "saved_files": saved_files,
                "should_stop": True,
                "storyboard_warnings": [],
            }
        while review == "retry":
            corrected_srt = run_srt_correction_with_progress(
                corrector=corrector,
                srt_content=srt_content,
                prompt_name=correction_prompt,
                console_obj=console,
            )
            write_file(corrected_srt_path, corrected_srt)
            console.print(f"[green]✓ 重新生成完成: {corrected_srt_path}[/]")
            review = step_review(corrected_srt_path, "SRT AI 修正")
            if review == "skip":
                return {
                    "saved_files": saved_files,
                    "should_stop": True,
                    "storyboard_warnings": [],
                }

    # 步骤 2: 修正后 SRT → TXT 提取文案
    console.print("\n[bold cyan]━━━ 步骤 2/3: 修正后 SRT → TXT 提取 ━━━[/]")
    with console.status("[cyan]提取文案中..."):
        corrected_text = convert_srt_to_txt(corrected_srt_path)
    corrected_path = os.path.join(out_dir, f"{stem}_corrected.txt")
    write_file(corrected_path, corrected_text)
    console.print(f"[green]✓ 完成: {corrected_path}[/]")
    saved_files.append(("文案提取", corrected_path))

    if not unattended:
        review = step_review(corrected_path, "文案提取")
        if review == "skip":
            return {
                "saved_files": saved_files,
                "should_stop": True,
                "storyboard_warnings": [],
            }

    # 步骤 3: 分镜生成
    console.print("\n[bold cyan]━━━ 步骤 3/3: AI 分镜脚本生成 ━━━[/]")
    sb_generator = StoryboardGenerator(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        max_chunk_size=Config.MAX_CHUNK_SIZE,
    )
    sb_path = os.path.join(out_dir, f"{stem}_storyboard.txt")
    storyboard_warnings = []

    def render_storyboard() -> str:
        nonlocal storyboard_warnings
        try:
            storyboard_result = run_storyboard_generation_with_progress(
                generator=sb_generator,
                text=corrected_text,
                prompt_name=storyboard_prompt,
                console_obj=console,
                return_diagnostics=True,
            )
        except RuntimeError as e:
            raise StageOneStoryboardPassError(str(e)) from e

        storyboard_warnings = list(storyboard_result["degraded_warnings"])
        return storyboard_result["text"]

    storyboard_text = render_storyboard()
    write_file(sb_path, storyboard_text)
    console.print(f"[green]✓ 完成: {sb_path}[/]")
    saved_files.append(("分镜脚本", sb_path))

    if not unattended:
        review = step_review(sb_path, "AI 分镜生成")
        if review == "skip":
            return {
                "saved_files": saved_files,
                "should_stop": True,
                "storyboard_warnings": storyboard_warnings,
            }
        while review == "retry":
            storyboard_text = render_storyboard()
            write_file(sb_path, storyboard_text)
            console.print(f"[green]✓ 重新生成完成: {sb_path}[/]")
            review = step_review(sb_path, "AI 分镜生成")
            if review == "skip":
                return {
                    "saved_files": saved_files,
                    "should_stop": True,
                    "storyboard_warnings": storyboard_warnings,
                }

    return {
        "saved_files": saved_files,
        "should_stop": False,
        "storyboard_warnings": storyboard_warnings,
    }


def run_postprocess_pipeline_for_storyboard(
    bundle: ClientBundle,
    storyboard_path: str,
    raw_prompt_path: str,
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

    console.print("\n[bold cyan]━━━ 步骤 4/5: 画面提示词优化 ━━━[/]")
    optimizer = PromptOptimizer(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
    )
    optimized_path = os.path.join(out_dir, f"{stem}_optimized_image_prompts.txt")
    write_txt_optimization_batches(
        optimizer=optimizer,
        storyboard_path=storyboard_path,
        raw_prompt_path=raw_prompt_path,
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
                raw_prompt_path=raw_prompt_path,
                prompt_name=optimize_prompt_name,
                output_path=optimized_path,
                batch_size=batch_size,
                console_obj=console,
            )
            console.print(f"[green]✓ 重新生成完成: {optimized_path}[/]")
            review = step_review(optimized_path, "画面提示词优化")
            if review == "skip":
                return saved_files

    console.print("\n[bold cyan]━━━ 步骤 5/5: 视频提示词生成 ━━━[/]")
    generator = VideoPromptGenerator(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
    )
    video_prompt_path = os.path.join(out_dir, f"{stem}_video_prompts.txt")
    write_txt_video_prompt_batches(
        generator=generator,
        storyboard_path=storyboard_path,
        optimized_image_prompt_path=optimized_path,
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
                optimized_image_prompt_path=optimized_path,
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


# ─── 单步执行 ────────────────────────────────────────────

def select_input_file(files: list[str], base_dir: str, label: str) -> str | None:
    """从文件列表中交互选择一个文件"""
    if not files:
        _print_error(console, "❌ 未找到文件", f"未找到可用的{label}文件。")
        return None

    console.print(f"[bold cyan]📂 可用的{label}文件：[/]\n")
    for i, f in enumerate(files, start=1):
        rel = os.path.relpath(f, base_dir) if base_dir else os.path.basename(f)
        console.print(f"  [yellow]{i}[/] — {rel}")
    console.print()

    while True:
        answer = _execute_prompt(inquirer.text(
            message=f"请输入文件编号：",
        )).strip()

        try:
            idx = int(answer)
        except ValueError:
            console.print("[red]请输入数字编号[/]")
            continue

        if idx < 1 or idx > len(files):
            console.print(f"[red]无效编号，有效范围 1~{len(files)}[/]")
            continue

        selected = files[idx - 1]
        console.print(f"[green]已选择: {os.path.basename(selected)}[/]\n")
        return selected


def select_storyboard_and_raw_prompt_files() -> tuple[str, str] | tuple[None, None]:
    storyboard_files = scan_output_files("_storyboard")
    if not storyboard_files:
        console.print("[red]未找到分镜 TXT 文件，请先执行步骤 3[/]")
        return None, None

    selected_storyboard = select_input_file(
        storyboard_files, Config.OUTPUT_DIR, "分镜 TXT"
    )
    if not selected_storyboard:
        return None, None

    txt_files = scan_storyboard_prompt_files(selected_storyboard)
    if not txt_files:
        console.print("[red]未找到同目录下的“画面提示词*.txt”文件[/]")
        return None, None

    selected_raw_prompt = select_input_file(
        txt_files, os.path.dirname(selected_storyboard), "原始画面提示词 TXT"
    )
    if not selected_raw_prompt:
        return None, None

    return selected_storyboard, selected_raw_prompt


def select_storyboard_input_mode() -> str:
    return _execute_prompt(inquirer.select(
        message="请选择分镜输入来源：",
        choices=[
            {"name": "修正后文本（原流程）", "value": "corrected"},
            {"name": "任意 TXT 文件（扫描 input/）", "value": "any_txt"},
        ],
        default="corrected",
    ))


def select_storyboard_and_optimized_prompt_files() -> tuple[str, str] | tuple[None, None]:
    storyboard_files = scan_output_files("_storyboard")
    if not storyboard_files:
        console.print("[red]未找到分镜 TXT 文件，请先执行步骤 3[/]")
        return None, None

    selected_storyboard = select_input_file(
        storyboard_files, Config.OUTPUT_DIR, "分镜 TXT"
    )
    if not selected_storyboard:
        return None, None

    txt_files = scan_storyboard_optimized_image_prompt_files(selected_storyboard)
    if not txt_files:
        console.print("[red]未找到同目录下的“*_optimized_image_prompts.txt”文件[/]")
        return None, None

    selected_prompt = select_input_file(
        txt_files, os.path.dirname(selected_storyboard), "优化后生图提示词 TXT"
    )
    if not selected_prompt:
        return None, None

    return selected_storyboard, selected_prompt


def run_single_step():
    """单步执行模式：选择从某一步开始执行"""
    try:
        _run_single_step_inner()
    except StoryboardGenerationUnstableError as e:
        _print_error(console, "❌ 分镜生成失败", str(e), _storyboard_failure_hint())
    except RuntimeError as e:
        _print_runtime_failure("❌ 单步执行失败", e)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚠️ 用户中断操作，正在返回主菜单...[/]")


def _run_single_step_inner():
    """单步执行内部实现"""
    console.print(Panel(
        "[bold]选择要执行的单个步骤[/]\n"
        "可从任意中间步骤开始，使用已有的中间文件作为输入。",
        title="🔧 单步执行模式",
        border_style="yellow",
    ))
    console.print()

    step = _execute_prompt(inquirer.select(
        message="请选择要执行的步骤：",
        choices=get_single_step_choices(),
    ))

    bundle = None

    if step == 1:
        srt_files = scan_srt_files(Config.INPUT_DIR)
        selected = select_input_file(srt_files, Config.INPUT_DIR, "SRT")
        if not selected:
            return

        bundle = get_client()
        prompt_name = select_prompt("srt_correction", "SRT 修正")
        srt_content = read_file(selected)
        corrector = SrtCorrector(
            client=bundle.client,
            model=bundle.model,
            prompts_dir=Config.PROMPTS_DIR,
            max_chunk_size=Config.MAX_CHUNK_SIZE,
        )
        stem = get_safe_stem(selected, Config.INPUT_DIR)
        out_dir = get_output_dir_for_file(stem)
        result = run_srt_correction_with_progress(
            corrector=corrector,
            srt_content=srt_content,
            prompt_name=prompt_name,
            console_obj=console,
        )
        out_path = os.path.join(out_dir, f"{stem}_corrected.srt")
        write_file(out_path, result)
        console.print(f"[green]✓ SRT 修正完成: {out_path}[/]")
        preview_file_content(out_path)

    elif step == 2:
        srt_files = scan_output_files("_corrected", ext=".srt")
        if not srt_files:
            console.print("[red]未找到修正后的 .srt 文件，请先执行步骤 1[/]")
            return

        selected = select_input_file(srt_files, Config.OUTPUT_DIR, "修正后 SRT")
        if not selected:
            return

        stem = os.path.basename(os.path.dirname(selected))
        out_dir = get_output_dir_for_file(stem)
        with console.status("[cyan]提取文案中..."):
            text = convert_srt_to_txt(selected)
        out_path = os.path.join(out_dir, f"{stem}_corrected.txt")
        write_file(out_path, text)
        console.print(f"[green]✓ 文案提取完成: {out_path}[/]")
        preview_file_content(out_path)

    elif step == 3:
        input_mode = select_storyboard_input_mode()
        if input_mode == "corrected":
            txt_files = scan_output_files("_corrected")
            if not txt_files:
                console.print("[red]未找到修正后的 .txt 文件，请先执行步骤 1 和 2[/]")
                return
            selected = select_input_file(txt_files, Config.OUTPUT_DIR, "修正后文本")
            stem = os.path.basename(os.path.dirname(selected)) if selected else ""
        else:
            txt_files = scan_input_txt_files(Config.INPUT_DIR)
            if not txt_files:
                console.print("[red]未找到 input/ 目录下的 .txt 文件[/]")
                return
            selected = select_input_file(txt_files, Config.INPUT_DIR, "TXT")
            stem = get_safe_stem(selected, Config.INPUT_DIR) if selected else ""

        if not selected:
            return

        bundle = get_client()
        prompt_name = select_prompt("storyboard", "分镜生成")
        text = read_file(selected)
        generator = StoryboardGenerator(
            client=bundle.client,
            model=bundle.model,
            prompts_dir=Config.PROMPTS_DIR,
            max_chunk_size=Config.MAX_CHUNK_SIZE,
        )
        out_dir = get_output_dir_for_file(stem)
        result = run_storyboard_generation_with_progress(
            generator=generator,
            text=text,
            prompt_name=prompt_name,
            console_obj=console,
        )
        out_path = os.path.join(out_dir, f"{stem}_storyboard.txt")
        write_file(out_path, result)
        console.print(f"[green]✓ 分镜生成完成: {out_path}[/]")
        preview_file_content(out_path)

    elif step == 4:
        optimization_mode = select_optimization_input_mode()

        if optimization_mode == "txt":
            selected_storyboard, selected_raw_prompt = select_storyboard_and_raw_prompt_files()
            if not selected_storyboard or not selected_raw_prompt:
                return

            bundle = get_client()
            prompt_name = select_prompt("image_prompt_optimize", "画面提示词优化模板")
            optimizer = PromptOptimizer(
                client=bundle.client,
                model=bundle.model,
                prompts_dir=Config.PROMPTS_DIR,
            )
            stem = os.path.basename(os.path.dirname(selected_storyboard))
            out_dir = get_output_dir_for_file(stem)
            out_path = os.path.join(out_dir, f"{stem}_optimized_image_prompts.txt")
            result = write_txt_optimization_batches(
                optimizer=optimizer,
                storyboard_path=selected_storyboard,
                raw_prompt_path=selected_raw_prompt,
                prompt_name=prompt_name,
                output_path=out_path,
                batch_size=10,
                console_obj=console,
            )
            console.print(f"[green]✓ 优化后提示词: {out_path}[/]")
            preview_file_content(out_path)
        else:
            selected_storyboard, selected_raw_prompt = select_storyboard_and_raw_prompt_files()
            if not selected_storyboard or not selected_raw_prompt:
                return

            bundle = get_client()
            prompt_name = select_prompt("image_prompt_optimize", "画面提示词优化模板")
            optimizer = PromptOptimizer(
                client=bundle.client,
                model=bundle.model,
                prompts_dir=Config.PROMPTS_DIR,
            )
            stem = os.path.basename(os.path.dirname(selected_storyboard))
            out_dir = get_output_dir_for_file(stem)
            out_path = os.path.join(out_dir, f"{stem}_optimized_image_prompts.csv")
            merged_rows = optimizer.build_rows_from_files(
                storyboard_path=selected_storyboard,
                raw_prompt_path=selected_raw_prompt,
            )
            result = write_csv_optimization_batches(
                optimizer=optimizer,
                rows=merged_rows,
                prompt_name=prompt_name,
                output_path=out_path,
                batch_size=10,
                console_obj=console,
            )
            console.print(f"[green]✓ 优化后提示词表: {out_path}[/]")
            preview_file_content(out_path)

    elif step == 5:
        generation_mode = select_optimization_input_mode(
            workflow_label="视频提示词生成",
            txt_label="storyboard.txt + *_optimized_image_prompts.txt",
            csv_label="storyboard_table.csv + optimized_image_prompt_table.csv",
        )

        if generation_mode == "txt":
            selected_storyboard, selected_prompt = select_storyboard_and_optimized_prompt_files()
            if not selected_storyboard or not selected_prompt:
                return

            bundle = get_client()
            prompt_name = select_prompt("video_prompt_from_image", "视频提示词生成模板")
            generator = VideoPromptGenerator(
                client=bundle.client,
                model=bundle.model,
                prompts_dir=Config.PROMPTS_DIR,
            )
            stem = os.path.basename(os.path.dirname(selected_storyboard))
            out_dir = get_output_dir_for_file(stem)
            out_path = os.path.join(out_dir, f"{stem}_video_prompts.txt")
            result = write_txt_video_prompt_batches(
                generator=generator,
                storyboard_path=selected_storyboard,
                optimized_image_prompt_path=selected_prompt,
                prompt_name=prompt_name,
                output_path=out_path,
                batch_size=10,
                console_obj=console,
            )
            console.print(f"[green]✓ 视频提示词: {out_path}[/]")
            preview_file_content(out_path)
        else:
            selected_storyboard, selected_prompt = select_storyboard_and_optimized_prompt_files()
            if not selected_storyboard or not selected_prompt:
                return

            bundle = get_client()
            prompt_name = select_prompt("video_prompt_from_image", "视频提示词生成模板")
            generator = VideoPromptGenerator(
                client=bundle.client,
                model=bundle.model,
                prompts_dir=Config.PROMPTS_DIR,
            )
            stem = os.path.basename(os.path.dirname(selected_storyboard))
            out_dir = get_output_dir_for_file(stem)
            out_path = os.path.join(out_dir, f"{stem}_video_prompts.csv")
            merged_rows = generator.build_rows_from_files(
                storyboard_path=selected_storyboard,
                optimized_image_prompt_path=selected_prompt,
            )
            result = write_csv_video_prompt_batches(
                generator=generator,
                rows=merged_rows,
                prompt_name=prompt_name,
                output_path=out_path,
                batch_size=10,
                console_obj=console,
            )
            console.print(f"[green]✓ 视频提示词表: {out_path}[/]")
            preview_file_content(out_path)

    console.print("\n[green]单步执行完成！[/]\n")


# ─── 配置管理 ────────────────────────────────────────────

ENV_CONFIG_ITEMS = [
    ("MODEL_API_KEY", "统一模型 API Key", ""),
    ("MODEL_BASE_URL", "统一模型 API 地址", "https://api.deepseek.com"),
    ("MODEL_NAME", "统一模型名称", "deepseek-chat"),
    ("MAX_RETRY", "最大重试次数（0 表示无限重试）", "5"),
    ("REQUEST_TIMEOUT", "请求超时(秒)", "300"),
    ("MAX_CHUNK_SIZE", "最大分块大小(字符)", "3000"),
]


def config_wizard():
    """交互式配置管理向导"""
    try:
        _config_wizard_inner()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚠️ 已取消配置修改，返回主菜单...[/]")


def _config_wizard_inner():
    """配置向导内部实现"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    env_example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.example")

    if not os.path.exists(env_path):
        if os.path.exists(env_example_path):
            import shutil
            shutil.copy2(env_example_path, env_path)
            console.print("[yellow]已从 .env.example 创建 .env 文件[/]\n")
        else:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("")
            console.print("[yellow]已创建空 .env 文件[/]\n")

    current_values = dotenv_values(env_path)

    console.print(Panel(
        "[bold]查看和修改程序配置[/]\n"
        "修改后会立即保存到 .env 文件并在下次启动时生效。",
        title="⚙️ 配置管理",
        border_style="blue",
        padding=_panel_padding(console),
    ))
    console.print()

    # 显示当前配置
    if _is_narrow_console(console):
        rows = []
        for i, (key, label, default) in enumerate(ENV_CONFIG_ITEMS, start=1):
            value = current_values.get(key, "")
            display_value = value if value else f"(默认: {default})"
            if "KEY" in key and value:
                display_value = value[:8] + "..." if len(value) > 8 else value
            rows.append((f"{i}. {key}", f"{label}\n{display_value}"))
        _print_key_value_summary("当前配置", rows, border_style="blue", console_obj=console)
    else:
        table = Table(title="当前配置", border_style="blue", show_lines=True, box=box.SIMPLE_HEAVY)
        table.add_column("#", style="dim", width=3)
        table.add_column("配置项", style="cyan", width=22)
        table.add_column("说明", style="dim", width=20)
        table.add_column("当前值", style="white")

        for i, (key, label, default) in enumerate(ENV_CONFIG_ITEMS, start=1):
            value = current_values.get(key, "")
            display_value = value if value else f"[dim](默认: {default})[/]"
            if "KEY" in key and value:
                display_value = value[:8] + "..." if len(value) > 8 else value
            table.add_row(str(i), key, label, display_value)

        console.print(table)
    console.print()

    # 询问是否要修改
    want_edit = _execute_prompt(inquirer.confirm(
        message="是否要修改配置？",
        default=False,
    ))

    if not want_edit:
        console.print("[dim]配置未修改[/]\n")
        return

    # 逐项询问是否修改
    modified = False
    for key, label, default in ENV_CONFIG_ITEMS:
        current = current_values.get(key, "")
        display_current = current if current else f"(默认: {default})"

        console.print(f"\n[cyan]{label}[/] ({key})")
        console.print(f"  当前值: {display_current}")

        want_change = _execute_prompt(inquirer.confirm(
            message=f"是否修改此项？",
            default=False,
        ))

        if not want_change:
            continue

        new_value = _execute_prompt(inquirer.text(
            message=f"请输入新值（留空使用默认值 {default}）：",
            default=current,
        )).strip()

        if new_value != current:
            set_key(env_path, key, new_value)
            console.print(f"[green]✓ 已更新 {key} = {new_value}[/]")
            modified = True

    if modified:
        console.print(Panel(
            "[green]配置已保存到 .env 文件[/]\n"
            "部分配置需要重启程序后生效。",
            title="✅ 保存成功",
            border_style="green",
            padding=_panel_padding(console),
        ))
        load_dotenv(env_path, override=True)
    else:
        console.print("\n[dim]配置未修改[/]")

    console.print()


# ─── 主入口 ─────────────────────────────────────────────

def run_interactive():
    """交互式向导主入口 — 主菜单"""
    console.clear()
    # 欢迎界面
    console.print(Panel(
        "[bold white]SRT 字幕 → AI 分镜 → 提示词 全自动生成工具[/]\n\n"
        "本工具将 SRT 字幕文件自动转换为分镜脚本和 AI 绘图/视频提示词。\n"
        "通过已配置的单一 OpenAI 兼容模型接口驱动。",
        title="🎬 text2story 交互向导",
        border_style="bright_blue",
        padding=_panel_padding(console),
    ))
    console.print()

    while True:
        try:
            choice = _execute_prompt(inquirer.select(
                message="请选择操作：",
                choices=get_main_menu_choices(),
                default="pipeline_stage_one",
            ))
        except KeyboardInterrupt:
            console.print("\n[dim]再见！[/]")
            break

        if choice == "exit":
            console.print("[dim]再见！[/]")
            break
        elif choice == "pipeline_stage_one":
            _run_full_pipeline()
        elif choice == "pipeline_stage_two":
            _run_postprocess_pipeline()
        elif choice == "single":
            run_single_step()
        elif choice == "config":
            config_wizard()

        console.clear()


def _run_full_pipeline():
    """完整流水线执行（原 run_interactive 的主体逻辑）"""
    try:
        _run_full_pipeline_inner()
    except RuntimeError as e:
        _print_runtime_failure("❌ 阶段一执行失败", e)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚠️ 用户中断操作，正在返回主菜单...[/]")


def _run_full_pipeline_inner():
    """阶段一完整流水线执行内部实现"""
    # 环境检查
    console.print("[bold cyan]🔍 环境检查[/]")
    bundle = get_client()

    # 步骤 1: 选择 SRT 文件
    console.print("[bold cyan]📂 步骤 1: 选择 SRT 文件[/]")
    srt_files = scan_srt_files(Config.INPUT_DIR)
    if not srt_files:
        _print_error(
            console,
            "❌ 未找到 SRT 文件",
            f"在 {_compact_path(Config.INPUT_DIR, console_obj=console)} 目录下未找到任何 .srt 文件。",
            "请把 SRT 字幕文件放入 input 目录后重试。",
        )
        return

    selected_files = select_files(srt_files)

    # 步骤 2: 选择系统提示词
    console.print("[bold cyan]📝 步骤 2: 选择系统提示词模板[/]")

    console.print("[dim]2.1 SRT 修正提示词[/]")
    correction_prompt = select_prompt("srt_correction", "SRT 修正")

    console.print("[dim]2.2 分镜生成提示词[/]")
    storyboard_prompt = select_prompt("storyboard", "分镜生成")

    # 步骤 4: 确认配置
    confirmed = show_summary_and_confirm(
        selected_files=selected_files,
        mode="stage_one",
        correction_prompt=correction_prompt,
        storyboard_prompt=storyboard_prompt,
        image_prompt=None,
        video_prompt=None,
        bundle=bundle,
    )

    if not confirmed:
        console.print("[yellow]已取消，退出。[/]")
        return

    # 询问是否开启无人值守模式
    unattended = _execute_prompt(inquirer.confirm(
        message="是否开启无人值守模式？（开启后将自动执行阶段一，不会中途暂停）",
        default=True,
    ))

    if unattended:
        console.print("[green]✓ 无人值守模式已开启，将全自动执行阶段一[/]\n")
    else:
        console.print("[yellow]✓ 交互模式，每步完成后可预览/编辑/重新生成[/]\n")

    # 执行流水线
    console.print(Panel(
        "[bold]开始执行流水线...[/]",
        title="🚀 开始执行",
        border_style="green",
        padding=_panel_padding(console),
    ))

    all_results: list[tuple[str, list[tuple[str, str]]]] = []
    total = len(selected_files)

    for i, srt_path in enumerate(selected_files, start=1):
        try:
            results = run_pipeline_for_file(
                bundle=bundle,
                srt_path=srt_path,
                correction_prompt=correction_prompt,
                storyboard_prompt=storyboard_prompt,
                file_index=i,
                total_files=total,
                unattended=unattended,
            )
            all_results.append((srt_path, results))
        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠️ 用户中断操作，正在返回主菜单...[/]")
            return
        except Exception as e:
            rel_name = os.path.relpath(srt_path, Config.INPUT_DIR)
            _print_error(
                console,
                f"❌ 处理失败: {rel_name}",
                str(e),
                "已跳过此文件，继续处理下一个。",
            )
            console.print()
            all_results.append((srt_path, [("错误", str(e))]))

    # 最终汇总
    console.print()
    console.print(Panel(
        f"[bold green]全部完成！共处理 {len(all_results)} 个文件[/]",
        title="🎉 处理完成",
        border_style="green",
        padding=_panel_padding(console),
    ))

    if _is_narrow_console(console):
        rows = []
        for srt_path, results in all_results:
            rel_name = _compact_path(srt_path, base_dir=Config.INPUT_DIR, console_obj=console)
            for label, path in results:
                rows.append((rel_name, f"{label}\n{_compact_path(path, console_obj=console)}"))
        _print_key_value_summary("📊 最终汇总", rows, border_style="bright_green", console_obj=console)
    else:
        final_table = Table(
            title="📊 最终汇总",
            border_style="bright_green",
            show_lines=True,
            box=box.SIMPLE_HEAVY,
        )
        final_table.add_column("文件", style="cyan", width=25)
        final_table.add_column("步骤", style="white", width=15)
        final_table.add_column("输出路径", style="dim")

        for srt_path, results in all_results:
            rel_name = os.path.relpath(srt_path, Config.INPUT_DIR)
            for j, (label, path) in enumerate(results):
                file_col = rel_name if j == 0 else ""
                final_table.add_row(file_col, label, path)

        console.print(final_table)
    console.print()


def _run_postprocess_pipeline():
    """阶段二完整流水线执行"""
    try:
        _run_postprocess_pipeline_inner()
    except RuntimeError as e:
        _print_runtime_failure("❌ 阶段二执行失败", e)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚠️ 用户中断操作，正在返回主菜单...[/]")


def _run_postprocess_pipeline_inner():
    console.print("[bold cyan]🔍 环境检查[/]")
    bundle = get_client()

    console.print("[bold cyan]📂 步骤 4: 选择分镜与原始画面提示词文件[/]")
    selected_storyboard, selected_raw_prompt = select_storyboard_and_raw_prompt_files()
    if not selected_storyboard or not selected_raw_prompt:
        return

    console.print("[bold cyan]📝 步骤 5: 选择系统提示词模板[/]")
    console.print("[dim]5.1 画面提示词优化模板[/]")
    optimize_prompt_name = select_prompt("image_prompt_optimize", "画面提示词优化模板")
    console.print("[dim]5.2 视频提示词生成模板[/]")
    video_prompt_name = select_prompt("video_prompt_from_image", "视频提示词生成模板")

    unattended = _execute_prompt(inquirer.confirm(
        message="是否开启无人值守模式？（开启后将自动执行阶段二，不会中途暂停）",
        default=True,
    ))

    if unattended:
        console.print("[green]✓ 无人值守模式已开启，将全自动执行阶段二[/]\n")
    else:
        console.print("[yellow]✓ 交互模式，每步完成后可预览/编辑/重新生成[/]\n")

    run_postprocess_pipeline_for_storyboard(
        bundle=bundle,
        storyboard_path=selected_storyboard,
        raw_prompt_path=selected_raw_prompt,
        optimize_prompt_name=optimize_prompt_name,
        video_prompt_name=video_prompt_name,
        batch_size=10,
        unattended=unattended,
    )
