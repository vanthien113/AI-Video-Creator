# AI Video Creator — Thiết kế

- Ngày: 2026-10-15
- Trạng thái: chờ duyệt spec
- Máy chạy: MacBook Apple M1, RAM 16GB, macOS 26

## 1. Mục tiêu

Tool chạy trên máy cá nhân, giúp chủ shop biến một ảnh chụp sản phẩm thành một clip quảng cáo 4K 60fps:

1. Tách sản phẩm khỏi nền, upscale lên 2K.
2. Viết prompt quảng cáo theo quy tắc trong `ad-rules.md`.
3. Gửi ảnh và prompt lên Google Flow (tài khoản đã đăng nhập sẵn), sinh video.
4. Tải video về, nâng lên 4K 60fps.
5. Xuất video ra thư mục chỉ định.

**Thành công nghĩa là:** kéo một ảnh vào giao diện, duyệt (hoặc để tự chạy) qua 3 điểm, nhận được file `*_4k60.mp4` trong thư mục xuất, không phải tự thao tác trên Flow.

## 2. Các quyết định đã chốt

| Chủ đề | Quyết định | Lý do |
|---|---|---|
| Người dùng | Một người (chủ shop), vài ảnh mỗi lần, có người theo dõi | Không cần xếp hàng phức tạp hay phân quyền |
| Sinh video | Google Flow qua trình duyệt, **không** dùng Veo API | Tận dụng credit gói Google AI đã mua |
| Chế độ Flow | Ingredients to Video | Sản phẩm đã tách nền là "nguyên liệu", Veo tự dựng bối cảnh |
| Đầu ra | 1 ảnh → 1 prompt → 1 clip | Ít credit nhất, đơn giản nhất |
| Viết prompt | `claude -p` (Claude Code không tương tác) | Dùng gói Claude sẵn có, không cần API key riêng |
| Giao diện | React (Vite + TypeScript), FastAPI phục vụ bản build | Một tiến trình khi dùng thật |
| Backend | Python 3.13 (Homebrew) + `venv` + FastAPI | Máy không có `uv`; `onnxruntime` đã hỗ trợ 3.13 |
| Điểm duyệt | Sau tách nền, sau prompt, sau khi có video Flow; mỗi điểm có ô "tự động chạy tiếp" | Chặn lỗi trước bước tốn công hoặc tốn credit |
| Upscale video | Cân bằng: RIFE lên 60fps + `ffmpeg` lanczos lên 4K | Khoảng 2–5 phút/clip trên M1 (sẽ đo lại) |
| Thiết lập | Mọi tham số nằm trong `config.yaml`, giao diện không có trang cài đặt | Một nơi sửa duy nhất |

## 3. Kiến trúc

```
┌──────────── React (Vite) ────────────┐
│ Kéo thả ảnh · Danh sách job · Duyệt   │
│ từng bước · Ô "tự động chạy tiếp"     │
└───────────────┬──────────────────────┘
                │ REST + SSE
┌───────────────▼──────────────────────┐
│ FastAPI                              │
│  ├─ JobStore  (jobs/{id}/state.json) │
│  ├─ EventBus  (đẩy tiến trình qua SSE)│
│  └─ PipelineRunner (1 worker)        │
│       1. cutout         rembg        │
│       2. upscale        Real-ESRGAN  │
│       3. prompt         claude -p    │
│       4. flow_generate  Playwright ──┼──► Chrome thật, hồ sơ riêng,
│       5. flow_download  Playwright ──┼──► đã đăng nhập Google
│       6. enhance        RIFE+ffmpeg  │
│       7. export         chép file    │
└──────────────────────────────────────┘
   config.yaml · ad-rules.md · flow-selectors.yaml
```

### 3.1 Giao diện chung của một bước

Mỗi bước là một module độc lập, cùng một giao diện:

```python
class Step(Protocol):
    name: str
    def run(self, job: JobContext, report: ProgressReporter) -> StepResult: ...
```

