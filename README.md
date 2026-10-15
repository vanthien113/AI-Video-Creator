# AI Video Creator

Gửi một link sản phẩm TikTok Shop từ điện thoại, nhận lại clip quảng cáo dọc 9:16, 2K 60fps, có người mẫu dùng sản phẩm và câu hook mở đầu. Mọi bước xử lý ảnh và video chạy trên máy Mac; chỉ phần viết prompt (Claude Code) và sinh video (Google Flow) dùng dịch vụ bên ngoài.

## Luồng xử lý

```
Telegram / giao diện ─▶ Đọc TikTok ─▶ Chọn ảnh ─▶ Tách nền + upscale ─▶ Claude viết prompt
      ─▶ Google Flow (Agent) ─▶ Tải video ─▶ 60fps + 2K ─▶ Xuất file ─▶ Trả về Telegram
```

1. **Nhận đầu vào.** Gửi link TikTok Shop cho bot Telegram, hoặc dán link / kéo ảnh vào giao diện `http://127.0.0.1:8765`.
2. **Đọc trang sản phẩm** trong Chrome riêng của tool: lấy tên, mô tả và toàn bộ ảnh sản phẩm.
3. **Chọn ảnh** trên giao diện: 1 đến 3 ảnh cho một video. Ảnh bấm đầu tiên là ảnh chính; các ảnh sau (góc khác, người mẫu mang thử...) đi kèm làm tham khảo.
4. **Tách nền và upscale** ảnh chính (rembg BiRefNet, Real-ESRGAN lên 2K). *Điểm duyệt 1.*
5. **Viết prompt** bằng Claude Code (`claude -p`) từ các ảnh, thông tin sản phẩm và quy tắc trong `ad-rules.md`: câu hook tiếng Việt ở 2 giây đầu, người mẫu dùng sản phẩm, 2–3 góc quay. *Điểm duyệt 2.*
6. **Sinh video trên Google Flow, chế độ Agent:** tool tạo dự án mới, đặt Agent luôn hỏi trước khi sinh, tải ảnh làm nguyên liệu, gửi yêu cầu kèm mô hình, tỉ lệ, độ phân giải, thời lượng. Agent hỏi lại "… costing 15 credits?": tool đọc số credit, chỉ bấm **Approve** khi không vượt `flow.max_credits`, ngược lại bấm **Reject**.
7. **Tải video** bản gốc 720p về. *Điểm duyệt 3.*
8. **Nâng chất lượng:** nội suy lên 60fps (RIFE), phóng to 2K, mã hoá HEVC.
9. **Xuất file** `{tên}_{ngày-giờ}_2k60.mp4` vào thư mục xuất (mặc định `~/Movies/AI-Video-Creator`).
10. **Trả về Telegram**, ngay dưới tin gửi link: video 1080p xem nhanh, file 2K gốc, rồi một tin chỉ có tên sản phẩm để copy.
11. *(Tuỳ chọn, đang tắt)* **Lưu nháp TikTok Studio:** tải video lên, mô tả là tên sản phẩm, bật nhãn "AI-generated content", bấm **Save draft**. Không bao giờ bấm Post.

Job từ link Telegram chạy thẳng không dừng sau khi chọn ảnh. Job tạo trên giao diện dừng ở 3 điểm duyệt, mỗi điểm có ô "tự động chạy tiếp".

## Điểm mạnh

- **Từ điện thoại tới video hoàn chỉnh:** chia sẻ link từ app TikTok sang Telegram là đủ; video và tên sản phẩm được gửi về đúng cuộc trò chuyện đó.
- **Kiểm soát credit:** Agent của Flow luôn phải hỏi duyệt; tool đọc kế hoạch và từ chối nếu số credit vượt mức cho phép hoặc không rõ. Tool không bao giờ tự gửi lại lên Flow lần hai: lỗi giữa chừng thì dừng để bạn kiểm tra.
- **Prompt theo hướng dẫn nội dung TikTok Shop:** có người dùng sản phẩm, nhiều góc quay, lời nói tiếng Việt, câu hook mở đầu; cấm chữ, watermark, giá tiền. Quy tắc nằm trong `ad-rules.md`, sửa được mà không cần code.
- **Giữ đúng sản phẩm:** ảnh chính được tách nền và upscale; tối đa 3 ảnh làm nguyên liệu; yêu cầu Agent chỉ dùng ảnh làm tham khảo chứ không làm khung hình đầu.
- **Xử lý tại máy:** tách nền, upscale, nội suy khung hình và mã hoá đều chạy cục bộ trên Apple Silicon; không tải ảnh sản phẩm lên dịch vụ xử lý nào khác.
- **An toàn với dữ liệu lạ:** Claude chạy không có công cụ nào (không đọc được file trên máy); chữ lấy từ trang TikTok luôn được coi là không tin cậy. Token và ID Telegram chỉ nằm trong `.env`, không lên git.
- **Chịu được khi giao diện đổi:** cách tìm nút trên Flow và TikTok Studio nằm trong `flow-selectors.yaml` / `tiktok-selectors.yaml`; lệnh kiểm tra chạy mọi thao tác trừ bước tốn credit. Mỗi lỗi lưu kèm ảnh chụp màn hình và HTML.
- **Thử lại không trùng lặp:** mỗi bước ghi lại những gì đã làm; bấm **Thử lại** không gửi trùng tin Telegram, không tạo bản nháp TikTok thứ hai.
- **Có kiểm thử:** bộ test pytest cho pipeline, API, Telegram, các quy tắc duyệt credit và chọn ảnh.

