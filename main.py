import os
import sys

import click
from rich.console import Console
from rich.panel import Panel

from config import Config
from api.client_factory import create_clients, ClientBundle
from core.srt_converter import convert_srt_to_txt
from core.srt_corrector import SrtCorrector
from core.storyboard_generator import StoryboardGenerator
from core.prompt_generator import PromptGenerator
from core.prompt_optimizer import PromptOptimizer, DEFAULT_BATCH_SIZE
from core.video_prompt_generator import VideoPromptGenerator
from core.interactive import (
    run_interactive,
    run_pipeline_for_file,
    run_postprocess_pipeline_for_storyboard,
    run_prompt_generation_with_progress,
    run_srt_correction_with_progress,
    run_storyboard_generation_with_progress,
    write_csv_optimization_batches,
    write_txt_optimization_batches,
    write_txt_video_prompt_batches,
    write_csv_video_prompt_batches,
    scan_storyboard_prompt_files,
)
from utils.file_utils import read_file, write_file, get_stem, get_safe_stem, get_output_dir_for_file, shorten_middle
from utils.table_utils import (
    merge_prompt_tables,
    merge_video_prompt_tables,
)

console = Console()


def _format_cli_path(path: str) -> str:
    width = max(40, getattr(console, "width", 80) or 80)
    max_length = max(24, width - 18)
    basename = os.path.basename(path)
    if len(basename) <= max_length:
        return basename
    return shorten_middle(path, max_length)


def _abort_cli(message: str, title: str = "❌ 错误"):
    console.print(
        Panel(
            message,
            title=title,
            border_style="red",
            padding=(0, 1),
        )
    )
    raise SystemExit(1)


def _stem_from_output_file(path: str) -> str:
    """从 output/{stem}/{stem}_xxx.txt 路径中提取 stem（即父目录名）"""
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    return parent if parent != Config.OUTPUT_DIR else get_stem(path)


def get_client_bundle() -> ClientBundle:
    """创建 API 客户端"""
    try:
        bundle = create_clients()
    except ValueError as e:
        _abort_cli(str(e), title="❌ 配置错误")

    console.print(
        f"[dim]当前模型: {Config.MODEL_NAME} ({Config.MODEL_BASE_URL})[/]"
    )
    console.print("[green]✓ API 配置已加载[/]")

    return bundle


@click.group(invoke_without_command=True)
@click.version_option(version="1.3.0", prog_name="text2story")
@click.pass_context
def cli(ctx):
    """SRT 字幕 → AI 分镜 → 提示词生成工具

    通过一个 OpenAI 兼容模型接口，
    将 SRT 字幕文件自动转换为分镜脚本和 AI 绘图/视频提示词。

    直接运行 python main.py 进入交互式向导模式。
    """
    if ctx.invoked_subcommand is None:
        run_interactive()


@cli.command()
@click.option("--input", "-i", "input_path", required=True,
              help="输入 SRT 文件路径")
@click.option("--output", "-o", "output_path", default=None,
              help="输出 TXT 文件路径（默认自动生成）")
def extract(input_path, output_path):
    """从 SRT 字幕文件中提取纯文本"""
    if not os.path.exists(input_path):
        _abort_cli(f"文件不存在: {_format_cli_path(input_path)}")

    with console.status("[bold cyan]正在提取文案..."):
        text = convert_srt_to_txt(input_path)

    if output_path is None:
        stem = get_safe_stem(input_path, Config.INPUT_DIR)
        output_path = os.path.join(get_output_dir_for_file(stem), f"{stem}_corrected.txt")

    write_file(output_path, text)
    console.print(f"[green]✓ 文案提取完成: {output_path}[/]")


@cli.command()
@click.option("--input", "-i", "input_path", required=True,
              help="输入 SRT 文件路径")
@click.option("--output", "-o", "output_path", default=None,
              help="输出修正后 SRT 文件路径")
@click.option("--prompt", "-p", "prompt_name", default="default",
              help="提示词文件名（不含 .txt）")
def correct(input_path, output_path, prompt_name):
    """步骤1: AI 修正 SRT 字幕（保留时间戳，仅修正文案）"""
    if not os.path.exists(input_path):
        _abort_cli(f"文件不存在: {_format_cli_path(input_path)}")

    bundle = get_client_bundle()
    corrector = SrtCorrector(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        max_chunk_size=Config.MAX_CHUNK_SIZE,
    )

    srt_content = read_file(input_path)
    result = run_srt_correction_with_progress(
        corrector=corrector,
        srt_content=srt_content,
        prompt_name=prompt_name,
        console_obj=console,
    )

    if output_path is None:
        stem = get_safe_stem(input_path, Config.INPUT_DIR)
        output_path = os.path.join(
            get_output_dir_for_file(stem), f"{stem}_corrected.srt"
        )

    write_file(output_path, result)
    console.print(f"[green]✓ SRT 修正完成: {output_path}[/]")


