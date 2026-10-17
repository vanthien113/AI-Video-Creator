# Đăng TikTok ngay / lên lịch — Thiết kế

- Ngày: 2026-10-17
- Trạng thái: chờ duyệt spec
- Dựa trên: [thiết kế gốc](2026-10-15-ai-video-creator-design.md), bước lưu nháp TikTok đang có (`tiktok_draft`, đang tắt)

## 1. Mục tiêu

Khi một job tạo từ link TikTok Shop đã xong (video đã xuất, đã có tên sản phẩm và hashtag), người dùng bấm **một nút** — trên tool hoặc trên Telegram — để tool tự đăng video lên TikTok, ngay hoặc theo lịch:

1. Mở TikTok Studio trong Chrome của tool, tải video lên, điền mô tả (tên + hashtag).
2. Gắn link sản phẩm (Add link) bằng cách tìm theo ID sản phẩm.
3. Bật nhãn **AI-generated content**.
4. Chọn **Now** hoặc **Schedule**; lịch đăng rơi vào khung giờ trống kế tiếp sau bài muộn nhất đã có.
5. Bấm **Post** / **Schedule**, rồi báo kết quả lên tool và Telegram.

**Thành công nghĩa là:** bấm một nút → video xuất hiện trong TikTok Studio (đã đăng, hoặc đã lên lịch đúng khung giờ), có mô tả, link sản phẩm và nhãn AI; trên Telegram tin "Đang" được cập nhật, tin chứa 2 nút đổi thành kết quả, và có một tin mới báo đã đăng (kèm giờ nếu lên lịch).

## 2. Các quyết định đã chốt

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Kích hoạt | Người dùng bấm; tool không bao giờ tự đăng | Đăng công khai là việc không đảo ngược |
| Nơi bấm | 2 nút trên tool (khung "Xong") và 2 nút trên Telegram | Bấm từ Mac hay điện thoại đều được |
| Vị trí nút Telegram | Một tin riêng mới, gửi sau tin tên + hashtag | Tách bạch với tin để copy |
| Xác nhận | Không — bấm là chạy | Người dùng chọn |
| Không tìm thấy sản phẩm khi Add link | Dừng, không đăng, báo lỗi | Không có bài nào lên thiếu link |
| Kiến trúc | Bước cuối `tiktok_post` trên worker hiện có, chỉ làm việc khi đã bấm nút | Không bao giờ lái Chrome cùng lúc với Flow; dùng lại lỗi/Thử lại/tin Telegram |
| Mô tả bài đăng | Đúng tin tên + hashtag đã gửi Telegram: `tên\n#a #b #c` | Người dùng đã thấy và đã duyệt nội dung này |
| Khung giờ lên lịch | 7, 9, 11, 13, 15, 17, 19, 21, 23h; hết khung thì sang ngày sau | Người dùng chỉ định |
| Số lần đăng | Mỗi video một lần; video mới (chạy lại từ Xuất file) đăng lại được | Chống đăng trùng |
| Phạm vi job | Chỉ job tạo từ link (có ID sản phẩm, tên, hashtag) | Job kéo ảnh không có ID để Add link |
| Chrome | Chrome riêng của tool, mọi trang mở bằng tab nền | Không kéo Chrome lên trước công việc của người dùng |

## 3. Luồng

```
Job "Xong" ──► [📤 Đăng ngay] / [🗓 Lên lịch]  (tool hoặc Telegram)
                 │
                 ▼  request_post(job, mode): ghi mode, current_step = tiktok_post, vào hàng chờ
            Worker chạy bước tiktok_post (tab nền trong Chrome của tool)
                 │  (schedule) đọc trang Content → tính khung giờ
                 │  tải video → mô tả → Add link → nhãn AI → Now/Schedule
                 │  ghi submitted_at → bấm Post/Schedule → chờ xác nhận → ghi done_at
                 ▼
            Job "Xong" + kết quả đăng
                 │
                 ├─► tool: dòng "✅ Đã đăng TikTok lúc 10:32" / "🗓 Đã lên lịch TikTok: 19:00 Chủ nhật 18/10"
                 └─► Telegram: sửa tin "Đang", sửa tin 2 nút, gửi tin mới báo kết quả
```

