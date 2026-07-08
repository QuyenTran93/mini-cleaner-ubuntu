"""
whitelist.py
Danh sách các tiến trình/dịch vụ lõi của hệ thống.
Những process này KHÔNG bao giờ được phép:
  - Kết thúc (kill) qua Process Manager
  - Gắn cờ "mồ côi / cần chú ý" dù logic phát hiện có khớp

Đây là lớp an toàn quan trọng nhất của app — luôn kiểm tra qua hàm
is_protected() trước khi cho phép bất kỳ thao tác nào tác động đến process.
"""

import os

PROTECTED_NAMES = {
    "systemd", "kthreadd", "init",
    "dbus-daemon", "dbus-broker",
    "NetworkManager", "ModemManager",
    "Xorg", "Xwayland", "gnome-shell", "gdm3", "gdm-x-session",
    "pulseaudio", "pipewire", "pipewire-pulse", "wireplumber",
    "polkitd", "accounts-daemon", "upowerd", "rtkit-daemon",
    "systemd-journald", "systemd-logind", "systemd-udevd", "systemd-resolved",
    "systemd-timesyncd", "systemd-oomd",
    "snapd", "cron", "cronie", "sshd", "avahi-daemon",
    "cups-browsed", "cupsd", "bluetoothd", "thermald",
    "packagekitd", "colord", "udisksd", "unattended-upgrades", "irqbalance",
    "power-profiles-daemon", "switcheroo-control",
}

# Process khởi động rất sớm trong quá trình boot thường là process hệ thống lõi.
# Đây CHỈ là heuristic bổ sung để giảm báo động giả cho nhãn "mồ côi",
# KHÔNG dùng để quyết định có cho kill hay không.
EARLY_BOOT_PID_THRESHOLD = 300


def is_protected(name: str, pid: int) -> bool:
    """Trả về True nếu process này không được phép kill / gắn cờ nghi vấn."""
    if pid <= 2:
        # pid 0 không tồn tại thực sự, pid 1 luôn là init/systemd
        return True
    if pid == os.getpid():
        # không bao giờ cho tự kill chính app Mini Cleaner
        return True

    name = (name or "").strip()
    if name in PROTECTED_NAMES:
        return True
    if name.startswith("[") and name.endswith("]"):
        # kernel thread, ví dụ [kworker/0:1], [ksoftirqd/0]
        return True

    return False
