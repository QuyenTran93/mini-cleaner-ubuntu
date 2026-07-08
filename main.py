#!/usr/bin/env python3
"""
main.py — Điểm khởi chạy ứng dụng Mini Cleaner.

Chạy bằng:  python3 main.py
Yêu cầu:    GTK4 + Libadwaita + PyGObject + psutil đã được cài đặt
            (xem README.md để biết lệnh cài đặt trên Ubuntu).
"""

import sys
import os

# Cho phép chạy trực tiếp `python3 main.py` từ thư mục gốc project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, Gdk

from ui.window import MainWindow

APP_ID = "com.miniclean.app"


class MiniCleanerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        self._load_css()
        win = MainWindow(app)
        win.present()

    def _load_css(self):
        css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "style.css")
        if not os.path.exists(css_path):
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(css_path)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def main():
    app = MiniCleanerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
