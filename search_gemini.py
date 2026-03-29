"""
Search Gemini - Standalone Script
Fix: JavaScript syntax, text detection, auto-complete mechanism, model selection
Profile: profiles/gemini/
Output: output/gemini_result.txt
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
PROFILE_DIR = BASE_DIR / "profiles" / "gemini"
STORAGE_STATE_PATH = BASE_DIR / "profiles" / "gemini_storage_state.json"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = OUTPUT_DIR / "temp"
TIMEOUT_MS = 60000


def select_model_with_fallback(page, engine, timestamp=None, output_dir=None):
    """Ưu tiên chọn model Tư duy (Thinking), fallback sang Nhanh (Fast)."""
    def open_model_menu():
        return page.evaluate(r"""
            () => {
                const normalize = (s) => (s || '')
                    .toLowerCase()
                    .normalize('NFD')
                    .replace(/[\u0300-\u036f]/g, '')
                    .replace(/đ/g, 'd')
                    .replace(/\s+/g, ' ')
                    .trim();

                const candidates = Array.from(document.querySelectorAll('button, div[role="button"], div[role="combobox"]'));
                let best = null;
                let bestScore = -1;

                for (const el of candidates) {
                    const rawText = (el.innerText || el.textContent || '');
                    const rawAria = (el.getAttribute('aria-label') || '');
                    const text = normalize(rawText);
                    const aria = normalize(rawAria);
                    const className = normalize(el.className || '');
                    const rect = el.getBoundingClientRect();

                    if (rect.width < 30 || rect.height < 16) continue;

                    let score = 0;
                    if (text.includes('nhanh') || text.includes('fast') || text.includes('quick')) score += 5;
                    if (text.includes('tu duy') || text.includes('thinking') || text.includes('deep think')) score += 6;
                    if (/\bpro\b/.test(text) || text.includes('flash')) score += 3;
                    if (text.includes('gemini 3') || text.includes('gemini 2')) score += 2;
                    if (aria.includes('model') || aria.includes('mo hinh')) score += 8;
                    if (
                        aria.includes('mo bo chon che do') ||
                        aria.includes('mode picker') ||
                        aria.includes('open mode picker') ||
                        aria.includes('open model picker') ||
                        aria.includes('mode switch')
                    ) score += 12;
                    if (el.getAttribute('aria-haspopup') === 'true') score += 4;
                    if (className.includes('input-area-switch')) score += 16;
                    if (el.querySelector('svg')) score += 1;

                    if (score > bestScore) {
                        bestScore = score;
                        best = el;
                    }
                }

                if (!best || bestScore < 4) {
                    return { ok: false, text: '', score: bestScore };
                }

                const chosenText = (best.innerText || best.textContent || '').replace(/\s+/g, ' ').trim();
                best.click();
                return { ok: true, text: chosenText.slice(0, 80), score: bestScore };
            }
        """)

    def collect_menu_info():
        return page.evaluate(r"""
            () => {
                const normalize = (s) => (s || '')
                    .toLowerCase()
                    .normalize('NFD')
                    .replace(/[\u0300-\u036f]/g, '')
                    .replace(/đ/g, 'd')
                    .replace(/\s+/g, ' ')
                    .trim();

                const items = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"], [role="menuitemradio"], li, button, div'));
                const options = [];
                const seen = new Set();

                for (const el of items) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 40 || rect.height < 16) continue;

                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

                    const raw = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                    if (!raw || raw.length > 160) continue;

                    const text = normalize(raw);
                    if (!text) continue;

                    const likelyModelOption =
                        text.includes('tu duy') || text.includes('nhanh') || text.includes('thinking') ||
                        text.includes('fast') || text.includes('quick') || /\bpro\b/.test(text) ||
                        text.includes('flash') || text.includes('giai quyet cac van de phuc tap') ||
                        text.includes('tra loi nhanh') || text.includes('complex problem') ||
                        text.includes('problem solving') || text.includes('quick response') ||
                        text.includes('quick responses') || text.includes('quick answer') ||
                        text.includes('quick answers') || text.includes('gemini 3');

                    if (!likelyModelOption) continue;
                    if (seen.has(text)) continue;

                    seen.add(text);
                    options.push({ text: raw, normalized: text });
                }

                return { count: options.length, options };
            }
        """)

    def get_current_model_label():
        return page.evaluate(r"""
            () => {
                const normalize = (s) => (s || '')
                    .toLowerCase()
                    .normalize('NFD')
                    .replace(/[\u0300-\u036f]/g, '')
                    .replace(/đ/g, 'd')
                    .replace(/\s+/g, ' ')
                    .trim();

                const candidates = Array.from(document.querySelectorAll('button, div[role="button"], div[role="combobox"]'));
                let best = null;
                let bestScore = -1;

                for (const el of candidates) {
                    const rawText = (el.innerText || el.textContent || '');
                    const rawAria = (el.getAttribute('aria-label') || '');
                    const text = normalize(rawText);
                    const aria = normalize(rawAria);
                    const className = normalize(el.className || '');
                    const rect = el.getBoundingClientRect();

                    if (rect.width < 30 || rect.height < 16) continue;

                    let score = 0;
                    if (text.includes('nhanh') || text.includes('fast') || text.includes('quick')) score += 5;
                    if (text.includes('tu duy') || text.includes('thinking') || text.includes('deep think')) score += 6;
                    if (/\bpro\b/.test(text) || text.includes('flash')) score += 3;
                    if (
                        aria.includes('mo bo chon che do') ||
                        aria.includes('mode picker') ||
                        aria.includes('open mode picker') ||
                        aria.includes('open model picker') ||
                        aria.includes('mode switch')
                    ) score += 12;
                    if (className.includes('input-area-switch')) score += 16;

                    if (score > bestScore) {
                        bestScore = score;
                        best = el;
                    }
                }

                if (!best) {
                    return { text: '', normalized: '', score: bestScore };
                }

                const raw = (best.innerText || best.textContent || '').replace(/\s+/g, ' ').trim();
                return { text: raw.slice(0, 80), normalized: normalize(raw), score: bestScore };
            }
        """)

    def click_model_option(target):
        return page.evaluate(r"""
            (target) => {
                const normalize = (s) => (s || '')
                    .toLowerCase()
                    .normalize('NFD')
                    .replace(/[\u0300-\u036f]/g, '')
                    .replace(/đ/g, 'd')
                    .replace(/\s+/g, ' ')
                    .trim();

                const menu = document.querySelector('.gds-mode-switch-menu, [role="menu"]') || document;
                const nodes = Array.from(menu.querySelectorAll('.mode-option-wrapper, .title-and-check, .title-and-description, [role="option"], [role="menuitem"], [role="menuitemradio"], li, button, div'));

                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 40 || rect.height < 16) return false;
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                };

                const clickElement = (el) => {
                    const targetNode =
                        el.querySelector('.title-and-check, .title-and-description, button, [role="menuitemradio"], [role="menuitem"], [role="option"]') ||
                        el;

                    targetNode.scrollIntoView({ block: 'center', inline: 'nearest' });
                    const rect = targetNode.getBoundingClientRect();
                    const clientX = rect.left + rect.width / 2;
                    const clientY = rect.top + rect.height / 2;

                    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        targetNode.dispatchEvent(new MouseEvent(type, {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            clientX,
                            clientY
                        }));
                    }

                    if (typeof targetNode.click === 'function') {
                        targetNode.click();
                    }
                };

                let best = null;
                let bestScore = -1;

                for (const el of nodes) {
                    if (!isVisible(el)) continue;

                    const raw = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                    if (!raw || raw.length > 120) continue;

                    const text = normalize(raw);
                    if (!text) continue;

                    const hasThinking = text.includes('tu duy') || text.includes('thinking');
                    const hasFast = text.includes('nhanh') || text.includes('fast') || text.includes('quick');
                    const hasPro = /\bpro\b/.test(text);

                    if (target === 'thinking' && (!hasThinking || hasFast || hasPro)) continue;
                    if (target === 'fast' && (!hasFast || hasThinking || hasPro)) continue;

                    const className = normalize(el.className || '');
                    const role = normalize(el.getAttribute('role') || '');
                    let score = 0;

                    if (target === 'thinking') {
                        if (text.includes('tu duy') || text.includes('thinking')) score += 14;
                        if (text.includes('giai quyet cac van de phuc tap')) score += 8;
                        if (text.includes('complex problem')) score += 8;
                        if (text.includes('problem solving')) score += 6;
                        if (text.includes('reasoning')) score += 4;
                    } else {
                        if (text.includes('nhanh') || text.includes('fast')) score += 14;
                        if (text.includes('tra loi nhanh')) score += 8;
                        if (text.includes('quick response') || text.includes('quick responses')) score += 8;
                        if (text.includes('quick answer') || text.includes('quick answers')) score += 6;
                    }

                    if (className.includes('mode-option-wrapper')) score += 16;
                    if (className.includes('title-and-check')) score += 12;
                    if (className.includes('title-and-description')) score += 8;
                    if (role === 'option' || role === 'menuitem' || role === 'menuitemradio') score += 10;

                    if (score > bestScore) {
                        bestScore = score;
                        best = { element: el, raw };
                    }
                }

                if (!best || bestScore < 12) {
                    return { ok: false, model: '', score: bestScore };
                }

                clickElement(best.element);
                return { ok: true, model: best.raw.slice(0, 120), score: bestScore };
            }
        """, target)

    def ensure_model_menu_open():
        is_open = page.evaluate("""() => !!document.querySelector('.gds-mode-switch-menu, [role="menu"]')""")
        if is_open:
            return True

        reopen_result = open_model_menu()
        if not reopen_result.get("ok"):
            return False

        print(f"[{engine}] ↻ Mở lại menu model (button: '{reopen_result.get('text')}', score={reopen_result.get('score')})")
        page.wait_for_timeout(1200)
        return True

    def verify_model(expected):
        current = get_current_model_label()
        normalized = current.get("normalized", "")
        if expected == "thinking":
            ok = "tu duy" in normalized or "thinking" in normalized or "reasoning" in normalized
        else:
            ok = "nhanh" in normalized or "fast" in normalized or "quick" in normalized
        return ok, current

    try:
        page.wait_for_timeout(2000)

        open_result = open_model_menu()

        if not open_result.get("ok"):
            print(f"[{engine}] ⚠ Không mở được menu model")
            return False

        print(f"[{engine}] ✓ Đã mở menu model (button: '{open_result.get('text')}', score={open_result.get('score')})")
        page.wait_for_timeout(1200)

        if timestamp and output_dir:
            try:
                debug_dir = output_dir / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_png = debug_dir / f"gemini_model_menu_open_{timestamp}.png"
                page.screenshot(path=str(debug_png), full_page=True)
                print(f"[{engine}] 🧪 Snapshot menu: {debug_png}")
            except Exception as e:
                print(f"[{engine}] ⚠ Không lưu snapshot menu được: {e}")

        menu_info = collect_menu_info()

        option_texts = [opt.get("text", "") for opt in menu_info.get("options", [])]
        if option_texts:
            print(f"[{engine}] Model options thấy được: {' | '.join(option_texts)}")
        else:
            print(f"[{engine}] ⚠ Không đọc được option nào trong menu model")

        selected_thinking = click_model_option("thinking")

        if selected_thinking.get("ok"):
            page.wait_for_timeout(900)
            verified_thinking, current_model = verify_model("thinking")
            if verified_thinking:
                print(
                    f"[{engine}] ✓ Đã chọn model Tư duy: '{selected_thinking.get('model')}' "
                    f"(chip hiện tại: '{current_model.get('text')}')"
                )

                # Chụp snapshot SAU KHI chọn Tư duy để verify
                if timestamp and output_dir:
                    try:
                        debug_dir = output_dir / "debug"
                        debug_png = debug_dir / f"gemini_after_select_thinking_{timestamp}.png"
                        page.screenshot(path=str(debug_png), full_page=True)
                        print(f"[{engine}] 🧪 Snapshot sau khi chọn Tư duy: {debug_png}")
                    except Exception as e:
                        print(f"[{engine}] ⚠ Không lưu snapshot sau chọn được: {e}")

                return True

            print(
                f"[{engine}] ⚠ Đã click Tư duy nhưng chip hiện tại vẫn là "
                f"'{current_model.get('text') or 'không đọc được'}'"
            )

        else:
            print(f"[{engine}] ⚠ Không thấy option Tư duy khả dụng")

        print(f"[{engine}] ⚠ Fallback sang Nhanh...")

        if not ensure_model_menu_open():
            print(f"[{engine}] ⚠ Không mở lại được menu model để fallback")
            return False

        selected_fast = click_model_option("fast")

        if selected_fast.get("ok"):
            page.wait_for_timeout(900)
            verified_fast, current_model = verify_model("fast")
            if verified_fast:
                print(
                    f"[{engine}] ✓ Đã fallback sang Nhanh: '{selected_fast.get('model')}' "
                    f"(chip hiện tại: '{current_model.get('text')}')"
                )
                return True

            print(
                f"[{engine}] ⚠ Đã click Nhanh nhưng chip hiện tại vẫn là "
                f"'{current_model.get('text') or 'không đọc được'}'"
            )

        print(f"[{engine}] ⚠ Không chọn được Tư duy hoặc Nhanh, giữ model hiện tại")
        page.keyboard.press("Escape")
        return False

    except Exception as e:
        print(f"[{engine}] ⚠ Lỗi khi chọn model: {e}")
        return False



def main():
    try:
        args = common.parse_worker_args(sys.argv, "search_gemini.py")
    except ValueError as e:
        print(str(e))
        sys.exit(1)

    engine = "Gemini"
    timestamp = args["timestamp"]

    if args["mode"] == "setup":
        with sync_playwright() as p:
            common.interactive_profile_setup(
                playwright=p,
                engine=engine,
                profile_dir=PROFILE_DIR,
                storage_state_path=STORAGE_STATE_PATH,
                start_url="https://gemini.google.com/app",
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

                print(f"[{engine}] Đang mở Gemini...")
                page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                blockers = common.detect_page_blockers(
                    page,
                    login_keywords=["sign in", "log in", "login", "đăng nhập", "dang nhap"],
                    captcha_keywords=["captcha", "verify", "robot"],
                    logout_keywords=["signed out"],
                )
                if blockers.get("hasCaptcha"):
                    raise Exception("Gemini yêu cầu CAPTCHA - cần xác minh thủ công trong profile")
                if blockers.get("hasLoginPrompt") or blockers.get("hasLogoutMarker"):
                    raise Exception("Gemini chưa đăng nhập trong profile - hãy chạy --setup")

                # Chọn model: ưu tiên Tư duy/Thinking, fallback sang Nhanh/Fast nếu verify thất bại
                print(f"[{engine}] Đang chọn model...")
                select_model_with_fallback(page, engine, timestamp, OUTPUT_DIR)

                print(f"[{engine}] Đang nhập câu hỏi...")
                textarea = page.wait_for_selector('div[contenteditable="true"][role="textbox"]', timeout=10000)
                textarea.click()
                page.wait_for_timeout(300)
                textarea.fill(query)
                page.wait_for_timeout(500)
                textarea.press("Enter")

                page.wait_for_timeout(2000)

                def is_gemini_busy():
                    return page.evaluate("""
                        () => {
                            const buttons = document.querySelectorAll('button');
                            for (const btn of buttons) {
                                const aria = btn.getAttribute('aria-label') || '';
                                if (aria.includes('Dừng') || aria.includes('Stop')) {
                                    return true;
                                }
                            }
                            const bodyText = document.body.innerText;
                            if (bodyText.includes('Đang tạo') || bodyText.includes('Generating')) {
                                return true;
                            }
                            return false;
                        }
                    """)

                prev_text = ""
                stable_count = 0
                max_wait = 180
                has_content = False
                min_success_chars = 20

                print(f"[{engine}] Đang đợi response...")

                for i in range(max_wait):
                    page.wait_for_timeout(1000)
                    is_busy = is_gemini_busy()

                    current_response = page.evaluate("""
                        () => {
                            const bodyText = document.body.innerText;
                            const markers = [
                                "Gemini đã nói",
                                "Gemini said",
                                "Gemini",
                            ];

                            let startIdx = -1;
                            let startMarker = "";

                            for (const marker of markers) {
                                startIdx = bodyText.indexOf(marker);
                                if (startIdx !== -1) {
                                    startMarker = marker;
                                    break;
                                }
                            }

                            if (startIdx === -1) return '';

                            startIdx += startMarker.length;

                            const endMarkers = ["\\nCông cụ\\n", "\\nGemini là AI", "\\nCâu trả lời tốt"];
                            let endIdx = bodyText.length;

                            for (const marker of endMarkers) {
                                const idx = bodyText.indexOf(marker, startIdx);
                                if (idx !== -1 && idx < endIdx) {
                                    endIdx = idx;
                                }
                            }

                            return bodyText.substring(startIdx, endIdx).trim();
                        }
                    """)

                    if is_busy:
                        if i % 10 == 0:
                            print(f"[{engine}] Đang suy nghĩ... ({i}s)")
                        stable_count = 0
                        prev_text = current_response
                        continue

                    if current_response and len(current_response) >= min_success_chars:
                        has_content = True

                        if current_response == prev_text:
                            stable_count += 1
                            if stable_count >= 5:
                                print(f"[{engine}] ✓ Text ổn định sau {i}s ({len(current_response)} chars)")
                                break
                        else:
                            if i % 5 == 0:
                                print(f"[{engine}] Đang nhận response... ({len(current_response)} chars)")
                            stable_count = 0
                            prev_text = current_response
                    else:
                        if i % 10 == 0 and not has_content:
                            print(f"[{engine}] Chưa có response... ({i}s)")
                        stable_count = 0
                        prev_text = current_response

                response_text = prev_text if prev_text else ""

                if has_content and len(response_text.strip()) >= min_success_chars:
                    result["success"] = True
                    result["data"] = response_text.strip()
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

    common.finalize_worker_run(engine, TEMP_DIR, "gemini", timestamp, result, log_enabled)
    sys.exit(0 if result["success"] else 1)

if __name__ == "__main__":
    main()
