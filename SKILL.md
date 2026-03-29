# Agent-Search v6

Skill này dùng để hỏi nhiều web AI song song qua `manager.py` rồi gom kết quả vào một file.

Chỉ dùng trên máy có giao diện desktop thật:
- hỗ trợ Windows hoặc Linux có màn hình và mở được browser
- không hỗ trợ máy chỉ có terminal, headless server, VPS không GUI

## Preflight Ngắn

Trước khi chạy skill, agent phải check nhanh:
1. Có phiên desktop đang mở và browser có thể hiện cửa sổ thật
2. Có Python chạy được
3. Có Chrome hoặc Chromium
4. Trong thư mục skill có đủ `manager.py`, `worker_common.py`, `search_*.py`
5. Có `profiles/` và session cũ hay chưa

Nếu thiếu Python, thiếu browser, thiếu `profiles/`, hoặc đây là máy mới:
- dừng quy trình dùng thường ngày
- mở `readme-for-new-setup.md` và làm theo setup lần đầu

Nếu worker chạy xong mà lỗi login/captcha/session:
- báo rõ worker nào lỗi
- mở profile đúng worker đó để user sửa tay
- ưu tiên dùng `fix-error.py`

## Quy Tắc Đường Dẫn

Không hard-code path tuyệt đối.

Code hiện tại đã tự bám theo thư mục chứa file worker:
- `profiles/`
- `output/`
- `storage_state`

Nghĩa là:
- nếu copy cả folder skill sang máy khác hoặc chỗ khác, path tự đi theo folder mới
- không cần sửa tay đường dẫn profile trong code chỉ vì đổi chỗ đặt folder
- profile luôn nằm cùng thư mục với worker để bundle dễ mang đi

## Chạy Bình Thường

Windows:

```bash
python manager.py "Câu hỏi của bạn" 1
python manager.py "Câu hỏi của bạn" 0
```

Linux:

```bash
python3 manager.py "Câu hỏi của bạn" 1
python3 manager.py "Câu hỏi của bạn" 0
```

Ý nghĩa:
- `1` = hiện log
- `0` = im lặng, chỉ in kết quả cuối

Setup hoặc login lại khi cần:

```bash
python manager.py --setup 1
python3 manager.py --setup 1
```

Quy tắc setup lần đầu:
- `manager.py --setup 1` sẽ mở cả 4 browser/profile cùng lúc, không mở tuần tự
- mỗi cửa sổ sẽ vào thẳng đúng website tương ứng để user dễ phân biệt
- không cần nhấn Enter trong terminal
- script không tự đóng browser ở chế độ setup
- user đăng nhập xong ở cửa sổ nào thì chờ 2-3 giây rồi tự đóng cửa sổ đó
- khi cả 4 cửa sổ đã đóng hết thì setup mới xem như hoàn tất

## Soạn Câu Hỏi Trước Khi Chạy

Agent không được đẩy nguyên câu hỏi ngắn, mơ hồ, hoặc thiếu ngữ cảnh của user vào web AI nếu trong cuộc trò chuyện hiện tại đã có thêm bối cảnh.

Nguyên tắc:
- web worker chỉ nhìn thấy đúng chuỗi query cuối cùng, không đọc được lịch sử chat
- vì vậy agent phải tự gom ngữ cảnh liên quan từ cuộc trò chuyện hiện tại trước khi chạy `manager.py`
- chỉ dùng thông tin thực sự có trong chat, file, log, hoặc bối cảnh đang mở
- không tự bịa thêm chi tiết mà user chưa nói
- nếu user đã viết câu hỏi rất rõ rồi thì giữ nguyên ý, chỉ làm nó đầy đủ hơn nếu cần

Khi câu hỏi còn thiếu ngữ cảnh, agent nên tự viết lại query theo mẫu sau và bỏ qua dòng nào không có dữ liệu:

```text
Context: [hệ thống, môi trường, stack, phiên bản, file liên quan]
Problem: [vấn đề cụ thể hoặc lỗi đang gặp]
Tried: [những gì đã thử và kết quả hiện tại]
Current state: [đang bị kẹt ở đâu]
Question: [điều cụ thể cần web AI trả lời]
Goal: [kết quả mong đợi]
```

Quy tắc dùng mẫu:
- có gì thì điền nấy, không có thì bỏ qua hẳn dòng đó
- luôn giữ `Question:` rõ ràng và cụ thể
- nếu đang debug code, nên nhắc đúng file, hành vi hiện tại, hành vi mong muốn
- nếu user hỏi quá ngắn kiểu "lỗi này là gì", "sửa sao", "vì sao không chạy", agent phải tự bổ sung phần `Context`, `Problem`, `Tried`, `Current state`
- nếu có log lỗi, selector, model name, website name, OS, browser, phiên bản Python, agent nên đưa vào query

Mục tiêu:
- để cả 4 web AI đều nhìn thấy cùng một brief đầy đủ
- giảm câu trả lời lan man
- tăng khả năng bám đúng vấn đề thật của user

## Đọc File Kết Quả Và Trả Lời User

Sau khi `manager.py` chạy xong, agent phải đọc file tổng hợp trong `output/result_<timestamp>.txt` rồi mới trả lời user.

