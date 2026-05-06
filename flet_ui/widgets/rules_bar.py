"""四规则下拉 + 顺序/并行切换 + 执行按钮（同行）"""
import glob
import os
import flet as ft
from flet_ui.theme import (
    BG_CARD, BG_INPUT, BORDER, PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_LABEL, SUCCESS,
)

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "prompts")
STEP_MAP = [
    ("SRT修正", "srt_correction"),
    ("分镜生成", "storyboard"),
    ("画面优化", "image_prompt_optimize"),
    ("视频提示词", "video_prompt_from_image"),
]


def _scan_prompts(subdir: str) -> list[str]:
    d = os.path.join(PROMPTS_DIR, subdir)
    if not os.path.isdir(d):
        return ["default"]
    files = glob.glob(os.path.join(d, "*.txt"))
    names = [os.path.splitext(os.path.basename(f))[0] for f in files]
    return sorted(names) if names else ["default"]


class RulesBar(ft.Container):
    """顶部规则栏：四下拉 + 模式切换 + 执行按钮"""

    def __init__(self, on_execute=None):
        self._on_execute = on_execute
        self._sequential = True
        self._dds: list[ft.Dropdown] = []

        # Mode toggle buttons
        self._mode_btn_seq = ft.Container(
            content=ft.Text("顺序", size=10, color=ft.Colors.WHITE),
            bgcolor=PRIMARY,
            border_radius=ft.border_radius.all(3),
            padding=ft.padding.symmetric(2, 7),
            on_click=lambda e: self._set_mode(True),
        )
        self._mode_btn_par = ft.Container(
            content=ft.Text("并行", size=10, color=TEXT_SECONDARY),
            bgcolor=None,
            border_radius=ft.border_radius.all(3),
            padding=ft.padding.symmetric(2, 7),
            on_click=lambda e: self._set_mode(False),
        )
        mode_switch = ft.Container(
            content=ft.Row([self._mode_btn_seq, self._mode_btn_par], spacing=0),
            bgcolor=BG_INPUT, border=ft.border.all(1, BORDER), border_radius=4, padding=1,
        )

        # Execute button
        self._exec_btn = ft.ElevatedButton(
            "▶ 顺序执行",
            style=ft.ButtonStyle(
                bgcolor=PRIMARY, color="#e8f0ff",
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=ft.padding.symmetric(5, 16),
            ),
            on_click=lambda e: self._fire(),
        )

        self._api_text = ft.Text("✓ API已连接", size=10, color=SUCCESS)

        # Build row children
        row_children = []
        for label, key in STEP_MAP:
            options = _scan_prompts(key)
            dd = ft.Dropdown(
                value="default",
                options=[ft.dropdown.Option(k, k) for k in options],
                width=110,
                text_size=11,
                dense=True,
                bgcolor=BG_INPUT,
                border_color=BORDER,
                color=TEXT_PRIMARY,
                content_padding=ft.padding.symmetric(4, 6),
            )
            self._dds.append(dd)
            row_children.append(ft.Text(label, size=10, color=TEXT_LABEL))
            row_children.append(dd)

        row_children.append(mode_switch)
        row_children.append(self._api_text)
        row_children.append(self._exec_btn)

        super().__init__(
            bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER),
            border_radius=8,
            padding=ft.padding.symmetric(8, 14),
            content=ft.Row(row_children, spacing=8, scroll=ft.ScrollMode.AUTO),
        )

    @property
    def sequential(self) -> bool:
        return self._sequential

    @property
    def rules(self) -> dict[str, str]:
        result = {}
        for i, (_, key) in enumerate(STEP_MAP):
            result[key] = self._dds[i].value or "default"
        return result

    def _set_mode(self, seq: bool):
        self._sequential = seq
        self._mode_btn_seq.bgcolor = PRIMARY if seq else None
        self._mode_btn_seq.content.color = ft.Colors.WHITE if seq else TEXT_SECONDARY
        self._mode_btn_par.bgcolor = PRIMARY if not seq else None
        self._mode_btn_par.content.color = ft.Colors.WHITE if not seq else TEXT_SECONDARY
        self._exec_btn.text = "▶ 顺序执行" if seq else "▶ 批量执行"
        self._mode_btn_seq.update()
        self._mode_btn_par.update()
        self._exec_btn.update()

    def _fire(self):
        if self._on_execute:
            self._on_execute()

    def set_api_connected(self, ok: bool):
        self._api_text.value = "✓ API已连接" if ok else "✗ API未连接"
        self._api_text.color = SUCCESS if ok else "#d84040"
        self._api_text.update()
