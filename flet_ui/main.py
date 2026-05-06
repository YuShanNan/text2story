"""Flet 桌面 GUI 入口"""
import flet as ft
from flet_ui.theme import page_style
from flet_ui.pages.pipeline_page import PipelinePage


def main(page: ft.Page):
    page_style(page)

    pipeline_page = PipelinePage(page)

    # Placeholder pages for tabs still under development
    placeholder = lambda text: ft.Container(
        content=ft.Text(text, size=14, color="#a0b8d8"),
        alignment=ft.alignment.Alignment(0, 0),
        expand=True,
    )

    tab_bar = ft.TabBar(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(label="流水线"),
            ft.Tab(label="SRT 修正"),
            ft.Tab(label="分镜生成"),
            ft.Tab(label="提示词生成"),
            ft.Tab(label="画面优化"),
            ft.Tab(label="视频提示词"),
        ],
        on_change=lambda e: _on_tab_change(e, tab_view),
    )

    tab_view = ft.TabBarView(
        controls=[
            pipeline_page,
            placeholder("SRT 修正 - 开发中"),
            placeholder("分镜生成 - 开发中"),
            placeholder("提示词生成 - 开发中"),
            placeholder("画面优化 - 开发中"),
            placeholder("视频提示词 - 开发中"),
        ],
    )

    page.add(
        ft.Column([
            tab_bar,
            ft.Divider(height=1, color="#182036"),
            tab_view,
        ], spacing=0, expand=True)
    )


def _on_tab_change(e, tab_view: ft.TabBarView):
    tab_view.selected_index = e.control.selected_index
    tab_view.update()


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.WEB_BROWSER, port=8550)