Job chạy bình thường vẫn đi qua `tiktok_post` nhưng bước này không làm gì (chưa bấm nút), nên job kết thúc ở "Xong" như hiện nay.

## 4. Dữ liệu

`STEPS` thêm `"tiktok_post"` sau `"tiktok_draft"`.

`JobState.post: TikTokPostState` (mới):

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `mode` | `"now" \| "schedule" \| None` | `None` = chưa bấm nút → bước không làm gì |
| `requested_at` | ISO hoặc `None` | Lúc bấm nút |
| `scheduled_for` | ISO (giờ máy) hoặc `None` | Khung giờ đã chọn; tính lại ở mỗi lần chạy chưa bấm Schedule |
| `submitted_at` | ISO hoặc `None` | Ghi **ngay trước** khi bấm Post/Schedule — mốc không quay lại |
| `done_at` | ISO hoặc `None` | TikTok đã xác nhận đăng / lên lịch |
| `notified` | bool | Đã gửi tin báo kết quả lên Telegram |
| `offer_token` | str hoặc `None` | Mã ngắn trong dữ liệu nút Telegram |
| `offer_message` | `TelegramMessageRef` hoặc `None` | Tin chứa 2 nút, để sửa về sau |

`SourceInfo.product_id: str = ""` (mới): bước Đọc TikTok lấy ID từ địa chỉ trang **sau khi chuyển hướng** (`ProductPage.url`, dạng `…/pdp/<id>`), vì link chia sẻ có thể là link rút gọn `vt.tiktok.com/…`. Job cũ chưa có trường này thì lấy từ `source.url` nếu đó là link `/pdp/<id>`; không lấy được thì không cho đăng (xem §5).

## 5. Kích hoạt

`LinkJobActions.request_post(job_id, mode)` — tool và Telegram đều gọi hàm này; kiểm tra trong khoá của store:

- job ở trạng thái `done`;
- job có `source` và lấy được ID sản phẩm — nếu không: "Không biết ID sản phẩm của job này; chạy lại bước Đọc TikTok.";
- `post.mode` đang trống — nếu không: "Video này đã được yêu cầu đăng." (chặn bấm hai lần, hoặc bấm ở cả tool lẫn Telegram).

Đạt thì ghi `post.mode`, `post.requested_at`, đặt `current_step = "tiktok_post"` và cho vào hàng chờ. Worker lấy job cũ nhất trước, nên lệnh đăng chạy ngay khi bước đang chạy của job khác (nếu có) kết thúc.

API: `POST /api/jobs/{id}/post`, thân `{"mode": "now" | "schedule"}`; lỗi điều kiện trả 409 như các hành động khác.

`JobActions.retry`:
- `step == "tiktok_post"`: xoá `submitted_at` (người dùng đã xác nhận trên giao diện là chấp nhận rủi ro đăng 2 lần), giữ `mode`;
- chạy lại từ bước `export` trở về trước: `post` về mặc định (video mới đăng lại được; Telegram sẽ có tin 2 nút mới).

`PipelineRunner.recover()`: job đang chạy `tiktok_post` mà đã có `submitted_at` nhưng chưa có `done_at` thì chuyển sang Lỗi — "Tool đã bấm Post/Schedule trước khi tắt; kiểm tra TikTok Studio" — không chạy lại.

## 6. Bước `tiktok_post`

```
mode trống                     → không làm gì
done_at có                     → chỉ gửi phần Telegram còn thiếu (§9), xong
submitted_at có, done_at trống → dừng: "Tool đã bấm Post/Schedule lúc …, không thấy TikTok xác nhận.
                                  Kiểm tra TikTok Studio; nếu chưa có bài thì bấm Thử lại."
còn lại                        → thao tác trên TikTok Studio như dưới, rồi §9
```

