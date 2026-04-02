# Agent-Search v6: New Machine Setup

File này chỉ dành cho setup lần đầu hoặc khi mang skill sang máy mới.

Không cần đọc file này mỗi lần dùng skill.

## Phạm Vi Hỗ Trợ

Skill này chỉ hỗ trợ:
- Windows có desktop GUI
- Linux có desktop GUI

Skill này không hỗ trợ:
- máy chỉ có terminal
- server headless
- VPS không có màn hình
- môi trường không mở được browser visible

## Điều Quan Trọng Nhất Về Đường Dẫn

Không cần sửa tay đường dẫn profile khi đổi chỗ folder.

Code đã tự resolve mọi path tương đối từ thư mục chứa worker:
- `profiles/`
- `output/`
- `storage_state`

Nghĩa là:
- cứ giữ `manager.py`, `fix-error.py`, `search_*.py` trong cùng một folder
- khi copy cả folder sang máy mới, path tự đúng theo folder mới
- profile luôn nằm trong `./profiles` cạnh các worker

Agent không nên hard-code path tuyệt đối.

## Checklist Agent Phải Check Trên Máy Mới

1. Máy có GUI thật không
2. Python có sẵn chưa
3. Chrome hoặc Chromium có sẵn chưa
4. `playwright` đã cài chưa
5. Browser runtime của Playwright đã cài chưa
6. Thư mục `profiles/` đã có session cũ chưa
7. Nếu user muốn chạy bằng `.venv`, agent đã tạo `.venv` và dùng đúng interpreter chưa

## Check Python

Windows:

```bash
python --version
```

Linux:

```bash
python3 --version
```

Nếu chưa có Python:
- Windows: cài Python 3 mới, nhớ bật PATH
- Linux: cài `python3` và `pip`

Ví dụ Windows có thể dùng:

```bash
winget install -e --id Python.Python.3.12
```

Ví dụ Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-pip
```

Nếu agent cài Python mới:
- chạy lại check version sau khi cài

## Check Chrome hoặc Chromium

Windows:

```bash
where chrome
```

Linux:

```bash
which google-chrome
which chromium
which chromium-browser
```

Nếu chưa có browser:
- Windows: cài Google Chrome
- Linux: cài Google Chrome hoặc Chromium bằng package manager phù hợp distro

Ví dụ Windows:

```bash
winget install -e --id Google.Chrome
```

Lưu ý:
- browser phải mở được cửa sổ thật
- không dùng headless cho skill này

## Cài Dependency Python

Mặc định skill này được viết theo kiểu dùng Python hệ thống.

### Cách mặc định: chạy thẳng bằng Python máy thật

Windows:

```bash
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Linux:

```bash
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

Nếu Linux thiếu dependency hệ thống cho browser:

```bash
python3 -m playwright install-deps chromium
```

### Nếu agent muốn dùng `.venv`

Chỉ làm khi policy hoặc môi trường của agent yêu cầu.

Windows:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```

Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

Nếu skill này sẽ được dùng lâu dài với `.venv`:
- agent phải dùng interpreter `.venv` cho tất cả lệnh sau đó
- agent phải cập nhật local workflow của skill cho đúng
- vì `SKILL.md` mặc định đang mô tả quy trình chạy thẳng bằng Python của máy thật

## Tạo Session Lần Đầu

Khi máy mới chưa có `profiles/` hoặc session cũ:

Windows:

```bash
python fix-error.py all
```

Linux (CHỈ DÙNG NOHUP, KHÔNG DÙNG fix-error.py):

⚠️ **Trên Linux, `fix-error.py` sẽ bị văng browser ngay vì process cha exit. Dùng `nohup` thay thế:**

```bash
# Mở cả 4 browser (ChatGPT, Gemini, DeepSeek, Qwen) cùng lúc:
nohup /usr/bin/google-chrome --user-data-dir=$PWD/profiles/chatgpt --profile-directory=Default --no-first-run --start-maximized --disable-gpu --disable-webgl --disable-software-rasterizer https://chatgpt.com/ > /dev/null 2>&1 &
nohup /usr/bin/google-chrome --user-data-dir=$PWD/profiles/gemini --profile-directory=Default --no-first-run --start-maximized --disable-gpu --disable-webgl --disable-software-rasterizer https://gemini.google.com/app > /dev/null 2>&1 &
nohup /usr/bin/google-chrome --user-data-dir=$PWD/profiles/deepseek --profile-directory=Default --no-first-run --start-maximized --disable-gpu --disable-webgl --disable-software-rasterizer https://chat.deepseek.com/ > /dev/null 2>&1 &
nohup /usr/bin/google-chrome --user-data-dir=$PWD/profiles/qwen --profile-directory=Default --no-first-run --start-maximized --disable-gpu --disable-webgl --disable-software-rasterizer https://chat.qwen.ai/ > /dev/null 2>&1 &
```

