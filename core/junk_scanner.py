"""
junk_scanner.py
Quét và tính dung lượng có thể dọn dẹp cho từng loại "rác" hệ thống.

Nguyên tắc an toàn:
  - Mọi hàm scan_* chỉ ĐỌC, không xóa gì cả — luôn hiển thị cho người dùng
    xem trước (dry-run) rồi mới cho xác nhận xóa ở tầng UI
  - Kernel cũ CHỈ hiển thị thông tin, KHÔNG có thao tác xóa tự động trong
    app này, vì xóa nhầm kernel đang chạy có thể khiến máy không boot được —
    rủi ro vượt quá giá trị của việc tự động hóa ở giai đoạn này
"""

import glob
import os
import re
import subprocess
from dataclasses import dataclass


def _dir_size(path: str) -> int:
    total = 0
    if not os.path.isdir(path):
        return 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                continue
    return total


def _files_size(pattern: str) -> int:
    total = 0
    for fp in glob.glob(pattern):
        try:
            total += os.path.getsize(fp)
        except OSError:
            continue
    return total


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


@dataclass
class JunkCategory:
    id: str
    title: str
    path_hint: str
    size_bytes: int
    requires_root: bool


def scan_apt_cache() -> JunkCategory:
    size = _files_size("/var/cache/apt/archives/*.deb")
    return JunkCategory("apt_cache", "Cache gói APT (.deb đã tải)", "/var/cache/apt/archives", size, True)


def scan_thumbnails() -> JunkCategory:
    path = os.path.expanduser("~/.cache/thumbnails")
    return JunkCategory("thumbnails", "Cache ảnh thu nhỏ (thumbnail)", path, _dir_size(path), False)


def scan_trash() -> JunkCategory:
    path = os.path.expanduser("~/.local/share/Trash")
    return JunkCategory("trash", "Thùng rác", path, _dir_size(path), False)


def scan_crash_reports() -> JunkCategory:
    path = "/var/crash"
    return JunkCategory("crash", "Báo cáo lỗi hệ thống (crash report)", path, _dir_size(path), True)


def _parse_journal_disk_usage(text: str) -> int:
    match = re.search(r"([\d.]+)\s*([KMGT]?)", text)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2)
    multiplier = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
    return int(value * multiplier.get(unit, 1))


def scan_journal_logs() -> JunkCategory:
    size = 0
    try:
        result = subprocess.run(
            ["journalctl", "--disk-usage"], capture_output=True, text=True, timeout=5
        )
        size = _parse_journal_disk_usage(result.stdout.strip())
    except Exception:
        pass
    return JunkCategory("journal", "Log hệ thống (journal)", "journalctl --vacuum-size", size, True)


def scan_user_tmp() -> JunkCategory:
    """Chỉ tính các file trong /tmp thuộc sở hữu user hiện tại (an toàn, không đụng file user khác)."""
    uid = os.getuid()
    total = 0
    try:
        with os.scandir("/tmp") as it:
            for entry in it:
                try:
                    st = entry.stat(follow_symlinks=False)
                    if st.st_uid == uid:
                        if entry.is_dir(follow_symlinks=False):
                            total += _dir_size(entry.path)
                        else:
                            total += st.st_size
                except OSError:
                    continue
    except OSError:
        pass
    return JunkCategory("user_tmp", "File tạm của bạn trong /tmp", "/tmp (chỉ file của bạn)", total, False)


def scan_orphan_packages() -> tuple[JunkCategory, list[str]]:
    """Trả về category (số lượng gói) + danh sách tên gói sẽ bị gỡ, dựa trên dry-run thật của apt."""
    names: list[str] = []
    try:
        result = subprocess.run(
            ["apt-get", "--dry-run", "autoremove"], capture_output=True, text=True, timeout=20
        )
        for line in result.stdout.splitlines():
            if line.startswith("Remv "):
                parts = line.split()
                if len(parts) >= 2:
                    names.append(parts[1])
    except Exception:
        pass
    cat = JunkCategory(
        "orphan_pkgs", f"Package mồ côi ({len(names)} gói)", "apt-get autoremove", 0, True
    )
    return cat, names


def scan_old_kernels() -> tuple[str, list[str]]:
    """CHỈ để hiển thị thông tin — không có thao tác xóa tự động (xem docstring đầu file)."""
    current = "?"
    kernels: list[str] = []
    try:
        current = subprocess.run(
            ["uname", "-r"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        result = subprocess.run(
            ["dpkg", "--list"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if line.startswith("ii") and "linux-image-" in line:
                parts = line.split()
                if len(parts) >= 2:
                    kernels.append(parts[1])
    except Exception:
        pass
    return current, kernels


# ---------- Dọn dẹp thật (chỉ cho các mục KHÔNG cần quyền root) ----------
# Các mục cần root (apt cache, crash report, journal, autoremove) nằm ở core/privileged.py

def clean_thumbnails() -> tuple[bool, str]:
    path = os.path.expanduser("~/.cache/thumbnails")
    try:
        if os.path.isdir(path):
            for entry in os.scandir(path):
                _remove_path(entry.path)
        return True, "Đã dọn cache thumbnail"
    except Exception as e:
        return False, str(e)


def clean_trash() -> tuple[bool, str]:
    base = os.path.expanduser("~/.local/share/Trash")
    try:
        for sub in ("files", "info"):
            sub_path = os.path.join(base, sub)
            if os.path.isdir(sub_path):
                for entry in os.scandir(sub_path):
                    _remove_path(entry.path)
        return True, "Đã dọn Thùng rác"
    except Exception as e:
        return False, str(e)


def clean_user_tmp() -> tuple[bool, str]:
    uid = os.getuid()
    errors = 0
    try:
        with os.scandir("/tmp") as it:
            for entry in it:
                try:
                    st = entry.stat(follow_symlinks=False)
                    if st.st_uid == uid:
                        _remove_path(entry.path)
                except OSError:
                    errors += 1
        msg = "Đã dọn file tạm của bạn" + (f" ({errors} mục bỏ qua do lỗi quyền)" if errors else "")
        return True, msg
    except Exception as e:
        return False, str(e)


def _remove_path(path: str):
    import shutil
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except OSError:
            pass
