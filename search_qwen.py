"""
Search Qwen - Standalone Script
Profile: profiles/qwen/
"""
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
import worker_common as common

common.configure_console()

# Cấu hình
BASE_DIR = Path(__file__).parent
PROFILE_DIR = common.resolve_profile_dir(BASE_DIR, "qwen", legacy_names=["Qwen"])
STORAGE_STATE_PATH = BASE_DIR / "profiles" / "qwen_storage_state.json"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = OUTPUT_DIR / "temp"
TIMEOUT_MS = 60000


def open_qwen_home(page):
    print("[Qwen] Đang mở Qwen...")
    page.goto("https://chat.qwen.ai/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)


def select_thinking_mode(page):
    print("[Qwen] Chọn chế độ Thinking...")
    selector = page.locator(".qwen-thinking-selector .ant-select-selector").first
    selector.click()
    page.wait_for_timeout(500)

    option = page.locator(".ant-select-dropdown .ant-select-item-option").filter(
        has_text="Thinking"
    ).last
    option.click()
    page.wait_for_timeout(800)


def enable_web_search(page):
    print("[Qwen] Bật Web search...")
    page.locator(".mode-select .ant-dropdown-trigger").first.click()
    page.wait_for_timeout(800)

    more_box = page.evaluate(
        """
        () => {
            const items = Array.from(
                document.querySelectorAll('.ant-dropdown-menu-item, .ant-dropdown-menu-submenu')
            );
            const target = items.find((el) => (el.innerText || '').trim() === 'More');
            if (!target) return null;
            const rect = target.getBoundingClientRect();
            return {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
            };
        }
        """
    )
    if not more_box:
        raise Exception("Không tìm thấy menu More")

    page.mouse.move(
        more_box["x"] + more_box["width"] / 2,
        more_box["y"] + more_box["height"] / 2,
    )
    page.wait_for_timeout(1200)

    search_item = page.locator(".ant-dropdown-menu-sub .ant-dropdown-menu-item").filter(
        has_text="Web search"
    ).first
    search_item.click()
    page.wait_for_timeout(1000)


def submit_query(page, query: str):
    print("[Qwen] Đang nhập câu hỏi...")
    textarea = page.locator("textarea.message-input-textarea").first
    textarea.click()
    textarea.fill(query)
    page.wait_for_timeout(400)

    try:
        textarea.press("Enter")
    except Exception:
        send_button = page.locator("button").filter(has=page.locator("svg")).last
        send_button.click()


def get_last_assistant_text(page):
    return page.evaluate(
        """
        () => {
            const messages = Array.from(
                document.querySelectorAll('.qwen-chat-message.qwen-chat-message-assistant')
            );
            if (!messages.length) return '';

            const lastMessage = messages[messages.length - 1];
            const candidateSelectors = [
                '.response-message-content',
                '.custom-qwen-markdown',
                '.chat-response-message-right',
            ];

            for (const selector of candidateSelectors) {
                const nodes = lastMessage.querySelectorAll(selector);
                for (let i = nodes.length - 1; i >= 0; i--) {
                    const text = (nodes[i].innerText || '').trim();
                    if (text) return text;
                }
            }

            return (lastMessage.innerText || '').trim();
        }
        """
    )


def get_assistant_count(page):
    return page.locator(".qwen-chat-message.qwen-chat-message-assistant").count()


def wait_for_response(page, previous_count: int):
    print("[Qwen] Đang đợi response...")
    prev_text = ""
    stable_count = 0
    max_wait = 180
    saw_new_message = False
    min_seconds = 12
    min_chars = 20

    for second in range(max_wait):
        page.wait_for_timeout(1000)

        current_count = get_assistant_count(page)
        current_text = get_last_assistant_text(page).strip()
        current_text_clean = current_text.replace("Thinking completed", "", 1).strip()

        if current_count > previous_count:
            saw_new_message = True

        if second % 10 == 0:
            print(
                f"[Qwen] Chờ response... ({second}s, assistants={current_count}, chars={len(current_text_clean)})"
            )

        if "Thinking" in current_text and len(current_text_clean) < 5:
            prev_text = current_text_clean or prev_text
            stable_count = 0
            continue

        if not saw_new_message or not current_text_clean:
            prev_text = current_text_clean or prev_text
            stable_count = 0
            continue

        if len(current_text_clean) < min_chars or second < min_seconds:
            prev_text = current_text_clean
            stable_count = 0
            continue

        if current_text_clean == prev_text:
            stable_count += 1
            if stable_count >= 8:
                print(f"[Qwen] ✓ Text ổn định sau {second}s")
                return current_text_clean
        else:
            prev_text = current_text_clean
            stable_count = 0

    return prev_text.strip()

def main():
    try:
        args = common.parse_worker_args(sys.argv, "search_qwen.py")
    except ValueError as e:
        print(str(e))
        sys.exit(1)

    engine = "Qwen"
    timestamp = args["timestamp"]

    if args["mode"] == "setup":
        with sync_playwright() as p:
            common.interactive_profile_setup(
                playwright=p,
                engine=engine,
                profile_dir=PROFILE_DIR,
                storage_state_path=STORAGE_STATE_PATH,
                start_url="https://chat.qwen.ai/",
                timeout=TIMEOUT_MS,
            )
        return

    query = args["query"]
    log_enabled = args["log_enabled"]
    result = {"success": False, "data": None, "error": None, "time": 0}
    start_time = datetime.now()

    common.ensure_dirs(PROFILE_DIR, OUTPUT_DIR, TEMP_DIR)

    context = None
    page = None
    stdout_cm = common.build_stdout_context(log_enabled)

    with stdout_cm:
        if log_enabled:
            print(f"\n[{engine}] Bắt đầu...")
            print(f"[{engine}] Timestamp: {timestamp}")

        try:
            with sync_playwright() as playwright:
                context = common.launch_persistent_context(
                    playwright=playwright,
                    profile_dir=PROFILE_DIR,
                    engine=engine,
                    storage_state_path=STORAGE_STATE_PATH,
                    timeout=30000,
                )

                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(TIMEOUT_MS)
                page.bring_to_front()

                open_qwen_home(page)

                blockers = common.detect_page_blockers(
                    page,
                    login_keywords=["sign in", "log in", "login", "continue with", "dang nhap"],
                    captcha_keywords=["captcha", "verify", "robot"],
                    logout_keywords=["signed out"],
                )
                if blockers.get("hasCaptcha"):
                    raise Exception("Qwen yêu cầu CAPTCHA - cần xác minh thủ công trong profile")
                if blockers.get("hasLoginPrompt") or blockers.get("hasLogoutMarker"):
                    raise Exception("Qwen chưa đăng nhập trong profile - hãy chạy --setup")

                previous_assistant_count = get_assistant_count(page)

                select_thinking_mode(page)
                enable_web_search(page)
                submit_query(page, query)

                response_text = wait_for_response(page, previous_assistant_count)

                if response_text and len(response_text.strip()) > 0:
                    result["success"] = True
                    result["data"] = response_text
                    print(f"[{engine}] ✓ Thành công ({len(response_text)} chars)")
                else:
                    result["error"] = "Response quá ngắn hoặc không lấy được"
                    result["data"] = response_text or None
                    print(f"[{engine}] ✗ Lỗi: {result['error']}")

                common.save_storage_state(context, STORAGE_STATE_PATH, engine)

        except PlaywrightTimeoutError as exc:
            result["error"] = f"Timeout: {exc}"
            print(f"[{engine}] ✗ Timeout: {exc}")
        except Exception as exc:
            result["error"] = f"Lỗi: {exc}"
            print(f"[{engine}] ✗ Lỗi: {exc}")
        finally:
            if context is not None:
                try:
                    if page is not None:
                        page.wait_for_timeout(1500)
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass

    result["time"] = (datetime.now() - start_time).total_seconds()
    common.finalize_worker_run(engine, TEMP_DIR, "qwen", timestamp, result, log_enabled)
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