@cli.command()
@click.option("--input", "-i", "input_path", required=True,
              help="输入修正后的文案文件路径")
@click.option("--output", "-o", "output_path", default=None,
              help="输出文件路径")
@click.option("--prompt", "-p", "prompt_name", default="default",
              help="提示词文件名（不含 .txt）")
def storyboard(input_path, output_path, prompt_name):
    """步骤3: AI 分镜脚本生成"""
    if not os.path.exists(input_path):
        _abort_cli(f"文件不存在: {_format_cli_path(input_path)}")

    bundle = get_client_bundle()
    generator = StoryboardGenerator(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
        max_chunk_size=Config.MAX_CHUNK_SIZE,
    )

    text = read_file(input_path)
    try:
        result = run_storyboard_generation_with_progress(
            generator=generator,
            text=text,
            prompt_name=prompt_name,
            console_obj=console,
        )
    except RuntimeError as e:
        _abort_cli(str(e), title="❌ 分镜生成失败")

    if output_path is None:
        stem = _stem_from_output_file(input_path)
        output_path = os.path.join(
            get_output_dir_for_file(stem), f"{stem}_storyboard.txt"
        )

    write_file(output_path, result)
    console.print(f"[green]✓ 分镜生成完成: {output_path}[/]")


@cli.command()
@click.option("--input", "-i", "input_path", required=True,
              help="输入分镜脚本文件路径")
@click.option("--mode", "-m", type=click.Choice(["image", "video", "both"]),
              default="both", help="生成模式: image/video/both")
@click.option("--image-prompt", "image_prompt_name", default="default",
              help="图片提示词模板名称")
@click.option("--video-prompt", "video_prompt_name", default="default",
              help="视频提示词模板名称")
@click.option("--output-dir", "-o", "output_dir", default=None,
              help="输出目录")
def prompt(input_path, mode, image_prompt_name, video_prompt_name, output_dir):
    """步骤4: AI 提示词生成"""
    if not os.path.exists(input_path):
        _abort_cli(f"文件不存在: {_format_cli_path(input_path)}")

    bundle = get_client_bundle()
    generator = PromptGenerator(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
    )

    text = read_file(input_path)
    stem = _stem_from_output_file(input_path)

    result = run_prompt_generation_with_progress(
        generator=generator,
        storyboard_text=text,
        mode=mode,
        image_prompt_name=image_prompt_name,
        video_prompt_name=video_prompt_name,
        console_obj=console,
    )

    out_dir = output_dir or get_output_dir_for_file(stem)
    saved_files = []

    if result["image_prompts"]:
        path = os.path.join(out_dir, f"{stem}_image_prompts.txt")
        write_file(path, result["image_prompts"])
        saved_files.append(("图片提示词", path))

    if result["video_prompts"]:
        path = os.path.join(out_dir, f"{stem}_video_prompts.txt")
        write_file(path, result["video_prompts"])
        saved_files.append(("视频提示词", path))

    for label, path in saved_files:
        console.print(f"[green]✓ {label}: {path}[/]")


@cli.command()
@click.option("--storyboard", "storyboard_path", default=None,
              help="输入分镜 TXT 文件路径")
@click.option("--raw-prompts", "raw_prompt_path", default=None,
              help="输入原始画面提示词 TXT 文件路径")
@click.option("--storyboard-table", "storyboard_table_path", default=None,
              help="输入分镜表 CSV 文件路径")
@click.option("--image-prompt-table", "image_prompt_table_path", default=None,
              help="输入原始画面提示词表 CSV 文件路径")
@click.option("--prompt", "-p", "prompt_name", default="default",
              help="提示词文件名（不含 .txt）")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, type=int,
              help="每批处理的分镜数量")
@click.option("--output", "-o", "output_path", default=None,
              help="输出优化后提示词文件路径")