Phần chung với bước lưu nháp được tách khỏi `tiktok/studio_upload.py` thành các hàm dùng lại được: mở trang tải lên, kiểm tra đăng nhập, tải video và chờ "Uploaded", đóng hộp giới thiệu, điền mô tả (có kiểm tra và điền lại), bật nhãn AI qua Show more. `save_draft` vẫn chạy y như cũ. Phần riêng của việc đăng nằm trong module mới `tiktok/studio_post.py`.

Thứ tự thao tác, mỗi việc báo tiến trình lên tool:

1. **(Lên lịch)** Mở tab nền `tiktok.content_url`, đọc thời gian các bài (§8), đóng tab. Tính khung giờ (§7), ghi `post.scheduled_for`.
2. Mở tab nền `tiktok.post_url`; chưa đăng nhập TikTok thì dừng như bước lưu nháp.
3. Tải file đã xuất (`job.export_path`, thiếu thì `final-4k60.mp4`) và chờ ô `upload_status_container` báo "Uploaded" (tối đa `tiktok.timeout_sec`). Không dựa vào chữ trên cả trang: trang luôn có câu "Checks can only start after the file is uploaded."
4. Điền tên sản phẩm (cắt ở `MAX_DESCRIPTION` = 2000), xuống dòng, rồi **gõ từng hashtag và chọn đúng tag đó trong danh sách gợi ý** của TikTok (mũi tên xuống tới tag, Enter) để thành hashtag thật. Tag không có trong gợi ý thì để dạng chữ và đăng tiếp. Dán cả chuỗi `#a #b #c` chỉ ra chữ thường (khảo sát §12).
5. **Add link**: nút Add → hộp "Add link" (Link type mặc định Products) → Next → hộp "Add product links": gõ ID vào "Search products", Enter, chọn dòng có cột Product ID **khớp đúng ID** → Next → ô "Product name" (TikTok điền sẵn, tối đa 30 ký tự) → Add. TikTok báo "Remove invalid characters: …" thì bỏ các ký tự đó rồi Add lại (tối đa 3 lần). Không có dòng nào khớp trong 15 giây → đóng hộp, `StepFailure("Không tìm thấy sản phẩm <id> khi Add link. Kiểm tra sản phẩm đã có trong showcase/shop của tài khoản TikTok này rồi bấm Thử lại.")`. Chưa có gì được đăng nên Thử lại an toàn.
6. Bật **AI-generated content** (bấm Show more nếu đang thu gọn).
7. **Settings → When to post**: chọn Now hoặc Schedule. Với Schedule: chọn ngày trên lịch trước, rồi giờ và phút, rồi đọc lại hai ô; khác `scheduled_for` thì dừng trước khi bấm.
8. Kiểm tra lần cuối: mô tả còn tên sản phẩm, link sản phẩm đang hiện trên form, nhãn AI đang bật, When to post đúng lựa chọn, nút có `data-e2e=post_video_button` và chữ đúng là "Post"/"Schedule". Ghi `post.submitted_at` (lưu xuống đĩa), rồi bấm.
9. Trong tối đa 90 giây sau khi bấm: hộp hỏi lại kiểu "Post now" / "Post anyway" (chưa khảo sát được vì phải đăng thật; danh sách nút trong `tiktok-selectors.yaml`) → bấm; trang rời khỏi form tải lên → thôi chờ.
10. **Xác nhận trên trang Content** (§8): tìm bài có mô tả bắt đầu bằng tên sản phẩm, tạo sau lúc bấm (cho lệch 2 phút) và, khi lên lịch, đúng giờ đã chọn; đọc lại tối đa 6 lần, cách nhau 20 giây. Thấy → ghi `post.done_at`. Không thấy → lỗi theo dòng thứ ba của bảng trên.

Lỗi Playwright hoặc `StudioError` → `StepFailure` kèm ảnh chụp màn hình + HTML vào `errors/` như các bước khác.

## 7. Chọn khung giờ

Hàm thuần `next_slot(now, slots, lead_min, taken) -> datetime`, với `taken` = `[latest_page, *tool_scheduled]`:

