"""
Manager Script - Điều phối 4 AI workers song song.

Usage:
    python manager.py "<câu hỏi>" [log_flag]
    python manager.py "<câu hỏi>" [timestamp] [log_flag]
    python manager.py --setup [log_flag]
"""

import io
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import worker_common as common


common.configure_console()

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = OUTPUT_DIR / "temp"
FIX_SCRIPT = BASE_DIR / "fix-error.py"

WORKER_TIMEOUT = 360

WORKERS = [
    {"name": "ChatGPT", "script": "search_chatgpt.py", "temp_prefix": "chatgpt", "fix_target": "chatgpt"},
    {"name": "Gemini", "script": "search_gemini.py", "temp_prefix": "gemini", "fix_target": "gemini"},
    {"name": "DeepSeek", "script": "search_deepseek.py", "temp_prefix": "deepseek", "fix_target": "deepseek"},
    {"name": "Qwen", "script": "search_qwen.py", "temp_prefix": "qwen", "fix_target": "qwen"},
]


def parse_manager_args(argv):
    if len(argv) < 2:
        raise ValueError('Usage: python manager.py "<câu hỏi>" [timestamp] [log_flag] | --setup [log_flag]')

    command = argv[1]
    if command in {"--setup", "setup"}:
        log_enabled = True
        if len(argv) >= 3:
            log_enabled = common.parse_log_flag(argv[2])
        if len(argv) > 3:
            raise ValueError("Usage: python manager.py --setup [log_flag]")
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
            log_enabled = common.parse_log_flag(third_arg)
        else:
            timestamp = third_arg

    if len(argv) >= 4:
        log_enabled = common.parse_log_flag(argv[3])

    if len(argv) > 4:
        raise ValueError('Usage: python manager.py "<câu hỏi>" [timestamp] [log_flag] | --setup [log_flag]')

    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return {
        "mode": "run",
        "query": query,
        "timestamp": timestamp,
        "log_enabled": log_enabled,
    }


def run_setup(log_enabled: bool):
    common.ensure_dirs(OUTPUT_DIR, TEMP_DIR)
    if log_enabled:
        print("=" * 80)
        print("AGENT-SEARCH SETUP")
        print("=" * 80)
        print("Chế độ này sẽ mở từng worker bằng profile riêng để đăng nhập lần đầu.")
        print("Sau mỗi worker, nhấn Enter trong terminal để lưu session rồi chuyển worker tiếp theo.")
        print("=" * 80)

    for worker in WORKERS:
        script_path = BASE_DIR / worker["script"]
        cmd = [sys.executable, str(script_path), "--setup", "1" if log_enabled else "0"]
        if log_enabled:
            print(f"\n[MANAGER] Setup {worker['name']} -> {script_path.name}")
        result = subprocess.run(cmd, cwd=str(BASE_DIR))
        if result.returncode != 0:
            raise RuntimeError(f"Setup {worker['name']} thất bại (exit code: {result.returncode})")

    if log_enabled:
        print("\n[MANAGER] ✓ Hoàn tất setup tất cả profile.")


def run_worker(worker_info, query, timestamp, log_enabled, status_map, lock):
    name = worker_info["name"]
    script_path = BASE_DIR / worker_info["script"]
    cmd = [sys.executable, str(script_path), query, timestamp, "1" if log_enabled else "0"]

    record = {
        "name": name,
        "script": str(script_path),
        "returncode": None,
        "ok": False,
        "timed_out": False,
        "stdout": "",
        "error": None,
    }

    if not script_path.exists():
        record["error"] = f"Không tìm thấy script: {script_path.name}"
        with lock:
            status_map[name] = record
        return

    try:
        syntax_check = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
        )
        if syntax_check.returncode != 0:
            record["error"] = f"Syntax error:\n{syntax_check.stderr.strip()}"
            with lock:
                status_map[name] = record
            return

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            cwd=str(BASE_DIR),
        )

        try:
            stdout, _ = process.communicate(timeout=WORKER_TIMEOUT)
        except subprocess.TimeoutExpired:
            record["timed_out"] = True
            process.terminate()
            try:
                stdout, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, _ = process.communicate()
            record["error"] = f"Timeout sau {WORKER_TIMEOUT}s"
        else:
            record["returncode"] = process.returncode
            record["ok"] = process.returncode == 0

        record["stdout"] = (stdout or "").strip()
        if record["returncode"] is None:
            record["returncode"] = process.returncode
            record["ok"] = process.returncode == 0

    except Exception as exc:
        record["error"] = str(exc)

    with lock:
        status_map[name] = record


def build_fix_command(target: str) -> str:
    return f'"{sys.executable}" "{FIX_SCRIPT}" {target}'


def classify_failure(worker, status) -> str:
    text = " ".join(
        [
            str(status.get("error") or ""),
            str(status.get("stdout") or ""),
        ]
    ).lower()

    login_keywords = [
        "chưa đăng nhập",
        "đăng nhập",
        "login",
        "log in",
        "sign in",
        "signed out",
        "captcha",
        "verify",
    ]

    if any(keyword in text for keyword in login_keywords):
        return (
            "Nghi lỗi session/login/captcha. "
            f"Mở profile để sửa tay: {build_fix_command(worker['fix_target'])}"
        )

    if status.get("timed_out"):
        return (
            "Worker bị timeout. Nếu nghi UI đang kẹt, mở profile kiểm tra: "
            f"{build_fix_command(worker['fix_target'])}"
        )

    return f"Nếu cần kiểm tra thủ công, mở profile này bằng: {build_fix_command(worker['fix_target'])}"


