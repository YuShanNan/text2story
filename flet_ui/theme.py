"""墨蓝黑配色方案"""
import flet as ft

BG_PRIMARY = "#020408"
BG_CARD = "#060a14"
BG_INPUT = "#010306"
BORDER = "#182036"
PRIMARY = "#142850"
PRIMARY_LIGHT = "#1a3a68"
TEXT_PRIMARY = "#d0dce8"
TEXT_SECONDARY = "#a0b8d8"
TEXT_MUTED = "#6a80a8"
TEXT_LABEL = "#8898b8"
SUCCESS = "#50c878"
WARNING = "#d8b840"


def get_theme() -> ft.Theme:
    return ft.Theme(
        color_scheme_seed=PRIMARY,
        visual_density=ft.VisualDensity.COMFORTABLE,
    )


def page_style(page: ft.Page):
    page.theme = get_theme()
    page.bgcolor = BG_PRIMARY
    page.padding = 0
    page.window.width = 1280
    page.window.height = 800
    page.window.min_width = 960
    page.window.min_height = 600
    page.window.title_bar_hidden = False
    page.title = "text2story"
