"""
privileged.py
Các thao tác cần quyền root được thực hiện qua `pkexec` — chỉ nâng quyền
cho ĐÚNG một lệnh cụ thể tại thời điểm cần, KHÔNG chạy toàn bộ ứng dụng GUI
bằng sudo/root. Chạy cả app GUI bằng root là thực hành KHÔNG an toàn (dễ gây
lỗi quyền file cấu hình desktop, mở rộng bề mặt tấn công không cần thiết).

`pkexec` sẽ tự động hiện hộp thoại xin mật khẩu qua polkit khi được gọi —
không cần cấu hình thêm gì trên Ubuntu desktop (GNOME) mặc định, miễn là
gói `policykit-1` đã được cài (mặc định có sẵn trên Ubuntu Desktop).
"""

import subprocess


def run_privileged(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Chạy một lệnh với quyền root qua pkexec. Trả về (thành công, thông báo)."""
    try:
        result = subprocess.run(
            ["pkexec"] + args, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return True, "Thành công"
        if result.returncode == 126:
            return False, "Bạn đã hủy xác thực quyền quản trị"
        if result.returncode == 127:
            return False, "Không tìm thấy pkexec — hãy cài: sudo apt install policykit-1"
        return False, (result.stderr.strip() or f"Lệnh thất bại (mã lỗi {result.returncode})")
    except subprocess.TimeoutExpired:
        return False, "Hết thời gian chờ xác thực"
    except FileNotFoundError:
        return False, "pkexec chưa được cài. Chạy: sudo apt install policykit-1"


def elevated_kill(pid: int) -> tuple[bool, str]:
    """Kết thúc process với quyền root — thử TERM (nhẹ nhàng) trước, rồi mới đến KILL."""
    ok, msg = run_privileged(["kill", "-TERM", str(pid)])
    if ok or "hủy xác thực" in msg:
        return ok, msg
    return run_privileged(["kill", "-KILL", str(pid)])


def clean_apt_cache() -> tuple[bool, str]:
    return run_privileged(["apt-get", "clean"])


def clean_crash_reports() -> tuple[bool, str]:
    # Đường dẫn cố định (không lấy từ input người dùng) nên an toàn khi truyền qua bash -c
    return run_privileged(["bash", "-c", "rm -rf /var/crash/* 2>/dev/null; exit 0"])


def vacuum_journal(target_size: str = "200M") -> tuple[bool, str]:
    return run_privileged(["journalctl", f"--vacuum-size={target_size}"])


def autoremove_packages() -> tuple[bool, str]:
    return run_privileged(["apt-get", "-y", "autoremove"])
