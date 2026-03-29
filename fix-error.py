"""
Launch one or more worker setup processes for manual login/captcha/session repair.

Usage:
    python fix-error.py
    python fix-error.py menu
    python fix-error.py chatgpt
    python fix-error.py gemini
    python fix-error.py deepseek
    python fix-error.py qwen
    python fix-error.py all
"""

import subprocess
import sys
from pathlib import Path

import worker_common as common


common.configure_console()

BASE_DIR = Path(__file__).parent

WORKERS = [
    {"key": "chatgpt", "label": "ChatGPT", "script": "search_chatgpt.py"},
    {"key": "gemini", "label": "Gemini", "script": "search_gemini.py"},
    {"key": "deepseek", "label": "DeepSeek", "script": "search_deepseek.py"},
    {"key": "qwen", "label": "Qwen", "script": "search_qwen.py"},
]

WORKER_MAP = {worker["key"]: worker for worker in WORKERS}


def parse_args(argv):
    if len(argv) <= 1:
        return "menu"

    command = argv[1].strip().lower()
    valid = {"menu", "all"} | set(WORKER_MAP.keys())
    if command not in valid:
        raise ValueError(
            "Usage: python fix-error.py [menu|chatgpt|gemini|deepseek|qwen|all]"
        )
    return command


def choose_from_menu():
    print("=" * 80)
    print("AGENT-SEARCH FIX ERROR")
    print("=" * 80)
    print("1. Mở ChatGPT")
    print("2. Mở Gemini")
    print("3. Mở DeepSeek")
    print("4. Mở Qwen")
    print("5. Mở tất cả")
    print("=" * 80)

    choice = input("Chọn 1-5: ").strip()
    mapping = {
        "1": "chatgpt",
        "2": "gemini",
        "3": "deepseek",
        "4": "qwen",
        "5": "all",
    }
    if choice not in mapping:
        raise ValueError("Lựa chọn không hợp lệ. Chỉ chấp nhận 1-5.")
    return mapping[choice]


def build_setup_command(worker):
    script_path = BASE_DIR / worker["script"]
    return [sys.executable, str(script_path), "--setup", "1"], script_path


def launch_worker_setup(worker):
    cmd, script_path = build_setup_command(worker)
    if not script_path.exists():
        raise FileNotFoundError(f"Không tìm thấy script: {script_path.name}")

    subprocess.Popen(cmd, cwd=str(BASE_DIR))
    print(f"[{worker['label']}] Đã mở setup qua {script_path.name}")


def run_fix(target):
    selected_workers = WORKERS if target == "all" else [WORKER_MAP[target]]

    print("Fix-error sẽ chỉ mở browser/profile rồi thoát ngay.")
    print("Browser sẽ giữ nguyên để user tự đăng nhập hoặc vượt captcha.")
    print("Khi sửa xong, user tự đóng các cửa sổ browser tương ứng.")
    print("")

    for worker in selected_workers:
        launch_worker_setup(worker)

    print("")
    print("✓ Đã mở xong các cửa sổ cần sửa lỗi.")
    print("✓ Lệnh này kết thúc ngay, không giữ vòng lặp chờ nữa.")


def main():
    try:
        target = parse_args(sys.argv)
        if target == "menu":
            target = choose_from_menu()
        run_fix(target)
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nNgười dùng đã hủy thao tác.")
        sys.exit(1)
    except EOFError:
        print("\nKhông nhận được input từ terminal.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nLỗi: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
