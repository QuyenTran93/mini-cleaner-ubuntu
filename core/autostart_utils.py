"""
autostart_utils.py
Giai đoạn 4 — Tối ưu hệ thống: quét danh sách ứng dụng khởi động cùng hệ thống
(theo chuẩn XDG Autostart) và các systemd user-service đang bật, cho phép
BẬT/TẮT — KHÔNG PHẢI xóa, người dùng luôn bật lại được bất cứ lúc nào.

Theo chuẩn XDG Autostart (freedesktop.org): một file .desktop trong
~/.config/autostart/ có CÙNG TÊN FILE với file trong /etc/xdg/autostart/ sẽ
ghi đè file hệ thống đó. Vì vậy để "tắt" một autostart hệ thống, ta chỉ cần
tạo 1 file override trong thư mục user với X-GNOME-Autostart-enabled=false —
KHÔNG cần quyền root, không đụng đến file gốc.
"""

import configparser
import os
import subprocess
from dataclasses import dataclass

USER_AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
SYSTEM_AUTOSTART_DIRS = ["/etc/xdg/autostart", "/usr/share/gnome/autostart"]


@dataclass
class AutostartEntry:
    id: str          # tên file .desktop, dùng làm khóa duy nhất
    name: str
    comment: str
    exec_cmd: str
    enabled: bool
    source: str       # "user" hoặc "system" — chỉ mang tính thông tin


def _parse_desktop_file(path: str) -> dict | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return None
    if "Desktop Entry" not in parser:
        return None
    section = parser["Desktop Entry"]
    return {
        "name": section.get("Name", fallback=os.path.basename(path)),
        "comment": section.get("Comment", fallback=""),
        "exec": section.get("Exec", fallback=""),
        "hidden": section.getboolean("Hidden", fallback=False),
        "enabled_key": section.get("X-GNOME-Autostart-enabled", fallback="true").strip().lower(),
        "no_display": section.getboolean("NoDisplay", fallback=False),
    }


def scan_autostart_apps() -> list[AutostartEntry]:
    """Quét autostart app, gộp theo tên file — bản user override bản system (chuẩn XDG)."""
    entries: dict[str, AutostartEntry] = {}

    for sys_dir in SYSTEM_AUTOSTART_DIRS:
        if not os.path.isdir(sys_dir):
            continue
        for fname in os.listdir(sys_dir):
            if not fname.endswith(".desktop"):
                continue
            data = _parse_desktop_file(os.path.join(sys_dir, fname))
            if not data or data["hidden"] or data["no_display"]:
                continue
            entries[fname] = AutostartEntry(
                id=fname,
                name=data["name"],
                comment=data["comment"],
                exec_cmd=data["exec"],
                enabled=(data["enabled_key"] != "false"),
                source="system",
            )

    if os.path.isdir(USER_AUTOSTART_DIR):
        for fname in os.listdir(USER_AUTOSTART_DIR):
            if not fname.endswith(".desktop"):
                continue
            data = _parse_desktop_file(os.path.join(USER_AUTOSTART_DIR, fname))
            if not data:
                continue
            if data["hidden"] or data["no_display"]:
                if fname in entries:
                    entries[fname].enabled = False
                    entries[fname].source = "user"
                continue
            entries[fname] = AutostartEntry(
                id=fname,
                name=data["name"],
                comment=data["comment"],
                exec_cmd=data["exec"],
                enabled=(data["enabled_key"] != "false"),
                source="user",
            )

    return sorted(entries.values(), key=lambda e: e.name.lower())


def set_autostart_enabled(entry: AutostartEntry, enabled: bool) -> tuple[bool, str]:
    """Bật/tắt 1 autostart entry bằng file override trong thư mục user — không cần root."""
    os.makedirs(USER_AUTOSTART_DIR, exist_ok=True)
    user_path = os.path.join(USER_AUTOSTART_DIR, entry.id)

    source_path = user_path if os.path.exists(user_path) else None
    if source_path is None:
        for sys_dir in SYSTEM_AUTOSTART_DIRS:
            candidate = os.path.join(sys_dir, entry.id)
            if os.path.exists(candidate):
                source_path = candidate
                break

    parser = configparser.ConfigParser(interpolation=None, strict=False)
    if source_path:
        try:
            parser.read(source_path, encoding="utf-8")
        except Exception:
            pass
    if "Desktop Entry" not in parser:
        parser["Desktop Entry"] = {}

    parser["Desktop Entry"]["X-GNOME-Autostart-enabled"] = "true" if enabled else "false"

    try:
        with open(user_path, "w", encoding="utf-8") as f:
            parser.write(f, space_around_delimiters=False)
        return True, "Đã cập nhật"
    except Exception as e:
        return False, str(e)


# ---------- Systemd user services (chạy trong phiên user, không cần root) ----------

@dataclass
class UserServiceEntry:
    name: str
    enabled: bool


def scan_user_services() -> list[UserServiceEntry]:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-unit-files", "--type=service", "--no-legend"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []

    services = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, state = parts[0], parts[1]
        if state not in ("enabled", "enabled-runtime"):
            continue
        if name.endswith("@.service"):
            continue  # template unit, không thao tác trực tiếp được
        services.append(UserServiceEntry(name=name, enabled=True))
    return sorted(services, key=lambda s: s.name.lower())


def set_user_service_enabled(name: str, enabled: bool) -> tuple[bool, str]:
    if enabled:
        args = ["systemctl", "--user", "enable", name]
    else:
        args = ["systemctl", "--user", "disable", "--now", name]

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except Exception as e:
        return False, str(e)

    if result.returncode == 0:
        return True, "Đã cập nhật"
    return False, (result.stderr.strip() or "Thất bại")