- `floor = max(now + lead_min phút, *taken)`; giá trị nào thiếu (`None`) thì bỏ qua.
  - `latest_page`: thời gian muộn nhất đọc được trên trang Content (bài đã đăng và bài đã lên lịch).
  - `tool_scheduled`: `post.scheduled_for` của các job khác đã bấm Schedule (`submitted_at` có), đề phòng TikTok chưa kịp hiện bài vừa lên lịch trong danh sách.
- Kết quả = khung đầu tiên **lớn hơn hẳn** `floor`, xét từ ngày của `floor`; hết khung trong ngày thì lấy khung đầu của ngày hôm sau.
- Giờ là giờ máy Mac (TikTok Studio hiển thị theo múi giờ của trình duyệt trên chính máy này).
- Sau khi tính, bước `tiktok_post` so với giới hạn lên lịch của TikTok: hôm nay + 30 ngày (khảo sát §12, hằng số `MAX_DAYS_AHEAD` trong `tiktok/post_plan.py`); vượt → `StepFailure` báo rõ khung giờ tính ra và giới hạn.

Ví dụ (`slots` = 7…23 lẻ, `lead_min` = 20, bây giờ 10:00 thứ Bảy 17/10):

| Bài muộn nhất | Kết quả | Vì sao |
|---|---|---|
| 08:30 17/10 (đã qua) | 11:00 17/10 | floor = 10:20 |
| 10:50 17/10 | 11:00 17/10 | |
| 11:00 17/10 | 13:00 17/10 | phải lớn hơn hẳn |
| 21:30 17/10 | 23:00 17/10 | |
| 23:00 17/10 | 07:00 18/10 | hết khung trong ngày |
| không có bài nào | 11:00 17/10 | |
| bây giờ 10:45, không có bài | 13:00 17/10 | 11:00 < 10:45 + 20 phút |

## 8. Đọc trang Content

Module `tiktok/studio_content.py`. Trang Content nhúng sẵn lượt bài đầu tiên dưới dạng JSON trong `<script id="__Creator_Center_Context__" type="application/json">`, khoá `firstBatchQueryItems.item_list` (khảo sát §12). Tool đọc JSON đó, không đọc chữ trên giao diện:

- Mỗi bài có `desc`, `create_time`, `post_time` (epoch giây; bài đã lên lịch thì là giờ sẽ đăng), `schedule_time` (chỉ bài đã lên lịch), `status` (140 = đã lên lịch, 102 = công khai), `is_pinned`.
- Thứ tự: bài đã lên lịch trên cùng, rồi bài ghim, rồi các bài khác mới nhất trước. Vì vậy "thời gian đăng mới nhất" là **giá trị lớn nhất** (`schedule_time`, không có thì `post_time`), không phải dòng đầu.
- Dùng lại để xác nhận bài vừa đăng (§6 bước 10): so mô tả sau khi bỏ dấu câu và khoảng trắng thừa, vì TikTok có thể đổi ký tự (tên "Dép sục+Tặng…" lên TikTok thành "Dép sục Tặng…").

Phần đọc JSON và so khớp là hàm thuần, có test với HTML mẫu. Không đọc được trang hoặc không thấy JSON (lỗi, đổi giao diện) → `StepFailure`, **không** đoán khung giờ.

## 9. Báo kết quả

**Tool**
- Khung "Xong" của job tạo từ link, chưa bấm nút: 2 nút **📤 Đăng ngay** và **🗓 Lên lịch** (bấm là chạy).
- Đang chạy: thanh bước có thêm ô "Đăng TikTok" (chỉ hiện với job đã bấm nút); dòng tiến trình hiện việc đang làm ("Đọc lịch đăng", "Tải video lên", "Gắn link sản phẩm", "Chọn 19:00 18/10", …).
- Xong: thay 2 nút bằng dòng "✅ Đã đăng TikTok lúc 10:32" hoặc "🗓 Đã lên lịch TikTok: 19:00 Chủ nhật 18/10".
- Lỗi: khung lỗi như các bước khác (lý do, ảnh chụp, Thử lại). Nếu `submitted_at` đã có, Thử lại hỏi "Tool đã bấm Post/Schedule trước đó, thử lại có thể đăng 2 lần. Tiếp tục?".