- `JobContext`: đường dẫn thư mục job, cấu hình, ghi chú, phản hồi của người dùng (nếu có).
- `ProgressReporter`: báo phần trăm và thông điệp, đi qua EventBus về giao diện.
- `StepResult`: `ok` hoặc `failed(reason, screenshot?)`.
- Bước ghi file kết quả vào thư mục job và được phép ghi đè, nên chạy lại bước nào cũng an toàn.

PipelineRunner không biết bên trong bước làm gì. Nó chỉ chạy lần lượt, cập nhật `state.json`, phát sự kiện, và dừng ở các điểm duyệt.

### 3.2 Thư mục job

```
jobs/20261015-1530-son-moi/
  input.jpg          ảnh gốc
  cutout.png         sản phẩm đã tách (để duyệt)
  mask.png           mặt nạ gốc
  product-2k.png     ảnh gửi lên Flow
  prompt.json        { prompt, summary }
  flow-raw.mp4       video tải từ Flow
  final-4k60.mp4     video thành phẩm
  state.json         trạng thái job
  log.txt            nhật ký
  errors/            ảnh chụp màn hình + HTML khi lỗi
  tmp/               khung hình tạm, xoá khi xong bước enhance
```

### 3.3 Trạng thái job

```
queued ─► running(step) ─► awaiting_review(gate) ─► queued ─► ... ─► done
                     └──► failed(step, reason)
any ─► cancelled
```

- Có 3 điểm duyệt (gate): `cutout` (sau bước 1), `prompt` (sau bước 3), `flow_video` (sau bước 5).
- Gate nào có ô "tự động" được bật thì đi thẳng qua, không dừng.
- Job ở trạng thái `awaiting_review` nhường worker cho job tiếp theo trong hàng đợi.
- `state.json` lưu: `status`, `current_step`, `auto_gates`, `note`, `history` (thời gian từng bước), `flow` (mã/đường dẫn video trên Flow, `submitted_at`), `error`.
- **Khởi động lại tool:** job đang `running` quay về `queued` ở đúng bước đó. Riêng `flow_generate`: nếu `state.flow.submitted_at` đã có (tức đã bấm sinh video trên Flow), job **không** tự gửi lại mà chuyển sang `failed` với lý do "Đã gửi lên Flow trước khi tắt — kiểm tra trên Flow rồi chọn tiếp tục hoặc sinh lại". Lý do: tránh tốn credit hai lần.

## 4. Chi tiết từng bước

### 4.1 `cutout` — tách nền

- Nhận jpg, png, webp, heic (heic đọc qua `pillow-heif`). Ảnh được xoay theo EXIF.
- `rembg` với mô hình đầu tiên trong `image.cutout_models` (mặc định `birefnet-general`, giấy phép MIT) tạo `mask.png`.
- Cùng ảnh, cùng mô hình thì luôn ra cùng kết quả, nên ở gate `cutout` không có nút "làm lại" suông. Thay vào đó có **Thử mô hình khác** (chuyển sang mô hình kế tiếp trong danh sách, ví dụ `isnet-general-use`) và **Thay ảnh khác** (tải ảnh mới, thay `input.*`, chạy lại bước 1).
- Cắt theo khung bao của sản phẩm, chừa lề `image.padding` (mặc định 8%), ghép lên nền `image.background` → `cutout.png`.
- **Không** dùng RMBG-2.0: giấy phép không cho dùng thương mại.
- Mặt nạ rỗng hoặc chiếm dưới 2% ảnh → `failed("Không tìm thấy sản phẩm")`.

### 4.2 `upscale` — lên 2K

- Upscale **vùng ảnh gốc đã cắt (RGB, chưa xoá nền)** bằng `realesrgan-ncnn-vulkan`, mô hình `realesrgan-x4plus`.
- Phóng mặt nạ đã cắt theo cùng tỉ lệ (lanczos), rồi ghép lên nền. Làm theo thứ tự này để mép sản phẩm sạch hơn so với upscale ảnh đã xoá nền.
- Chỉnh về cạnh dài đúng `image.long_edge` (mặc định 2048) → `product-2k.png`.
- Ảnh gốc đã lớn hơn 2048 thì bỏ qua Real-ESRGAN, chỉ thu nhỏ lại.