Không được chỉ nói chung chung kiểu "mình đã hỏi 4 AI". Agent phải tổng hợp lại thành một câu trả lời có cấu trúc.

Khung trả lời ưu tiên:

```text
Tóm tắt chi tiết

Quan điểm từng AI
- ChatGPT: ...
- Gemini: ...
- DeepSeek: ...
- Qwen: ...

Link dẫn chứng
- URL 1
- URL 2

Điểm chung kết quả của từng AI

Đánh giá của Agent

Đề xuất của Agent sau khi tổng hợp thông tin

Kiểm tra lỗi worker
```

Quy tắc tổng hợp:
- `Tóm tắt chi tiết`: viết lại ý chính dễ hiểu, bám đúng câu hỏi gốc của user
- `Quan điểm từng AI`: nêu ngắn gọn lập luận hoặc kết luận riêng của từng worker
- `Link dẫn chứng`: nếu trong output có URL thì trích nguyên văn URL ra; nếu không có thì ghi rõ là không thấy link rõ ràng trong output
- `Điểm chung kết quả của từng AI`: nêu phần giao nhau đáng tin nhất
- `Đánh giá của Agent`: nói rõ AI nào đáng tin hơn, AI nào có dấu hiệu suy đoán, thiếu căn cứ, hoặc lạc đề, và vì sao
- `Đề xuất của Agent`: đưa ra kết luận hoặc hướng hành động cuối cùng sau khi cân nhắc tất cả nguồn
- `Kiểm tra lỗi worker`: ghi rõ worker nào thành công, worker nào lỗi login/captcha/session/timeout nếu có

Nếu có xung đột giữa các AI:
- agent phải chỉ ra chỗ mâu thuẫn
- ưu tiên ý nào có dẫn chứng, lý lẽ cụ thể, hoặc bám sát context của user hơn
- không được giả vờ rằng tất cả đều đồng ý nếu thực tế đang mâu thuẫn

Nếu có worker lỗi:
- vẫn trả lời dựa trên các worker còn chạy được
- nhưng phải nói rõ worker nào bị lỗi
- nếu lỗi liên quan login/captcha/session thì đề xuất dùng `fix-error.py`

## Fix Lỗi Nhanh

Nếu worker fail sau khi chạy:
1. đọc summary hoặc `output/result_<timestamp>.txt`
2. xác định worker nào lỗi
3. mở profile đúng worker đó
4. để user đăng nhập lại hoặc vượt captcha
5. `fix-error.py` chỉ có nhiệm vụ mở đúng browser/profile rồi tự kết thúc lệnh
6. khi sửa xong, user tự đóng cửa sổ browser đó
7. chạy lại `manager.py`

Lệnh nhanh từng worker:

Windows:

```bash
python fix-error.py chatgpt
python fix-error.py gemini
python fix-error.py deepseek
python fix-error.py qwen
python fix-error.py all
```

Linux:

```bash
python3 fix-error.py chatgpt
python3 fix-error.py gemini
python3 fix-error.py deepseek
python3 fix-error.py qwen
python3 fix-error.py all
```

Nếu user nói:
- "mở ChatGPT lên để kiểm tra" -> chạy `fix-error.py chatgpt`
- "mở Gemini lên để kiểm tra" -> chạy `fix-error.py gemini`
- "mở DeepSeek lên để kiểm tra" -> chạy `fix-error.py deepseek`
- "mở Qwen lên để kiểm tra" -> chạy `fix-error.py qwen`
- "mở hết lên để tôi đăng nhập lại" -> chạy `fix-error.py all`

Nếu agent cần menu tương tác 5 lựa chọn:

```bash
python fix-error.py
python3 fix-error.py
```

Lưu ý:
- `fix-error.py chatgpt|gemini|deepseek|qwen|all` không cần nhập thêm trong terminal
- `fix-error.py` chỉ là launcher, mở xong browser/profile là lệnh kết thúc ngay
- browser vẫn giữ mở để user tự đăng nhập hoặc vượt captcha
- user chỉ cần tự đóng browser khi sửa xong

## Worker Common Làm Gì

`worker_common.py` là lõi dùng chung cho các worker:
- parse args và log `0/1`
- tạo thư mục cần thiết
- launch browser helper
- load/save `storage_state`
- detect login prompt, logout, captcha
- ghi temp file và finalize output

Mỗi worker riêng chỉ nên giữ:
- selector/UI của site đó
- chọn model/mode
- nhập prompt
- scrape response

## Nếu Dùng `.venv`

Mặc định skill này viết theo kiểu chạy thẳng bằng Python của máy thật.

Nếu agent quyết định cài trong `.venv`:
- agent phải tự tạo `.venv`
- tự cài dependency trong `.venv`
- tự dùng interpreter của `.venv` cho mọi lệnh chạy skill
- nếu deployment này sẽ dùng lâu dài, agent phải cập nhật local workflow hoặc ghi chú rõ rằng skill này đang chạy bằng `.venv`, không phải system Python

Chi tiết lần đầu và checklist cài đặt:
- xem `readme-for-new-setup.md`