**Telegram** — job tạo từ bot:
1. Sau tin tên + hashtag (bước "Gửi Telegram"), khi job đi qua bước `tiktok_post` mà chưa ai bấm nút (tức ngay trước khi job "Xong"): gửi tin riêng "📤 Đăng video này lên TikTok?" với 2 nút `📤 Đăng ngay` (`t:<token>:n`) và `🗓 Lên lịch` (`t:<token>:s`), trả lời dưới tin link. Ghi `offer_token`, `offer_message`; Thử lại không gửi lại khi `offer_message` đã có. Gửi lỗi chỉ ghi log, không làm hỏng job (vẫn bấm được trên tool). Gửi ở đây thay vì trong bước "Gửi Telegram" để lúc tin đến, job đã sắp xong, bấm là nhận ngay.
2. Bấm nút → `request_post`; tin 2 nút đổi thành "⏳ Đã nhận: Đăng ngay / Lên lịch. Đang chờ lượt…" (mất nút). Đã yêu cầu ở bên kia rồi thì hiện toast "Video này đã được yêu cầu đăng" và gỡ nút.
3. Tin "Đang" (`StatusNotifier`): khi chạy bước này hiện "⏳ Đang: Đăng TikTok" / "⏳ Đang: Lên lịch TikTok"; khi xong hiện "✅ Đã đăng TikTok" / "🗓 Đã lên lịch TikTok 19:00 18/10" thay cho "✅ Xong". Job đi qua bước này mà chưa ai bấm nút thì hiện "✅ Xong" luôn (bước không làm gì).
6. Bấm vào nút của một tin cũ (video đã làm lại nên trạng thái đăng đã xoá): toast "Nút này đã cũ, dùng tin mới nhất hoặc nút trên tool.", không đăng gì.
4. Đăng xong:
   - **tin 2 nút** đổi thành "✅ Đã đăng lên TikTok lúc 10:32" / "🗓 Đã lên lịch đăng TikTok: 19:00 Chủ nhật 18/10";
   - **tin mới**, trả lời dưới tin link: "✅ Đã đăng lên TikTok: <tên>" / "🗓 Đã lên lịch đăng TikTok lúc 19:00 Chủ nhật 18/10: <tên>". Gửi được thì ghi `notified`; lỗi mạng → `StepFailure("Đã đăng nhưng nhắn Telegram lỗi…")`, Thử lại chỉ nhắn lại (vì `done_at` đã có).
5. Lỗi: tin báo lỗi kèm ảnh chụp như mọi bước (đã có sẵn); tin 2 nút đổi thành "❌ Đăng lỗi, mở AI Video Creator để thử lại" (trừ khi bài đã lên và chỉ tin nhắn Telegram lỗi). Thử lại làm trên tool.

Job tạo bằng cách dán link trên tool: 2 nút chỉ có trên tool; tin "Đang" và tin báo kết quả gửi cho ID Telegram đầu tiên (`notify_target`, như bước lưu nháp).

Code: `telegram/telegram_post.py` (bàn phím 2 nút, đọc dữ liệu nút, `PostHandler` xử lý bấm nút, sửa tin 2 nút). `TelegramListener` nhận một hàm chuyển tiếp lượt bấm: tiền tố `p:`/`g:` → `PickHandler`, `t:` → `PostHandler`. Sửa chữ của tin có nút dùng `editMessageText` (tin thường, không phải ảnh), không gửi `reply_markup` để gỡ nút.

## 10. Cấu hình và selector

`config.yaml`, mục `tiktok:` (thêm):

```yaml
  post_url: https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video
  content_url: https://www.tiktok.com/tiktokstudio/content
  schedule_slots: [7, 9, 11, 13, 15, 17, 19, 21, 23]   # giờ trong ngày, giờ máy
  schedule_lead_min: 20                                # khung giờ phải cách bây giờ ít nhất chừng này phút
```