### 4.3 `prompt` — viết prompt

- Gọi `claude -p` với thư mục làm việc là thư mục job, `--output-format json`, `--allowedTools Read`, thời gian chờ tối đa `prompt.timeout_sec` (mặc định 180s).
- Lời gọi yêu cầu Claude: đọc `product-2k.png`, đọc file quy tắc (`paths.rules_file`), xét ghi chú của người dùng và góp ý viết lại (nếu có), rồi trả về **duy nhất** một khối JSON `{ "prompt": "...", "summary": "..." }`.
  - `prompt`: gửi lên Flow, ngôn ngữ theo quy tắc (mẫu mặc định: tiếng Anh).
  - `summary`: giải thích ngắn bằng tiếng Việt cho người duyệt.
- Tool đọc trường `result` trong JSON trả về, lấy khối JSON bên trong và kiểm tra đủ hai trường. Sai định dạng thì thử lại 1 lần, vẫn sai thì `failed`, kèm nội dung thô trong `log.txt`.
- Tool đi kèm một file `ad-rules.md` mẫu (cấu trúc gợi ý: giọng văn, bối cảnh, chuyển động máy quay, ánh sáng, điều cấm, độ dài prompt, ngôn ngữ).
- Ở điểm duyệt `prompt`, người dùng sửa thẳng `prompt` (lưu lại vào `prompt.json`), hoặc bấm "Viết lại" kèm góp ý (chạy lại bước 3 có thêm góp ý).

### 4.4 `flow_generate` — sinh video trên Flow

**Kết nối trình duyệt:**
- `ChromeLauncher` mở Google Chrome thật với `--user-data-dir=./chrome-profile` và `--remote-debugging-port` (cổng trong cấu hình). Chrome 136 trở lên bắt buộc dùng hồ sơ riêng thì mới bật được cổng debug, và hồ sơ riêng cũng giúp tránh việc Google chặn đăng nhập trên trình duyệt tự động.
- Người dùng đăng nhập Google một lần trong cửa sổ đó, từ đó về sau hồ sơ giữ phiên đăng nhập.
- `FlowClient` kết nối bằng `playwright.chromium.connect_over_cdp`. Tool không bao giờ tự mở trình duyệt chạy ẩn.

**Các thao tác:**
1. Mở (luôn tải lại trang) `flow.project_url`; để trống thì bấm "New project" ở `https://flow.google.com/` và lưu URL vào `state.json`. Tự đóng hộp thoại giới thiệu tính năng ("Get started").
2. Mở "Settings trigger": chọn Video → Ingredients → `flow.aspect_ratio` → x`flow.outputs` → mô hình `flow.model` (Omni 1.1 Flash / Veo 3.1 - Lite / Fast / Quality). Kiểm tra nhãn nút thiết lập khớp cấu hình.
3. "Add ingredients" → "Upload media" (tên file `{job_id}.png` để không nhầm ảnh cũ) → tự bấm "I agree" ở hộp thoại quyền sử dụng ảnh → chờ hết "Uploading" → bấm ảnh (và "Add to prompt" nếu hiện) → dán `prompt` vào ô "What do you want to create?".
4. Ghi `state.flow.submitted_at`, **rồi mới** bấm sinh video.
5. Chờ tối đa `flow.timeout_sec` (mặc định 600s), kiểm tra trạng thái mỗi 5s. Nhận diện: đang sinh / xong / bị chặn vì chính sách / hết credit / lỗi khác.
6. Xong: lưu định danh video trên Flow vào `state.flow.video_ref`.

