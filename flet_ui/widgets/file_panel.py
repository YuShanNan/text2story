"""可多选的文件列表面板"""
import os
import flet as ft

from flet_ui.theme import (
    BG_CARD, BG_INPUT, BORDER, PRIMARY, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED, SUCCESS,
)


class FilePanel(ft.Container):
    """左侧文件选择面板，支持多选、添加文件/目录"""

    def __init__(self, on_selection_change=None):
        self._files: list[str] = []
        self._selected: set[str] = set()
        self._on_selection_change = on_selection_change
        self._file_list = ft.Column(spacing=0)
        self._count_text = ft.Text("已选 0", size=11, color=SUCCESS)

        super().__init__(
            width=240,
            bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER),
            border_radius=8,
            padding=14,
            content=ft.Column([
                ft.Row([
                    ft.Text("📁 文件队列", size=11, color=TEXT_SECONDARY),
                    self._count_text,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(
                    bgcolor=BG_INPUT,
                    border=ft.border.all(1, BORDER),
                    border_radius=6,
                    padding=6,
                    content=self._file_list,
                    expand=True,
                ),
                ft.Row([
                    ft.ElevatedButton(
                        "📂 添加文件",
                        style=_btn_style(),
                        on_click=self._pick_files,
                    ),
                    ft.ElevatedButton(
                        "📁 目录",
                        style=_btn_style_secondary(),
                        on_click=self._pick_dir,
                    ),
                ], spacing=6),
                ft.Container(
                    bgcolor=BG_INPUT,
                    border=ft.border.all(1, BORDER),
                    border_radius=6,
                    padding=ft.padding.symmetric(8, 10),
                    content=ft.Text(
                        "输出: output/<文件名>/",
                        size=10,
                        color=TEXT_MUTED,
                    ),
                ),
            ], spacing=10, expand=True),
        )

    @property
    def selected_files(self) -> list[str]:
        return sorted(self._selected)

    def _refresh_list(self):
        self._file_list.controls.clear()
        if not self._files:
            self._file_list.controls.append(
                ft.Text("拖放文件或点击浏览", size=11, color=TEXT_MUTED)
            )
        for path in self._files:
            name = os.path.basename(path)
            size = os.path.getsize(path)
            size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
            is_selected = path in self._selected
            self._file_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.CHECK_BOX if is_selected else ft.icons.CHECK_BOX_OUTLINE_BLANK,
                                size=16, color=SUCCESS if is_selected else TEXT_MUTED),
                        ft.Text(name, size=11, color=TEXT_PRIMARY if is_selected else TEXT_MUTED),
                        ft.Text(size_str, size=10, color=TEXT_MUTED),
                    ], spacing=8),
                    on_click=lambda e, p=path: self._toggle(p),
                    padding=ft.padding.symmetric(5, 8),
                    bgcolor=BG_INPUT if is_selected else None,
                    border_radius=3,
                )
            )
        self._count_text.value = f"已选 {len(self._selected)}"
        self._count_text.update()
        self._file_list.update()

    def _toggle(self, path: str):
        if path in self._selected:
            self._selected.discard(path)
        else:
            self._selected.add(path)
        self._refresh_list()
        if self._on_selection_change:
            self._on_selection_change(self._selected)

    def _pick_files(self, e):
        picker = ft.FilePicker(
            on_result=lambda r: self._on_files_picked(r)
        )
        self.page.overlay.append(picker)
        picker.pick_files(allow_multiple=True, file_type="custom",
                          allowed_extensions=["srt", "txt", "csv"])

    def _pick_dir(self, e):
        picker = ft.FilePicker(
            on_result=lambda r: self._on_dir_picked(r)
        )
        self.page.overlay.append(picker)
        picker.get_directory_path()

    def _on_files_picked(self, result):
        if result.files:
            for f in result.files:
                if f.path not in self._files:
                    self._files.append(f.path)
                    self._selected.add(f.path)
            self._refresh_list()
            if self._on_selection_change:
                self._on_selection_change(self._selected)

    def _on_dir_picked(self, result):
        if result.path:
            for name in os.listdir(result.path):
                full = os.path.join(result.path, name)
                if os.path.isfile(full) and name.split(".")[-1] in ("srt", "txt", "csv"):
                    if full not in self._files:
                        self._files.append(full)
                        self._selected.add(full)
            self._refresh_list()
            if self._on_selection_change:
                self._on_selection_change(self._selected)


def _btn_style():
    return ft.ButtonStyle(
        bgcolor=PRIMARY,
        color="#d8e4ff",
        shape=ft.RoundedRectangleBorder(radius=6),
        padding=ft.padding.symmetric(8, 12),
    )


def _btn_style_secondary():
    return ft.ButtonStyle(
        bgcolor=BG_CARD,
        color=TEXT_SECONDARY,
        shape=ft.RoundedRectangleBorder(radius=6),
        side=ft.BorderSide(1, BORDER),
        padding=ft.padding.symmetric(8, 12),
    )
