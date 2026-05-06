"""python -m flet_ui"""
import flet as ft
from flet_ui.main import main

if __name__ == "__main__":
    ft.run(main, view=ft.AppView.WEB_BROWSER, port=0)
