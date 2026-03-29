"""
Search ChatGPT - Standalone Script
Profile: profiles/chatgpt/
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
PROFILE_DIR = BASE_DIR / "profiles" / "chatgpt"
STORAGE_STATE_PATH = BASE_DIR / "profiles" / "chatgpt_storage_state.json"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = OUTPUT_DIR / "temp"
DEBUG_DIR = OUTPUT_DIR / "debug"
TIMEOUT_MS = 60000

def _verify_web_search_on(page) -> bool:
    """Chỉ tin vào bằng chứng trực quan trong UI.

    Điều kiện PASS (theo yêu cầu Sếp):
    - BẮT BUỘC phải có chip/nút 'Search' màu xanh (kèm icon globe) gần composer.
    (Không bắt buộc placeholder 'Search the web'.)

    Không dùng 'Sources' sau khi gửi để suy luận.
    """
    try:
        return page.evaluate(r"""
            () => {
                const norm = (t) => (t || '').replace(/\s+/g,' ').trim().toLowerCase();

                // BẮT BUỘC: tìm chip/button 'Search' có màu xanh trong vùng composer.
                // Tiêu chí: text == 'Search' + computedStyle.color là xanh-ish, và nằm nửa dưới màn hình.
                const isBlue = (rgb) => {
                    // rgb like 'rgb(0, 122, 255)' or 'rgba(...)'
                    const m = rgb && rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
                    if (!m) return false;
                    const r = parseInt(m[1],10), g = parseInt(m[2],10), b = parseInt(m[3],10);
                    // xanh: b cao, r thấp tương đối
                    return (b >= 140 && g >= 80 && r <= 120);
                };

                const els = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                for (const el of els) {
                    const t = norm(el.innerText || el.textContent || '');
                    if (t !== 'search') continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < 30 || r.height < 14) continue;
                    if (r.top < window.innerHeight * 0.5) continue;

                    const style = window.getComputedStyle(el);
                    const color = style && style.color;
                    if (!isBlue(color)) continue;

                    // icon globe gần đó (svg) hoặc emoji globe
                    const hasSvg = !!el.querySelector('svg');
                    const hasGlobeEmoji = (el.innerText || '').includes('🌐') || (el.textContent || '').includes('🌐');

                    // Nhiều UI có icon ở element sibling, check parent
                    const parent = el.parentElement;
                    const parentHasSvg = parent ? !!parent.querySelector('svg') : false;
                    const okIcon = hasSvg || hasGlobeEmoji || parentHasSvg;

                    if (okIcon) return true;
                }

                return false;
            }
        """)
    except Exception:
        return False


def enable_web_search(page, engine, timestamp):
    """Bật Web search và PHẢI verify bằng UI 'Search the web' + Search xanh.

    Quy tắc mới:
    - Chỉ đi theo đường UI đúng như ảnh mẫu: '+' -> More -> Web search.
    - Sau khi click, bắt buộc verify _verify_web_search_on(page) == True.
    """
    try:
        print(f"[{engine}] Đang bật Tìm kiếm trên mạng (bắt buộc hiện 'Search the web' + Search xanh)...")

        def has_web_search_menu_item():
            try:
                return page.evaluate(r"""
                    () => {
                        const patterns = [
                            /^web\s*search$/i,
                            /^search\s*the\s*web$/i,
                            /tìm\s*kiếm\s*trên\s*mạng/i,
                            /tìm\s*kiếm\s*trên\s*web/i
                        ];
                        const nodes = Array.from(document.querySelectorAll('div[role="menuitem"],button[role="menuitem"],div[role="option"],button,div'));
                        const visible = (el) => {
                            const r = el.getBoundingClientRect();
                            if (r.width < 40 || r.height < 16) return false;
                            if (r.bottom < 0 || r.top > window.innerHeight) return false;
                            const s = window.getComputedStyle(el);
                            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                        };
                        for (const el of nodes) {
                            if (!visible(el)) continue;
                            const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                            if (!text || text.length > 80) continue;
                            if (patterns.some((re) => re.test(text))) return true;
                        }
                        return false;
                    }
                """)
            except Exception:
                return False

        def open_plus_menu():
            plus_btn = page.locator("[data-testid=composer-plus-btn]")
            # Khi chạy song song trong manager, UI đôi lúc lag -> tăng timeout.
            plus_btn.click(timeout=15000, force=True)
            page.wait_for_timeout(800)

        # Thử nhiều vòng vì UI đôi lúc không mở menu/submenu ngay
        for attempt in range(1, 4):
            print(f"[{engine}]   - Attempt {attempt}/3: mở menu + ...")
            open_plus_menu()

            # Mở submenu 'More' / 'Thêm'
            try:
                more = page.locator(
                    "div[role='menuitem'][data-has-submenu]:has-text('More'), "
                    "button[role='menuitem'][data-has-submenu]:has-text('More'), "
                    "div[role='menuitem'][data-has-submenu]:has-text('Thêm'), "
                    "button[role='menuitem'][data-has-submenu]:has-text('Thêm'), "
                    "div[role='menuitem']:has-text('More'), "
                    "button[role='menuitem']:has-text('More'), "
                    "div[role='menuitem']:has-text('Thêm'), "
                    "button[role='menuitem']:has-text('Thêm')"
                ).first
                more.hover(timeout=6000)
                page.wait_for_timeout(600)
                if not has_web_search_menu_item():
                    more.click(timeout=4000, force=True)
                    page.wait_for_timeout(800)
            except Exception:
                page.evaluate(r"""
                    () => {
                        const pick = (re) => {
                            const nodes = Array.from(document.querySelectorAll('div[role="menuitem"],button[role="menuitem"],div'));
                            for (const el of nodes) {
                                const t = (el.innerText||'').replace(/\s+/g,' ').trim();
                                if (re.test(t)) return el;
                            }
                            return null;
                        };
                        const more = pick(/^More$/i) || pick(/^Thêm$/i);
                        if (!more) return;
                        more.dispatchEvent(new MouseEvent('mouseover', {bubbles:true}));
                        more.dispatchEvent(new MouseEvent('click', {bubbles:true}));
                    }
                """)
                page.wait_for_timeout(800)

            # Click 'Web search'
            clicked = page.evaluate(r"""
                () => {
                    const patterns = [/^web\s*search$/i,/tìm\s*kiếm\s*trên\s*mạng/i,/tìm\s*kiếm\s*trên\s*web/i,/search\s*the\s*web/i];
                    const nodes = Array.from(document.querySelectorAll('div[role="menuitem"],button[role="menuitem"],div[role="option"],button,div'));
                    const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        if (r.width < 40 || r.height < 16) return false;
                        if (r.bottom < 0 || r.top > window.innerHeight) return false;
                        const s = window.getComputedStyle(el);
                        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
                        return true;
                    };
                    for (const el of nodes) {
                        if (!visible(el)) continue;
                        const text = (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim();
                        if (!text || text.length > 80) continue;
                        for (const re of patterns) {
                            if (re.test(text)) { el.click(); return true; }
                        }
                    }
                    return false;
                }
            """)

            if not clicked:
                print(f"[{engine}]   - Không click được Web search trong submenu, thử lại...")
                page.wait_for_timeout(1200)
                continue

            page.wait_for_timeout(1200)

            # VERIFY bắt buộc
            ok = _verify_web_search_on(page)
            # debug ảnh verify ngay tại thời điểm BEFORE SEND
            try:
                dbg_png = DEBUG_DIR / f"chatgpt_websearch_verify_{timestamp}_attempt{attempt}.png"
                page.screenshot(path=str(dbg_png), full_page=True)
                print(f"[{engine}] 🧪 Verify screenshot: {dbg_png}")
            except Exception:
                pass

            if ok:
                print(f"[{engine}] ✓ VERIFY PASS: UI đã hiện trạng thái Web Search ON")
                return True

            print(f"[{engine}] ⚠ VERIFY FAIL: chưa thấy 'Search the web' + Search xanh, thử lại...")
            page.wait_for_timeout(1200)

        print(f"[{engine}] ✗ Không bật/verify được Web Search ON theo UI (sau 3 attempts)")
        return False

    except Exception as e:
        print(f"[{engine}] ⚠ Lỗi enable_web_search: {e}")
        return False


def ensure_logged_in_chat_ui(page, engine):
    try:
        page.wait_for_selector("#prompt-textarea", timeout=12000)
        return
    except Exception:
        pass

    current_url = page.url
    page_text = ""
    try:
        page_text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        pass

    if "log in" in page_text or "đăng nhập" in page_text or "sign up" in page_text or "bắt đầu" in page_text:
        raise Exception("ChatGPT chưa đăng nhập trong profile - hãy chạy --setup")

    raise Exception(
        f"ChatGPT chưa vào được giao diện chat đã đăng nhập (url hiện tại: {current_url}) - hãy chạy --setup"
    )


def main():
    try:
        args = common.parse_worker_args(sys.argv, "search_chatgpt.py")
    except ValueError as e:
        print(str(e))
        sys.exit(1)

    engine = "ChatGPT"
    timestamp = args["timestamp"]

    if args["mode"] == "setup":
        with sync_playwright() as p:
            common.interactive_profile_setup(
                playwright=p,
                engine=engine,
                profile_dir=PROFILE_DIR,
                storage_state_path=STORAGE_STATE_PATH,
                start_url="https://chatgpt.com/",
                timeout=TIMEOUT_MS,
            )
        return

    query = args["query"]
    log_enabled = args["log_enabled"]

    result = {"success": False, "data": None, "error": None, "time": 0}
    start_time = datetime.now()

    common.ensure_dirs(PROFILE_DIR, OUTPUT_DIR, TEMP_DIR, DEBUG_DIR)

    browser = None
    context = None
    page = None
    stdout_cm = common.build_stdout_context(log_enabled)

    with stdout_cm:
        if log_enabled:
            print(f"\n[{engine}] Bắt đầu...")
            print(f"[{engine}] Timestamp: {timestamp}")

        try:
            with sync_playwright() as p:
                browser = common.launch_browser(
                    playwright=p,
                    engine=engine,
                    timeout=30000,
                )

                context_options = {}
                if STORAGE_STATE_PATH.exists():
                    context_options["storage_state"] = str(STORAGE_STATE_PATH)

                context = browser.new_context(**context_options)
                common.add_stealth_script(context)

                page = context.new_page()
                page.set_default_timeout(TIMEOUT_MS)
                page.bring_to_front()

                print(f"[{engine}] Đang mở ChatGPT...")
                page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
                page.wait_for_timeout(1000)
                ensure_logged_in_chat_ui(page, engine)

                blockers = common.detect_page_blockers(
                    page,
                    login_keywords=["log in", "login", "sign up", "đăng nhập", "đăng ký"],
                    captcha_keywords=["verify you are human", "captcha", "robot"],
                    logout_keywords=["signed out"],
                )
                if blockers.get("hasCaptcha"):
                    raise Exception("ChatGPT yêu cầu CAPTCHA - cần xác minh thủ công trong profile")
                if blockers.get("hasLoginPrompt") or blockers.get("hasLogoutMarker"):
                    raise Exception("ChatGPT chưa đăng nhập trong profile - hãy chạy --setup")

                page.wait_for_timeout(2000)
                enabled = enable_web_search(page, engine, timestamp)

                try:
                    dbg_png = DEBUG_DIR / f"chatgpt_tools_{timestamp}.png"
                    dbg_html = DEBUG_DIR / f"chatgpt_tools_{timestamp}.html"
                    page.screenshot(path=str(dbg_png), full_page=True)
                    dbg_html.write_text(page.content(), encoding="utf-8")
                    print(f"[{engine}] 🧪 Debug saved: {dbg_png}")
                    print(f"[{engine}] 🧪 Debug saved: {dbg_html}")
                except Exception as e:
                    print(f"[{engine}] ⚠ Không lưu debug được: {e}")

                if not enabled:
                    result["error"] = "BẮT BUỘC Web Search ON nhưng không bật được (UI/feature bị ẩn hoặc selector không khớp)"
                    print(f"[{engine}] ✗ {result['error']}")
                    try:
                        dbg_fail_png = DEBUG_DIR / f"chatgpt_websearch_fail_{timestamp}.png"
                        dbg_fail_html = DEBUG_DIR / f"chatgpt_websearch_fail_{timestamp}.html"
                        page.screenshot(path=str(dbg_fail_png), full_page=True)
                        dbg_fail_html.write_text(page.content(), encoding="utf-8")
                        print(f"[{engine}] 🧪 Debug saved: {dbg_fail_png}")
                        print(f"[{engine}] 🧪 Debug saved: {dbg_fail_html}")
                    except Exception as e:
                        print(f"[{engine}] ⚠ Không lưu debug fail-websearch được: {e}")

                    common.save_storage_state(context, STORAGE_STATE_PATH, engine)
                    raise Exception(result["error"])

                print(f"[{engine}] Đang nhập câu hỏi...")
                textarea = page.wait_for_selector("#prompt-textarea", timeout=10000)
                textarea.click()
                textarea.fill(query)

                send_button = page.wait_for_selector('button[data-testid="send-button"]', timeout=5000)
                send_button.click()

                page.wait_for_timeout(2000)

                try:
                    dbg2_png = DEBUG_DIR / f"chatgpt_after_send_{timestamp}.png"
                    dbg2_html = DEBUG_DIR / f"chatgpt_after_send_{timestamp}.html"
                    page.screenshot(path=str(dbg2_png), full_page=True)
                    dbg2_html.write_text(page.content(), encoding="utf-8")
                    print(f"[{engine}] 🧪 Debug saved: {dbg2_png}")
                    print(f"[{engine}] 🧪 Debug saved: {dbg2_html}")
                except Exception as e:
                    print(f"[{engine}] ⚠ Không lưu debug after_send được: {e}")

                def is_chatgpt_busy():
                    return page.evaluate(r"""
                        () => {
                            const buttons = Array.from(document.querySelectorAll('button'));
                            for (const btn of buttons) {
                                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                                if (aria.includes('stop') || aria.includes('dừng')) return true;
                            }
                            const ta = document.querySelector('#prompt-textarea');
                            if (ta && ta.hasAttribute('disabled')) return true;
                            return false;
                        }
                    """)

                def looks_like_ui_noise(t: str) -> bool:
                    if not t or not t.strip():
                        return True
                    low = t.strip().lower()
                    bad = [
                        'log in', 'login', 'sign up', 'đăng nhập', 'đăng ký',
                        'something went wrong', 'có lỗi', 'try again', 'thử lại',
                        'verify you are human', 'captcha'
                    ]
                    return any(x in low for x in bad)

                prev_text = ""
                stable_count = 0
                max_wait = 180
                stable_needed = 3

                def scrape_last_assistant_text():
                    return page.evaluate(r"""
                        () => {
                            const norm = (t) => (t || '').replace(/\s+$/g,'').trim();
                            const assistantNodes = document.querySelectorAll('[data-message-author-role="assistant"]');
                            if (assistantNodes && assistantNodes.length) {
                                const last = assistantNodes[assistantNodes.length - 1];
                                const content = last.querySelector('.markdown, .prose') || last;
                                let t = norm(content.innerText);
                                const lines = t.split('\n').map(x => x.trim());
                                const filtered = [];
                                for (const line of lines) {
                                    if (/^[a-z0-9.-]+\.[a-z]{2,}(\/.*)?$/i.test(line) && line.length <= 60) {
                                        continue;
                                    }
                                    filtered.push(line);
                                }
                                t = filtered.join('\n').trim();
                                return t;
                            }

                            const articles = document.querySelectorAll('article[data-testid^="conversation-turn"]');
                            if (articles && articles.length) {
                                const lastArticle = articles[articles.length - 1];
                                const content = lastArticle.querySelector('.markdown, .prose') || lastArticle;
                                let text = norm(content.innerText);
                                text = text.replace(/^ChatGPT( đã nói:| said:)?\s*/i, '').trim();
                                return text;
                            }

                            const main = document.querySelector('main');
                            return main ? norm(main.innerText) : '';
                        }
                    """)

                for i in range(max_wait):
                    page.wait_for_timeout(1000)

                    try:
                        is_busy = is_chatgpt_busy()
                    except Exception:
                        is_busy = True

                    try:
                        current_response = scrape_last_assistant_text()
                    except Exception:
                        current_response = ""

                    if is_busy:
                        if i % 10 == 0:
                            print(f"[{engine}] Đang tạo response... ({i}s)")
                        stable_count = 0
                        if current_response:
                            prev_text = current_response
                        continue

                    if current_response and (not looks_like_ui_noise(current_response)):
                        if current_response == prev_text:
                            stable_count += 1
                            if stable_count >= stable_needed:
                                print(f"[{engine}] ✓ Text ổn định sau {i}s")
                                break
                        else:
                            if i % 5 == 0:
                                print(f"[{engine}] Đang nhận response... ({len(current_response)} chars)")
                            stable_count = 0
                            prev_text = current_response
                    else:
                        stable_count = 0
                        if current_response:
                            prev_text = current_response

                response_text = (prev_text or "").strip()

                if response_text and (not looks_like_ui_noise(response_text)):
                    result["success"] = True
                    result["data"] = response_text
                    print(f"[{engine}] ✓ Thành công ({len(response_text)} chars)")
                else:
                    result["error"] = "Response rỗng/không hợp lệ hoặc không scrape được"
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
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass

    result["time"] = (datetime.now() - start_time).total_seconds()
    common.finalize_worker_run(engine, TEMP_DIR, "chatgpt", timestamp, result, log_enabled)
    sys.exit(0 if result["success"] else 1)

if __name__ == "__main__":
    main()