def merge_results(query, timestamp, worker_status):
    common.ensure_dirs(OUTPUT_DIR, TEMP_DIR)
    result_file = OUTPUT_DIR / f"result_{timestamp}.txt"

    success_count = 0
    lines = []
    lines.append("=" * 80)
    lines.append("AI PARALLEL SEARCH RESULT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Câu hỏi: {query}")
    lines.append(f"Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for worker in WORKERS:
        status = worker_status.get(worker["name"], {})
        if status.get("ok"):
            success_count += 1

    lines.append(f"Thành công: {success_count}/{len(WORKERS)} engines")
    lines.append("")
    lines.append("=" * 80)
    lines.append("")

    for worker in WORKERS:
        name = worker["name"]
        temp_file = TEMP_DIR / f"{worker['temp_prefix']}_{timestamp}.txt"
        status = worker_status.get(name, {})

        lines.append(f"[{name}]")
        lines.append("-" * 40)

        if temp_file.exists():
            try:
                lines.append(temp_file.read_text(encoding="utf-8").rstrip())
            except Exception as exc:
                lines.append(f"Lỗi đọc file temp: {exc}")
            if not status.get("ok"):
                lines.append("")
                lines.append(f"Gợi ý fix: {classify_failure(worker, status)}")
        else:
            lines.append("Trạng thái: Thất bại")
            if status.get("timed_out"):
                lines.append(f"Lỗi: Timeout sau {WORKER_TIMEOUT}s")
            elif status.get("error"):
                lines.append(f"Lỗi: {status['error']}")
            elif status.get("returncode") is not None:
                lines.append(f"Lỗi: Worker exit code {status['returncode']}")
            else:
                lines.append("Lỗi: Worker không tạo được file temp")

            stdout = status.get("stdout", "").strip()
            if stdout:
                lines.append("")
                lines.append("Log cuối:")
                lines.extend(stdout.splitlines()[-20:])

            lines.append("")
            lines.append(f"Gợi ý fix: {classify_failure(worker, status)}")

        lines.append("")
        lines.append("=" * 80)
        lines.append("")

    result_file.write_text("\n".join(lines), encoding="utf-8")
    return result_file


def print_summary(log_enabled: bool, query: str, timestamp: str, result_file: Path, worker_status):
    if log_enabled:
        print("\n" + "=" * 80)
        print("KẾT THÚC QUY TRÌNH")
        print("=" * 80)
        failed_workers = []
        for worker in WORKERS:
            status = worker_status.get(worker["name"], {})
            label = "OK" if status.get("ok") else "FAIL"
            reason = ""
            if status.get("timed_out"):
                reason = " (timeout)"
            elif status.get("error"):
                reason = f" ({status['error']})"
            elif status.get("returncode") not in (None, 0):
                reason = f" (exit code {status['returncode']})"
            print(f"{worker['name']}: {label}{reason}")
            if not status.get("ok"):
                failed_workers.append(worker)
        print(f"\nResult file: {result_file}")
        if failed_workers:
            print("\nGợi ý fix nhanh:")
            for worker in failed_workers:
                status = worker_status.get(worker["name"], {})
                print(f"- {worker['name']}: {classify_failure(worker, status)}")
            print(f'- Mở menu sửa lỗi: {build_fix_command("menu")}')
        print("=" * 80)
    else:
        print(result_file.read_text(encoding="utf-8"))


def main():
    try:
        args = parse_manager_args(sys.argv)
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)

    log_enabled = args["log_enabled"]

    if args["mode"] == "setup":
        run_setup(log_enabled)
        return

    query = args["query"]
    timestamp = args["timestamp"]

    common.ensure_dirs(OUTPUT_DIR, TEMP_DIR)

    if log_enabled:
        print("=" * 80)
        print("AI PARALLEL SEARCH MANAGER")
        print("=" * 80)
        print(f"Câu hỏi: {query}")
        print(f"Timestamp: {timestamp}")
        print("=" * 80)

    threads = []
    worker_status = {}
    lock = threading.Lock()

    for worker in WORKERS:
        thread = threading.Thread(
            target=run_worker,
            args=(worker, query, timestamp, log_enabled, worker_status, lock),
            daemon=True,
        )
        thread.start()
        threads.append((worker["name"], thread))
        if log_enabled:
            print(f"[MANAGER] Khởi động {worker['name']}...")

    for name, thread in threads:
        thread.join()
        status = worker_status.get(name, {})
        if log_enabled:
            print(f"[MANAGER] {name} xong: {'OK' if status.get('ok') else 'FAIL'}")
            stdout = status.get("stdout", "").strip()
            if stdout:
                for line in stdout.splitlines():
                    text = line.strip()
                    if text:
                        print(f"  [{name}] {text}")

    result_file = merge_results(query, timestamp, worker_status)
    print_summary(log_enabled, query, timestamp, result_file, worker_status)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[MANAGER] Người dùng hủy thao tác.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[MANAGER] Lỗi không mong muốn: {exc}")
        sys.exit(1)
