import contextlib
import io
import json
import os
import platform
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_BROWSER_ARGS = [
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-sync",
    "--no-first-run",
    "--profile-directory=Default",
    "--disable-gpu",
]


def configure_console():
    """Best-effort UTF-8 console cho Windows/Linux."""
    try:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    except Exception:
        pass


def parse_log_flag(value: str) -> bool:
    if value not in {"0", "1"}:
        raise ValueError("log_flag phải là '0' hoặc '1'")
    return value == "1"


def parse_worker_args(argv, script_name: str):
    """Parse args: query [timestamp|log_flag] [log_flag] or --setup [log_flag]."""
    if len(argv) < 2:
        raise ValueError(f'Usage: python {script_name} "<câu hỏi>" [timestamp] [log_flag]')

    command = argv[1]
    if command in {"--setup", "setup"}:
        log_enabled = True
        if len(argv) >= 3:
            log_enabled = parse_log_flag(argv[2])
        if len(argv) > 3:
            raise ValueError(f"Usage: python {script_name} --setup [log_flag]")
        return {
            "mode": "setup",
            "query": None,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "log_enabled": log_enabled,
        }

    query = command
    timestamp = None
    log_enabled = True

    if len(argv) >= 3:
        third_arg = argv[2]
        if third_arg in {"0", "1"} and len(argv) == 3:
            log_enabled = parse_log_flag(third_arg)
        else:
            timestamp = third_arg

    if len(argv) >= 4:
        log_enabled = parse_log_flag(argv[3])

    if len(argv) > 4:
        raise ValueError(f'Usage: python {script_name} "<câu hỏi>" [timestamp] [log_flag]')

    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return {
        "mode": "run",
        "query": query,
        "timestamp": timestamp,
        "log_enabled": log_enabled,
    }


def build_stdout_context(log_enabled: bool):
    if log_enabled:
        return contextlib.nullcontext()
    return contextlib.redirect_stdout(io.StringIO())


def ensure_dirs(*dirs: Path):
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)


def resolve_profile_dir(base_dir: Path, primary_name: str, legacy_names=None) -> Path:
    profiles_dir = base_dir / "profiles"
    primary_path = profiles_dir / primary_name
    if primary_path.exists():
        return primary_path

    for legacy_name in legacy_names or []:
        legacy_path = profiles_dir / legacy_name
        if legacy_path.exists():
            return legacy_path

    return primary_path


def clear_profile_lock(profile_path: Path):
    lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie", "LOCK"]
    for file_name in lock_files:
        lock_file = profile_path / file_name
        if lock_file.exists():
            try:
                lock_file.unlink()
            except Exception:
                pass


def load_storage_state(context, state_path: Path):
    if not state_path.exists():
        return
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return

    cookies = data.get("cookies", [])
    if cookies:
        try:
            context.add_cookies(cookies)
        except Exception:
            pass

    origins = data.get("origins", [])
    for origin in origins:
        url = origin.get("origin")
        items = origin.get("localStorage", [])
        if not url or not items:
            continue
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.evaluate(
                """(entries) => {
                    for (const entry of entries) {
                        localStorage.setItem(entry.name, entry.value);
                    }
                }""",
                items,
            )
        except Exception:
            pass
        finally:
            try:
                page.close()
            except Exception:
                pass


def save_storage_state(context, state_path: Path, engine: str):
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(state_path))
        print(f"[{engine}] ✓ Đã lưu storage_state: {state_path}")
    except Exception as exc:
        print(f"[{engine}] ✗ Lưu storage_state thất bại: {exc}")