(Lưu ý: nếu Chrome ở đường dẫn khác, thay `/usr/bin/google-chrome` bằng `which google-chrome` hoặc `which chromium`)

Quy trình setup:
1. Dùng `nohup` command trên để mở 4 cửa sổ Chrome cho cả 4 profile
2. Mỗi cửa sổ vào thẳng đúng website tương ứng
3. Agent hoặc user đăng nhập vào từng dịch vụ trong đúng cửa sổ đó
4. Nếu có captcha, xử lý ngay trong browser tương ứng
5. Nếu có popup che ô chat, đóng nó
6. Không cần nhấn `Enter` trong terminal
7. Browser sẽ giữ mở cho tới khi user tự đóng cửa sổ
8. Script `nohup` đã exit, nhưng Chrome vẫn chạy độc lập
9. Đăng nhập xong ở cửa sổ nào thì tự đóng cửa sổ đó

Sau setup, nên kiểm tra:
- `profiles/chatgpt`
- `profiles/gemini`
- `profiles/deepseek`
- `profiles/qwen`
- các file `*_storage_state.json`

## Smoke Test Sau Setup

Windows:

```bash
python manager.py "test" 1
```

Linux:

```bash
python3 manager.py "test" 1
```

Nếu muốn ít log:

```bash
python manager.py "test" 0
python3 manager.py "test" 0
```

## Khi Nào Phải Chạy Setup Lại

- máy mới hoàn toàn
- `profiles/` chưa có
- session hết hạn
- worker báo chưa đăng nhập
- worker bị captcha và chưa lưu lại session mới
- user xóa profile hoặc storage state

## Sửa Lỗi Login hoặc Captcha Sau Này

Không phải lúc nào cũng cần mở lại cả 4 profile.

Nếu chỉ một worker bị lỗi:
- mở đúng profile của worker đó
- để user sửa tay
- khi sửa xong, user tự đóng browser
- chạy lại manager

Windows:

```bash
python fix-error.py chatgpt
python fix-error.py gemini
python fix-error.py deepseek
python fix-error.py qwen
python fix-error.py all
```

Linux (DÙNG NOHUP, KHÔNG DÙNG fix-error.py):
⚠️ **`fix-error.py` có thể bị văng browser trên Linux. Dùng `nohup` cho từng profile:**

```bash
# Mở từng cái cần sửa:
nohup /usr/bin/google-chrome --user-data-dir=$HOME/.openclaw/workspace/skills/agent-Ai-search/profiles/chatgpt --profile-directory=Default --disable-gpu https://chatgpt.com/ > /dev/null 2>&1 &
nohup /usr/bin/google-chrome --user-data-dir=$HOME/.openclaw/workspace/skills/agent-Ai-search/profiles/gemini --profile-directory=Default --disable-gpu https://gemini.google.com/app > /dev/null 2>&1 &
nohup /usr/bin/google-chrome --user-data-dir=$HOME/.openclaw/workspace/skills/agent-Ai-search/profiles/deepseek --profile-directory=Default --disable-gpu https://chat.deepseek.com/ > /dev/null 2>&1 &
nohup /usr/bin/google-chrome --user-data-dir=$HOME/.openclaw/workspace/skills/agent-Ai-search/profiles/qwen --profile-directory=Default --disable-gpu https://chat.qwen.ai/ > /dev/null 2>&1 &
```

Lưu ý:
- `fix-error.py` hoạt động như launcher (mở Chrome xong exit) — tốt trên Windows
- Trên Linux, browser sẽ bị kill theo parent process → **dùng `nohup` thay thế**
- Browser sẽ giữ mở cho tới khi user tự đóng cửa sổ
- Không dùng bước nhấn `Enter` trong terminal

## Lưu Ý GitHub

Có thể đẩy folder skill lên GitHub, nhưng không nên đẩy:
- `profiles/`
- `output/`
- `__pycache__/`

`.gitignore` đã chặn các thư mục này.

## Tóm Tắt Ngắn Cho Agent

Nếu máy mới:
1. check GUI
2. check Python
3. check Chrome/Chromium
4. cài dependency
5. chạy `fix-error.py all`
6. đăng nhập từng profile
7. chạy smoke test
8. sau đó mới dùng skill bình thường