`tiktok_post` không phụ thuộc `tiktok.save_draft`; dùng chung `ai_generated_label` và `timeout_sec`.

`tiktok-selectors.yaml` (thêm, theo khảo sát §12): ô trạng thái tải lên, nút Add link và vùng link, hai hộp Add link / Add product links và các phần bên trong (ô tìm, dòng sản phẩm, cột ID, nút Next / Add / Cancel, ô Product name), lựa chọn Now / Schedule, lịch chọn ngày, danh sách gợi ý hashtag, nút Post / Schedule và chữ trên nút, các nút "vẫn đăng" có thể hiện sau khi bấm, câu báo ký tự không hợp lệ. JSON của trang Content là cấu trúc dữ liệu, nằm trong code (`studio_content.py`).

## 11. Lỗi

| Tình huống | Xử lý |
|---|---|
| Chrome chưa mở / chưa đăng nhập TikTok | `StepFailure` như bước lưu nháp; Thử lại an toàn |
| Không đọc được trang Content | `StepFailure`, không đoán giờ; Thử lại an toàn |
| Không tìm thấy sản phẩm khi Add link | `StepFailure`, không đăng; Thử lại an toàn |
| Bộ chọn ngày giờ không nhận đúng khung | `StepFailure` trước khi bấm; Thử lại an toàn (khung giờ tính lại) |
| Khung giờ vượt giới hạn lên lịch của TikTok | `StepFailure` nêu khung và giới hạn |
| Đã bấm Post/Schedule, không thấy xác nhận | `StepFailure`, tab giữ nguyên; Thử lại phải xác nhận trên tool |
| Tool tắt giữa chừng sau khi bấm | `recover()` chuyển sang Lỗi, không chạy lại |
| Tool tắt trước khi bấm | `recover()` cho vào hàng chờ lại như mọi bước |
| Telegram lỗi sau khi đã đăng | `StepFailure`; Thử lại chỉ nhắn lại |
| Huỷ job khi đang chờ đăng | Job thành Đã huỷ như mọi job; video đã xuất vẫn còn trên Mac |

## 12. Kết quả khảo sát (2026-10-17)

Làm trong tab nền của Chrome riêng của tool, lúc không có job nào chạy, giao diện tiếng Anh, **không bấm Post / Schedule / Save draft**. Trước và sau khảo sát: 79 bài, 1 bản nháp.

