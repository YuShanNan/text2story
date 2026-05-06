"""流水线 Tab：批量多文件 + 顺序/并行切换"""
import os
import sys
import threading
import concurrent.futures
import flet as ft

# Ensure project root in path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flet_ui.widgets.file_panel import FilePanel
from flet_ui.widgets.rules_bar import RulesBar
from flet_ui.widgets.queue_view import QueueView
from flet_ui.widgets.progress_bar import ProgressBar


class PipelinePage(ft.Column):
    """流水线主页面：文件选择 -> 规则配置 -> 执行队列 -> 进度条"""

    def __init__(self, page: ft.Page):
        self.page = page
        self._progress = ProgressBar()
        self._queue = QueueView()
        self._rules = RulesBar(on_execute=self._on_execute)
        self._files = FilePanel(on_selection_change=self._on_files_changed)
        self._running = False

        super().__init__(
            controls=[
                ft.Row([
                    self._files,
                    ft.Column([
                        self._rules,
                        self._queue,
                    ], spacing=10, expand=True),
                ], spacing=10, expand=True),
                self._progress,
            ],
            spacing=10,
            expand=True,
        )

    def _on_files_changed(self, selected: set[str]):
        """文件选择变化时更新队列视图"""
        names = [os.path.basename(p) for p in sorted(selected)]
        self._queue.set_files(names)

    def _on_execute(self):
        """点击执行按钮 -> 启动后台流水线"""
        if self._running:
            self._progress.log("WARN: 已有任务在运行", "warn")
            return
        files = self._files.selected_files
        if not files:
            self._progress.log("WARN: 请先选择文件", "warn")
            return
        seq = self._rules.sequential
        rules = self._rules.rules
        self._progress.log(
            "开始{}执行 {} 个文件".format("顺序" if seq else "并行", len(files)),
            "info",
        )
        self._running = True
        # Run pipeline in background thread; Flet WebSocket updates are thread-safe
        threading.Thread(
            target=self._run_pipeline, args=(files, seq, rules), daemon=True
        ).start()

    def _run_pipeline(self, files: list[str], seq: bool, rules: dict[str, str]):
        """在后台线程中运行完整流水线"""
        from config import Config
        from api.client_factory import create_clients

        try:
            bundle = create_clients()
            self._call_ui(lambda: self._rules.set_api_connected(True))
        except ValueError as e:
            self._call_ui(lambda: self._rules.set_api_connected(False))
            self._call_ui(lambda: self._progress.log(
                "ERROR: API 配置错误: {}".format(e), "warn",
            ))
            self._running = False
            return

        def process_file(filepath: str) -> bool:
            name = os.path.basename(filepath)
            self._call_ui(lambda n=name: self._queue.set_status(n, "running", 0.0))
            self._call_ui(lambda n=name: self._progress.update_progress(
                "[{}] 阶段一开始".format(n), 0.0,
            ))

            try:
                from core.srt_corrector import SrtCorrector
                from core.srt_converter import convert_srt_to_txt
                from core.storyboard_generator import StoryboardGenerator
                from utils.file_utils import (
                    read_file, write_file,
                    get_output_dir_for_file, get_safe_stem,
                )

                stem = get_safe_stem(filepath, Config.INPUT_DIR)
                out_dir = get_output_dir_for_file(stem)
                os.makedirs(out_dir, exist_ok=True)

                # Step 1: SRT correction
                self._call_ui(lambda n=name: self._progress.log(
                    "[{}] SRT 修正...".format(n), "info",
                ))
                self._call_ui(lambda n=name: self._progress.update_progress(
                    "[{}] SRT 修正中".format(n), 0.1,
                ))
                corrector = SrtCorrector(
                    client=bundle.client, model=bundle.model,
                    prompts_dir=Config.PROMPTS_DIR,
                    max_chunk_size=Config.MAX_CHUNK_SIZE,
                )
                srt = read_file(filepath)
                corrected = _collect_generator(
                    corrector.iter_correct_with_progress(
                        srt, rules.get("srt_correction", "default"),
                    )
                )
                corrected_path = os.path.join(out_dir, "{}_corrected.srt".format(stem))
                write_file(corrected_path, corrected)
                self._call_ui(lambda n=name: self._progress.log(
                    "[{}] SRT 修正完成".format(n), "success",
                ))
                self._call_ui(lambda n=name: self._progress.update_progress(
                    "[{}] SRT 修正".format(n), 0.3,
                ))

                # Step 2: Extract text
                txt = convert_srt_to_txt(corrected_path)
                txt_path = os.path.join(out_dir, "{}_corrected.txt".format(stem))
                write_file(txt_path, txt)

                # Step 3: Storyboard generation
                self._call_ui(lambda n=name: self._progress.log(
                    "[{}] 分镜生成...".format(n), "info",
                ))
                self._call_ui(lambda n=name: self._progress.update_progress(
                    "[{}] 分镜生成中".format(n), 0.4,
                ))
                generator = StoryboardGenerator(
                    client=bundle.client, model=bundle.model,
                    prompts_dir=Config.PROMPTS_DIR,
                    max_chunk_size=Config.MAX_CHUNK_SIZE,
                )
                sb = _collect_generator(
                    generator.iter_generate_progress(
                        txt, rules.get("storyboard", "default"),
                    )
                )
                sb_path = os.path.join(out_dir, "{}_storyboard.txt".format(stem))
                write_file(sb_path, sb)
                self._call_ui(lambda n=name: self._progress.log(
                    "[{}] 分镜生成完成".format(n), "success",
                ))
                self._call_ui(lambda n=name: self._progress.update_progress(
                    "[{}] 阶段一完成".format(n), 1.0,
                ))
                self._call_ui(lambda n=name: self._queue.set_status(n, "done", 1.0))
                return True

            except Exception as e:
                self._call_ui(lambda n=name: self._progress.log(
                    "[{}] ERROR: {}".format(n, e), "warn",
                ))
                self._call_ui(lambda n=name: self._queue.set_status(n, "failed", 0.0))
                return False

        total = len(files)
        if seq:
            for idx, fp in enumerate(files):
                process_file(fp)
                self._call_ui(lambda i=idx: self._progress.update_progress(
                    "已完成 {}/{}".format(i + 1, total), (i + 1) / total,
                ))
        else:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(total, 4),
            ) as ex:
                futures = [ex.submit(process_file, fp) for fp in files]
                for i, _ in enumerate(concurrent.futures.as_completed(futures)):
                    self._call_ui(lambda i=i: self._progress.update_progress(
                        "已完成 {}/{}".format(i + 1, total), (i + 1) / total,
                    ))

        self._call_ui(lambda: self._progress.log(
            "全部完成 ({} 文件)".format(total), "success",
        ))
        self._running = False

    def _call_ui(self, fn):
        """执行 UI 更新操作。Flet WebSocket 机制天然线程安全，直接调用即可。"""
        try:
            fn()
        except Exception:
            pass


def _collect_generator(gen) -> str:
    """将 generator 产生的 event dict 中的 content 拼接为单个字符串"""
    results = []
    for event in gen:
        if event.get("content"):
            results.append(event["content"])
    return "\n".join(results)
