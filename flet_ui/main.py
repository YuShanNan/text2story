"""Flet 桌面 GUI 入口"""
import flet as ft
from flet_ui.theme import page_style
from flet_ui.pages.pipeline_page import PipelinePage


def main(page: ft.Page):
    page_style(page)

    pipeline_page = PipelinePage(page)

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(text="流水线", content=pipeline_page),
            ft.Tab(text="SRT 修正", content=ft.Text("SRT 修正 - 开发中")),
            ft.Tab(text="分镜生成", content=ft.Text("分镜生成 - 开发中")),
            ft.Tab(text="提示词生成", content=ft.Text("提示词生成 - 开发中")),
            ft.Tab(text="画面优化", content=ft.Text("画面优化 - 开发中")),
            ft.Tab(text="视频提示词", content=ft.Text("视频提示词 - 开发中")),
        ],
    )
    page.add(tabs)


if __name__ == "__main__":
    ft.app(target=main)