def optimize_image_prompts(
    storyboard_path, raw_prompt_path, storyboard_table_path, image_prompt_table_path,
    prompt_name, batch_size, output_path
):
    """优化青风导出的画面提示词"""
    text_mode = bool(storyboard_path or raw_prompt_path)
    csv_mode = bool(storyboard_table_path or image_prompt_table_path)

    if text_mode and csv_mode:
        _abort_cli("TXT 模式和 CSV 模式参数不能混用，请二选一。")

    if not text_mode and not csv_mode:
        _abort_cli("请提供 TXT 模式参数或 CSV 模式参数中的一组。")

    if text_mode and (not storyboard_path or not raw_prompt_path):
        _abort_cli("TXT 模式需要同时提供 --storyboard 和 --raw-prompts。")

    if csv_mode and (not storyboard_table_path or not image_prompt_table_path):
        _abort_cli("CSV 模式需要同时提供 --storyboard-table 和 --image-prompt-table。")

    required_paths = []
    if text_mode:
        required_paths.extend([storyboard_path, raw_prompt_path])
    else:
        required_paths.extend([storyboard_table_path, image_prompt_table_path])

    for path in required_paths:
        if not os.path.exists(path):
            _abort_cli(f"文件不存在: {_format_cli_path(path)}")

    bundle = get_client_bundle()
    optimizer = PromptOptimizer(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
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
            raw_prompt_path=raw_prompt_path,
            prompt_name=prompt_name,
            output_path=output_path,
            batch_size=batch_size,
            console_obj=console,
        )

        console.print(f"[green]✓ 优化后提示词: {output_path}[/]")
        return

    if output_path is None:
        stem = get_stem(storyboard_table_path)
        output_path = os.path.join(
            get_output_dir_for_file(stem), f"{stem}_optimized_image_prompts.csv"
        )

    merged_rows = merge_prompt_tables(
        storyboard_table_path=storyboard_table_path,
        image_prompt_table_path=image_prompt_table_path,
    )
    write_csv_optimization_batches(
        optimizer=optimizer,
        rows=merged_rows,
        prompt_name=prompt_name,
        output_path=output_path,
        batch_size=batch_size,
        console_obj=console,
    )

    console.print(f"[green]✓ 优化后提示词表: {output_path}[/]")


@cli.command()
@click.option("--storyboard", "storyboard_path", default=None,
              help="输入分镜 TXT 文件路径")
@click.option("--optimized-image-prompts", "optimized_image_prompt_path", default=None,
              help="输入优化后生图提示词 TXT 文件路径")
@click.option("--storyboard-table", "storyboard_table_path", default=None,
              help="输入分镜表 CSV 文件路径")
@click.option("--image-prompt-table", "image_prompt_table_path", default=None,
              help="输入优化后生图提示词表 CSV 文件路径")
@click.option("--prompt", "-p", "prompt_name", default="default",
              help="提示词文件名（不含 .txt）")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, type=int,
              help="每批处理的分镜数量")
@click.option("--output", "-o", "output_path", default=None,
              help="输出视频提示词文件路径")
def generate_video_prompts(
    storyboard_path, optimized_image_prompt_path, storyboard_table_path,
    image_prompt_table_path, prompt_name, batch_size, output_path
):
    """根据分镜原文和优化后生图提示词生成视频提示词"""
    text_mode = bool(storyboard_path or optimized_image_prompt_path)
    csv_mode = bool(storyboard_table_path or image_prompt_table_path)

    if text_mode and csv_mode:
        _abort_cli("TXT 模式和 CSV 模式参数不能混用，请二选一。")

    if not text_mode and not csv_mode:
        _abort_cli("请提供 TXT 模式参数或 CSV 模式参数中的一组。")

    if text_mode and (not storyboard_path or not optimized_image_prompt_path):
        _abort_cli("TXT 模式需要同时提供 --storyboard 和 --optimized-image-prompts。")

    if csv_mode and (not storyboard_table_path or not image_prompt_table_path):
        _abort_cli("CSV 模式需要同时提供 --storyboard-table 和 --image-prompt-table。")

    required_paths = []
    if text_mode:
        required_paths.extend([storyboard_path, optimized_image_prompt_path])
    else:
        required_paths.extend([storyboard_table_path, image_prompt_table_path])

    for path in required_paths:
        if not os.path.exists(path):
            _abort_cli(f"文件不存在: {_format_cli_path(path)}")

    bundle = get_client_bundle()
    generator = VideoPromptGenerator(
        client=bundle.client,
        model=bundle.model,
        prompts_dir=Config.PROMPTS_DIR,
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
            optimized_image_prompt_path=optimized_image_prompt_path,
            prompt_name=prompt_name,
            output_path=output_path,
            batch_size=batch_size,
            console_obj=console,
        )

        console.print(f"[green]✓ 视频提示词: {output_path}[/]")
        return

    if output_path is None:
        stem = get_stem(storyboard_table_path)
        output_path = os.path.join(
            get_output_dir_for_file(stem), f"{stem}_video_prompts.csv"
        )

    merged_rows = merge_video_prompt_tables(
        storyboard_table_path=storyboard_table_path,
        image_prompt_table_path=image_prompt_table_path,
    )
    write_csv_video_prompt_batches(
        generator=generator,
        rows=merged_rows,
        prompt_name=prompt_name,
        output_path=output_path,
        batch_size=batch_size,
        console_obj=console,
    )
    console.print(f"[green]✓ 视频提示词表: {output_path}[/]")


