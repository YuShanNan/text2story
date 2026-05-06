"""执行队列列表（每文件独立进度条）"""
import flet as ft
from flet_ui.theme import BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, SUCCESS, WARNING


class QueueView(ft.Container):
    def __init__(self):
        self._items: dict[str, "QueueItem"] = {}
        self._list = ft.Column(spacing=6)

        super().__init__(
            bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER),
            border_radius=8,
            padding=ft.padding.symmetric(12, 14),
            content=ft.Column([
                ft.Text("📋 执行队列", size=11, color=TEXT_SECONDARY),
                self._list,
            ], spacing=8),
            expand=True,
        )

    def set_files(self, filenames: list[str]):
        """初始化队列：清空原有项，为每个文件名创建 QueueItem。"""
        self._items.clear()
        self._list.controls.clear()
        for name in filenames:
            item = QueueItem(name)
            self._items[name] = item
            self._list.controls.append(item)
        self._list.update()

    def set_status(self, filename: str, status: str, pct: float = 1.0):
        """更新指定文件的进度条和状态文字。status 取值: waiting/running/done/failed"""
        if filename in self._items:
            self._items[filename].set_status(status, pct)
            self._items[filename].update()


class QueueItem(ft.Container):
    """队列中单个文件的进度行。"""

    _STATUS_LABELS = {
        "waiting": "等待",
        "running": "⏳ 处理中...",
        "done": "✓ 完成",
        "failed": "✗ 失败",
    }
    _STATUS_COLORS = {
        "waiting": TEXT_SECONDARY,
        "running": WARNING,
        "done": SUCCESS,
        "failed": "#d84040",
    }

    def __init__(self, filename: str):
        self._status_text = ft.Text(
            QueueItem._STATUS_LABELS["waiting"],
            size=11,
            color=QueueItem._STATUS_COLORS["waiting"],
        )
        self._bar = ft.ProgressBar(
            value=0,
            height=3,
            bgcolor=BG_INPUT,
            color=SUCCESS,
        )

        super().__init__(
            content=ft.Column([
                ft.Row([
                    ft.Text(filename, size=11, color=TEXT_PRIMARY),
                    self._status_text,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self._bar,
            ], spacing=2),
        )

    def set_status(self, status: str, pct: float):
        self._status_text.value = self._STATUS_LABELS.get(status, status)
        self._status_text.color = self._STATUS_COLORS.get(status, TEXT_SECONDARY)
        self._bar.value = pct
