"""Flet 桌面 GUI 入口"""
import flet as ft
from flet_ui.theme import page_style, BG_CARD, BORDER, PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY
from flet_ui.pages.pipeline_page import PipelinePage


def main(page: ft.Page):
    page_style(page)

    pipeline_page = PipelinePage(page)

    def _placeholder(text):
        return ft.Container(
            content=ft.Text(text, size=14, color=TEXT_SECONDARY),
            alignment=ft.alignment.Alignment(0, 0),
            expand=True,
        )

    pages = [
        pipeline_page,
        _placeholder("SRT 修正 - 开发中"),
        _placeholder("分镜生成 - 开发中"),
        _placeholder("提示词生成 - 开发中"),
        _placeholder("画面优化 - 开发中"),
        _placeholder("视频提示词 - 开发中"),
    ]

    tab_labels = ["流水线", "SRT 修正", "分镜生成", "提示词生成", "画面优化", "视频提示词"]

    content_area = ft.Container(content=pages[0], expand=True)

    def make_tab(idx):
        is_selected = idx == 0
        return ft.Container(
            content=ft.Text(tab_labels[idx], size=12,
                           color=ft.Colors.WHITE if is_selected else TEXT_SECONDARY,
                           weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.NORMAL),
            bgcolor=PRIMARY if is_selected else None,
            border_radius=6,
            padding=ft.padding.symmetric(5, 12),
            on_click=lambda e, i=idx: switch_tab(i),
        )

    def switch_tab(idx):
        content_area.content = pages[idx]
        for i, tab in enumerate(tab_row.controls):
            sel = i == idx
            tab.bgcolor = PRIMARY if sel else None
            tab.content.color = ft.Colors.WHITE if sel else TEXT_SECONDARY
            tab.content.weight = ft.FontWeight.W_600 if sel else ft.FontWeight.NORMAL
            tab.update()
        content_area.update()

    tab_row = ft.Row(
        controls=[make_tab(i) for i in range(6)],
        spacing=2,
    )

    tab_bar = ft.Container(
        content=tab_row,
        bgcolor=BG_CARD,
        border=ft.border.all(1, BORDER),
        border_radius=8,
        padding=ft.padding.symmetric(6, 12),
    )

    page.add(
        ft.Column([
            tab_bar,
            content_area,
        ], spacing=10, expand=True)
    )


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.WEB_BROWSER, port=0)