## Cài đặt (một lần)

Cần: macOS Apple Silicon, Homebrew `python@3.13`, `ffmpeg`, Node.js, Google Chrome, Claude Code đã đăng nhập.

```bash
./scripts/setup.sh
```

Script tạo `.venv`, tải Real-ESRGAN, RIFE, mô hình tách nền (khoảng 1.2GB), build giao diện và chạy thử công cụ xử lý ảnh/video.

## Dùng hằng ngày

```bash
./scripts/start.sh        # mở http://127.0.0.1:8765
```

1. Lần đầu: bấm **Mở Chrome cho Flow**, đăng nhập Google (tài khoản có gói AI Pro/Ultra) trong cửa sổ Chrome đó. Hồ sơ lưu ở `chrome-profile/` (không lên git), các lần sau không phải đăng nhập lại. Có thể thu nhỏ cửa sổ này; nếu lỡ đóng hết cửa sổ, tool tự mở lại khi cần.
2. Kéo ảnh sản phẩm vào khung bên trái, thêm ghi chú nếu muốn, chọn các ô tự động, bấm **Bắt đầu**.
3. Duyệt ở từng điểm dừng. Video thành phẩm nằm trong `paths.export_dir`.

## Gửi link TikTok Shop từ điện thoại (Telegram)