@cli.command()
@click.option("--input", "-i", "input_path", required=True,
              help="输入 SRT 文件路径")
@click.option("--correction-prompt", default="default",
              help="修正提示词名称")
@click.option("--storyboard-prompt", default="default",
              help="分镜提示词名称")
@click.option("--output-dir", "-o", "output_dir", default=None,
              help="输出根目录")
def run(input_path, correction_prompt, storyboard_prompt, output_dir):
    """阶段一完整流水线: SRT → AI修正 → 提取文案 → 分镜"""
    if not os.path.exists(input_path):
        _abort_cli(f"文件不存在: {_format_cli_path(input_path)}")

    bundle = get_client_bundle()
    try:
        run_pipeline_for_file(
            bundle=bundle,
            srt_path=input_path,
            correction_prompt=correction_prompt,
            storyboard_prompt=storyboard_prompt,
            file_index=1,
            total_files=1,
            unattended=True,
            output_dir=output_dir,
        )
    except RuntimeError as e:
        _abort_cli(str(e), title="❌ 流水线执行失败")


@cli.command(name="continue-run")
@click.option("--storyboard", "-s", "storyboard_paths", multiple=True, required=True,
              help="输入分镜 TXT 文件路径（可多次指定，如 -s a.txt -s b.txt）")
@click.option("--raw-prompts", "-r", "raw_prompt_paths", multiple=True, default=None,
              help="手动指定原始画面提示词 TXT 路径（按顺序与 --storyboard 一一对应；省略则自动配对）")
@click.option("--optimize-prompt", default="default",
              help="画面提示词优化模板名称")
@click.option("--video-prompt", "video_prompt_name", default="default",
              help="视频提示词模板名称")
@click.option("--batch-size", default=DEFAULT_BATCH_SIZE, type=int,
              help="每批处理的分镜数量")
@click.option("--output-dir", "-o", "output_dir", default=None,
              help="输出目录（仅单文件模式生效，多文件时各文件输出到自身目录）")
def continue_run(storyboard_paths, raw_prompt_paths, optimize_prompt, video_prompt_name,
                 batch_size, output_dir):
    """阶段二完整流水线: 画面提示词优化 → 视频提示词生成（支持多文件批量处理）"""
    for path in storyboard_paths:
        if not os.path.exists(path):
            _abort_cli(f"文件不存在: {_format_cli_path(path)}")

    # 构建 (storyboard, raw_prompt) 配对
    if raw_prompt_paths:
        if len(raw_prompt_paths) != len(storyboard_paths):
            _abort_cli(
                f"--raw-prompts 数量({len(raw_prompt_paths)})与 "
                f"--storyboard 数量({len(storyboard_paths)})不匹配，必须一一对应"
            )
        pairs = list(zip(storyboard_paths, raw_prompt_paths))
    else:
        pairs = []
        for sb_path in storyboard_paths:
            txt_files = scan_storyboard_prompt_files(sb_path)
            if len(txt_files) == 0:
                _abort_cli(
                    f"未找到 {os.path.dirname(sb_path)} 目录下的\"画面提示词*.txt\"文件，"
                    f"请用 --raw-prompts 手动指定"
                )
            if len(txt_files) > 1:
                _abort_cli(
                    f"{os.path.dirname(sb_path)} 目录下存在 {len(txt_files)} 个"
                    f"\"画面提示词*.txt\"文件，无法自动确定配对，请用 --raw-prompts 手动指定"
                )
            pairs.append((sb_path, txt_files[0]))

    multi_file = len(pairs) > 1
    bundle = get_client_bundle()

    failed_files = []
    for i, (storyboard_path, raw_prompt_path) in enumerate(pairs, start=1):
        stem = os.path.basename(os.path.dirname(os.path.abspath(storyboard_path)))
        if multi_file:
            console.print(
                f"\n[bold cyan]━━━ [{i}/{len(pairs)}] {stem} ━━━[/]"
            )

        try:
            run_postprocess_pipeline_for_storyboard(
                bundle=bundle,
                storyboard_path=storyboard_path,
                raw_prompt_path=raw_prompt_path,
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
                f"\n[yellow]✓ 完成 {len(pairs) - len(failed_files)}/{len(pairs)} 个文件，"
                f"失败: {', '.join(failed_files)}[/]"
            )
        else:
            console.print(f"\n[bold green]✓ 全部完成！共处理 {len(pairs)} 个文件[/]")


@cli.command()
def gui():
    """启动 Flet 桌面 GUI（浏览器模式）"""
    import flet as ft
    from flet_ui.main import main as flet_main
    ft.run(flet_main, view=ft.AppView.WEB_BROWSER, port=0)


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        print("\n程序已退出。")