**Quy tắc:**
- Mọi selector nằm trong `flow-selectors.yaml`. Code chỉ tham chiếu theo tên (`ingredients_tab`, `prompt_input`, `generate_button`, ...).
- Mỗi thao tác cách nhau một khoảng ngẫu nhiên 0.5–1.5s. Không chạy song song, không tự thử lại khi bị chặn vì chính sách hoặc hết credit.
- Mọi lỗi: chụp màn hình và lưu HTML vào `errors/`, rồi `failed(reason)`.

### 4.5 `flow_download` — tải video

- Tách khỏi bước 4 để tải lại được mà **không phải sinh lại** (không tốn credit).
- Dựa vào `state.flow.video_ref`, thử menu tải xuống chọn `flow.download` (mặc định 1080p). Không được thì tải thẳng nguồn video gốc (720p, Flow sinh ở 720p) và ghi chú vào log.
- Bắt file bằng `page.expect_download()` → `flow-raw.mp4`. Kiểm tra bằng `ffprobe`: có luồng hình, thời lượng lớn hơn 0.

### 4.6 `enhance` — 4K 60fps

1. Kiểm tra dung lượng trống còn ít nhất 3GB, không đủ thì `failed`.
2. `ffprobe` đọc fps, thời lượng, kích thước của `flow-raw.mp4`.
3. `ffmpeg` tách khung hình (png) vào `tmp/in/`.
4. `rife-ncnn-vulkan` với `rife-v4.6`, `-n round(thời_lượng × video.fps)` → `tmp/out/`.
5. `ffmpeg` ghép lại ở `video.fps`, scale lanczos lên cạnh dài `video.long_edge` (3840×2160 cho video ngang, 2160×3840 cho video dọc), `unsharp` nhẹ, mã hoá `hevc_videotoolbox` ở `video.bitrate` (mặc định 45M), gắn tag `hvc1` để QuickTime mở được, chép nguyên âm thanh từ `flow-raw.mp4` → `final-4k60.mp4`.
6. Xoá `tmp/`.
- Tiến trình báo theo số khung RIFE đã xử lý.
- Các lệnh `ffmpeg`/RIFE do hàm thuần (`ffmpeg_commands.py`) dựng ra, để kiểm thử được mà không cần chạy thật.

### 4.7 `export` — xuất file

- Chép `final-4k60.mp4` sang `paths.export_dir` với tên `{tên-ảnh-gốc}_{yyyyMMdd-HHmm}_4k60.mp4`. Trùng tên thì thêm hậu tố `-2`, `-3`.
- Thư mục xuất chưa có thì tạo. Không ghi được thì `failed`, file trong job vẫn còn.

## 5. Xử lý lỗi

Khi một bước Flow (`flow_generate`, `flow_download`) bị lỗi, giao diện hiện ảnh chụp màn hình, nhật ký và các lựa chọn:

| Lựa chọn | Tác dụng |
|---|---|
| Thử lại | Chạy lại bước bị lỗi |
| Tôi đã sửa tay, tiếp tục | Người dùng tự thao tác trong cửa sổ Chrome; tool đọc lại trang và chạy tiếp (với `flow_generate`: chuyển sang chờ kết quả) |
| Tải video lên thủ công | Kéo thả mp4 đã tải từ Flow; tool lưu thành `flow-raw.mp4` và chạy tiếp từ điểm duyệt `flow_video` |
| Huỷ job | Chuyển sang `cancelled` |

Bước không liên quan đến Flow chỉ có "Thử lại" và "Huỷ job".

## 6. API