def add_stealth_script(context):
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """
    )


def _candidate_browser_refs():
    env_exec = os.environ.get("AGENT_SEARCH_BROWSER_EXECUTABLE")
    if env_exec:
        env_path = Path(env_exec)
        if env_path.exists():
            yield {"executable_path": str(env_path)}, f"executable:{env_path}"

    system = platform.system()
    candidates = []
    if system == "Windows":
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        ]
    elif system == "Linux":
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
            Path("/snap/bin/chromium"),
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]

    for candidate in candidates:
        if candidate.exists():
            yield {"executable_path": str(candidate)}, f"executable:{candidate}"

    channel = os.environ.get("AGENT_SEARCH_BROWSER_CHANNEL", "chrome")
    if channel:
        yield {"channel": channel}, f"channel:{channel}"

    yield {}, "playwright-default"


def launch_persistent_context(playwright, profile_dir: Path, engine: str, storage_state_path: Path = None, timeout: int = 30000, extra_args=None):
    ensure_dirs(profile_dir)
    clear_profile_lock(profile_dir)
    args = list(DEFAULT_BROWSER_ARGS)
    if extra_args:
        args.extend(extra_args)

    last_error = None
    for browser_ref, browser_label in _candidate_browser_refs():
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                args=args,
                timeout=timeout,
                **browser_ref,
            )
            add_stealth_script(context)
            if storage_state_path is not None:
                load_storage_state(context, storage_state_path)
            print(f"[{engine}] ✓ Browser ready ({browser_label})")
            return context
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Không khởi động được browser cho {engine}: {last_error}")


def launch_browser(playwright, engine: str, timeout: int = 30000, extra_args=None):
    args = list(DEFAULT_BROWSER_ARGS)
    if extra_args:
        args.extend(extra_args)

    last_error = None
    for browser_ref, browser_label in _candidate_browser_refs():
        try:
            browser = playwright.chromium.launch(
                headless=False,
                args=args,
                timeout=timeout,
                **browser_ref,
            )
            print(f"[{engine}] ✓ Browser ready ({browser_label})")
            return browser
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Không khởi động được browser cho {engine}: {last_error}")


def detect_page_blockers(page, login_keywords=None, captcha_keywords=None, logout_keywords=None):
    payload = {
        "login_keywords": [k.lower() for k in (login_keywords or [])],
        "captcha_keywords": [k.lower() for k in (captcha_keywords or [])],
        "logout_keywords": [k.lower() for k in (logout_keywords or [])],
    }
    return page.evaluate(
        """(payload) => {
            const bodyText = (document.body.innerText || '').toLowerCase();
            const interactiveText = Array.from(document.querySelectorAll('button, a'))
                .map((el) => (el.innerText || '').toLowerCase().trim())
                .filter(Boolean)
                .join(' | ');

            const includesAny = (haystack, needles) => needles.some((needle) => haystack.includes(needle));

            return {
                hasCaptcha: includesAny(bodyText, payload.captcha_keywords),
                hasLoginPrompt: includesAny(bodyText, payload.login_keywords) || includesAny(interactiveText, payload.login_keywords),
                hasLogoutMarker: includesAny(bodyText, payload.logout_keywords),
            };
        }""",
        payload,
    )


def write_temp_file(temp_dir: Path, temp_prefix: str, engine: str, timestamp: str, result: dict):
    ensure_dirs(temp_dir)
    temp_file = temp_dir / f"{temp_prefix}_{timestamp}.txt"
    with open(temp_file, "w", encoding="utf-8") as handle:
        handle.write(f"[{engine}]\n")
        handle.write(f"Trạng thái: {'Thành công' if result['success'] else 'Thất bại'}\n")
        handle.write(f"Thời gian: {result['time']:.1f}s\n")
        handle.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        if result.get("data"):
            handle.write(f"\nKết quả:\n{result['data']}\n")
        else:
            handle.write(f"\nLỗi: {result.get('error')}\n")
    return temp_file


def finalize_worker_run(engine: str, temp_dir: Path, temp_prefix: str, timestamp: str, result: dict, log_enabled: bool):
    temp_file = write_temp_file(temp_dir, temp_prefix, engine, timestamp, result)
    if log_enabled:
        print(f"[{engine}] ✓ Đã lưu temp: {temp_file}")
        print(f"[{engine}] ✓ Hoàn thành ({result['time']:.1f}s)")
    else:
        if result.get("data"):
            print(result["data"])
        elif result.get("error"):
            print(f"[{engine}] {result['error']}")
    return temp_file


def interactive_profile_setup(playwright, engine: str, profile_dir: Path, storage_state_path: Path, start_url: str, timeout: int = 30000):
    ensure_dirs(profile_dir, storage_state_path.parent)
    context = launch_persistent_context(
        playwright,
        profile_dir=profile_dir,
        engine=engine,
        storage_state_path=storage_state_path,
        timeout=timeout,
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(timeout)
    page.goto(start_url, wait_until="domcontentloaded")
    page.bring_to_front()
    print(f"[{engine}] Đã mở trang setup: {start_url}")
    print(f"[{engine}] Hãy đăng nhập/tắt popup cần thiết trong cửa sổ browser này.")
    input(f"[{engine}] Nhấn Enter sau khi hoàn tất đăng nhập để lưu session... ")
    save_storage_state(context, storage_state_path, engine)
    context.close()