- **Tải lên:** `[data-e2e=upload_status_container]` hiện "Uploaded（30.44MB）" khi xong. Câu "Checks can only start after the file is uploaded." luôn có trên trang, nên mẫu `\buploaded\b` áp lên cả trang sẽ báo xong quá sớm (bước lưu nháp hiện tại đang mắc lỗi này; phần dùng chung sửa luôn).
- **Add link:** `[data-e2e=anchor_container]` có nút "Add". Hộp "Add link" (Link type: Products) → Next → hộp "Add product links", tab "Showcase products", ô `placeholder="Search products"`, bảng cột Product name / **Product ID** / Price / Stock / Status, mỗi dòng một radio; Next bị khoá tới khi chọn. Tìm `1737383451447231991` ra đúng 1 dòng; tìm `1737477284468917824` (không có trong showcase) ra bảng trống, không có chữ báo. Next → ô "Product name" điền sẵn 30 ký tự; "[JOLY 01] Dép sục+Tặng 1 bộ ch" bị từ chối với "Remove invalid characters: +", bỏ "+" thì Add được, cả hai hộp đóng và tên hiện trong `anchor_container`.
- **When to post:** `[data-e2e=schedule_container]`, radio `name=postSchedule` giá trị `post_now` / `schedule` (đọc `aria-checked`). Chọn Schedule hiện ô giờ chỉ đọc (`10:40`, gợi ý sẵn khoảng 15 phút sau) với cột giờ 00–23 rồi cột phút 00–55 (bước 5 phút), và ô ngày chỉ đọc (`2026-10-17`) với lịch `.calendar-wrapper` (`.month-title`, `.year-title`, hai `.arrow`, ngày chọn được là `span.day.valid`). Ngày chọn được: 17/10 → 16/11, tức **hôm nay + 30 ngày**. Chọn 19 rồi 00 → ô giờ `19:00`; chọn ngày 18 → ô ngày `2026-10-18`, giờ giữ nguyên. Nút đổi chữ thành "Schedule", vẫn `data-e2e=post_video_button`.
- **Hashtag:** dán hay gõ `#tag` chỉ ra chữ thường. Gõ `#giaybupbe` mở danh sách `[role=option]` (`.hash-tag-topic` "#giaybupbe", "368.0K posts"), dòng đầu được chọn sẵn (`aria-selected=true`); Enter biến chữ thành `span[data-testid=mentionText]` và tự thêm dấu cách. Bấm chuột vào gợi ý không được trong tab nền (danh sách nằm ngoài khung nhìn).
- **Nhãn AI:** có thêm `[data-e2e=aigc_container]`; code cũ tìm theo chữ vẫn dùng được.
- **Trang Content:** xem §8. Lúc khảo sát (10:19) dòng đầu là bài đã lên lịch 11:20 cùng ngày (`status` 140), tiếp đến 3 bài ghim từ tháng 7–8, rồi các bài mới nhất.
- **Chưa khảo sát được** (phải đăng thật): hộp hỏi lại sau khi bấm Post/Schedule và trang hiện gì sau đó. Vì vậy tool xác nhận bằng trang Content (§6 bước 10) và lần đăng thật đầu tiên do người dùng bấm.

## 13. Kiểm thử

**pytest (không mạng, không Chrome):**
- `next_slot`: các ví dụ ở §7, cộng `tool_scheduled` muộn hơn trang Content, và vượt giới hạn ngày.
- Lấy ID sản phẩm: link `/pdp/<id>` có và không có query, link rút gọn (không lấy được), ưu tiên `product_id` đã lưu.
- Đọc JSON của trang Content (HTML mẫu): thời gian muộn nhất (bài ghim nằm trên bài mới hơn), tìm bài vừa đăng (TikTok đổi dấu câu), thiếu JSON thì báo lỗi.
- Phần thuần của thao tác form: bỏ ký tự không hợp lệ khỏi tên sản phẩm, chọn hashtag trong gợi ý (giả lập danh sách), selector file có đủ mục.
- `request_post`: chỉ job Xong, chỉ job từ link, không có ID thì từ chối, không cho yêu cầu lần hai.
- Bước `tiktok_post` (thay phần trình duyệt bằng giả lập như test lưu nháp): `mode` trống không làm gì; `done_at` có thì chỉ nhắn; `submitted_at` có thì dừng mà không gọi trình duyệt; thành công ghi `submitted_at` trước khi bấm và `done_at` sau đó.
- `retry` và `recover()` theo §5.
- Telegram: bàn phím 2 nút, đọc dữ liệu nút, `PostHandler` (bấm lần đầu, bấm lại, job không còn), chữ tin 2 nút ở từng trạng thái, `status_text` khi đang đăng và đã đăng/lên lịch, tin 2 nút không gửi trùng khi Thử lại.
- API `POST /api/jobs/{id}/post`.

**Chạy thử trên trang thật:** `python -m app.tiktok.check_post <job-id> [--schedule]` chạy toàn bộ §6 **trừ** bước bấm Post/Schedule, để tab mở cho người dùng xem (video được tải lên TikTok nhưng không đăng). Lần đăng thật đầu tiên do người dùng bấm.

## 14. Ngoài phạm vi

- Bước lưu nháp TikTok: giữ nguyên, vẫn tắt.
- Nút Thử lại trên Telegram.
- Đăng một video lên nhiều tài khoản, hoặc đăng lại video đã đăng.
- Đổi lịch / huỷ bài đã lên lịch (làm trên TikTok Studio).
- Sửa quyền xem, bình luận, duet… (giữ mặc định của TikTok).