| Phương thức | Đường dẫn | Mục đích |
|---|---|---|
| POST | `/api/jobs` | Tạo job: `images[]`, `note`, `auto_gates` (multipart) |
| GET | `/api/jobs` · `/api/jobs/{id}` | Danh sách / chi tiết |
| GET | `/api/jobs/{id}/files/{name}` | Lấy file trong thư mục job (chỉ tên file trong danh sách cho phép) |
| POST | `/api/jobs/{id}/approve` | Duyệt gate hiện tại; gate `prompt` có thể kèm `prompt` đã sửa |
| POST | `/api/jobs/{id}/retry` | Chạy lại từ `step` (multipart), tuỳ chọn kèm `feedback`, `cutout_model`, hoặc `image` mới |
| POST | `/api/jobs/{id}/continue` | Tiếp tục sau khi sửa tay |
| POST | `/api/jobs/{id}/manual-video` | Tải mp4 lên thủ công |
| POST | `/api/jobs/{id}/cancel` | Huỷ job |
| GET | `/api/events` | SSE: thay đổi trạng thái và tiến trình |
| GET | `/api/flow/status` | Chrome: chưa mở / chưa đăng nhập / sẵn sàng |
| POST | `/api/flow/launch-chrome` | Mở Chrome với hồ sơ riêng |
| POST | `/api/open-export-dir` | Mở thư mục xuất trong Finder (`open`) |

Server chỉ nghe trên `127.0.0.1`.

## 7. Giao diện

- **Thanh trên cùng:** trạng thái Chrome/Flow, nút "Mở Chrome cho Flow".
- **Trang chính:** vùng kéo thả (nhiều ảnh, mỗi ảnh một job), ô ghi chú, 3 ô "tự động chạy tiếp" (giá trị mặc định lấy từ `review` trong cấu hình), nút Bắt đầu. Bên dưới là danh sách job, mỗi job có thanh 7 bước; job chờ duyệt được làm nổi bật.
- **Chi tiết job:**
  - Gate `cutout`: ảnh gốc và ảnh đã tách đặt cạnh nhau. Nút Duyệt, Thử mô hình khác, Thay ảnh khác.
  - Gate `prompt`: ô sửa prompt, phần giải thích tiếng Việt. Nút Duyệt, Viết lại (kèm góp ý).
  - Gate `flow_video`: trình phát video. Nút Duyệt, Sinh lại (chạy lại từ `flow_generate`, tốn credit — giao diện hỏi xác nhận).
  - Khi lỗi: ảnh chụp màn hình, nhật ký, các lựa chọn ở mục 5.
  - Khi xong: trình phát video 4K, nút "Mở thư mục xuất".

## 8. Cấu hình — `config.yaml`

```yaml
server:  { port: 8765 }
paths:
  export_dir: ~/Movies/AI-Video-Creator
  rules_file: ./ad-rules.md
  jobs_dir: ./jobs
  chrome_profile: ./chrome-profile
image:
  long_edge: 2048
  background: white          # white | transparent
  padding: 0.08
  cutout_models: [birefnet-general, isnet-general-use]
prompt:  { timeout_sec: 180 }
flow:
  project_url: ""            # trống = tạo dự án mới
  model: "Veo 3.1 - Fast"    # đúng tên hiển thị trên Flow
  aspect_ratio: "9:16"
  outputs: 1
  download: 1080p
  timeout_sec: 600
  cdp_port: 9222
video:   { fps: 60, long_edge: 3840, rife_model: rife-v4.6, bitrate: 45M }
review:  { cutout: manual, prompt: manual, flow_video: manual }   # manual | auto
```

Cấu hình được kiểm tra bằng Pydantic khi khởi động; sai thì báo lỗi rõ ràng và không chạy.

## 9. Cấu trúc dự án

```
AI-Video-Creator/
  config.yaml · ad-rules.md · flow-selectors.yaml · pyproject.toml
  scripts/setup.sh          # tải Real-ESRGAN, RIFE (bản macOS) + mô hình vào bin/, kiểm tra chạy được
  backend/app/
    main.py                 # FastAPI, phục vụ frontend/dist
    config.py · job_store.py · pipeline_runner.py · event_bus.py
    api/        jobs_routes.py · flow_routes.py
    steps/      cutout_step.py · upscale_step.py · prompt_step.py
                flow_generate_step.py · flow_download_step.py
                enhance_video_step.py · export_step.py
    flow/       chrome_launcher.py · flow_client.py · flow_selectors.py
    media/      ffmpeg_commands.py · binaries.py
  backend/tests/
  frontend/                 # Vite + React + TypeScript
  bin/ jobs/ chrome-profile/   # không đưa vào git
```

