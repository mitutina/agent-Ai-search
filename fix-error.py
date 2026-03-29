"""
Open one or more worker profiles for manual login/captcha/session repair.

Usage:
    python fix-error.py
    python fix-error.py menu
    python fix-error.py chatgpt
    python fix-error.py gemini
    python fix-error.py deepseek
    python fix-error.py qwen
    python fix-error.py all
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import worker_common as common


common.configure_console()

BASE_DIR = Path(__file__).parent
TIMEOUT_MS = 60000
AUTOSAVE_INTERVAL = 5


def build_worker_specs():
    return [
        {
            "key": "chatgpt",
            "label": "ChatGPT",
            "url": "https://chatgpt.com/",
            "profile_dir": BASE_DIR / "profiles" / "chatgpt",
            "storage_state_path": BASE_DIR / "profiles" / "chatgpt_storage_state.json",
        },
        {
            "key": "gemini",
            "label": "Gemini",
            "url": "https://gemini.google.com/app",
            "profile_dir": BASE_DIR / "profiles" / "gemini",
            "storage_state_path": BASE_DIR / "profiles" / "gemini_storage_state.json",
        },
        {
            "key": "deepseek",
            "label": "DeepSeek",
            "url": "https://chat.deepseek.com/",
            "profile_dir": BASE_DIR / "profiles" / "deepseek",
            "storage_state_path": BASE_DIR / "profiles" / "deepseek_storage_state.json",
        },
        {
            "key": "qwen",
            "label": "Qwen",
            "url": "https://chat.qwen.ai/",
            "profile_dir": common.resolve_profile_dir(BASE_DIR, "qwen", legacy_names=["Qwen"]),
            "storage_state_path": BASE_DIR / "profiles" / "qwen_storage_state.json",
        },
    ]


WORKERS = build_worker_specs()
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


def open_worker_context(playwright, worker):
    common.ensure_dirs(worker["profile_dir"], worker["storage_state_path"].parent)
    context = common.launch_persistent_context(
        playwright=playwright,
        profile_dir=worker["profile_dir"],
        engine=worker["label"],
        storage_state_path=worker["storage_state_path"],
        timeout=TIMEOUT_MS,
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    page.goto(worker["url"], wait_until="domcontentloaded")
    page.bring_to_front()
    print(f"[{worker['label']}] Đã mở profile tại: {worker['profile_dir']}")
    print(f"[{worker['label']}] Hãy đăng nhập lại hoặc xử lý captcha nếu cần.")
    print(f"[{worker['label']}] Khi sửa xong, hãy đóng cửa sổ browser này.")
    return context


def save_state_quietly(context, state_path: Path):
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(state_path))
    except Exception:
        pass


def wait_until_windows_closed(opened_contexts):
    active = {
        worker["key"]: {
            "worker": worker,
            "context": context,
            "last_save": 0.0,
        }
        for worker, context in opened_contexts
    }

    print("")
    print("Các cửa sổ browser đã mở để user tự sửa tay.")
    print("Script sẽ tự autosave session định kỳ.")
    print("Khi user sửa xong, chỉ cần đóng các cửa sổ browser tương ứng.")

    while active:
        now = time.time()
        closed_keys = []

        for key, item in active.items():
            worker = item["worker"]
            context = item["context"]

            try:
                _ = context.pages
                if now - item["last_save"] >= AUTOSAVE_INTERVAL:
                    save_state_quietly(context, worker["storage_state_path"])
                    item["last_save"] = now
            except Exception:
                closed_keys.append(key)

        for key in closed_keys:
            active.pop(key, None)

        if active:
            time.sleep(1)


def run_fix(target):
    selected_workers = WORKERS if target == "all" else [WORKER_MAP[target]]

    opened_contexts = []
    failed_workers = []

    with sync_playwright() as playwright:
        for worker in selected_workers:
            try:
                context = open_worker_context(playwright, worker)
                opened_contexts.append((worker, context))
            except Exception as exc:
                failed_workers.append((worker, exc))
                print(f"[{worker['label']}] ✗ Không mở được profile: {exc}")

        if not opened_contexts:
            raise RuntimeError("Không mở được profile nào để sửa lỗi.")

        wait_until_windows_closed(opened_contexts)

    if failed_workers:
        labels = ", ".join(worker["label"] for worker, _ in failed_workers)
        raise RuntimeError(f"Một số profile không mở được: {labels}")


def main():
    try:
        target = parse_args(sys.argv)
        if target == "menu":
            target = choose_from_menu()
        run_fix(target)
        print("✓ Hoàn tất quy trình sửa lỗi profile.")
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
