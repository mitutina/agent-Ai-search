"""
Search DeepSeek - Standalone Script
Profile: profiles/deepseek/
Fix: Extract content AFTER collapsing reasoning panel
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
PROFILE_DIR = BASE_DIR / "profiles" / "deepseek"
STORAGE_STATE_PATH = BASE_DIR / "profiles" / "deepseek_storage_state.json"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = OUTPUT_DIR / "temp"
TIMEOUT_MS = 60000


def collapse_reasoning_panel(page, engine):
    """Ẩn phần reasoning (Đã suy nghĩ xx giây) bằng cách click mũi tên"""
    try:
        clicked = page.evaluate("""
            () => {
                const span = document.querySelector('span._5255ff8._4d41763');
                if (!span) return {ok:false, reason:'no-span'};

                const parent = span.parentElement;
                let chevronBtn = null;

                if (parent) {
                    const svg = parent.querySelector('svg');
                    if (svg) chevronBtn = svg.closest('button') || svg.parentElement;
                }

                if (!chevronBtn && span.nextElementSibling) {
                    const svg2 = span.nextElementSibling.querySelector('svg');
                    if (svg2) chevronBtn = svg2.closest('button') || svg2.parentElement;
                }

                if (chevronBtn && chevronBtn.click) {
                    chevronBtn.click();
                    return {ok:true, method:'chevron'};
                }

                // Fallback: click just to the right of the span
                const r = span.getBoundingClientRect();
                const x = r.right + 12;
                const y = (r.top + r.bottom) / 2;
                const evt = new MouseEvent('click', {bubbles:true, clientX:x, clientY:y});
                span.dispatchEvent(evt);
                return {ok:true, method:'offset'};
            }
        """)

        if clicked.get('ok'):
            print(f"[{engine}] ✓ Đã ẩn reasoning ({clicked.get('method')})")
            return True

        print(f"[{engine}] ⚠ Không tìm thấy dòng Đã suy nghĩ")
        return False
    except Exception as e:
        print(f"[{engine}] ⚠ Lỗi khi ẩn reasoning: {e}")
        return False


def extract_response_text(page, engine):
    """Extract response text from DeepSeek page, excluding reasoning content"""
    return page.evaluate("""
        () => {
            // DeepSeek uses .ds-markdown or .ds-markdown--block for response content
            const responseElements = document.querySelectorAll('.ds-markdown, .ds-markdown--block, [class*="markdown"]');

            if (responseElements.length > 0) {
                // Get the last response element (most recent)
                const lastResponse = responseElements[responseElements.length - 1];
                let responseText = lastResponse.innerText || lastResponse.textContent;

                if (responseText && responseText.length > 50) {
                    // Clean the text by removing reasoning lines
                    const lines = responseText.split('\\n').map(line => line.trim());
                    const filteredLines = [];

                    for (const line of lines) {
                        if (!line.includes('Đã suy nghĩ') &&
                            !line.includes('Đã đọc') &&
                            !line.includes('Thinking') &&
                            !line.includes('Reading') &&
                            line.length > 0) {
                            filteredLines.push(line);
                        }
                    }

                    let cleaned = filteredLines.join('\\n');
                    cleaned = cleaned.replace(/\\n{3,}/g, '\\n\\n');

                    if (cleaned && cleaned.length > 50) {
                        return cleaned.trim();
                    }
                }
            }

            // Fallback: try to find any div with long text content
            const allDivs = document.querySelectorAll('div');
            for (let i = allDivs.length - 1; i >= 0; i--) {
                const div = allDivs[i];
                const text = div.innerText || div.textContent;
                if (text && text.length > 200 && !text.includes('Nhắn tin') && !text.includes('Message')) {
                    // Filter out reasoning lines
                    const lines = text.split('\\n').map(line => line.trim());
                    const filteredLines = [];
                    for (const line of lines) {
                        if (!line.includes('Đã suy nghĩ') &&
                            !line.includes('Đã đọc') &&
                            !line.includes('Thinking') &&
                            !line.includes('Reading') &&
                            line.length > 0) {
                            filteredLines.push(line);
                        }
                    }
                    let cleaned = filteredLines.join('\\n');
                    cleaned = cleaned.replace(/\\n{3,}/g, '\\n\\n');
                    if (cleaned && cleaned.length > 50) {
                        return cleaned.trim();
                    }
                }
            }

            return '';
        }
    """)


def clean_response_text(query: str, response_text: str) -> str:
    if not response_text:
        return ""

    cleaned_lines = []
    for line in response_text.splitlines():
        text = line.strip()
        if not text:
            continue
        lower = text.lower()
        if text == query.strip():
            continue
        if lower in {
            "suy nghĩ sâu",
            "tìm kiếm thông minh",
            "được tạo bởi ai, chỉ để tham khảo",
        }:
            continue
        cleaned_lines.append(text)

    return "\n".join(cleaned_lines).strip()


def main():
    try:
        args = common.parse_worker_args(sys.argv, "search_deepseek.py")
    except ValueError as e:
        print(str(e))
        sys.exit(1)

    engine = "DeepSeek"
    timestamp = args["timestamp"]

    if args["mode"] == "setup":
        with sync_playwright() as p:
            common.interactive_profile_setup(
                playwright=p,
                engine=engine,
                profile_dir=PROFILE_DIR,
                storage_state_path=STORAGE_STATE_PATH,
                start_url="https://chat.deepseek.com/",
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
            with sync_playwright() as p:
                context = common.launch_persistent_context(
                    playwright=p,
                    profile_dir=PROFILE_DIR,
                    engine=engine,
                    storage_state_path=STORAGE_STATE_PATH,
                    timeout=30000,
                )

                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(TIMEOUT_MS)
                page.bring_to_front()

                print(f"[{engine}] Đang mở DeepSeek...")
                page.goto("https://chat.deepseek.com/", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                blockers = common.detect_page_blockers(
                    page,
                    login_keywords=["sign in", "log in", "login", "dang nhap"],
                    captcha_keywords=["captcha", "verify", "robot", "vérifions"],
                    logout_keywords=["you have signed out"],
                )
                if blockers.get("hasCaptcha"):
                    raise Exception("DeepSeek yêu cầu CAPTCHA - cần xác minh thủ công trong profile")
                if blockers.get("hasLoginPrompt") or blockers.get("hasLogoutMarker"):
                    raise Exception("DeepSeek chưa đăng nhập trong profile - hãy chạy --setup")

                try:
                    debug_dir = OUTPUT_DIR / "debug"
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    debug_png = debug_dir / f"deepseek_before_input_{timestamp}.png"
                    page.screenshot(path=str(debug_png), full_page=True)
                    print(f"[{engine}] 🧪 Debug saved: {debug_png}")
                except Exception as e:
                    print(f"[{engine}] ⚠ Không lưu debug được: {e}")

                print(f"[{engine}] Đang nhập câu hỏi...")
                textarea = None
                selectors = [
                    'textarea[placeholder*="Nhắn tin"]',
                    'textarea[placeholder*="Message"]',
                    'textarea'
                ]
                for sel in selectors:
                    try:
                        textarea = page.wait_for_selector(sel, timeout=3000)
                        print(f"[{engine}] ✓ Tìm thấy textarea: {sel}")
                        break
                    except Exception:
                        continue

                if not textarea:
                    raise Exception("Không tìm thấy textarea")

                textarea.click()
                textarea.fill(query)
                page.wait_for_timeout(500)
                textarea.press("Enter")

                page.wait_for_timeout(2000)

                def is_deepseek_busy():
                    return page.evaluate("""
                        () => {
                            const buttons = document.querySelectorAll('button');
                            for (const btn of buttons) {
                                const aria = btn.getAttribute('aria-label') || '';
                                if (aria.includes('Stop') || aria.includes('Dừng')) {
                                    return true;
                                }
                            }
                            const bodyText = document.body.innerText;
                            if (bodyText.includes('Thinking') || bodyText.includes('Đang suy nghĩ')) {
                                return true;
                            }
                            return false;
                        }
                    """)

                prev_text = ""
                stable_count = 0
                max_wait = 180
                min_detect_chars = 20

                for i in range(max_wait):
                    page.wait_for_timeout(1000)
                    is_busy = is_deepseek_busy()

                    current_response = page.evaluate("""
                        () => {
                            const messages = document.querySelectorAll('[class*="message"]');
                            for (let i = messages.length - 1; i >= 0; i--) {
                                const msg = messages[i];
                                const text = msg.innerText || msg.textContent;
                                if (text && text.length > 50 && !text.includes('Nhắn tin')) {
                                    return text.trim();
                                }
                            }
                            return '';
                        }
                    """)

                    if is_busy:
                        if i % 10 == 0:
                            print(f"[{engine}] Đang suy nghĩ... ({i}s)")
                        stable_count = 0
                        prev_text = current_response
                        continue

                    if current_response and len(current_response) >= min_detect_chars:
                        if current_response == prev_text:
                            stable_count += 1
                            if stable_count >= 5:
                                print(f"[{engine}] ✓ Text ổn định sau {i}s")
                                break
                        else:
                            if i % 5 == 0:
                                print(f"[{engine}] Đang nhận response... ({len(current_response)} chars)")
                            stable_count = 0
                            prev_text = current_response
                    else:
                        stable_count = 0
                        prev_text = current_response

                print(f"[{engine}] BƯỚC 1: Đợi 5s trước khi ẩn reasoning...")
                page.wait_for_timeout(5000)

                print(f"[{engine}] BƯỚC 2: Ẩn reasoning panel...")
                collapse_reasoning_panel(page, engine)
                page.wait_for_timeout(2000)

                print(f"[{engine}] BƯỚC 3: Extract content SAU KHI collapse...")
                response_text = extract_response_text(page, engine)
                response_text = clean_response_text(query, response_text)

                print(f"[{engine}] DEBUG: response_text length = {len(response_text)}")
                print(f"[{engine}] DEBUG: response_text preview = {response_text[:200]}...")

                if response_text and len(response_text) >= 20:
                    result["success"] = True
                    result["data"] = response_text
                    print(f"[{engine}] ✓ Thành công ({len(response_text)} chars)")
                else:
                    result["error"] = "Response quá ngắn hoặc không lấy được"
                    print(f"[{engine}] ✗ Lỗi: {result['error']}")
                    if response_text:
                        result["data"] = response_text

                common.save_storage_state(context, STORAGE_STATE_PATH, engine)

        except PlaywrightTimeoutError as e:
            result["error"] = f"Timeout: {str(e)}"
            print(f"[{engine}] ✗ Timeout: {e}")
        except Exception as e:
            result["error"] = f"Lỗi: {str(e)}"
            print(f"[{engine}] ✗ Lỗi: {e}")
        finally:
            if context:
                try:
                    if page:
                        page.wait_for_timeout(2000)
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass

    result["time"] = (datetime.now() - start_time).total_seconds()
    common.finalize_worker_run(engine, TEMP_DIR, "deepseek", timestamp, result, log_enabled)
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