- File Python đặt tên snake_case vì Python không import được tên có dấu gạch ngang. File frontend đặt tên kebab-case.
- Mỗi file dưới 200 dòng.
- Lệnh `python -m app.flow.check_selectors` (`flow check`): chạy thật mọi thao tác trên Flow tới ngay trước nút sinh video, **không** bấm sinh. Đã chạy đạt 5/5 trên Flow ngày 2026-10-15.

## 10. Kiểm thử

| Tầng | Nội dung |
|---|---|
| Đơn vị | PipelineRunner: dừng đúng gate, gate tự động đi thẳng, nhường worker khi chờ duyệt, chạy lại từ một bước, khôi phục sau khởi động lại (kể cả trường hợp `submitted_at` của `flow_generate`) |
| Đơn vị | `ffmpeg_commands`: số khung đích, kích thước 16:9 và 9:16, tham số mã hoá |
| Đơn vị | Đọc kết quả `claude -p`: JSON đúng, JSON lẫn trong văn bản, thiếu trường, rỗng |
| Tích hợp (chạy thật) | `cutout` + `upscale` trên ảnh mẫu: cạnh dài 2048, nền đúng, mặt nạ không rỗng |
| Tích hợp (chạy thật) | `enhance` trên clip 2s 24fps 720p có âm thanh do `ffmpeg` tự tạo: ra 60fps, 3840×2160 (hoặc 2160×3840), có âm thanh |
| Tích hợp | Toàn bộ pipeline với `FakeFlowClient` (trả về clip mẫu) |
| Thủ công | `flow check` + một lần chạy thật trên Flow, theo danh sách kiểm tra |

Không có kiểm thử tự động nào chạy trên Flow thật, vì mỗi lần chạy tốn credit.

## 11. Rủi ro

| Rủi ro | Cách giảm |
|---|---|
| Google đổi giao diện Flow | Selector gom trong `flow-selectors.yaml`, có `flow check`, có đường lui tải video thủ công |
| Tài khoản bị đánh dấu vì tự động hoá (có thể vi phạm điều khoản của Google) | Chrome thật hiện trên màn hình, thao tác có độ trễ, không chạy song song, số lượng ít, không tự thử lại khi bị chặn |
| Veo làm sai chi tiết sản phẩm (logo, chữ in) | Gate `flow_video`; `ad-rules.md` có thể yêu cầu giữ nguyên chi tiết |
| Gửi lên Flow hai lần sau khi khởi động lại | Ghi `submitted_at` trước khi bấm; khôi phục không tự gửi lại |
| `onnxruntime` chưa có bản cho Python 3.14 | Dùng Python 3.13 của Homebrew |
| Bản ncnn (Vulkan qua MoltenVK) không chạy trên máy | `setup.sh` chạy thử từng bản và báo lỗi ngay |
| Bước enhance chậm hoặc máy nóng | Đo thời gian thật khi làm; RIFE chạy ở 1080p, chỉ phóng to 4K bằng `ffmpeg` |

## 12. Cần xác minh khi bắt tay vào làm

- Giao diện thật của Flow trong tài khoản người dùng (tên tab, nút, menu tải xuống, tên mô hình hiển thị). Phải khảo sát trong lúc đã đăng nhập rồi mới viết `flow-selectors.yaml`.
- Flow có cho tải 1080p với video 9:16 trong gói của người dùng không. Không có thì dùng bản gốc (đã xử lý ở 4.5).
- Thời gian thật của `enhance` trên M1, để điều chỉnh ước lượng trên giao diện.

## 13. Ngoài phạm vi

Nhiều người dùng; nhiều bộ quy tắc; ghép nhiều cảnh thành một video; gọi Veo qua API; chạy song song nhiều job trên Flow; chạy bước enhance song song với bước Flow; trang cài đặt trên giao diện; chạy trên Windows/Linux.

## 14. Ghi nhận khi triển khai (2026-10-15)

