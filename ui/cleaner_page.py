"""
cleaner_page.py
Trang Dọn dẹp rác: quét dung lượng từng loại rác hệ thống chạy trong
background thread (tránh treo UI), hiển thị checkbox để người dùng chọn,
xác nhận rồi mới xóa thật. Mục cần quyền root được xử lý qua pkexec
(core/privileged.py); mục không cần root xử lý trực tiếp
(core/junk_scanner.py).

Kernel cũ CHỈ hiển thị thông tin — không có nút xóa tự động (xem lý do
trong core/junk_scanner.py).
"""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from core import junk_scanner as scanner
from core import privileged


# id -> (hàm dọn khi requires_root=False, hàm dọn qua pkexec khi requires_root=True)
CLEAN_ACTIONS = {
    "apt_cache": ("root", privileged.clean_apt_cache),
    "thumbnails": ("local", scanner.clean_thumbnails),
    "trash": ("local", scanner.clean_trash),
    "crash": ("root", privileged.clean_crash_reports),
    "journal": ("root", privileged.vacuum_journal),
    "user_tmp": ("local", scanner.clean_user_tmp),
}


class CleanerRow(Gtk.Box):
    """Một dòng: checkbox + tên + đường dẫn + dung lượng + badge 'cần quyền root'."""

    def __init__(self, category: scanner.JunkCategory):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.category = category
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        self.checkbox = Gtk.CheckButton()
        self.checkbox.set_valign(Gtk.Align.CENTER)
        self.append(self.checkbox)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_label = Gtk.Label(label=category.title, xalign=0)
        title_label.add_css_class("heading")
        path_label = Gtk.Label(label=category.path_hint, xalign=0)
        path_label.add_css_class("dim-label")
        path_label.add_css_class("caption")
        text_box.append(title_label)
        text_box.append(path_label)
        text_box.set_hexpand(True)
        self.append(text_box)

        if category.requires_root:
            root_badge = Gtk.Label(label="cần quyền root")
            root_badge.add_css_class("dim-label")
            root_badge.add_css_class("caption")
            root_badge.set_valign(Gtk.Align.CENTER)
            self.append(root_badge)

        size_label = Gtk.Label(label=scanner.human_size(category.size_bytes))
        size_label.add_css_class("numeric")
        size_label.set_valign(Gtk.Align.CENTER)
        size_label.set_width_chars(10)
        self.append(size_label)

        # Không có gì để dọn -> không cho chọn, tránh thao tác thừa
        if category.size_bytes <= 0:
            self.checkbox.set_sensitive(False)


class CleanerPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._rows: list[CleanerRow] = []
        self._orphan_pkg_names: list[str] = []

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Dọn dẹp rác hệ thống", xalign=0)
        title.add_css_class("title-4")
        title.set_hexpand(True)
        header_row.append(title)

        self.rescan_btn = Gtk.Button(label="Quét lại")
        self.rescan_btn.connect("clicked", lambda _b: self._start_scan())
        header_row.append(self.rescan_btn)
        self.append(header_row)

        self.status_label = Gtk.Label(label="Đang quét lần đầu...", xalign=0)
        self.status_label.add_css_class("dim-label")
        self.append(self.status_label)

        self.spinner = Gtk.Spinner()
        self.append(self.spinner)

        self.rows_box = Gtk.ListBox()
        self.rows_box.add_css_class("boxed-list")
        self.rows_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.rows_box)
        scroller.set_vexpand(True)
        self.append(scroller)

        # ---------- Thông tin kernel cũ (chỉ đọc) ----------
        self.kernel_label = Gtk.Label(wrap=True, xalign=0)
        self.kernel_label.add_css_class("dim-label")
        self.kernel_label.add_css_class("caption")
        self.append(self.kernel_label)

        # ---------- Thanh hành động ----------
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.total_label = Gtk.Label(label="", xalign=0)
        self.total_label.set_hexpand(True)
        action_row.append(self.total_label)

        self.clean_btn = Gtk.Button(label="Dọn các mục đã chọn")
        self.clean_btn.add_css_class("destructive-action")
        self.clean_btn.connect("clicked", self._on_clean_clicked)
        self.clean_btn.set_sensitive(False)
        action_row.append(self.clean_btn)
        self.append(action_row)

        self._start_scan()

    # ---------- Quét (chạy nền để không treo UI) ----------

    def _start_scan(self):
        self.status_label.set_text("Đang quét dung lượng rác (có thể mất vài giây)...")
        self.spinner.start()
        self.clean_btn.set_sensitive(False)
        self.rescan_btn.set_sensitive(False)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        categories = [
            scanner.scan_apt_cache(),
            scanner.scan_thumbnails(),
            scanner.scan_trash(),
            scanner.scan_crash_reports(),
            scanner.scan_journal_logs(),
            scanner.scan_user_tmp(),
        ]
        orphan_cat, orphan_names = scanner.scan_orphan_packages()
        categories.append(orphan_cat)
        current_kernel, all_kernels = scanner.scan_old_kernels()

        GLib.idle_add(
            self._on_scan_done, categories, orphan_names, current_kernel, all_kernels
        )

    def _on_scan_done(self, categories, orphan_names, current_kernel, all_kernels):
        self._orphan_pkg_names = orphan_names

        child = self.rows_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.rows_box.remove(child)
            child = nxt
        self._rows = []

        for cat in categories:
            row = CleanerRow(cat)
            row.checkbox.connect("toggled", lambda _c: self._update_total())
            self._rows.append(row)
            self.rows_box.append(row)

        other_kernels = [k for k in all_kernels if current_kernel not in k]
        if other_kernels:
            self.kernel_label.set_text(
                f"Kernel đang chạy: {current_kernel}. Kernel cũ khác đã cài: "
                f"{', '.join(other_kernels)}. "
                "App không tự xóa kernel để tránh rủi ro — nếu muốn dọn, kiểm tra kỹ rồi chạy thủ công: "
                f"sudo apt remove <tên-gói-kernel-cũ>"
            )
        else:
            self.kernel_label.set_text(f"Kernel đang chạy: {current_kernel}. Không có kernel cũ nào khác.")

        self.spinner.stop()
        self.status_label.set_text("Quét xong. Chọn các mục muốn dọn rồi bấm nút bên dưới.")
        self.rescan_btn.set_sensitive(True)
        self._update_total()
        return False  # GLib.idle_add: chạy 1 lần rồi thôi

    # ---------- Tính tổng dung lượng đã chọn ----------

    def _update_total(self):
        selected = [r for r in self._rows if r.checkbox.get_active()]
        total = sum(r.category.size_bytes for r in selected)
        if selected:
            self.total_label.set_text(f"Đã chọn {len(selected)} mục — {scanner.human_size(total)}")
        else:
            self.total_label.set_text("Chưa chọn mục nào")
        self.clean_btn.set_sensitive(len(selected) > 0)

    # ---------- Dọn dẹp thật ----------

    def _on_clean_clicked(self, _btn):
        selected = [r for r in self._rows if r.checkbox.get_active()]
        if not selected:
            return

        names = "\n".join(f"• {r.category.title}" for r in selected)
        total = sum(r.category.size_bytes for r in selected)
        needs_root = any(r.category.requires_root for r in selected)

        secondary = f"Sẽ dọn khoảng {scanner.human_size(total)}.\n{names}"
        if needs_root:
            secondary += "\n\nMột số mục cần quyền quản trị — hệ thống sẽ hỏi mật khẩu qua hộp thoại polkit."

        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Xác nhận dọn dẹp?",
            secondary_text=secondary,
        )
        dialog.connect("response", self._on_clean_confirmed, selected)
        dialog.present()

    def _on_clean_confirmed(self, dialog, response, selected: list[CleanerRow]):
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return

        self.status_label.set_text("Đang dọn dẹp...")
        self.spinner.start()
        self.clean_btn.set_sensitive(False)
        threading.Thread(target=self._clean_worker, args=(selected,), daemon=True).start()

    def _clean_worker(self, selected: list[CleanerRow]):
        results = []
        for row in selected:
            kind, action = CLEAN_ACTIONS.get(row.category.id, (None, None))
            if action is None:
                # Package mồ côi xử lý riêng vì cần chạy autoremove, không phải xóa file
                if row.category.id == "orphan_pkgs":
                    ok, msg = privileged.autoremove_packages()
                else:
                    ok, msg = False, "Không có hành động dọn cho mục này"
            else:
                ok, msg = action()
            results.append((row.category.title, ok, msg))

        GLib.idle_add(self._on_clean_done, results)

    def _on_clean_done(self, results):
        self.spinner.stop()
        lines = []
        for title, ok, msg in results:
            icon = "✅" if ok else "❌"
            lines.append(f"{icon} {title}: {msg}")

        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Kết quả dọn dẹp",
            secondary_text="\n".join(lines),
        )
        dialog.connect("response", lambda d, _r: d.destroy())
        dialog.present()

        self._start_scan()  # quét lại để cập nhật dung lượng mới
        return False