Cài một lần:
1. Trên Telegram, nhắn [@BotFather](https://t.me/BotFather), gõ `/newbot`, đặt tên, nhận token.
2. Chép `.env.example` thành `.env`, điền `TELEGRAM_BOT_TOKEN=<token>`, khởi động lại tool.
3. Nhắn `/start` cho bot của bạn, bot trả lời ID Telegram của bạn. Điền vào `.env`: `TELEGRAM_ALLOWED_USER_IDS=<ID>` (nhiều ID cách nhau bằng dấu phẩy), rồi khởi động lại tool.
4. Thanh trên cùng hiện **"Telegram đang nghe"** là xong. Từ giờ trong app TikTok, bấm Chia sẻ, chọn Telegram, gửi cho bot của bạn.

Bot chỉ nhận link từ những ID đã khai báo. Sau khi nhận link, tool đọc trang rồi chờ bạn **chọn ảnh trên giao diện**; chọn xong, tool tự chạy đến khi xuất video.

Khi video xong, bot **trả lời ngay dưới tin bạn gửi link**, theo thứ tự:
- video 1080p xem ngay, kèm tên sản phẩm, link và tên file đã xuất trên Mac;
- file 2K 60fps gốc dạng tệp đính kèm nếu không quá 50MB (2K 10 giây khoảng 30MB). Vượt quá thì bot gửi một dòng cho biết file nằm ở đâu trên Mac, vì Telegram giới hạn bot gửi file tối đa 50MB;
- một tin chỉ có tên sản phẩm, để bấm giữ là copy được.

Nếu gửi lỗi (mất mạng...), video vẫn đã xuất trên Mac; bấm **Thử lại** ở bước "Gửi Telegram" để gửi lại phần còn thiếu.

Khi không có điện thoại bên cạnh, dán link vào ô **"Hoặc dán link sản phẩm TikTok Shop"** trên giao diện: tool chạy giống hệt, chỉ là không có tin nhắn Telegram trả về (vì không có tin nào để trả lời).

Kiểm tra xem tool có đọc được một link hay không (không tạo job):

```bash
cd backend && ../.venv/bin/python -m app.sources.check_product_page "<link TikTok Shop>"
```

**Mạng chặn TikTok** (ví dụ tường lửa công ty): bước "Đọc TikTok" sẽ báo "Mạng hiện tại đang chặn TikTok". Khi đó bấm **"Dùng ảnh của tôi"** để tự tải ảnh lên, các bước sau vẫn chạy bình thường.

## Lưu nháp TikTok (tuỳ chọn)

Đang tắt. Bật bằng `tiktok.save_draft: true` trong `config.yaml`, rồi đăng nhập TikTok trong cửa sổ Chrome của tool bằng tài khoản dùng để đăng video.

- Bản nháp tạo trên TikTok Studio web chỉ xem được trên máy tính (`tiktok.com/tiktokstudio/content?tab=draft`), không hiện trong mục nháp của app điện thoại.
- Tin báo "Đã lưu nháp" trả lời dưới tin gửi link nếu job tạo từ bot; job tạo trên giao diện thì nhắn cho ID đầu tiên đã khai báo.
- TikTok chạy "Content check lite" khoảng 10 phút sau khi tải lên. Tool không chờ: khi TikTok hỏi "Save draft? The copyright check is still running", tool chọn **Save anyway** (việc kiểm tra đó dừng lại). Mở bản nháp xem kỹ trước khi đăng.
- Bấm **Thử lại** ở bước này sau khi lưu nháp xong chỉ nhắn lại Telegram, không tạo bản nháp thứ hai. Chạy lại từ bước trước "Xuất file" thì video mới sẽ có bản nháp mới.

## Tuỳ chỉnh

| File | Dùng để |
|---|---|
| `config.yaml` | Thư mục xuất, mô hình Flow, tỉ lệ khung hình, độ phân giải và thời lượng, số video mỗi lượt, số ảnh tối đa, mức credit tối đa, chất lượng tải, fps/độ phân giải xuất, mặc định các ô tự động, Telegram, lưu nháp TikTok |
| `.env` | Token bot và ID Telegram được phép (bí mật, không đưa lên git; mẫu ở `.env.example`) |
| `ad-rules.md` | Quy tắc viết prompt quảng cáo (gửi nguyên văn cho Claude) |
| `flow-selectors.yaml` | Cách tìm nút bấm trên Flow. Google đổi giao diện thì sửa ở đây |
| `tiktok-selectors.yaml` | Cách tìm nút bấm trên TikTok Studio. TikTok đổi giao diện thì sửa ở đây |

Sửa `config.yaml` hoặc `.env` xong phải khởi động lại tool.

## Khi Flow đổi giao diện

```bash
cd backend && ../.venv/bin/python -m app.flow.check_selectors --project <URL dự án Flow để thử>
```

Lệnh chạy mọi thao tác **trừ** gửi prompt cho Agent (không tốn credit) và báo bước nào hỏng. Sửa mục tương ứng trong `flow-selectors.yaml`.

Trong lúc chờ sửa, khi bước Flow lỗi bạn vẫn có thể tự sinh video trên Flow, tải về rồi bấm **Tải video lên thủ công**. Tool chạy tiếp phần nâng 60fps và xuất file.

## Chi phí và thời gian (đo ngày 2026-10-15)

| Mô hình (9:16, ×1) | Credit mỗi video |
|---|---|
| Veo 3.1 - Lite / Fast / Quality (720p, 8s) | 10 / 20 / 100 |
| Omni 1.1 Flash 720p, 4/6/8/10s | 7 / 10 / 12 / 15 |

Từ lúc chọn ảnh đến khi nhận video trên Telegram khoảng 8 phút (một job đo ngày 2026-10-15, chưa tính thời gian duyệt): tách nền ~20s, upscale ~20s, prompt ~25s, Flow ~4,5 phút (có lúc phải xếp hàng), tải video ~1 phút, nâng 60fps ~1,5 phút cho clip 10 giây, gửi Telegram ~20s.

Tool tải bản gốc 720p (`flow.download: original`) rồi tự nâng lên 2K 60fps; Flow cũng cho tải bản 1080p (`flow.download: 1080p`). Video Flow có watermark ✦ nhỏ ở góc dưới bên phải.

## Lưu ý

- Tool **tự bấm "I agree"** ở hộp thoại "Rights to use this image" của Flow mỗi lần tải ảnh lên. Chỉ dùng ảnh bạn có quyền sử dụng.
- Video có người do AI tạo trông như thật: khi đăng TikTok hãy bật nhãn **"AI-generated content"**; TikTok có thể gỡ video AI như thật mà không gắn nhãn.
- Tự động hoá giao diện Flow và TikTok có thể trái điều khoản của các dịch vụ này. Tool thao tác chậm như người, không chạy song song, nhưng rủi ro tài khoản bị đánh dấu vẫn còn.
- Bấm **Approve** cho Agent là trừ credit. Đã gửi rồi mà tool tắt giữa chừng thì job chuyển sang lỗi để bạn kiểm tra trên Flow trước.
- Mỗi job lưu trong `jobs/<id>/` (ảnh, prompt, video gốc, video đã nâng cấp, `log.txt`, ảnh chụp màn hình khi lỗi); thư mục này không lên git.

## Kiểm thử

```bash
cd backend && ../.venv/bin/python -m pytest -q
```