Các điểm ở mục 12 đã xác minh trên Flow thật (`flow.google.com`, tài khoản Workspace của người dùng), qua một lượt sinh video thật đã được người dùng cho phép:

- **Thiết lập:** chọn mô hình **trước**, vì đổi mô hình làm Flow đặt lại độ phân giải và thời lượng. Omni 1.1 Flash cho chọn thêm `resolution` (360p/720p) và `duration` (4/6/8/10s), nên có thêm hai trường này trong `config.yaml`.
- **Giá mỗi video 9:16 ×1:**
  - Veo 3.1 Lite 10 credit, Fast 20 credit, Quality 100 credit (720p, 8 giây cố định).
  - Omni 1.1 Flash: ở 720p là 7/10/12/15 credit cho 4/6/8/10 giây.
- **Kết quả:** Flow hiện % khi đang sinh. Omni 720p 10 giây mất khoảng 40 giây. Video xong là một ô `<flow-video-tile>` có ảnh thu nhỏ; thẻ `<video>` chỉ xuất hiện khi rê chuột. Mã media ngay sau khi sinh (`flow-content.google/...`) khác với mã sau khi tải lại trang (`flow.google.com/asb/...`, giữ nguyên qua các lần tải lại). Vì vậy tool tải lại trang một lần rồi lưu mã ổn định làm `video_ref`.
- **Tải xuống:** "More options" → "Download" → 270p GIF / 720p Original size / 1080p Upscaled / 4K Upscaled. Trên tài khoản này, 1080p và 4K bị khoá (`disabled`), nên tool tự lùi về Original size (720p). Video gốc có watermark ✦ của Flow ở góc dưới bên phải.
- **Bước enhance trên M1:** clip 720×1280, 10 giây, 24fps ra 2160×3840 60fps có âm thanh trong **54 giây** (45MB).
- **Tách nền BiRefNet:** lần đầu 32 giây (nạp mô hình 1GB). **Upscale** 8 giây. **Prompt** (`claude -p` với `--setting-sources ""`, vẫn dùng đăng nhập OAuth) 12–15 giây.
- **Rà soát code:** đã sửa lỗi gửi lên Flow hai lần sau sự cố và lỗi cạnh tranh giữa huỷ và thử lại (khoá trạng thái theo `active_job_id`). API thêm `TrustedHostMiddleware` và kiểm tra `Origin`. Có kiểm thử hồi quy trong `backend/tests/test_review_regressions.py`.

## 15. Nhận link TikTok Shop qua Telegram (thêm 2026-10-15)

Đã chốt với người dùng:
- Telegram chỉ là kênh **nhận link**. Ảnh được chọn trên giao diện của tool, không chọn trên điện thoại. Bot chỉ trả lời "Đã nhận".
- Chỉ xử lý link sản phẩm **TikTok Shop**.
- Đọc trang bằng Chrome riêng của tool (hướng A).

Thiết kế:
- **Bot:** `telegram/telegram_listener.py` hỏi tin mới (long-poll `getUpdates`) trong một luồng nền, không cần cổng mở hay địa chỉ công khai.
  - Chỉ nhận tin từ `telegram.allowed_user_ids`. Người lạ nhắn `/start` thì nhận lại ID của họ; tin khác thì bot im lặng.
  - Vị trí tin đã đọc lưu ở `jobs/.telegram-offset`, khởi động lại không xử lý trùng.
  - Token lấy từ biến môi trường `TELEGRAM_BOT_TOKEN` (có thể đặt trong file env ở thư mục dự án), không bao giờ hiện trong thông báo lỗi.
- **Job từ link:** thêm bước 0 `fetch_source` và điểm dừng `pick_image` (luôn dừng chờ người dùng).
  - Job từ link bật tự động cả 3 điểm duyệt cũ (`telegram.auto_review`).
  - Một link đang chờ hoặc đang chạy mà gửi lại thì bỏ qua.
  - Job tải ảnh như cũ vẫn bắt đầu từ `cutout`.
