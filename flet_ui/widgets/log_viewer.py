"""可折叠的日志查看面板"""
import flet as ft
from flet_ui.theme import (
    BG_CARD, BORDER, TEXT_PRIMARY, TEXT_MUTED, SUCCESS, WARNING,
)


class LogViewer(ft.Container):
    """可展开/折叠的日志面板，支持 info/warn/success 三种级别着色"""

    def __init__(self):
        self._expanded = False
        self._logs: list[tuple[str, str]] = []
        self._log_area = ft.Column(spacing=2, scroll=ft.ScrollMode.ALWAYS)
        self._toggle_text = ft.Text("🔽 展开详细日志", size=10, color=TEXT_MUTED)

        super().__init__(
            bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER),
            border_radius=8,
            padding=ft.padding.symmetric(10, 14),
            content=ft.Column([
                self._toggle_text,
                self._log_area,
            ], spacing=6),
            on_click=lambda e: self._toggle(),
        )

    def append(self, text: str, level: str = "info"):
        """追加一条日志。level: info/warn/success"""
        color = {"info": TEXT_PRIMARY, "warn": WARNING, "success": SUCCESS}.get(level, TEXT_PRIMARY)
        self._logs.append((text, color))
        if self._expanded:
            self._log_area.controls.append(
                ft.Text(text, size=11, color=color, font_family="monospace")
            )
            self._log_area.update()

    def _toggle(self):
        self._expanded = not self._expanded
        self._toggle_text.value = "🔼 收起日志" if self._expanded else "🔽 展开详细日志"
        self._toggle_text.update()
        if self._expanded:
            self._log_area.controls.clear()
            for text, color in self._logs:
                self._log_area.controls.append(
                    ft.Text(text, size=11, color=color, font_family="monospace")
                )
        else:
            self._log_area.controls.clear()
        self._log_area.update()
