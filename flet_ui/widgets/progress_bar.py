"""底部进度条 + 日志组件"""
import flet as ft
from flet_ui.theme import (
    BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_MUTED, SUCCESS, WARNING,
)
from flet_ui.widgets.log_viewer import LogViewer


class ProgressBar(ft.Container):
    """底部进度条，包含标签、百分比文本、进度条和可展开日志面板"""

    def __init__(self):
        self._label = ft.Text("", size=11, color=TEXT_PRIMARY)
        self._pct_text = ft.Text("0%", size=11, color=TEXT_MUTED)
        self._bar = ft.ProgressBar(
            value=0,
            height=5,
            bgcolor=BG_INPUT,
            color="#1a3a68",
        )
        self.log_viewer = LogViewer()

        super().__init__(
            content=ft.Column([
                ft.Container(
                    bgcolor=BG_CARD,
                    border=ft.border.all(1, BORDER),
                    border_radius=8,
                    padding=ft.padding.symmetric(10, 14),
                    content=ft.Column([
                        ft.Row([
                            self._label,
                            self._pct_text,
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        self._bar,
                    ], spacing=4),
                ),
                self.log_viewer,
            ], spacing=6),
        )

    def update_progress(self, label: str, pct: float):
        """更新进度条。label: 描述文字, pct: 0.0 ~ 1.0"""
        self._label.value = label
        self._pct_text.value = f"{int(pct * 100)}%"
        self._bar.value = pct
        self._label.update()
        self._pct_text.update()
        self._bar.update()

    def log(self, text: str, level: str = "info"):
        """快捷追加日志，委派给 log_viewer.append"""
        self.log_viewer.append(text, level)