- **Đọc trang** (`sources/product_page_reader.py`): không bám vào selector cụ thể.
  - Lấy `og:title`, `og:description`, `og:image`, cùng các ảnh trên trang có cả hai cạnh từ 500px.
  - Bỏ ảnh trùng theo đường dẫn trước dấu `~` (biến thể kích thước trên CDN của TikTok). Tối đa 12 ảnh, lưu thành `candidates/NN.jpg`.
  - Nhận ra trang chặn của tường lửa, captcha, trang yêu cầu đăng nhập và lỗi HTTP, rồi báo lỗi bằng tiếng Việt kèm ảnh chụp màn hình.
- **Chọn ảnh** (`POST /api/jobs/{id}/pick`): chọn một ảnh trong `candidates`, hoặc tải ảnh của mình lên (dùng được cả khi bước đọc TikTok bị lỗi). Thông tin sản phẩm sửa được và được gửi cho Claude cùng ảnh khi viết prompt.
- **Lối khác:** `POST /api/links` (ô dán link trên giao diện) hoạt động giống như gửi link qua Telegram. Máy Mac bật thông báo khi có sản phẩm chờ chọn ảnh.

**Gửi kết quả về Telegram** (người dùng yêu cầu thêm, thay cho quyết định ban đầu "chỉ báo đã nhận"):
- Bước cuối `send_telegram` chỉ chạy với job có `telegram` (lưu `chat_id` và `message_id` của tin chứa link). Với các job khác, bước này không làm gì và giao diện cũng không hiện nó.
- Bot trả lời ngay dưới tin gốc (`reply_parameters`, vẫn gửi được nếu tin gốc đã bị xoá):
  1. Video 1080p H.264, tạo bằng `libx264` với CRF 19. Clip 10 giây ra khoảng 4.5MB, tạo trong khoảng 11 giây. Chú thích gồm tên sản phẩm, link và tên file 4K.
  2. File 4K gốc dạng tệp đính kèm nếu không quá 50MB (giới hạn Bot API). Vượt quá thì gửi một dòng ghi đường dẫn file trên Mac.
- Phần nào gửi xong thì được đánh dấu (`preview_sent`, `file_sent`), nên bấm "Thử lại" chỉ gửi phần còn thiếu. Gửi lỗi không làm mất video đã xuất.

Bảo mật (sau đợt rà soát):
- **Văn bản trên trang shop không đáng tin.** Bước prompt gọi `claude -p` **không có công cụ nào** (`--tools ""`). Ảnh được gửi kèm ngay trong tin nhắn (`--input-format stream-json`). Thông tin sản phẩm được rào trong thẻ `<shop_page>` kèm yêu cầu bỏ qua mọi câu lệnh bên trong. Đã thử chạy thật với một câu lệnh độc hại: Claude bỏ qua và không đọc được file nào.
- **Ảnh:** chỉ tải ảnh qua `https`, không tải từ IP thô hay localhost. Tối đa 15MB và 40 triệu điểm ảnh mỗi ảnh. Trang sau khi chuyển hướng phải vẫn thuộc `tiktok.com`.
- **Telegram:**
  - Một tin xử lý lỗi không chặn các tin sau (vị trí đã đọc luôn được lưu).
  - Lần chạy đầu bỏ qua các tin cũ tồn đọng.
  - Không để thư viện HTTP ghi log URL có chứa token.
- **Chọn ảnh:** chuẩn bị file và kiểm tra có đúng là ảnh hay không ở bên ngoài khoá; trong khoá chỉ đổi tên file và cập nhật trạng thái.

Kiểm chứng:
- Chạy thật bước đọc TikTok bằng Chrome trên trang HTML mẫu: đạt.
- Link thật của người dùng (`shop.tiktok.com/vn/pdp/1737628275640009880`) trên mạng công ty bị **FortiGate Application Control chặn** (TikTok, Social.Media). Tool báo đúng lý do. **Chưa đọc được trang TikTok Shop thật nào**: cần chạy `python -m app.sources.check_product_page <link>` trên một mạng cho phép TikTok.
