# Đăng TikTok ngay / lên lịch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sau khi job tạo từ link TikTok Shop xong, người dùng bấm **Đăng ngay** hoặc **Lên lịch** (trên tool hoặc Telegram) để tool tự đăng video lên TikTok Studio: mô tả = tên + hashtag thật, gắn link sản phẩm theo ID, bật nhãn AI, chọn Now hoặc khung giờ trống kế tiếp, bấm Post/Schedule, xác nhận trên trang Content, rồi báo kết quả lên tool và Telegram.

**Architecture:** Thêm bước cuối `tiktok_post` vào pipeline hiện có; bước này không làm gì (chỉ gửi 2 nút lên Telegram) cho tới khi `request_post()` ghi `job.post.mode` và cho job vào hàng chờ lại. Thao tác trình duyệt nằm trong `tiktok/` (form tải lên dùng chung với bước lưu nháp, phần đăng, đọc JSON trang Content); phần thuần (khung giờ, ID sản phẩm, so khớp bài) tách riêng để test không cần Chrome. `submitted_at` được ghi ngay trước cú bấm, `done_at` chỉ khi thấy bài trên trang Content, nên Thử lại / khởi động lại không bao giờ tự bấm Post lần hai.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Playwright 1.64 (sync, CDP vào Chrome riêng của tool), pytest; React 19 + TypeScript + Vite.

**Spec:** `docs/superpowers/specs/2026-10-17-tiktok-post-schedule-design.md` (đọc §6, §7, §8, §9, §12 trước khi làm task trình duyệt).

## Global Constraints

- Nhánh `tiktok-post-schedule`. Mỗi task kết thúc bằng một commit; message kiểu câu tiếng Anh như lịch sử repo (ví dụ "Hashtags checked on TikTok, asked by the main product type"), dòng cuối: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Test backend: `cd backend && ../.venv/bin/python -m pytest -q` (151 test pass lúc bắt đầu). Frontend: `cd frontend && npm run build`.
- Chữ người dùng thấy: tiếng Việt có dấu. Comment trong code: tiếng Anh, ngắn, ít như code xung quanh.
- **Task 1–9 không được chạm Chrome thật / TikTok thật:** không chạy `check_post`, không kết nối cổng 9222, không mở trang TikTok. Test dùng giả lập. Chạy thử trên trang thật là Task 10, chỉ sau khi người dùng đồng ý và tool không có job nào đang chạy.
- Mọi thao tác trình duyệt chỉ trong tab nền tạo bằng `new_tab()` (`app/flow/cdp_connection.py`); không dùng `context.new_page()` hay `bring_to_front()` (kéo Chrome lên trước công việc của người dùng).
- Tool chỉ bấm nút Post/Schedule ở đúng một chỗ: trong `post_video()` sau khi `before_click()` đã lưu `submitted_at`. Chạy thử (`dry_run`) không bao giờ bấm.
- Selector và chữ tiếng Anh của giao diện TikTok nằm trong `tiktok-selectors.yaml` (dạng `{css: …}`, `{role: …, name: …, exact: true}`, `{text: …}`; `{value}` được thay bằng tham số), không viết cứng trong code. Ngoại lệ: cấu trúc JSON của trang Content (`studio_content.py`).
- Khung giờ: `[7, 9, 11, 13, 15, 17, 19, 21, 23]`, đệm `20` phút, giới hạn `MAX_DAYS_AHEAD = 30` ngày, giờ máy Mac.
- Không khởi động lại tool đang chạy (cổng 8765); việc đó hỏi người dùng ở Task 10.

## Review Focus

- Khung giờ qua cuối tháng / cuối năm (31/10 23:30 → 07:00 1/11; 31/12 → 1/1) phải ra đúng ngày → test trong Task 1.
- Job lưu trước khi có tính năng (state.json không có `post`, `product_id`) phải tải được, không có nút sai, lấy ID từ link `/pdp/` → test trong Task 1.
- Bấm nút của tin Telegram cũ sau khi video đã làm lại (trạng thái đăng đã xoá) → toast "Nút này đã cũ…", không đăng gì → test trong Task 5.
- Hashtag không có trong gợi ý của TikTok → để dạng chữ, không bấm Enter (Enter lúc đó có thể chọn nhầm tag khác), vẫn đăng tiếp → test trong Task 3.
- TikTok đổi dấu câu trong mô tả ("Dép sục+Tặng" → "Dép sục Tặng") → vẫn xác nhận được bài vừa đăng → test trong Task 2.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/app/job_models.py` (sửa) | `STEPS` thêm `tiktok_post`; `TikTokPostState`; `SourceInfo.product_id`; `JobState.post` |
| `backend/app/config.py`, `config.yaml` (sửa) | `tiktok.post_url`, `content_url`, `schedule_slots`, `schedule_lead_min` |
| `backend/app/tiktok/post_plan.py` (mới) | Thuần: ID sản phẩm, tên đăng, `next_slot`, `too_far`, `slot_label` |
| `backend/app/tiktok/studio_content.py` (mới) | Đọc JSON trang Content: thời gian muộn nhất, tìm bài vừa đăng |
| `backend/app/tiktok/studio_upload.py` (sửa) | Tách các bước form tải lên dùng chung; `save_draft` dùng lại |
| `backend/app/tiktok/studio_post.py` (mới) | Form đăng: hashtag từ gợi ý, Add link, nhãn AI, When to post, kiểm tra, bấm |
| `tiktok-selectors.yaml` (sửa) | Selector mới theo khảo sát 2026-10-17 |
| `backend/app/link_job_actions.py`, `job_actions.py`, `pipeline_runner.py`, `api/jobs_routes.py` (sửa) | `request_post`, Thử lại, khởi động lại, `POST /api/jobs/{id}/post` |
| `backend/app/telegram/telegram_post.py` (mới) | 2 nút, chữ các trạng thái, gửi/sửa tin nút, `PostHandler` |
| `backend/app/telegram/telegram_api.py`, `telegram_setup.py`, `telegram_notify.py` (sửa) | `send_message(reply_markup=)`, chia lượt bấm theo tiền tố, tin "Đang" |
| `backend/app/steps/tiktok_post_step.py` (mới), `step_registry.py` (sửa) | Bước `tiktok_post`: kế hoạch, `BrowserStudio`, xác nhận, báo Telegram |
| `backend/app/steps/fetch_product_step.py` (sửa) | Lưu `source.product_id` |
| `backend/app/tiktok/check_post.py` (mới) | Lệnh chạy thử, dừng trước cú bấm |
| `frontend/src/api-client.ts`, `components/job-detail-panel.tsx`, `styles.css` (sửa) | 2 nút, dòng kết quả, xác nhận Thử lại |
| `README.md` (sửa) | Hướng dẫn |

---

### Task 1: Dữ liệu, cấu hình và các hàm thuần của việc đăng

**Files:**
- Modify: `backend/app/job_models.py`
- Modify: `backend/app/config.py` (class `TikTokConfig`)
- Modify: `config.yaml` (mục `tiktok:`)
- Create: `backend/app/tiktok/post_plan.py`
- Modify: `backend/app/steps/fetch_product_step.py` (hàm `save` trong `run_fetch_product`)
- Test: `backend/tests/test_post_plan.py`

**Interfaces:**
- Produces:
  - `job_models.STEPS[-1] == "tiktok_post"`
  - `class TikTokPostState(BaseModel)`: `mode: Literal["now","schedule"] | None`, `requested_at: str | None`, `scheduled_for: str | None` (ISO giờ máy, ví dụ `"2026-10-18T19:00:00"`), `submitted_at: str | None`, `done_at: str | None`, `notified: bool`, `offer_token: str | None`, `offer_message: TelegramMessageRef | None`
  - `SourceInfo.product_id: str = ""`; `JobState.post: TikTokPostState`
  - `TikTokConfig.post_url: str`, `content_url: str`, `schedule_slots: list[int]` (đã sắp xếp, không trùng), `schedule_lead_min: int`
  - `post_plan.MAX_DAYS_AHEAD = 30`
  - `post_plan.product_id_from_url(url: str) -> str`, `job_product_id(job: JobState) -> str`, `post_title(job: JobState) -> str`
  - `post_plan.next_slot(now: datetime, slots: list[int], lead_min: int, taken: Iterable[datetime | None]) -> datetime`
  - `post_plan.too_far(slot: datetime, now: datetime) -> bool`, `slot_label(when: datetime, weekday: bool = True) -> str`

- [ ] **Step 1: Viết test (fail)**

Tạo `backend/tests/test_post_plan.py`:

```python
"""What gets posted on TikTok and when: product ID, title, the next free schedule slot (pure helpers)."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.config import TikTokConfig
from app.job_models import STEPS, JobState, SourceInfo, TikTokPostState
from app.tiktok.post_plan import (MAX_DAYS_AHEAD, job_product_id, next_slot, post_title, product_id_from_url,
                                  slot_label, too_far)

SLOTS = [7, 9, 11, 13, 15, 17, 19, 21, 23]
NOW = datetime(2026, 10, 17, 10, 0)  # Saturday


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute)


def job(**kw) -> JobState:
    return JobState(id="t", name="giay", input_file="input.jpg", created_at="t", **kw)


def test_next_slot_examples_from_the_spec():
    assert next_slot(NOW, SLOTS, 20, [at(17, 8, 30)]) == at(17, 11)
    assert next_slot(NOW, SLOTS, 20, [at(17, 10, 50)]) == at(17, 11)
    assert next_slot(NOW, SLOTS, 20, [at(17, 11)]) == at(17, 13)  # strictly after the latest post
    assert next_slot(NOW, SLOTS, 20, [at(17, 21, 30)]) == at(17, 23)
    assert next_slot(NOW, SLOTS, 20, [at(17, 23)]) == at(18, 7)  # no slot left that day
    assert next_slot(NOW, SLOTS, 20, []) == at(17, 11)
    assert next_slot(at(17, 10, 45), SLOTS, 20, []) == at(17, 13)  # 11:00 is closer than 20 minutes


def test_next_slot_takes_the_latest_of_everything_and_skips_missing_values():
    assert next_slot(NOW, SLOTS, 20, [None, at(17, 13), at(17, 17)]) == at(17, 19)
    assert next_slot(at(17, 23, 50), SLOTS, 20, []) == at(18, 7)
    assert next_slot(NOW, [19, 7], 20, [at(17, 20)]) == at(18, 7)  # config order does not matter


def test_next_slot_rolls_over_month_and_year():
    assert next_slot(datetime(2026, 10, 31, 23, 30), SLOTS, 20, []) == datetime(2026, 11, 1, 7)
    assert next_slot(datetime(2026, 12, 31, 22), SLOTS, 20, [datetime(2026, 12, 31, 23)]) == datetime(2027, 1, 1, 7)


def test_too_far_matches_tiktoks_30_day_calendar():
    assert MAX_DAYS_AHEAD == 30
    assert not too_far(datetime(2026, 11, 16, 23), NOW)  # 17/10 + 30 days = 16/11, still offered
    assert too_far(datetime(2026, 11, 17, 7), NOW)


def test_slot_label_is_vietnamese():
    assert slot_label(at(18, 19)) == "19:00 Chủ nhật 18/10"
    assert slot_label(at(17, 7)) == "07:00 thứ Bảy 17/10"
    assert slot_label(at(19, 9)) == "09:00 thứ Hai 19/10"
    assert slot_label(at(18, 19), weekday=False) == "19:00 18/10"


def test_product_id_from_links():
    assert product_id_from_url("https://shop.tiktok.com/vn/pdp/1737477284468917824?_t=ZS-9AcOmdV11T0") \
        == "1737477284468917824"
    assert product_id_from_url("https://shop.tiktok.com/vn/pdp/giay-mary-jane/1737477284468917824") \
        == "1737477284468917824"
    assert product_id_from_url("https://shop.tiktok.com/view/product/1729384756102938475") == "1729384756102938475"
    assert product_id_from_url("https://vt.tiktok.com/ZS9UDYUDtqn7v-WCASA") == ""
    assert product_id_from_url("") == ""


def test_job_product_id_prefers_the_saved_id_then_the_link():
    short = SourceInfo(url="https://vt.tiktok.com/ZS9UDYUDtqn7v-WCASA", product_id="1737383451447231991")
    assert job_product_id(job(source=short)) == "1737383451447231991"
    pdp = SourceInfo(url="https://shop.tiktok.com/vn/pdp/1735751598590428933?_t=x")
    assert job_product_id(job(source=pdp)) == "1735751598590428933"
    assert job_product_id(job(source=SourceInfo(url="https://vt.tiktok.com/x"))) == ""
    assert job_product_id(job()) == ""


def test_jobs_saved_before_posting_existed_still_load():
    old = {"id": "t", "name": "giay", "input_file": "input.jpg", "created_at": "t",
           "source": {"url": "https://shop.tiktok.com/vn/pdp/1735751598590428933", "title": "Giày"}}
    loaded = JobState.model_validate(old)
    assert loaded.post == TikTokPostState() and loaded.post.mode is None
    assert loaded.source.product_id == "" and job_product_id(loaded) == "1735751598590428933"


def test_post_title_and_step_order():
    assert post_title(job(source=SourceInfo(url="u", title="  Giày Mary Jane  "))) == "Giày Mary Jane"
    assert post_title(job()) == "giay"
    assert STEPS[-2:] == ["tiktok_draft", "tiktok_post"]


def test_tiktok_config_defaults_and_checks():
    cfg = TikTokConfig()
    assert cfg.schedule_slots == SLOTS and cfg.schedule_lead_min == 20
    assert cfg.post_url == "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video"
    assert cfg.content_url == "https://www.tiktok.com/tiktokstudio/content"
    assert TikTokConfig(schedule_slots=[21, 7, 7]).schedule_slots == [7, 21]
    with pytest.raises(ValidationError):
        TikTokConfig(schedule_slots=[25])
    with pytest.raises(ValidationError):
        TikTokConfig(schedule_lead_min=5)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_post_plan.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tiktok.post_plan'` (và `ImportError` cho `TikTokPostState`).

- [ ] **Step 3: Sửa `backend/app/job_models.py`**

Thêm import ở đầu file (sau `from enum import Enum`):

```python
from typing import Literal
```

Thay khối comment + `STEPS`:

```python
# "fetch_source" only runs for jobs created from a TikTok Shop link; upload jobs start at "cutout".
# "send_telegram" only does work for jobs that came from Telegram; for the others it is a no-op.
# "tiktok_draft" saves the video as a TikTok Studio draft (never posts) when tiktok.save_draft is on.
# "hashtags" asks Google's AI Mode (Claude as fallback) for 3 hashtags; it never fails the job.
# "tiktok_post" posts or schedules the video on TikTok, only after the user pressed Đăng ngay / Lên lịch;
# until then it only sends those two buttons to Telegram.
STEPS = ["fetch_source", "cutout", "upscale", "prompt", "flow_generate", "flow_download", "enhance", "export",
         "hashtags", "send_telegram", "tiktok_draft", "tiktok_post"]
```

Trong `class SourceInfo`, thêm sau dòng `candidates`:

```python
    product_id: str = ""  # from the page address after redirects; short vt.tiktok.com links carry none
```

Thêm ngay sau `class TikTokDraftState`:

```python
class TikTokPostState(BaseModel):
    """Đăng ngay / Lên lịch, started by a button in the tool or on Telegram. submitted_at is saved right before
    Post/Schedule is clicked and done_at once the post shows on TikTok Studio, so the tool never clicks twice."""

    mode: Literal["now", "schedule"] | None = None  # None = nobody asked: the step only offers the buttons
    requested_at: str | None = None
    scheduled_for: str | None = None  # local time, e.g. "2026-10-18T19:00:00"
    submitted_at: str | None = None
    done_at: str | None = None
    notified: bool = False  # result message sent on Telegram
    offer_token: str | None = None  # carried in the Telegram button data
    offer_message: TelegramMessageRef | None = None  # the message with the two buttons
```

Trong `class JobState`, thêm sau dòng `tiktok: TikTokDraftState = ...`:

```python
    post: TikTokPostState = Field(default_factory=TikTokPostState)
```

- [ ] **Step 4: Sửa `TikTokConfig` trong `backend/app/config.py`**

```python
class TikTokConfig(BaseModel):
    save_draft: bool = True  # after export: upload to TikTok Studio and Save draft (never Post)
    upload_url: str = "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video"
    post_url: str = "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video"
    content_url: str = "https://www.tiktok.com/tiktokstudio/content"
    schedule_slots: list[int] = Field(default_factory=lambda: [7, 9, 11, 13, 15, 17, 19, 21, 23], min_length=1)
    schedule_lead_min: int = Field(20, ge=15)  # TikTok Studio only offers times about 15 minutes ahead or later
    ai_generated_label: bool = True  # TikTok may take down realistic AI video that is not labelled
    timeout_sec: int = Field(600, ge=60)  # upload + processing of the exported file

    @field_validator("schedule_slots")
    @classmethod
    def _hours(cls, value: list[int]) -> list[int]:
        if any(not 0 <= hour <= 23 for hour in value):
            raise ValueError("schedule_slots: giờ phải từ 0 đến 23")
        return sorted(set(value))
```

- [ ] **Step 5: Sửa mục `tiktok:` trong `config.yaml`**

Thay khối `tiktok:` bằng:

```yaml
tiktok:                      # TikTok Studio, trong Chrome của tool (phải đăng nhập TikTok trước)
  save_draft: false          # LƯU NHÁP sau khi xuất file (không bao giờ bấm Post). TẠM TẮT; bật lại: true
  ai_generated_label: true   # bật nhãn "AI-generated content"; TikTok có thể gỡ video AI trông như thật mà không gắn nhãn
  timeout_sec: 600           # thời gian tối đa chờ tải video lên
  # Nút "Đăng ngay" / "Lên lịch" (trên tool và Telegram) dùng các mục dưới:
  post_url: https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video
  content_url: https://www.tiktok.com/tiktokstudio/content    # đọc giờ của bài muộn nhất khi lên lịch
  schedule_slots: [7, 9, 11, 13, 15, 17, 19, 21, 23]          # khung giờ lên lịch (giờ máy); hết khung thì sang ngày sau
  schedule_lead_min: 20      # khung giờ phải cách bây giờ ít nhất chừng này phút (TikTok cần ≥ 15)
```

- [ ] **Step 6: Tạo `backend/app/tiktok/post_plan.py`**

```python
"""What gets posted on TikTok and when: product ID, title, the next free schedule slot. Pure, no browser."""

import re
from collections.abc import Iterable
from datetime import datetime, timedelta

from ..job_models import JobState

PRODUCT_ID = re.compile(r"/(?:pdp|product)/(?:[^/?#]+/)?(\d{10,})")
MAX_DAYS_AHEAD = 30  # TikTok Studio's calendar offered today + 30 days (surveyed 2026-10-17)
WEEKDAYS = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]


def product_id_from_url(url: str) -> str:
    match = PRODUCT_ID.search(url or "")
    return match.group(1) if match else ""


def job_product_id(job: JobState) -> str:
    """Saved when the product page was read; older jobs fall back to their link when it is a /pdp/ link."""
    if not job.source:
        return ""
    return job.source.product_id or product_id_from_url(job.source.url)


def post_title(job: JobState) -> str:
    return ((job.source.title if job.source else "") or job.name).strip()


def next_slot(now: datetime, slots: list[int], lead_min: int, taken: Iterable[datetime | None]) -> datetime:
    """First slot strictly after the latest post already there (on TikTok or scheduled by this tool) and at
    least lead_min minutes from now; past the day's last slot, the first slot of the next day."""
    floor = max([now + timedelta(minutes=lead_min), *(t for t in taken if t)])
    day = floor.replace(hour=0, minute=0, second=0, microsecond=0)
    hours = sorted(set(slots))
    for hour in hours:
        if day.replace(hour=hour) > floor:
            return day.replace(hour=hour)
    return day + timedelta(days=1, hours=hours[0])


def too_far(slot: datetime, now: datetime) -> bool:
    return slot.date() > (now + timedelta(days=MAX_DAYS_AHEAD)).date()


def slot_label(when: datetime, weekday: bool = True) -> str:
    """'19:00 Chủ nhật 18/10' for messages; weekday=False gives the short '19:00 18/10'."""
    day = f" {WEEKDAYS[when.weekday()]}" if weekday else ""
    return f"{when:%H:%M}{day} {when:%d/%m}"
```

- [ ] **Step 7: Lưu ID sản phẩm khi đọc trang (`backend/app/steps/fetch_product_step.py`)**

Thêm import:

```python
from ..tiktok.post_plan import product_id_from_url
```

Trong hàm `save` của `run_fetch_product`, thêm dòng sau dòng gán `j.source.title, ...`:

```python
        j.source.product_id = product_id_from_url(product.url) or product_id_from_url(j.source.url)
```

- [ ] **Step 8: Chạy test, xác nhận pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_post_plan.py -q`
Expected: PASS (10 test).

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: toàn bộ pass (các test pipeline tự gồm bước mới vì chúng dựng bước giả từ `STEPS`).

- [ ] **Step 9: Commit**

```bash
git add backend/app/job_models.py backend/app/config.py config.yaml backend/app/tiktok/post_plan.py \
        backend/app/steps/fetch_product_step.py backend/tests/test_post_plan.py
git commit -m "Post state, schedule slots and product ID for posting on TikTok

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Đọc trang Content của TikTok Studio

**Files:**
- Create: `backend/app/tiktok/studio_content.py`
- Test: `backend/tests/test_studio_content.py`

**Interfaces:**
- Consumes: không có.
- Produces:
  - `class ContentPageError(Exception)` (thông điệp tiếng Việt cho người dùng)
  - `items_from_html(page_html: str) -> list[dict]`
  - `item_time(item: dict) -> datetime | None`, `latest_time(items: list[dict]) -> datetime | None`
  - `find_new_post(items: list[dict], title: str, since: datetime, scheduled_for: datetime | None) -> dict | None`
  - `read_items(page, url: str) -> list[dict]` (Playwright page)

- [ ] **Step 1: Viết test (fail)**

Tạo `backend/tests/test_studio_content.py`:

```python
"""TikTok Studio's Content page: the embedded post list (saved HTML, no browser)."""

import html
import json
from datetime import datetime

import pytest

from app.tiktok.studio_content import ContentPageError, find_new_post, item_time, items_from_html, latest_time


def epoch(day, hour, minute=0, month=10):
    return str(int(datetime(2026, month, day, hour, minute).timestamp()))


def page(items) -> str:
    # Shaped like the real page (2026-10-17): HTML-escaped JSON in a script tag.
    payload = json.dumps({"appContext": {"x": 1},
                          "firstBatchQueryItems": {"cursor": 5, "has_more": True, "item_list": items}})
    return ('<html><head><script type="application/json" id="__Creator_Center_Context__">'
            f"{html.escape(payload)}</script></head><body></body></html>")


SCHEDULED = {"desc": "0807 (1)", "create_time": epoch(17, 10, 3), "post_time": epoch(17, 11, 20),
             "schedule_time": epoch(17, 11, 20), "status": 140, "is_pinned": False}
PINNED_OLD = {"desc": "Váy Nữ #vay", "create_time": epoch(9, 6, 10, 8), "post_time": epoch(9, 6, 10, 8),
              "status": 102, "is_pinned": True}
POSTED = {"desc": "Giày Thể Thao Nữ #giaydepnu", "create_time": epoch(17, 9, 5), "post_time": epoch(17, 9, 5),
          "status": 102, "is_pinned": False}


def test_reads_the_embedded_post_list():
    items = items_from_html(page([SCHEDULED, PINNED_OLD, POSTED]))
    assert [i["desc"] for i in items] == ["0807 (1)", "Váy Nữ #vay", "Giày Thể Thao Nữ #giaydepnu"]


def test_latest_time_is_the_max_not_the_first_row():
    # Pinned posts sit above newer ones; scheduled posts sit above everything.
    assert latest_time(items_from_html(page([PINNED_OLD, POSTED]))) == datetime(2026, 10, 17, 9, 5)
    assert latest_time(items_from_html(page([SCHEDULED, PINNED_OLD, POSTED]))) == datetime(2026, 10, 17, 11, 20)
    assert latest_time([]) is None
    assert item_time({"post_time": "0", "create_time": epoch(17, 8)}) == datetime(2026, 10, 17, 8)
    assert item_time({"schedule_time": None, "post_time": epoch(17, 8)}) == datetime(2026, 10, 17, 8)


def test_missing_or_broken_list_is_an_error_not_a_guess():
    with pytest.raises(ContentPageError):
        items_from_html("<html><body>Log in to TikTok</body></html>")
    with pytest.raises(ContentPageError):
        items_from_html('<script type="application/json" id="__Creator_Center_Context__">{not json</script>')
    with pytest.raises(ContentPageError):
        items_from_html('<script type="application/json" id="__Creator_Center_Context__">{"a": 1}</script>')


def test_finds_the_post_just_made_even_when_tiktok_changes_punctuation():
    title = "[JOLY 01] Dép sục+Tặng 1 bộ charm ngẫu nhiên"
    ours = {"desc": "[JOLY 01] Dép sục Tặng 1 bộ charm ngẫu nhiên #giaydepnu ", "create_time": epoch(17, 10, 31),
            "post_time": epoch(18, 19), "schedule_time": epoch(18, 19), "status": 140}
    clicked = datetime(2026, 10, 17, 10, 32)  # created a minute before the recorded click: clock skew is allowed
    assert find_new_post([POSTED, ours], title, clicked, datetime(2026, 10, 18, 19)) is ours
    assert find_new_post([POSTED, ours], title, clicked, datetime(2026, 10, 18, 21)) is None  # another slot
    assert find_new_post([POSTED, ours], title, datetime(2026, 10, 17, 11), None) is None  # older than the click
    now_post = {**ours, "schedule_time": None, "post_time": epoch(17, 10, 31), "status": 102}
    assert find_new_post([now_post], title, clicked, None) is now_post
    assert find_new_post([POSTED], title, clicked, None) is None
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_studio_content.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tiktok.studio_content'`.

- [ ] **Step 3: Tạo `backend/app/tiktok/studio_content.py`**

```python
"""TikTok Studio's Content page: when the latest post goes (or went) out, and whether a new post is there.

Surveyed 2026-10-17: the page embeds its first batch of posts as HTML-escaped JSON in
<script id="__Creator_Center_Context__" type="application/json"> under firstBatchQueryItems.item_list.
Each item has desc, create_time, post_time (epoch seconds; for a scheduled post the time it goes out),
schedule_time (scheduled posts only), status (140 = scheduled, 102 = public) and is_pinned.
Order: scheduled first, then pinned, then the rest newest first, so the latest time is the max, not the first row.
"""

import html as html_lib
import json
import re
from datetime import datetime, timedelta

CONTEXT_SCRIPT = re.compile(r'<script[^>]*id="__Creator_Center_Context__"[^>]*>(.*?)</script>', re.S)
CLOCK_SKEW = timedelta(minutes=2)


class ContentPageError(Exception):
    """The Content page could not be read; message is meant for the user."""


def read_items(page, url: str) -> list[dict]:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if "/login" in page.url:
        raise ContentPageError("Chrome của tool chưa đăng nhập TikTok. Đăng nhập TikTok trong cửa sổ Chrome đó "
                               "rồi bấm 'Thử lại'.")
    try:
        page.locator("#__Creator_Center_Context__").wait_for(state="attached", timeout=20000)
    except Exception:
        pass  # items_from_html explains what is missing
    return items_from_html(page.content())


def items_from_html(page_html: str) -> list[dict]:
    match = CONTEXT_SCRIPT.search(page_html or "")
    if not match:
        raise ContentPageError("Không thấy danh sách bài trên trang Content của TikTok Studio (TikTok đổi giao diện?).")
    try:
        data = json.loads(html_lib.unescape(match.group(1)))
    except ValueError as exc:
        raise ContentPageError("Danh sách bài trên trang Content của TikTok Studio không đọc được.") from exc
    batch = _find(data, "firstBatchQueryItems")
    if not isinstance(batch, dict) or not isinstance(batch.get("item_list"), list):
        raise ContentPageError("Trang Content của TikTok Studio không có danh sách bài như mong đợi.")
    return batch["item_list"]


def item_time(item: dict) -> datetime | None:
    """When the post goes out (scheduled) or went out, local time."""
    for key in ("schedule_time", "post_time", "create_time"):
        try:
            value = int(item.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return datetime.fromtimestamp(value)
    return None


def latest_time(items: list[dict]) -> datetime | None:
    times = [t for t in map(item_time, items) if t]
    return max(times) if times else None


def find_new_post(items: list[dict], title: str, since: datetime, scheduled_for: datetime | None) -> dict | None:
    """The post the tool just made: its description starts with the product title (punctuation aside: TikTok
    turned "sục+Tặng" into "sục Tặng"), it was created after `since` and, when scheduled, goes out at
    `scheduled_for`."""
    head = _words(title)[:40]
    for item in items:
        try:
            created = datetime.fromtimestamp(int(item.get("create_time") or 0))
        except (TypeError, ValueError):
            continue
        if created < since - CLOCK_SKEW or not _words(item.get("desc", "")).startswith(head):
            continue
        if scheduled_for and item_time(item) != scheduled_for:
            continue
        return item
    return None


def _words(text: str) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", text or "").casefold().split())


def _find(node, key: str):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            found = _find(child, key)
            if found is not None:
                return found
    return None
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_studio_content.py -q`
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/tiktok/studio_content.py backend/tests/test_studio_content.py
git commit -m "Read the post list embedded in TikTok Studio's Content page

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Form đăng trên TikTok Studio (dùng chung form tải lên với bước lưu nháp)

**Files:**
- Modify: `backend/app/tiktok/studio_upload.py` (viết lại toàn file như dưới)
- Create: `backend/app/tiktok/studio_post.py`
- Modify: `tiktok-selectors.yaml`
- Test: `backend/tests/test_studio_post.py`

**Interfaces:**
- Consumes: `post_plan.slot_label` (Task 1).
- Produces (`studio_upload`): `StudioError`, `MAX_DESCRIPTION`, `load_selectors(selectors=None) -> (FlowSelectors, dict[str, re.Pattern])`, `open_upload_form(page, sel, texts, url)`, `upload_video(page, sel, texts, video: Path, timeout_sec: int)`, `wait_until(page, condition, seconds) -> bool`, `has_description(page, sel, text) -> bool`, `fill_description(page, sel, text, video, log)`, `dismiss(page, sel)`, `ai_label_on(page, row_text) -> bool`, `turn_on_ai_label(page, sel, row_text)`, `save_draft(...)` (chữ ký cũ, không đổi).
- Produces (`studio_post`):
  - `@dataclass PostPlan(video: Path, title: str, hashtags: list[str], product_id: str, schedule_at: datetime | None = None)`
  - `class ProductNotFound(StudioError)`
  - `post_video(page, cfg: TikTokConfig, plan: PostPlan, report, log, before_click: Callable[[], None], dry_run: bool = False, selectors=None) -> None`
  - thuần: `invalid_chars(message: str, pattern: re.Pattern) -> list[str]`, `clean_product_name(name: str, bad: list[str]) -> str`, `button_label(sel, schedule: bool) -> str`, `pick_suggestion(page, sel, tag: str, wait_sec: float = 6.0) -> bool`

- [ ] **Step 1: Viết test (fail)**

Tạo `backend/tests/test_studio_post.py`:

```python
"""Pure parts of the TikTok Studio post form, and the selectors file it relies on (no browser)."""

import re

from app.tiktok.studio_post import button_label, clean_product_name, invalid_chars, pick_suggestion
from app.tiktok.studio_upload import load_selectors

INVALID = re.compile(r"invalid characters?:\s*(.+)", re.I)


def test_invalid_characters_are_read_from_tiktoks_message():
    assert invalid_chars("Product name\nRemove invalid characters: +\n30/30", INVALID) == ["+"]
    assert invalid_chars("Remove invalid characters: + & +", INVALID) == ["+", "&"]
    assert invalid_chars("Product name\n30/30", INVALID) == []


def test_product_name_is_cleaned_and_kept_short():
    assert clean_product_name("[JOLY 01] Dép sục+Tặng 1 bộ ch", ["+"]) == "[JOLY 01] Dép sục Tặng 1 bộ ch"
    assert len(clean_product_name("a&" * 40, ["&"])) <= 30
    assert clean_product_name("+++", ["+"]) == "Sản phẩm"


def test_selectors_file_has_every_key_the_post_uses():
    sel, texts = load_selectors()
    for key in ["file_input", "upload_status", "description_editor", "show_more", "ai_label_confirm",
                "save_draft_button", "post_button", "add_link_button", "anchor_container", "link_dialog",
                "product_dialog", "product_search", "product_rows", "product_id_cell", "product_radio",
                "product_name_input", "dialog_next", "dialog_add", "dialog_cancel", "schedule_container",
                "when_option", "when_input", "calendar", "calendar_month", "calendar_year", "calendar_arrow",
                "calendar_day", "hashtag_topics", "hashtag_selected", "hashtag_done"]:
        assert sel.spec(key)
    assert {"login_page", "upload_done", "ai_label_row", "draft_saved", "invalid_chars"} <= set(texts)
    assert sel.data["confirm_post_buttons"]
    assert texts["upload_done"].search("Uploaded（30.44MB）")
    assert button_label(sel, schedule=False) == "Post" and button_label(sel, schedule=True) == "Schedule"


# ---- picking a hashtag from TikTok's suggestion list (fake list + keyboard) ----------

class Listing:
    def __init__(self, topics):
        self.topics, self.selected = topics, 0


class FakeKeys:
    def __init__(self, listing):
        self.listing, self.pressed = listing, []

    def press(self, key):
        self.pressed.append(key)
        if key == "ArrowDown":
            self.listing.selected = min(self.listing.selected + 1, len(self.listing.topics) - 1)


class FakeLocator:
    def __init__(self, texts):
        self.texts = texts

    def all_inner_texts(self):
        return self.texts()

    def count(self):
        return len(self.texts())

    @property
    def first(self):
        return self

    def inner_text(self):
        return self.texts()[0]


class FakeSel:
    def __init__(self, listing):
        self.listing = listing

    def locate(self, scope, key, value=None):
        if key == "hashtag_topics":
            return FakeLocator(lambda: list(self.listing.topics))
        if key == "hashtag_selected":
            return FakeLocator(lambda: [self.listing.topics[self.listing.selected]] if self.listing.topics else [])
        raise KeyError(key)


class FakePage:
    def __init__(self, listing):
        self.keyboard = FakeKeys(listing)

    def wait_for_timeout(self, ms):
        pass


def test_hashtag_is_picked_from_the_suggestions_with_the_arrow_keys():
    listing = Listing(["#giaybupbe", "#giaybupbenu", "#giaybupbebegai"])
    page = FakePage(listing)
    assert pick_suggestion(page, FakeSel(listing), "#giaybupbenu", wait_sec=0.05)
    assert page.keyboard.pressed == ["ArrowDown", "Enter"]


def test_first_suggestion_needs_no_arrow_and_case_does_not_matter():
    listing = Listing(["#GiayBupBe", "#giaybupbenu"])
    page = FakePage(listing)
    assert pick_suggestion(page, FakeSel(listing), "#giaybupbe", wait_sec=0.05)
    assert page.keyboard.pressed == ["Enter"]


def test_missing_hashtag_stays_text_and_enter_is_never_pressed():
    listing = Listing(["#giaybupbenu"])  # Enter here would turn "#giaybupbe" into another tag
    page = FakePage(listing)
    assert not pick_suggestion(page, FakeSel(listing), "#giaybupbe", wait_sec=0.05)
    assert "Enter" not in page.keyboard.pressed
    empty = Listing([])
    page = FakePage(empty)
    assert not pick_suggestion(page, FakeSel(empty), "#giaybupbe", wait_sec=0.05)
    assert page.keyboard.pressed == []
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_studio_post.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tiktok.studio_post'`.

- [ ] **Step 3: Viết lại `backend/app/tiktok/studio_upload.py`**

Thay toàn bộ file bằng (logic lưu nháp giữ nguyên; các hàm dùng chung thành public; chờ tải xong đọc ô trạng thái thay vì cả trang):

```python
"""Shared steps of TikTok Studio's upload form, and Save draft on top of them.

Observed 2026-10-15: the upload page has a hidden <input type=file accept=video/*>; once a file is
chosen the form appears with a DraftJS description editor (pre-filled with the file name), a
"Show more" section holding the "AI-generated content" switch (turning it on opens a dialog:
"Not now" / "Turn on"), and the buttons Post / Save draft / Discard (data-e2e attributes).
Observed 2026-10-17: the upload is done when [data-e2e=upload_status_container] says "Uploaded（30.44MB）".
The page body cannot tell: it always says "Checks can only start after the file is uploaded."
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

from ..config import ROOT, TikTokConfig
from ..flow.flow_selectors import FlowSelectors, build_locator

SELECTORS_FILE = ROOT / "tiktok-selectors.yaml"
MAX_DESCRIPTION = 2000


class StudioError(Exception):
    pass


def load_selectors(selectors: FlowSelectors | None = None) -> tuple[FlowSelectors, dict[str, re.Pattern]]:
    sel = selectors or FlowSelectors.load(SELECTORS_FILE)
    return sel, {k: re.compile(v, re.I) for k, v in sel.data.get("texts", {}).items()}


def save_draft(page, cfg: TikTokConfig, video: Path, description: str,
               report: Callable[[float, str], None], log: Callable[[str], None],
               selectors: FlowSelectors | None = None) -> None:
    sel, texts = load_selectors(selectors)

    report(0.05, "Mở TikTok Studio")
    open_upload_form(page, sel, texts, cfg.upload_url)
    report(0.1, f"Tải {video.name} lên TikTok")
    upload_video(page, sel, texts, video, cfg.timeout_sec)
    save = sel.locate(page, "save_draft_button").first
    if not wait_until(page, lambda: save.count() and save.is_enabled(), 30):
        raise StudioError("Nút lưu nháp vẫn bị khoá sau khi tải video xong.")

    report(0.6, "Điền mô tả")
    text = description[:MAX_DESCRIPTION]
    fill_description(page, sel, text, video, log)

    if cfg.ai_generated_label:
        report(0.7, "Gắn nhãn nội dung do AI tạo")
        turn_on_ai_label(page, sel, texts["ai_label_row"])

    report(0.85, "Lưu nháp")
    if not has_description(page, sel, text):
        log("tiktok_draft: mô tả bị mất trước khi lưu, điền lại")
        fill_description(page, sel, text, video, log)
    if save.get_attribute("data-e2e") != "save_draft_button":
        raise StudioError("Nút lưu nháp không đúng như mong đợi, tool dừng để không bấm nhầm nút đăng.")
    save.click()
    _wait_saved(page, sel, texts["draft_saved"])
    log(f"tiktok_draft: saved draft '{description[:60]}' (AI label: {cfg.ai_generated_label})")


# ---- shared with the post step (studio_post) -------------------------------------------

def open_upload_form(page, sel: FlowSelectors, texts: dict[str, re.Pattern], url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        sel.locate(page, "file_input").first.wait_for(state="attached", timeout=30000)
    except Exception as exc:
        if texts["login_page"].search(page.title()) or "/login" in page.url:
            raise StudioError("Chrome của tool chưa đăng nhập TikTok. Đăng nhập TikTok trong cửa sổ Chrome đó rồi bấm 'Thử lại'.") from exc
        raise StudioError("Không thấy ô chọn video trên trang tải lên của TikTok Studio.") from exc


def upload_video(page, sel: FlowSelectors, texts: dict[str, re.Pattern], video: Path, timeout_sec: int) -> None:
    sel.locate(page, "file_input").first.set_input_files(str(video))
    status = sel.locate(page, "upload_status").first
    deadline = time.time() + timeout_sec
    while not (status.count() and texts["upload_done"].search(status.inner_text())):
        if time.time() > deadline:
            raise StudioError(f"Quá {timeout_sec}s video vẫn chưa tải xong lên TikTok.")
        page.wait_for_timeout(2000)
    dismiss(page, sel)


def wait_until(page, condition: Callable[[], bool], seconds: float) -> bool:
    deadline = time.time() + seconds
    while not condition():
        if time.time() > deadline:
            return False
        page.wait_for_timeout(300)
    return True


def has_description(page, sel: FlowSelectors, text: str) -> bool:
    return text[:40].strip() in sel.locate(page, "description_editor").first.inner_text()


def fill_description(page, sel: FlowSelectors, text: str, video: Path, log: Callable[[str], None]) -> None:
    """Once seen: right after "Uploaded", typed text vanished and left the box empty. TikTok pre-fills the
    file name when the editor is ready, so wait for that, then type and check, a few times if needed."""
    editor = sel.locate(page, "description_editor").first
    if not wait_until(page, lambda: video.stem[:20] in editor.inner_text(), 15):
        log("tiktok: ô mô tả chưa điền sẵn tên file sau 15s, vẫn điền tiếp")
    for attempt in range(1, 4):
        editor.click()
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(text)
        page.keyboard.press("Escape")  # closes the hashtag / mention suggestions
        if wait_until(page, lambda: has_description(page, sel, text), 5):
            return
        log(f"tiktok: lần {attempt} điền mô tả chưa vào ô (đang là: {editor.inner_text()[:60]!r})")
        page.wait_for_timeout(1500)
    raise StudioError("Không điền được mô tả vào TikTok Studio.")


def dismiss(page, sel: FlowSelectors) -> None:
    for spec in sel.dismiss_specs():
        button = build_locator(page, spec)
        if button.count() and button.first.is_visible():
            button.first.click(timeout=3000)
            page.wait_for_timeout(500)


def _ai_switch(page, row_text: re.Pattern):
    row = page.locator("div").filter(has_text=row_text).filter(has=page.locator("input[role=switch]")).last
    return row.locator("input[role=switch]").first


def ai_label_on(page, row_text: re.Pattern) -> bool:
    return _ai_switch(page, row_text).is_checked()


def turn_on_ai_label(page, sel: FlowSelectors, row_text: re.Pattern) -> None:
    # The switch is in the DOM even while "Show more" is collapsed, so check visibility, not presence.
    # The input itself is covered by the switch body; its parent is what shows and takes clicks.
    if not _ai_switch(page, row_text).locator("xpath=..").is_visible():
        sel.locate(page, "show_more").first.click(timeout=10000)
        page.wait_for_timeout(1000)
    switch = _ai_switch(page, row_text)
    if not switch.locator("xpath=..").is_visible():
        raise StudioError("Không thấy công tắc 'AI-generated content'. Tắt tiktok.ai_generated_label nếu muốn đăng không gắn nhãn.")
    if not switch.is_checked():
        switch.locator("xpath=..").click(timeout=10000)
        # The "Labeling AI-generated content" dialog (Not now / Turn on) only shows the first time.
        confirm = sel.locate(page, "ai_label_confirm").first
        deadline = time.time() + 10
        while not switch.is_checked() and time.time() < deadline:
            if confirm.count() and confirm.is_visible():
                confirm.click()
            page.wait_for_timeout(500)
    if not switch.is_checked():
        raise StudioError("Không bật được nhãn 'AI-generated content' trên TikTok Studio.")


def _wait_saved(page, sel: FlowSelectors, saved_text: re.Pattern, timeout: float = 90) -> None:
    """Saved when a confirmation shows, the page leaves the upload form, or the form resets."""
    save_anyway = sel.locate(page, "save_anyway_button").first
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.wait_for_timeout(2000)
        if save_anyway.count() and save_anyway.is_visible():
            save_anyway.click()  # "Content check lite" takes ~10 min; saving now stops it (not waited for)
            continue
        if "/upload" not in page.url or saved_text.search(page.inner_text("body")):
            return
        if not sel.locate(page, "save_draft_button").count() and sel.locate(page, "file_input").count():
            return
    raise StudioError("Đã bấm 'Save draft' nhưng không thấy TikTok xác nhận đã lưu. Kiểm tra mục Bản nháp trên TikTok Studio.")
```

- [ ] **Step 4: Thêm selector vào `tiktok-selectors.yaml`**

Thay dòng comment thứ 3 ở đầu file (`# Tool chỉ bấm "Save draft" ...`) bằng:

```yaml
# Bước lưu nháp chỉ bấm "Save draft". Bước "Đăng TikTok" chỉ bấm Post/Schedule sau khi người dùng bấm nút
# Đăng ngay / Lên lịch.
```

Thêm vào cuối khối `texts:` (thụt lề 2 dấu cách như các dòng khác):

```yaml
  invalid_chars: "invalid characters?:\\s*(.+)"   # "Remove invalid characters: +" dưới ô Product name
```

Thêm vào cuối file:

```yaml
# ---- Đăng ngay / Lên lịch (khảo sát 2026-10-17, giao diện tiếng Anh, không bấm Post/Schedule) ----
upload_status: {css: "[data-e2e=upload_status_container]"}   # "Uploaded（30.44MB）" khi tải xong
post_button: {css: "[data-e2e=post_video_button]"}
post_button_text: {now: "Post", schedule: "Schedule"}       # chữ trên nút theo lựa chọn When to post

# Add link: nút Add → hộp "Add link" (Products) → Next → hộp "Add product links" → tìm ID → chọn dòng → Next
# → ô "Product name" → Add
add_link_button: {css: "[data-e2e=anchor_container] button"}
anchor_container: {css: "[data-e2e=anchor_container]"}       # hiện tên sản phẩm sau khi gắn link
link_dialog: {role: dialog, name: "Add link", exact: true}
product_dialog: {role: dialog, name: "Add product links", exact: true}
product_search: {css: "input[placeholder='Search products']"}
product_rows: {css: "tbody tr"}
product_id_cell: {css: "td:nth-child(2)"}                    # cột "Product ID"
product_radio: {css: "input[type=radio]"}
product_name_input: {css: "input[type=text]:not([placeholder='Search products'])"}
dialog_next: {role: button, name: "Next", exact: true}
dialog_add: {role: button, name: "Add", exact: true}
dialog_cancel: {role: button, name: "Cancel", exact: true}

# When to post: radio name=postSchedule, value post_now | schedule (đọc aria-checked)
schedule_container: {css: "[data-e2e=schedule_container]"}
when_option: {css: "[data-e2e=schedule_container] label:has(input[name=postSchedule][value='{value}'])"}
when_input: {css: "[data-e2e=schedule_container] input[name=postSchedule][value='{value}']"}
calendar: {css: ".calendar-wrapper"}
calendar_month: {css: ".month-title"}                        # "October"
calendar_year: {css: ".year-title"}                          # "2026"
calendar_arrow: {css: ".arrow"}                              # đầu tiên = tháng trước, cuối = tháng sau
calendar_day: {css: ".day.valid"}                            # chỉ ngày chọn được (hôm nay → +30 ngày)

# Gợi ý hashtag khi gõ "#tag": dòng đầu được chọn sẵn; Enter biến chữ thành hashtag thật
hashtag_topics: {css: "[role=option] .hash-tag-topic"}
hashtag_selected: {css: "[role=option][aria-selected=true] .hash-tag-topic"}
hashtag_done: {css: "[data-testid=mentionText]"}

# Hộp TikTok có thể hỏi lại SAU KHI tool đã bấm Post/Schedule. Chưa khảo sát được (phải đăng thật):
# tên nút là phỏng đoán; tool chỉ bấm chúng sau cú bấm Post/Schedule của chính nó.
confirm_post_buttons:
  - {role: button, name: "Post now", exact: true}
  - {role: button, name: "Post anyway", exact: true}
  - {role: button, name: "Schedule anyway", exact: true}
```

- [ ] **Step 5: Tạo `backend/app/tiktok/studio_post.py`**

```python
"""Post now or schedule in TikTok Studio: the upload form (shared steps in studio_upload), hashtags, Add link,
the AI label, When to post, a last check, and the one click on Post / Schedule.

Surveyed 2026-10-17 (English UI, nothing posted); selectors live in tiktok-selectors.yaml:
- Hashtags only become real tags when picked from the suggestions: typing "#tag" lists [role=option] items
  (.hash-tag-topic), the first one selected; Enter turns the text into span[data-testid=mentionText] and adds
  a space. Clicking a suggestion fails in a background tab (the list is outside the viewport).
- Add link: anchor_container's "Add" → "Add link" (Link type: Products) → Next → "Add product links": the search
  leaves only rows whose 2nd cell (Product ID) is the ID, or none when the product is not in the account's
  showcase (no message, an empty table). Radio → Next → "Product name" (pre-filled, 30 chars; TikTok may answer
  "Remove invalid characters: +") → Add; both dialogs close and the name shows in anchor_container.
- When to post: radios post_now / schedule. Schedule shows a read-only time input "HH:MM" (an hour column
  00–23 then a minute column 00–55 by 5) and a date input "YYYY-MM-DD" (calendar, today + 30 days). The post
  button keeps data-e2e=post_video_button and reads "Schedule".
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import TikTokConfig
from ..flow.flow_selectors import FlowSelectors, build_locator
from .post_plan import slot_label
from .studio_upload import (MAX_DESCRIPTION, StudioError, ai_label_on, fill_description, has_description,
                            load_selectors, open_upload_form, turn_on_ai_label, upload_video, wait_until)

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
DATE_VALUE, TIME_VALUE = re.compile(r"^\d{4}-\d{2}-\d{2}$"), re.compile(r"^\d{2}:\d{2}$")
PRODUCT_NAME_MAX = 30


class ProductNotFound(StudioError):
    pass


@dataclass
class PostPlan:
    video: Path
    title: str
    hashtags: list[str]
    product_id: str
    schedule_at: datetime | None = None  # None = post now


# ---- pure parts ---------------------------------------------------------------------

def invalid_chars(message: str, pattern: re.Pattern) -> list[str]:
    """Characters TikTok refuses in the product name, from e.g. "Remove invalid characters: +"."""
    match = pattern.search(message or "")
    if not match:
        return []
    return list(dict.fromkeys(c for c in match.group(1) if not c.isspace()))


def clean_product_name(name: str, bad: list[str]) -> str:
    for char in bad:
        name = name.replace(char, " ")
    return " ".join(name.split())[:PRODUCT_NAME_MAX].strip() or "Sản phẩm"


def button_label(sel: FlowSelectors, schedule: bool) -> str:
    return sel.data["post_button_text"]["schedule" if schedule else "now"]


def pick_suggestion(page, sel: FlowSelectors, tag: str, wait_sec: float = 6.0) -> bool:
    """Move the selection onto the exact tag with the arrow keys and press Enter. False (nothing pressed but
    arrows) when TikTok does not suggest that tag: Enter would then pick a different one."""
    want = tag.casefold()
    topics = sel.locate(page, "hashtag_topics")
    selected = sel.locate(page, "hashtag_selected")

    def shown() -> list[str]:
        return [t.strip().casefold() for t in topics.all_inner_texts()]

    if not wait_until(page, lambda: want in shown(), wait_sec):
        return False
    for _ in range(shown().index(want)):
        page.keyboard.press("ArrowDown")
    if not wait_until(page, lambda: selected.count() and selected.first.inner_text().strip().casefold() == want, 2):
        return False
    page.keyboard.press("Enter")
    return True


# ---- the form -------------------------------------------------------------------------

def post_video(page, cfg: TikTokConfig, plan: PostPlan, report: Callable[[float, str], None],
               log: Callable[[str], None], before_click: Callable[[], None], dry_run: bool = False,
               selectors: FlowSelectors | None = None) -> None:
    sel, texts = load_selectors(selectors)
    schedule = plan.schedule_at is not None
    label = button_label(sel, schedule)

    report(0.15, "Mở trang tải lên TikTok Studio")
    open_upload_form(page, sel, texts, cfg.post_url)
    report(0.2, f"Tải {plan.video.name} lên TikTok")
    upload_video(page, sel, texts, plan.video, cfg.timeout_sec)

    report(0.5, "Điền mô tả và hashtag")
    title = plan.title[:MAX_DESCRIPTION]
    fill_description(page, sel, title, plan.video, log)
    picked = add_hashtags(page, sel, plan.hashtags, log)

    report(0.6, f"Gắn link sản phẩm {plan.product_id}")
    product_name = add_product_link(page, sel, texts, plan.product_id, log)

    if cfg.ai_generated_label:
        report(0.7, "Bật nhãn nội dung do AI tạo")
        turn_on_ai_label(page, sel, texts["ai_label_row"])

    if schedule:
        report(0.8, f"Chọn lịch {slot_label(plan.schedule_at, weekday=False)}")
        choose_schedule(page, sel, plan.schedule_at)
    else:
        choose_when(page, sel, "post_now")

    button = check_ready(page, sel, texts, cfg, plan, product_name, label)
    log(f"tiktok_post: sẵn sàng bấm {label}: '{title[:40]}', {picked}/{len(plan.hashtags)} hashtag thật, "
        f"link '{product_name}'")
    if dry_run:
        report(1, f"Chạy thử xong, dừng trước khi bấm {label}")
        return
    before_click()
    report(0.9, f"Bấm {label}")
    button.click()
    wait_submitted(page, sel, log)


def add_hashtags(page, sel: FlowSelectors, tags: list[str], log: Callable[[str], None]) -> int:
    """On a new line after the title, type each tag and pick it from TikTok's suggestions so it becomes a real
    hashtag; a tag TikTok does not suggest stays as text. Returns how many became real hashtags."""
    editor = sel.locate(page, "description_editor").first
    picked = 0
    for i, tag in enumerate(tags):
        editor.click()
        page.keyboard.press("Meta+ArrowDown")  # caret to the end of the text
        if i == 0:
            page.keyboard.insert_text("\n")
        page.keyboard.type(tag, delay=60)
        if pick_suggestion(page, sel, tag):
            picked += 1  # TikTok adds the space after a picked tag
        else:
            log(f"tiktok_post: TikTok không gợi ý {tag}, để dạng chữ")
            page.keyboard.press("Escape")
            page.keyboard.type(" ")
    log(f"tiktok_post: {sel.locate(page, 'hashtag_done').count()} hashtag thật trong mô tả")
    return picked


def add_product_link(page, sel: FlowSelectors, texts: dict[str, re.Pattern], product_id: str,
                     log: Callable[[str], None]) -> str:
    """Returns the product name shown on the form."""
    sel.locate(page, "add_link_button").first.click(timeout=10000)
    link_dialog = sel.locate(page, "link_dialog").first
    link_dialog.wait_for(state="visible", timeout=10000)
    sel.locate(link_dialog, "dialog_next").first.click(timeout=10000)  # Link type is "Products" by default

    products = sel.locate(page, "product_dialog").last
    search = sel.locate(products, "product_search").first
    search.wait_for(state="visible", timeout=15000)
    search.fill(product_id)
    search.press("Enter")
    exact_id = re.compile(rf"^\s*{re.escape(product_id)}\s*$")
    row = sel.locate(products, "product_rows").filter(has=sel.locate(page, "product_id_cell").filter(has_text=exact_id))
    if not wait_until(page, lambda: row.count() > 0, 15):
        close_dialogs(page, sel)
        raise ProductNotFound(f"Không tìm thấy sản phẩm {product_id} khi Add link. Kiểm tra sản phẩm đã có trong "
                              "showcase/shop của tài khoản TikTok này rồi bấm Thử lại.")
    sel.locate(row.first, "product_radio").first.check(force=True)
    sel.locate(products, "dialog_next").first.click(timeout=10000)

    name_box = sel.locate(products, "product_name_input").first
    name_box.wait_for(state="visible", timeout=10000)
    for _ in range(3):
        sel.locate(products, "dialog_add").first.click(timeout=10000)
        if wait_until(page, lambda: sel.locate(page, "product_dialog").count() == 0, 5):
            break
        message = products.inner_text()
        bad = invalid_chars(message, texts["invalid_chars"])
        if not bad:
            raise StudioError(f"TikTok không nhận link sản phẩm: {' '.join(message.split())[:200]}")
        cleaned = clean_product_name(name_box.input_value(), bad)
        log(f"tiktok_post: bỏ ký tự {' '.join(bad)} khỏi tên sản phẩm → {cleaned!r}")
        name_box.fill(cleaned)
    else:
        raise StudioError("Không gắn được link sản phẩm: TikTok vẫn từ chối tên sản phẩm.")

    shown = [line.strip() for line in sel.locate(page, "anchor_container").first.inner_text().splitlines()]
    names = [line for line in shown if line and line not in ("Add link", "Add")]
    if not names:
        raise StudioError("Đã bấm Add nhưng form chưa hiện link sản phẩm.")
    return names[0]


def close_dialogs(page, sel: FlowSelectors) -> None:
    for _ in range(3):
        dialogs = page.get_by_role("dialog")
        if not dialogs.count():
            return
        cancel = sel.locate(dialogs.last, "dialog_cancel")
        if not cancel.count():
            return
        cancel.first.click(timeout=5000)
        page.wait_for_timeout(500)


def choose_when(page, sel: FlowSelectors, value: str) -> None:
    sel.locate(page, "when_option", value).first.click(timeout=10000)
    if not wait_until(page, lambda: sel.locate(page, "when_input", value).first.get_attribute("aria-checked") == "true", 5):
        raise StudioError(f"Không chọn được '{value}' ở mục When to post.")


def choose_schedule(page, sel: FlowSelectors, when: datetime) -> None:
    """Date first (a time can depend on the day), then hour and minute; then read both inputs back."""
    choose_when(page, sel, "schedule")
    box = sel.locate(page, "schedule_container").first
    if not wait_until(page, lambda: _picker(box, DATE_VALUE) is not None and _picker(box, TIME_VALUE) is not None, 10):
        raise StudioError("Không thấy ô chọn ngày giờ sau khi chọn Schedule.")
    _pick_date(page, sel, box, when)
    _pick_time(page, box, when)
    shown = (_picker(box, DATE_VALUE).input_value(), _picker(box, TIME_VALUE).input_value())
    if shown != (f"{when:%Y-%m-%d}", f"{when:%H:%M}"):
        raise StudioError(f"TikTok đang hiện lịch {shown[1]} {shown[0]}, không phải {when:%H:%M %Y-%m-%d}; "
                          "tool dừng trước khi bấm Schedule.")


def _picker(box, pattern: re.Pattern):
    fields = box.locator("input[type=text]")
    for i in range(fields.count()):
        if pattern.match(fields.nth(i).input_value() or ""):
            return fields.nth(i)
    return None


def _pick_date(page, sel: FlowSelectors, box, when: datetime) -> None:
    _picker(box, DATE_VALUE).click()
    calendar = sel.locate(box, "calendar").first
    calendar.wait_for(state="visible", timeout=5000)
    target = when.year * 12 + when.month - 1
    for _ in range(3):
        month = MONTHS.index(sel.locate(calendar, "calendar_month").first.inner_text().strip())
        shown = int(sel.locate(calendar, "calendar_year").first.inner_text().strip()) * 12 + month
        if shown == target:
            break
        arrows = sel.locate(calendar, "calendar_arrow")
        (arrows.last if shown < target else arrows.first).click()
        page.wait_for_timeout(400)
    day = sel.locate(calendar, "calendar_day").filter(has_text=re.compile(rf"^\s*{when.day}\s*$"))
    if day.count() != 1:
        raise StudioError(f"Lịch của TikTok không cho chọn ngày {when:%d/%m/%Y}.")
    day.first.click()
    if not wait_until(page, lambda: not calendar.is_visible(), 3):
        page.keyboard.press("Escape")


def _pick_time(page, box, when: datetime) -> None:
    """The hour column comes first in the DOM and the minute column last, so "15" (both) is told apart by order."""
    _picker(box, TIME_VALUE).click()
    page.wait_for_timeout(500)
    visible = box.locator("span").filter(visible=True)
    visible.filter(has_text=re.compile(rf"^{when.hour:02d}$")).first.click()
    page.wait_for_timeout(400)
    visible.filter(has_text=re.compile(rf"^{when.minute:02d}$")).last.click()
    page.wait_for_timeout(400)
    page.keyboard.press("Escape")


def check_ready(page, sel: FlowSelectors, texts: dict[str, re.Pattern], cfg: TikTokConfig, plan: PostPlan,
                product_name: str, label: str):
    """Last look before the click; returns the button to press."""
    if not has_description(page, sel, plan.title[:MAX_DESCRIPTION]):
        raise StudioError("Mô tả trên TikTok Studio bị mất trước khi đăng; tool dừng, không bấm.")
    if product_name not in sel.locate(page, "anchor_container").first.inner_text():
        raise StudioError("Link sản phẩm không còn trên form; tool dừng, không bấm.")
    if cfg.ai_generated_label and not ai_label_on(page, texts["ai_label_row"]):
        raise StudioError("Nhãn 'AI-generated content' chưa bật; tool dừng, không bấm.")
    value = "schedule" if plan.schedule_at else "post_now"
    if sel.locate(page, "when_input", value).first.get_attribute("aria-checked") != "true":
        raise StudioError("Mục When to post không đúng lựa chọn; tool dừng, không bấm.")
    button = sel.locate(page, "post_button").first
    if button.get_attribute("data-e2e") != "post_video_button" or button.inner_text().strip() != label:
        raise StudioError(f"Nút {label} không đúng như mong đợi; tool dừng, không bấm.")
    if not wait_until(page, lambda: button.is_enabled() and button.get_attribute("data-disabled") != "true", 30):
        raise StudioError(f"Nút {label} đang bị khoá; tool dừng, không bấm.")
    return button


def wait_submitted(page, sel: FlowSelectors, log: Callable[[str], None], timeout: float = 90) -> None:
    """After the click: answer a "post anyway?" kind of dialog, wait for the form to go away. Not seeing that is
    not an error here; the Content page check that follows decides."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        page.wait_for_timeout(1500)
        for spec in sel.data.get("confirm_post_buttons", []):
            button = build_locator(page, spec)
            if button.count() and button.first.is_visible():
                log(f"tiktok_post: TikTok hỏi lại, bấm '{spec.get('name')}'")
                button.first.click(timeout=5000)
        if "/upload" not in page.url:
            return
    log("tiktok_post: sau khi bấm, trang tải lên vẫn còn; kiểm tra trên trang Content")
```

- [ ] **Step 6: Chạy test, xác nhận pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_studio_post.py tests/test_tiktok_draft.py -q`
Expected: PASS (test lưu nháp không đổi vì chúng giả lập `save_draft_in_browser`).

Run: `cd backend && ../.venv/bin/python -c "import app.tiktok.studio_post, app.steps.tiktok_draft_step"`
Expected: không lỗi import.

- [ ] **Step 7: Commit**

```bash
git add backend/app/tiktok/studio_upload.py backend/app/tiktok/studio_post.py tiktok-selectors.yaml \
        backend/tests/test_studio_post.py
git commit -m "TikTok Studio post form: real hashtags, product link, schedule, one guarded click

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Yêu cầu đăng, Thử lại, khởi động lại và API

**Files:**
- Modify: `backend/app/link_job_actions.py`
- Modify: `backend/app/job_actions.py` (`retry`)
- Modify: `backend/app/pipeline_runner.py` (`recover`)
- Modify: `backend/app/api/jobs_routes.py`
- Test: `backend/tests/test_tiktok_post_actions.py`

**Interfaces:**
- Consumes: `TikTokPostState`, `job_product_id` (Task 1).
- Produces:
  - `LinkJobActions.request_post(job_id: str, mode: str) -> JobState` — `InvalidAction` với các thông điệp chứa: "đã được yêu cầu đăng", "đã xong", "link TikTok Shop", "ID sản phẩm", "không hợp lệ".
  - `POST /api/jobs/{job_id}/post` thân `{"mode": "now" | "schedule"}` → job; 409 khi `InvalidAction`; 422 khi `mode` sai.
  - test helper `done_link_job(store, runner, url=URL) -> str` trong `tests/test_tiktok_post_actions.py` (Task 5 dùng lại).

- [ ] **Step 1: Viết test (fail)**

Tạo `backend/tests/test_tiktok_post_actions.py`:

```python
"""Đăng ngay / Lên lịch: who may ask, and retries or restarts never click Post a second time on their own."""

import pytest
from fastapi.testclient import TestClient

from app.job_actions import InvalidAction
from app.job_models import JobStatus, SourceInfo
from app.main import create_app
from app.steps.step_types import StepFailure

from .test_api_end_to_end import fake_steps, wait_for
from .test_link_jobs import URL
from .test_pipeline_runner import drain, new_job, rig  # noqa: F401  (fixture re-export)

ALL_AUTO = {"cutout": True, "prompt": True, "flow_video": True}


def done_link_job(store, runner, url=URL) -> str:
    job = new_job(store, ALL_AUTO)
    store.update(job.id, lambda j: setattr(j, "source", SourceInfo(url=url, title="Giày búp bê")))
    drain(store, runner)
    assert store.get(job.id).status == JobStatus.done
    return job.id


def test_request_post_runs_the_post_step_once(rig):
    store, runner, actions, calls, _ = rig
    job_id = done_link_job(store, runner)
    calls.clear()
    queued = actions.request_post(job_id, "schedule")
    assert queued.status == JobStatus.queued and queued.current_step == "tiktok_post"
    assert queued.post.mode == "schedule" and queued.post.requested_at
    drain(store, runner)
    assert calls == ["tiktok_post"] and store.get(job_id).status == JobStatus.done
    with pytest.raises(InvalidAction, match="đã được yêu cầu đăng"):
        actions.request_post(job_id, "now")  # second tap, or the other side (tool / Telegram)


def test_request_post_only_for_finished_link_jobs_with_a_product_id(rig):
    store, runner, actions, _, _ = rig
    upload = new_job(store, ALL_AUTO)
    drain(store, runner)
    with pytest.raises(InvalidAction, match="link TikTok Shop"):
        actions.request_post(upload.id, "now")
    short = done_link_job(store, runner, url="https://vt.tiktok.com/ZS9UDYUDtqn7v-WCASA")
    with pytest.raises(InvalidAction, match="ID sản phẩm"):
        actions.request_post(short, "now")
    with pytest.raises(InvalidAction, match="không hợp lệ"):
        actions.request_post(short, "later")
    waiting = new_job(store)  # queued, far from done
    store.update(waiting.id, lambda j: setattr(j, "source", SourceInfo(url=URL)))
    with pytest.raises(InvalidAction, match="đã xong"):
        actions.request_post(waiting.id, "now")


def test_retry_after_a_click_without_confirmation_is_the_users_call(rig):
    store, runner, actions, _, behaviour = rig
    job_id = done_link_job(store, runner)

    def clicked_then_lost(ctx):
        ctx.update_job(lambda j: setattr(j.post, "submitted_at", "2026-10-17T10:31:00"))
        raise StepFailure("không thấy bài trên TikTok Studio")

    behaviour["tiktok_post"] = clicked_then_lost
    actions.request_post(job_id, "now")
    drain(store, runner)
    failed = store.get(job_id)
    assert failed.status == JobStatus.failed and failed.error.step == "tiktok_post" and failed.post.submitted_at
    actions.retry(job_id, "tiktok_post")  # the UI warned "có thể đăng 2 lần" before sending this
    retried = store.get(job_id)
    assert retried.post.submitted_at is None and retried.post.mode == "now"


def test_retry_after_posting_keeps_the_post_and_a_new_video_resets_it(rig):
    store, runner, actions, _, behaviour = rig
    job_id = done_link_job(store, runner)
    behaviour["tiktok_post"] = lambda ctx: ctx.update_job(
        lambda j: (setattr(j.post, "submitted_at", "t"), setattr(j.post, "done_at", "t")))
    actions.request_post(job_id, "now")
    drain(store, runner)
    actions.retry(job_id, "tiktok_post")  # e.g. only the Telegram message had failed
    kept = store.get(job_id).post
    assert kept.done_at == "t" and kept.submitted_at == "t"
    drain(store, runner)
    actions.retry(job_id, "export")  # a new video file may be posted again
    assert store.get(job_id).post.mode is None and store.get(job_id).post.done_at is None


def test_recover_never_clicks_post_again(rig):
    store, runner, _, _, _ = rig
    clicked, waiting = new_job(store), new_job(store)

    def at_post(submitted):
        def mutate(j):
            j.status, j.current_step, j.post.mode, j.post.submitted_at = (JobStatus.running, "tiktok_post",
                                                                         "schedule", submitted)
        return mutate

    store.update(clicked.id, at_post("2026-10-17T10:31:00"))
    store.update(waiting.id, at_post(None))
    runner.recover()
    recovered = store.get(clicked.id)
    assert recovered.status == JobStatus.failed and recovered.error.step == "tiktok_post"
    assert "TikTok Studio" in recovered.error.reason
    assert store.get(waiting.id).status == JobStatus.queued


def test_post_endpoint(make_config):
    app = create_app(make_config(), steps=fake_steps(), allowed_hosts=["testserver"])
    with TestClient(app) as client:
        svc = app.state.services
        job = svc.store.create("a.jpg", b"img", "", ALL_AUTO)
        wait_for(client, job.id, lambda j: j["status"] == "done")
        svc.store.update(job.id, lambda j: setattr(j, "source", SourceInfo(url=URL, title="Giày")))
        res = client.post(f"/api/jobs/{job.id}/post", json={"mode": "schedule"})
        assert res.status_code == 200 and res.json()["post"]["mode"] == "schedule"
        wait_for(client, job.id, lambda j: j["status"] == "done")
        assert client.post(f"/api/jobs/{job.id}/post", json={"mode": "now"}).status_code == 409
        assert client.post(f"/api/jobs/{job.id}/post", json={"mode": "later"}).status_code == 422
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_tiktok_post_actions.py -q`
Expected: FAIL — `AttributeError: 'LinkJobActions' object has no attribute 'request_post'`.

- [ ] **Step 3: Thêm `request_post` vào `backend/app/link_job_actions.py`**

Sửa import:

```python
from .job_models import GATES, PICK_GATE, JobState, JobStatus, TelegramOrigin, now_iso
from .tiktok.post_plan import job_product_id
```

Thêm hằng số dưới `FINISHED`:

```python
POST_MODES = ("now", "schedule")
```

Thêm method vào `LinkJobActions` (sau `pick_image`):

```python
    def request_post(self, job_id: str, mode: str) -> JobState:
        """Đăng ngay / Lên lịch from the tool or Telegram: queue the tiktok_post step of a finished link job, once."""
        if mode not in POST_MODES:
            raise InvalidAction("Chế độ đăng không hợp lệ.")

        def mutate(j: JobState) -> None:
            self._require_idle(j)
            if j.post.mode:
                raise InvalidAction("Video này đã được yêu cầu đăng.")
            if j.status != JobStatus.done:
                raise InvalidAction("Chỉ đăng được khi job đã xong.")
            if j.source is None:
                raise InvalidAction("Chỉ job tạo từ link TikTok Shop mới đăng được (cần ID sản phẩm để Add link).")
            if not job_product_id(j):
                raise InvalidAction("Không biết ID sản phẩm của job này; chạy lại bước Đọc TikTok.")
            j.post.mode, j.post.requested_at = mode, now_iso()
            j.current_step = "tiktok_post"
            self._queue(j)

        return self._apply(job_id, mutate)
```

- [ ] **Step 4: Sửa `retry` trong `backend/app/job_actions.py`**

Sửa import:

```python
from .job_models import (FLOW_STEPS, PICK_GATE, STEPS, FlowState, JobState, JobStatus, TikTokDraftState,
                         TikTokPostState)
```

Thay khối:

```python
            if STEPS.index(step) <= STEPS.index("export"):
                j.tiktok = TikTokDraftState()  # a new video gets its own draft
```

bằng:

```python
            if STEPS.index(step) <= STEPS.index("export"):
                j.tiktok = TikTokDraftState()  # a new video gets its own draft
                j.post = TikTokPostState()  # ... and may be posted again
            elif step == "tiktok_post" and not j.post.done_at:
                j.post.submitted_at = None  # the UI warned that this may post twice
```

- [ ] **Step 5: Sửa `recover` trong `backend/app/pipeline_runner.py`**

Thêm nhánh ngay trước `else:` cuối trong vòng lặp của `recover`:

```python
            elif job.current_step == "tiktok_post" and job.post.submitted_at and not job.post.done_at:
                self.fail(job.id, "tiktok_post",
                          "Tool đã bấm Post/Schedule trước khi tắt — kiểm tra TikTok Studio; "
                          "nếu chưa có bài thì bấm 'Thử lại'.")
```

- [ ] **Step 6: Thêm API vào `backend/app/api/jobs_routes.py`**

Thêm import: `from typing import Literal`. Thêm sau route `cancel`:

```python
class PostBody(BaseModel):
    mode: Literal["now", "schedule"]


@router.post("/jobs/{job_id}/post")
def post_on_tiktok(request: Request, job_id: str, body: PostBody):
    """Đăng ngay / Lên lịch on TikTok for a finished link job."""
    svc = services(request)
    return guarded(lambda: job_payload(svc, svc.actions.request_post(job_id, body.mode)))
```

- [ ] **Step 7: Chạy test, xác nhận pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_tiktok_post_actions.py tests/test_pipeline_runner.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/link_job_actions.py backend/app/job_actions.py backend/app/pipeline_runner.py \
        backend/app/api/jobs_routes.py backend/tests/test_tiktok_post_actions.py
git commit -m "Ask to post a finished job; retries and restarts never click Post twice

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Telegram — 2 nút, chữ từng trạng thái, tin "Đang"

**Files:**
- Modify: `backend/app/telegram/telegram_api.py` (`send_message`)
- Create: `backend/app/telegram/telegram_post.py`
- Modify: `backend/app/telegram/telegram_setup.py`
- Modify: `backend/app/telegram/telegram_notify.py` (`STEP_NAMES`, `status_text`)
- Test: `backend/tests/test_telegram_post.py`

**Interfaces:**
- Consumes: `request_post` (Task 4), `job_product_id`, `post_title`, `slot_label` (Task 1), test helper `done_link_job` (Task 4).
- Produces:
  - `TelegramApi.send_message(chat_id, text, reply_to=None, reply_markup: dict | None = None) -> int | None`
  - `telegram_post`: `OFFER_TEXT`, `FAILED_TEXT`, `STALE_TEXT`, `keyboard(token) -> dict`, `parse(data) -> tuple[str, str] | None` (token, mode), `waiting_text(mode)`, `done_text(job)`, `result_message(job)`, `state_text(job)`, `send_offer(job, api, update_job) -> JobState`, `edit_offer(job, api, text) -> None`, `class PostHandler(actions, api)` với `.handle(callback) -> str`
  - `telegram_setup.route_taps(pick, post) -> Callable[[dict], str | None]`

- [ ] **Step 1: Viết test (fail)**

Tạo `backend/tests/test_telegram_post.py`:

```python
"""Đăng ngay / Lên lịch buttons on Telegram and the status line while posting (fake Bot API)."""

import json

import httpx
import pytest

from app.job_models import JobState, JobStatus, SourceInfo, TelegramMessageRef, TelegramOrigin, TikTokPostState
from app.telegram.telegram_api import TelegramApi
from app.telegram.telegram_notify import status_text
from app.telegram.telegram_post import (FAILED_TEXT, OFFER_TEXT, PostHandler, done_text, keyboard, parse,
                                        result_message, send_offer, waiting_text)
from app.telegram.telegram_setup import route_taps

from .test_link_jobs import URL
from .test_pipeline_runner import new_job, rig  # noqa: F401  (fixture re-export)
from .test_tiktok_post_actions import done_link_job

CHAT, LINK_MSG, OFFER_MSG = 111222333, 7, 99


class FakeApi:
    def __init__(self):
        self.sent, self.edits = [], []

    def send_message(self, chat_id, text, reply_to=None, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "markup": reply_markup})
        return 300 + len(self.sent)

    def edit_text(self, chat_id, message_id, text):
        self.edits.append((chat_id, message_id, text))


def tap(data):
    return {"id": "cb", "from": {"id": CHAT}, "data": data, "message": {"message_id": OFFER_MSG, "chat": {"id": CHAT}}}


def job(**kw) -> JobState:
    return JobState(id="t", name="giay", input_file="input.jpg", created_at="t",
                    source=SourceInfo(url=URL, title="Giày búp bê"), **kw)


def updater(target: JobState):
    def update(fn):
        fn(target)
        return target
    return update


# ---- pure parts ---------------------------------------------------------------

def test_buttons_and_their_data():
    row = keyboard("abcd1234")["inline_keyboard"][0]
    assert [b["text"] for b in row] == ["📤 Đăng ngay", "🗓 Lên lịch"]
    assert all(len(b["callback_data"].encode()) <= 64 for b in row)
    assert parse("t:abcd1234:n") == ("abcd1234", "now") and parse("t:abcd1234:s") == ("abcd1234", "schedule")
    assert parse("t:abcd1234:x") is None and parse("p:abcd1234:1") is None and parse("") is None


def test_texts_for_each_state():
    scheduled = job(post=TikTokPostState(mode="schedule", scheduled_for="2026-10-18T19:00:00",
                                         done_at="2026-10-17T10:32:00"))
    assert done_text(scheduled) == "🗓 Đã lên lịch đăng TikTok: 19:00 Chủ nhật 18/10"
    assert result_message(scheduled) == "🗓 Đã lên lịch đăng TikTok lúc 19:00 Chủ nhật 18/10: Giày búp bê"
    posted = job(post=TikTokPostState(mode="now", done_at="2026-10-17T10:32:00"))
    assert done_text(posted) == "✅ Đã đăng lên TikTok lúc 10:32"
    assert result_message(posted) == "✅ Đã đăng lên TikTok: Giày búp bê"
    assert waiting_text("schedule") == "⏳ Đã nhận: Lên lịch. Đang chờ lượt…"


def test_offer_goes_once_under_the_link_and_only_for_bot_jobs_with_a_product_id():
    api = FakeApi()
    bot = job(telegram=TelegramOrigin(chat_id=CHAT, message_id=LINK_MSG))
    send_offer(bot, api, updater(bot))
    (sent,) = api.sent
    assert sent["text"] == OFFER_TEXT and sent["chat_id"] == CHAT and sent["reply_to"] == LINK_MSG
    assert sent["markup"] == keyboard(bot.post.offer_token) and bot.post.offer_message.message_id == 301
    send_offer(bot, api, updater(bot))  # a retry does not send a second one
    tool_only = job()
    send_offer(tool_only, api, updater(tool_only))  # pasted in the tool: buttons are in the tool
    short = JobState(id="s", name="s", input_file="", created_at="t", source=SourceInfo(url="https://vt.tiktok.com/x"),
                     telegram=TelegramOrigin(chat_id=CHAT, message_id=LINK_MSG))
    send_offer(short, api, updater(short))  # no product ID: nothing to Add link with
    assert len(api.sent) == 1


def test_send_message_can_carry_buttons():
    seen = []
    api = TelegramApi("1:T", httpx.Client(transport=httpx.MockTransport(
        lambda r: seen.append(r) or httpx.Response(200, json={"ok": True, "result": {"message_id": 77}}))))
    assert api.send_message(5, "hi", reply_to=9, reply_markup=keyboard("abcd1234")) == 77
    body = json.loads(seen[0].content)
    assert body["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "t:abcd1234:n"
    api.send_message(5, "plain")
    assert "reply_markup" not in json.loads(seen[1].content)


# ---- taps, with a real job store ---------------------------------------------------

@pytest.fixture
def offered(rig):
    store, runner, actions, _, _ = rig
    job_id = done_link_job(store, runner)

    def give_offer(j):
        j.post.offer_token = "abcd1234"
        j.post.offer_message = TelegramMessageRef(chat_id=CHAT, message_id=OFFER_MSG)

    store.update(job_id, give_offer)
    api = FakeApi()
    return store, actions, api, job_id, PostHandler(actions, api)


def test_tap_queues_the_post_and_drops_the_buttons(offered):
    store, _, api, job_id, handler = offered
    assert handler.handle(tap("t:abcd1234:s")) == "Lên lịch!"
    queued = store.get(job_id)
    assert queued.post.mode == "schedule" and queued.status == JobStatus.queued
    assert api.edits[-1] == (CHAT, OFFER_MSG, "⏳ Đã nhận: Lên lịch. Đang chờ lượt…")


def test_second_tap_or_tool_first_only_explains(offered):
    store, actions, api, job_id, handler = offered
    actions.request_post(job_id, "now")  # pressed in the tool first
    assert "đã được yêu cầu" in handler.handle(tap("t:abcd1234:s"))
    assert store.get(job_id).post.mode == "now"
    assert api.edits[-1][2] == "⏳ Đã nhận: Đăng ngay. Đang chờ lượt…"


def test_tap_before_the_job_is_done_keeps_the_buttons(rig):
    store, _, actions, _, _ = rig
    waiting = new_job(store)
    store.update(waiting.id, lambda j: (setattr(j, "source", SourceInfo(url=URL)),
                                        setattr(j.post, "offer_token", "ffff0000")))
    api = FakeApi()
    assert "đã xong" in PostHandler(actions, api).handle(tap("t:ffff0000:n"))
    assert api.edits == []


def test_stale_button_after_the_video_was_remade_posts_nothing(offered):
    store, actions, api, job_id, handler = offered
    actions.retry(job_id, "export")  # new video: post state (and its token) reset
    assert "đã cũ" in handler.handle(tap("t:abcd1234:n"))
    assert store.get(job_id).post.mode is None
    assert "đã cũ" in api.edits[-1][2]


def test_taps_are_routed_by_prefix():
    class Handler:
        def __init__(self, name):
            self.name = name

        def handle(self, callback):
            return self.name

    route = route_taps(Handler("pick"), Handler("post"))
    assert route({"data": "t:x:n"}) == "post"
    assert route({"data": "p:x:1"}) == "pick" and route({"data": "g:x"}) == "pick" and route({}) == "pick"


def test_status_message_while_posting():
    j = job(status=JobStatus.running, current_step="tiktok_post")
    assert status_text(j).endswith("✅ Xong")  # nobody pressed a button: nothing to do there
    j.post.mode = "now"
    assert status_text(j).endswith("⏳ Đang: Đăng TikTok")
    j.post.mode = "schedule"
    assert status_text(j).endswith("⏳ Đang: Lên lịch TikTok")
    j.status, j.post.scheduled_for, j.post.done_at = JobStatus.done, "2026-10-18T19:00:00", "2026-10-17T10:32:00"
    assert status_text(j).endswith("🗓 Đã lên lịch TikTok 19:00 18/10")
    j.post.mode = "now"
    assert status_text(j).endswith("✅ Đã đăng TikTok")
    assert FAILED_TEXT.startswith("❌")
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_telegram_post.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.telegram.telegram_post'`.

- [ ] **Step 3: `send_message` nhận `reply_markup` (`backend/app/telegram/telegram_api.py`)**

Thay method `send_message`:

```python
    def send_message(self, chat_id: int, text: str, reply_to: int | None = None,
                     reply_markup: dict | None = None) -> int | None:
        data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True, **self._reply(reply_to)}
        if reply_markup:
            data["reply_markup"] = reply_markup
        body = self._call("sendMessage", data, as_json=True)
        return (body.get("result") or {}).get("message_id")
```

- [ ] **Step 4: Tạo `backend/app/telegram/telegram_post.py`**

```python
"""Đăng ngay / Lên lịch on Telegram: a message of its own with two buttons, sent once the job is about to be
done, then edited as the post moves on. Button data is "t:<token>:n" (now) or "t:<token>:s" (schedule),
under Telegram's 64 bytes."""

import secrets
from collections.abc import Callable
from datetime import datetime

from ..job_actions import InvalidAction
from ..job_models import JobState, TelegramMessageRef
from ..tiktok.post_plan import job_product_id, post_title, slot_label
from .telegram_api import TelegramApiError

MODES = {"n": "now", "s": "schedule"}
MODE_NAMES = {"now": "Đăng ngay", "schedule": "Lên lịch"}
OFFER_TEXT = "📤 Đăng video này lên TikTok?"
FAILED_TEXT = "❌ Đăng lỗi, mở AI Video Creator để thử lại."
STALE_TEXT = "Nút này đã cũ, dùng tin mới nhất hoặc nút trên tool."


def keyboard(token: str) -> dict:
    return {"inline_keyboard": [[{"text": "📤 Đăng ngay", "callback_data": f"t:{token}:n"},
                                 {"text": "🗓 Lên lịch", "callback_data": f"t:{token}:s"}]]}


def parse(data: str) -> tuple[str, str] | None:
    parts = (data or "").split(":")
    if len(parts) == 3 and parts[0] == "t" and parts[1] and parts[2] in MODES:
        return parts[1], MODES[parts[2]]
    return None


def waiting_text(mode: str) -> str:
    return f"⏳ Đã nhận: {MODE_NAMES[mode]}. Đang chờ lượt…"


def done_text(job: JobState) -> str:
    """The button message once TikTok has the post."""
    post = job.post
    if post.mode == "schedule" and post.scheduled_for:
        return f"🗓 Đã lên lịch đăng TikTok: {slot_label(datetime.fromisoformat(post.scheduled_for))}"
    return f"✅ Đã đăng lên TikTok lúc {datetime.fromisoformat(post.done_at):%H:%M}"


def result_message(job: JobState) -> str:
    """The new message under the link."""
    post = job.post
    if post.mode == "schedule" and post.scheduled_for:
        when = slot_label(datetime.fromisoformat(post.scheduled_for))
        return f"🗓 Đã lên lịch đăng TikTok lúc {when}: {post_title(job)}"
    return f"✅ Đã đăng lên TikTok: {post_title(job)}"


def state_text(job: JobState) -> str:
    """The button message for a job already asked to post, from either side."""
    return done_text(job) if job.post.done_at else waiting_text(job.post.mode)


def send_offer(job: JobState, api, update_job: Callable) -> JobState:
    """Bot jobs with a product ID get the two buttons under their link message, once."""
    origin = job.telegram
    if not origin or job.post.offer_message or job.post.mode or not job_product_id(job):
        return job
    token = secrets.token_hex(4)
    message_id = api.send_message(origin.chat_id, OFFER_TEXT, reply_to=origin.message_id, reply_markup=keyboard(token))

    def remember(j: JobState) -> None:
        j.post.offer_token = token
        if message_id:
            j.post.offer_message = TelegramMessageRef(chat_id=origin.chat_id, message_id=message_id)

    return update_job(remember)


def edit_offer(job: JobState, api, text: str) -> None:
    """New text, no buttons (editMessageText without reply_markup drops them). Best effort."""
    ref = job.post.offer_message
    if not ref:
        return
    try:
        api.edit_text(ref.chat_id, ref.message_id, text)
    except TelegramApiError:
        pass  # deleted message or "not modified": the post itself is what matters


class PostHandler:
    """Turns a tap on Đăng ngay / Lên lịch into request_post; returns the toast text."""

    def __init__(self, actions, api):
        self.actions, self.api = actions, api

    def handle(self, callback: dict) -> str:
        parsed = parse(callback.get("data", ""))
        message = callback.get("message") or {}
        chat_id, message_id = (message.get("chat") or {}).get("id"), message.get("message_id")
        if not parsed or chat_id is None:
            return ""
        token, mode = parsed
        job = next((j for j in self.actions.store.list() if j.post.offer_token == token), None)
        if job is None:
            self._edit(chat_id, message_id, STALE_TEXT)
            return STALE_TEXT
        try:
            self.actions.request_post(job.id, mode)
        except InvalidAction as exc:
            if job.post.mode:  # already asked here or in the tool: show where it stands, drop the buttons
                self._edit(chat_id, message_id, state_text(job))
            return str(exc)[:190]
        self._edit(chat_id, message_id, waiting_text(mode))
        return f"{MODE_NAMES[mode]}!"

    def _edit(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            self.api.edit_text(chat_id, message_id, text)
        except TelegramApiError:
            pass
```

- [ ] **Step 5: Chia lượt bấm theo tiền tố (`backend/app/telegram/telegram_setup.py`)**

Thêm import `from .telegram_post import PostHandler`. Thêm hàm trên `start_telegram`:

```python
def route_taps(pick, post):
    """Photo picker buttons carry "p:"/"g:", the post buttons "t:"."""
    def handle(callback: dict) -> str | None:
        return (post if (callback.get("data") or "").startswith("t:") else pick).handle(callback)

    return handle
```

Trong `start_telegram`, thay dòng `on_callback=PickHandler(actions, api, config).handle,` bằng:

```python
        on_callback=route_taps(PickHandler(actions, api, config), PostHandler(actions, api)),
```

- [ ] **Step 6: Tin "Đang" khi đăng (`backend/app/telegram/telegram_notify.py`)**

Thêm import:

```python
from datetime import datetime

from ..tiktok.post_plan import slot_label
```

Trong `STEP_NAMES`, thêm `"tiktok_post": "Đăng TikTok"` (sau `"tiktok_draft": "Lưu nháp TikTok"`).

Thay `status_text` bằng:

```python
def status_text(job: JobState) -> str:
    title = (job.source.title if job.source else "") or job.name
    if job.status == JobStatus.done:
        line = _posted(job) or "✅ Xong"
    elif job.status == JobStatus.failed:
        line = f"❌ Lỗi ở bước {STEP_NAMES.get(job.error.step, job.error.step) if job.error else ''}".rstrip()
    elif job.status == JobStatus.cancelled:
        line = "⏹ Đã huỷ"
    elif job.status == JobStatus.awaiting_review:
        line = "🖼 Chờ chọn ảnh" if job.gate == PICK_GATE else f"⏸ Chờ duyệt: {GATE_NAMES.get(job.gate, job.gate)}"
    elif job.current_step == "tiktok_post" and not job.post.mode:
        line = "✅ Xong"  # nobody pressed a post button: the step has nothing to do
    elif job.current_step == "tiktok_post" and job.post.mode == "schedule":
        line = "⏳ Đang: Lên lịch TikTok"
    else:
        line = f"⏳ Đang: {STEP_NAMES.get(job.current_step, job.current_step)}"
    return f"🎬 {title}\n{line}"


def _posted(job: JobState) -> str:
    post = job.post
    if not post.done_at:
        return ""
    if post.mode == "schedule" and post.scheduled_for:
        return f"🗓 Đã lên lịch TikTok {slot_label(datetime.fromisoformat(post.scheduled_for), weekday=False)}"
    return "✅ Đã đăng TikTok"
```

- [ ] **Step 7: Chạy test, xác nhận pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_telegram_post.py tests/test_status_message.py tests/test_telegram_pick.py tests/test_send_telegram.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/telegram/telegram_api.py backend/app/telegram/telegram_post.py \
        backend/app/telegram/telegram_setup.py backend/app/telegram/telegram_notify.py \
        backend/tests/test_telegram_post.py
git commit -m "Telegram: Đăng ngay / Lên lịch buttons and the posting status line

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Bước `tiktok_post`

**Files:**
- Create: `backend/app/steps/tiktok_post_step.py`
- Modify: `backend/app/steps/step_registry.py`
- Test: `backend/tests/test_tiktok_post_step.py`

**Interfaces:**
- Consumes: `PostPlan`, `post_video`, `StudioError` (Task 3); `read_items`, `latest_time`, `find_new_post`, `ContentPageError` (Task 2); `next_slot`, `too_far`, `slot_label`, `job_product_id`, `post_title`, `MAX_DAYS_AHEAD` (Task 1); `send_offer`, `edit_offer`, `done_text`, `result_message`, `FAILED_TEXT` (Task 5); `notify_target` (`telegram_notify`).
- Produces:
  - `run_tiktok_post(ctx: JobContext) -> None` (đăng ký trong `build_steps()` với tên `"tiktok_post"`)
  - `class BrowserStudio(ctx)` với `content_items() -> list[dict]`, `post(plan, before_click, dry_run=False) -> None`, `find_post(title, since, schedule_at) -> bool`
  - `open_studio(ctx) -> BrowserStudio` và `make_api(token)` (test thay thế)
  - `make_plan(ctx: JobContext, studio, now: datetime | None = None) -> PostPlan` (Task 7 dùng)
  - `other_scheduled(ctx: JobContext) -> list[datetime]`

- [ ] **Step 1: Viết test (fail)**

Tạo `backend/tests/test_tiktok_post_step.py`:

```python
"""The tiktok_post step with a fake TikTok Studio and a fake Bot API."""

from datetime import datetime, timedelta

import pytest

from app.config import TelegramConfig
from app.job_models import JobState, SourceInfo, TelegramMessageRef, TelegramOrigin, TikTokPostState
from app.steps import tiktok_post_step
from app.steps.step_types import StepFailure
from app.steps.tiktok_post_step import other_scheduled, run_tiktok_post
from app.telegram.telegram_api import TelegramApiError
from app.telegram.telegram_post import FAILED_TEXT, OFFER_TEXT
from app.tiktok.post_plan import slot_label

URL = "https://shop.tiktok.com/vn/pdp/1737383451447231991"
TITLE = "[JOLY 01] Dép sục+Tặng 1 bộ charm"


class FakeStudio:
    def __init__(self):
        self.items, self.found, self.fail = [], True, None
        self.posted, self.clicks = [], 0

    def latest(self, when: datetime):
        self.items = [{"desc": "bài cũ", "post_time": str(int(when.timestamp()))}]

    def content_items(self):
        return self.items

    def post(self, plan, before_click, dry_run=False):
        self.posted.append(plan)
        if self.fail:
            raise StepFailure(self.fail)
        before_click()
        self.clicks += 1

    def find_post(self, title, since, schedule_at):
        return self.found


class FakeApi:
    def __init__(self):
        self.sent, self.edits, self.fail = [], [], False

    def send_message(self, chat_id, text, reply_to=None, reply_markup=None):
        if self.fail:
            raise TelegramApiError("Bad Gateway")
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "markup": reply_markup})
        return 400 + len(self.sent)

    def edit_text(self, chat_id, message_id, text):
        self.edits.append((message_id, text))


@pytest.fixture
def rig(make_context, make_config, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
    exported = tmp_path / "dep-suc_2k60.mp4"
    exported.write_bytes(b"video")
    studio, api = FakeStudio(), FakeApi()
    monkeypatch.setattr(tiktok_post_step, "open_studio", lambda ctx: studio)
    monkeypatch.setattr(tiktok_post_step, "make_api", lambda token: api)

    def build(mode="now", offered=True, **job_fields):
        post = TikTokPostState(mode=mode)
        if offered:
            post.offer_token, post.offer_message = "abcd1234", TelegramMessageRef(chat_id=111, message_id=99)
        fields = dict(source=SourceInfo(url=URL, title=TITLE), hashtags=["#depsuc", "#giaydepnu"],
                      telegram=TelegramOrigin(chat_id=111, message_id=42), export_path=str(exported), post=post)
        fields.update(job_fields)
        job = JobState(id="t", name="dep-suc", input_file="input.jpg", created_at="t", **fields)
        return make_context(job=job, config=make_config(telegram=TelegramConfig(allowed_user_ids=[111])))

    return build, studio, api, exported


def test_post_now_clicks_once_confirms_then_reports(rig):
    build, studio, api, exported = rig
    ctx = build("now")
    run_tiktok_post(ctx)
    (plan,) = studio.posted
    assert plan.video == exported and plan.title == TITLE and plan.hashtags == ["#depsuc", "#giaydepnu"]
    assert plan.product_id == "1737383451447231991" and plan.schedule_at is None
    post = ctx.job.post
    assert post.submitted_at and post.done_at and post.notified and studio.clicks == 1
    assert api.edits == [(99, f"✅ Đã đăng lên TikTok lúc {datetime.fromisoformat(post.done_at):%H:%M}")]
    (msg,) = api.sent
    assert msg["text"] == f"✅ Đã đăng lên TikTok: {TITLE}" and msg["reply_to"] == 42 and msg["chat_id"] == 111


def test_schedule_takes_the_slot_after_the_latest_post(rig):
    build, studio, api, _ = rig
    ctx = build("schedule")
    latest = (datetime.now() + timedelta(days=2)).replace(hour=21, minute=30, second=0, microsecond=0)
    studio.latest(latest)
    run_tiktok_post(ctx)
    want = latest.replace(hour=23, minute=0)
    assert studio.posted[0].schedule_at == want
    assert ctx.job.post.scheduled_for == want.isoformat(timespec="seconds")
    assert api.sent[0]["text"] == f"🗓 Đã lên lịch đăng TikTok lúc {slot_label(want)}: {TITLE}"
    assert api.edits[-1] == (99, f"🗓 Đã lên lịch đăng TikTok: {slot_label(want)}")


def test_slots_this_tool_already_scheduled_count_too(rig):
    build, studio, _, _ = rig
    ctx = build("schedule")
    taken = (datetime.now() + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    other_dir = ctx.config.paths.jobs_dir / "20261017-090000-other"
    other_dir.mkdir(parents=True)
    other = JobState(id="other", name="x", input_file="", created_at="t",
                     post=TikTokPostState(mode="schedule", scheduled_for=taken.isoformat(), submitted_at="t"))
    (other_dir / "state.json").write_text(other.model_dump_json(), encoding="utf-8")
    assert other_scheduled(ctx) == [taken]
    run_tiktok_post(ctx)
    assert studio.posted[0].schedule_at == taken.replace(hour=11)


def test_too_far_ahead_stops_before_uploading(rig):
    build, studio, api, _ = rig
    ctx = build("schedule")
    studio.latest(datetime.now() + timedelta(days=31))
    with pytest.raises(StepFailure, match="30 ngày"):
        run_tiktok_post(ctx)
    assert studio.posted == [] and api.edits[-1] == (99, FAILED_TEXT)


def test_failure_before_the_click_can_simply_be_retried(rig):
    build, studio, api, _ = rig
    ctx = build("now")
    studio.fail = "Không tìm thấy sản phẩm 1737383451447231991 khi Add link."
    with pytest.raises(StepFailure, match="Không tìm thấy sản phẩm"):
        run_tiktok_post(ctx)
    assert ctx.job.post.submitted_at is None and api.edits[-1] == (99, FAILED_TEXT)
    studio.fail = None
    run_tiktok_post(ctx)
    assert ctx.job.post.done_at and studio.clicks == 1


def test_not_seen_after_the_click_never_clicks_again(rig):
    build, studio, _, _ = rig
    ctx = build("now")
    studio.found = False
    with pytest.raises(StepFailure, match="Tool đã bấm Post"):
        run_tiktok_post(ctx)
    assert ctx.job.post.submitted_at and not ctx.job.post.done_at
    studio.found = True
    with pytest.raises(StepFailure, match="Tool đã bấm Post"):
        run_tiktok_post(ctx)  # without the user's Thử lại (which clears submitted_at) it stays put
    assert studio.clicks == 1


def test_telegram_error_after_posting_only_resends_the_message(rig):
    build, studio, api, _ = rig
    ctx = build("now")
    api.fail = True
    with pytest.raises(StepFailure, match="nhắn Telegram lỗi"):
        run_tiktok_post(ctx)
    assert ctx.job.post.done_at and not ctx.job.post.notified
    assert all(text != FAILED_TEXT for _, text in api.edits)  # the post did go out
    api.fail = False
    run_tiktok_post(ctx)
    assert studio.clicks == 1 and len(api.sent) == 1 and ctx.job.post.notified


def test_nobody_asked_only_offers_the_buttons_once(rig):
    build, studio, api, _ = rig
    ctx = build(None, offered=False)
    run_tiktok_post(ctx)
    (msg,) = api.sent
    assert msg["text"] == OFFER_TEXT and msg["reply_to"] == 42 and msg["markup"]["inline_keyboard"]
    run_tiktok_post(ctx)
    assert len(api.sent) == 1 and studio.posted == []


def test_offer_failure_never_fails_the_job(rig):
    build, studio, api, _ = rig
    ctx = build(None, offered=False)
    api.fail = True
    run_tiktok_post(ctx)  # no exception: the tool's buttons still work
    assert ctx.job.post.offer_message is None and studio.posted == []


def test_missing_video_fails_before_any_browser_work(rig):
    build, studio, _, exported = rig
    exported.unlink()
    with pytest.raises(StepFailure, match="video đã xuất"):
        run_tiktok_post(build("now"))
    assert studio.posted == []
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_tiktok_post_step.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.steps.tiktok_post_step'`.

- [ ] **Step 3: Tạo `backend/app/steps/tiktok_post_step.py`**

```python
"""Last step: post the exported video on TikTok now, or at the next free slot, once the user pressed Đăng ngay /
Lên lịch (tool or Telegram). For jobs nobody asked to post it only sends those two buttons to Telegram.

submitted_at is saved right before the Post/Schedule click and done_at only once the post shows on TikTok
Studio's Content page, so neither "Thử lại" nor a restart ever clicks a second time on its own.
"""

import time
from datetime import datetime
from pathlib import Path

from ..flow.cdp_connection import BrowserNotRunning, browser_context, capture_page_error, new_tab
from ..job_models import JobState, now_iso
from ..telegram.telegram_api import TelegramApi, TelegramApiError
from ..telegram.telegram_notify import notify_target
from ..telegram.telegram_post import FAILED_TEXT, done_text, edit_offer, result_message, send_offer
from ..tiktok.post_plan import MAX_DAYS_AHEAD, job_product_id, next_slot, post_title, slot_label, too_far
from ..tiktok.studio_content import ContentPageError, find_new_post, latest_time, read_items
from ..tiktok.studio_post import PostPlan, post_video
from ..tiktok.studio_upload import StudioError
from .step_types import JobContext, StepFailure

CONFIRM_TRIES, CONFIRM_WAIT_SEC = 6, 20  # up to 2 minutes for a new post to show on the Content page


def make_api(token: str) -> TelegramApi:  # replaced in tests
    return TelegramApi(token)


class BrowserStudio:
    """TikTok Studio in background tabs of the tool's Chrome. A tab that fails stays open for the user to see."""

    def __init__(self, ctx: JobContext):
        self.ctx = ctx

    def content_items(self) -> list[dict]:
        return self._in_tab(lambda page: read_items(page, self.ctx.config.tiktok.content_url))

    def post(self, plan: PostPlan, before_click, dry_run: bool = False) -> None:
        self._in_tab(lambda page: post_video(page, self.ctx.config.tiktok, plan, self.ctx.report, self.ctx.log,
                                             before_click, dry_run=dry_run), keep_open=dry_run)

    def find_post(self, title: str, since: datetime, schedule_at: datetime | None) -> bool:
        for attempt in range(CONFIRM_TRIES):
            if find_new_post(self.content_items(), title, since, schedule_at):
                return True
            if attempt + 1 < CONFIRM_TRIES:
                time.sleep(CONFIRM_WAIT_SEC)
        return False

    def _in_tab(self, work, keep_open: bool = False):
        try:
            with browser_context(self.ctx.config.flow.cdp_port) as context:
                page = new_tab(context)  # background tab: Chrome stays behind the user's work
                try:
                    result = work(page)
                except (StudioError, ContentPageError) as exc:
                    raise StepFailure(str(exc), screenshot=capture_page_error(page, self.ctx.path("errors"))) from exc
                except Exception as exc:
                    shot = capture_page_error(page, self.ctx.path("errors"))
                    reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                    raise StepFailure(f"Thao tác trên TikTok Studio lỗi: {reason}", screenshot=shot) from exc
                if not keep_open:
                    page.close()  # only on success: a failed tab stays open so the user can look at it
                return result
        except BrowserNotRunning as exc:
            raise StepFailure(str(exc)) from exc


def open_studio(ctx: JobContext) -> BrowserStudio:  # replaced in tests
    return BrowserStudio(ctx)


def run_tiktok_post(ctx: JobContext) -> None:
    job = ctx.job
    if job.post.mode is None:
        offer_buttons(ctx)
        return
    try:
        if not job.post.done_at:
            job = post_now_or_later(ctx)
        job = tell_telegram(ctx, job)
    except StepFailure:
        latest = ctx.update_job(lambda j: None)
        if not latest.post.done_at:  # a failed Telegram message after posting is not a failed post
            mark_offer(ctx, latest, FAILED_TEXT)
        raise
    ctx.report(1, done_text(job))


def post_now_or_later(ctx: JobContext) -> JobState:
    job = ctx.job
    if job.post.submitted_at:
        raise StepFailure(unconfirmed(job))
    studio = open_studio(ctx)
    plan = make_plan(ctx, studio)
    if plan.schedule_at:
        ctx.update_job(lambda j: setattr(j.post, "scheduled_for", plan.schedule_at.isoformat(timespec="seconds")))
    clicked: dict[str, JobState] = {}

    def before_click() -> None:
        clicked["job"] = ctx.update_job(lambda j: setattr(j.post, "submitted_at", now_iso()))

    try:
        studio.post(plan, before_click)
    except StepFailure as exc:
        if "job" in clicked:  # failed after the click: say so, never suggest a plain retry
            raise StepFailure(unconfirmed(clicked["job"]), screenshot=exc.screenshot) from exc
        raise
    if "job" not in clicked:
        raise StepFailure("Tool chưa bấm Post/Schedule (thao tác dừng giữa chừng). Bấm Thử lại.")
    submitted = clicked["job"]
    ctx.report(0.95, "Kiểm tra bài trên TikTok Studio")
    try:
        found = studio.find_post(plan.title, datetime.fromisoformat(submitted.post.submitted_at), plan.schedule_at)
    except StepFailure:
        found = False
    if not found:
        raise StepFailure(unconfirmed(submitted))
    job = ctx.update_job(lambda j: setattr(j.post, "done_at", now_iso()))
    ctx.log(f"tiktok_post: {done_text(job)}")
    return job


def make_plan(ctx: JobContext, studio, now: datetime | None = None) -> PostPlan:
    """What to post and, for Lên lịch, the slot after the latest post on TikTok and in this tool."""
    job = ctx.job
    product_id = job_product_id(job)
    if not product_id:
        raise StepFailure("Không biết ID sản phẩm của job này; chạy lại bước Đọc TikTok.")
    plan = PostPlan(video=exported_video(ctx), title=post_title(job), hashtags=list(job.hashtags),
                    product_id=product_id)
    if job.post.mode == "schedule":
        ctx.report(0.05, "Đọc lịch đăng trên TikTok Studio")
        now = now or datetime.now()
        latest = latest_time(studio.content_items())
        cfg = ctx.config.tiktok
        plan.schedule_at = next_slot(now, cfg.schedule_slots, cfg.schedule_lead_min, [latest, *other_scheduled(ctx)])
        ctx.log(f"tiktok_post: bài muộn nhất {latest or 'không có'}, chọn {plan.schedule_at}")
        if too_far(plan.schedule_at, now):
            raise StepFailure(f"Khung giờ kế tiếp là {slot_label(plan.schedule_at)}, quá {MAX_DAYS_AHEAD} ngày "
                              "TikTok cho lên lịch trước. Bớt bài đã lên lịch trên TikTok Studio rồi bấm Thử lại.")
    return plan


def exported_video(ctx: JobContext) -> Path:
    exported = Path(ctx.job.export_path) if ctx.job.export_path else None
    video = exported if exported and exported.exists() else ctx.path("final-4k60.mp4")
    if not video.exists():
        raise StepFailure("Không thấy video đã xuất, chạy lại bước xuất file.")
    return video


def other_scheduled(ctx: JobContext) -> list[datetime]:
    """Slots this tool already scheduled for other jobs: TikTok's list may not show a fresh one yet."""
    taken = []
    for state in ctx.config.paths.jobs_dir.glob("*/state.json"):
        if state.parent.resolve() == ctx.job_dir.resolve():
            continue
        try:
            other = JobState.model_validate_json(state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if other.post.mode == "schedule" and other.post.submitted_at and other.post.scheduled_for:
            taken.append(datetime.fromisoformat(other.post.scheduled_for))
    return taken


def unconfirmed(job: JobState) -> str:
    label = "Schedule" if job.post.mode == "schedule" else "Post"
    clicked = datetime.fromisoformat(job.post.submitted_at)
    return (f"Tool đã bấm {label} lúc {clicked:%H:%M %d/%m} nhưng chưa thấy bài trên TikTok Studio. "
            "Kiểm tra TikTok Studio; nếu chưa có bài thì bấm Thử lại.")


def tell_telegram(ctx: JobContext, job: JobState) -> JobState:
    """The button message shows the result and a new message goes under the link; only the latter can fail."""
    token = ctx.config.telegram.bot_token
    target = notify_target(job, ctx.config.telegram)
    if job.post.notified or not token or not target:
        return job
    api = make_api(token)
    edit_offer(job, api, done_text(job))
    chat_id, reply_to = target
    try:
        api.send_message(chat_id, result_message(job), reply_to=reply_to)
    except TelegramApiError as exc:
        verb = "lên lịch" if job.post.mode == "schedule" else "đăng"
        raise StepFailure(f"Đã {verb} TikTok nhưng nhắn Telegram lỗi: {exc}. Bấm 'Thử lại' để nhắn lại.") from exc
    return ctx.update_job(lambda j: setattr(j.post, "notified", True))


def offer_buttons(ctx: JobContext) -> None:
    token = ctx.config.telegram.bot_token
    if not token or not ctx.job.telegram:
        return
    try:
        send_offer(ctx.job, make_api(token), ctx.update_job)
    except (TelegramApiError, OSError) as exc:
        ctx.log(f"tiktok_post: không gửi được nút Đăng ngay / Lên lịch lên Telegram ({exc}); dùng nút trên tool")


def mark_offer(ctx: JobContext, job: JobState, text: str) -> None:
    token = ctx.config.telegram.bot_token
    if token:
        edit_offer(job, make_api(token), text)
```

- [ ] **Step 4: Đăng ký bước (`backend/app/steps/step_registry.py`)**

Thêm import `from .tiktok_post_step import run_tiktok_post` và dòng `"tiktok_post": run_tiktok_post,` sau `"tiktok_draft": run_tiktok_draft,`.

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_tiktok_post_step.py -q`
Expected: PASS (10 test).

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: toàn bộ pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/steps/tiktok_post_step.py backend/app/steps/step_registry.py backend/tests/test_tiktok_post_step.py
git commit -m "tiktok_post step: post or schedule, confirm on the Content page, report on Telegram

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Lệnh chạy thử `check_post` (dừng trước cú bấm)

**Files:**
- Create: `backend/app/tiktok/check_post.py`
- Test: `backend/tests/test_check_post.py`

**Interfaces:**
- Consumes: `BrowserStudio`, `make_plan` (Task 6); `load_config`, `JobStore`, `JobContext`.
- Produces: `check_post.main(argv: list[str] | None = None) -> int` (0 xong, 1 lỗi bước, 2 không có job).

- [ ] **Step 1: Viết test (fail)**

Tạo `backend/tests/test_check_post.py`:

```python
"""The dry-run command: plans like the step, calls the studio with dry_run, never changes the job."""

from app.job_models import SourceInfo
from app.job_store import JobStore
from app.tiktok import check_post

URL = "https://shop.tiktok.com/vn/pdp/1737383451447231991"


def test_dry_run_never_clicks_and_leaves_the_job_alone(make_config, monkeypatch, tmp_path, capsys):
    config = make_config()
    store = JobStore(config.paths.jobs_dir)
    job = store.create("a.jpg", b"img", "", {"cutout": True, "prompt": True, "flow_video": True})
    video = tmp_path / "out.mp4"
    video.write_bytes(b"video")
    store.update(job.id, lambda j: (setattr(j, "source", SourceInfo(url=URL, title="Dép sục")),
                                    setattr(j, "export_path", str(video))))
    seen = {}

    class Studio:
        def __init__(self, ctx):
            pass

        def content_items(self):
            return []

        def post(self, plan, before_click, dry_run=False):
            seen.update(plan=plan, dry_run=dry_run)

    monkeypatch.setattr(check_post, "load_config", lambda: config)
    monkeypatch.setattr(check_post, "BrowserStudio", Studio)
    assert check_post.main([job.id, "--schedule"]) == 0
    assert seen["dry_run"] is True and seen["plan"].schedule_at and seen["plan"].product_id == "1737383451447231991"
    assert JobStore(config.paths.jobs_dir).get(job.id).post.mode is None  # nothing saved
    assert check_post.main(["no-such-job"]) == 2
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_check_post.py -q`
Expected: FAIL — `ImportError: cannot import name 'check_post'`.

- [ ] **Step 3: Tạo `backend/app/tiktok/check_post.py`**

```python
"""Dry run of the Đăng TikTok step on a real job: everything in TikTok Studio except the final Post/Schedule click.

    cd backend && ../.venv/bin/python -m app.tiktok.check_post <job-id> [--schedule]

With --schedule it reads the Content page and picks the slot like the step does. It uploads the job's exported
video into the form (nothing is posted), fills the title and hashtags, adds the product link, turns on the AI
label, sets When to post, and stops. The tab stays open in the tool's Chrome, in the background: look at it, then
close it to throw the upload away. The job's state is not changed. Run it while no job is running.
"""

import argparse
import sys

from ..config import load_config
from ..job_store import JobNotFound, JobStore
from ..steps.step_types import JobContext, StepFailure
from ..steps.tiktok_post_step import BrowserStudio, make_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chạy thử Đăng TikTok, dừng trước nút Post/Schedule.")
    parser.add_argument("job_id")
    parser.add_argument("--schedule", action="store_true", help="chạy thử Lên lịch (mặc định: Đăng ngay)")
    args = parser.parse_args(argv)
    config = load_config()
    store = JobStore(config.paths.jobs_dir)
    try:
        job = store.get(args.job_id)
    except JobNotFound:
        print(f"Không có job {args.job_id}")
        return 2
    job.post.mode = "schedule" if args.schedule else "now"  # local copy only, never saved
    ctx = JobContext(job=job, job_dir=store.job_dir(job.id), config=config,
                     report=lambda p, m: print(f"[{p:4.0%}] {m}"), log=print, update_job=lambda fn: job)
    studio = BrowserStudio(ctx)
    try:
        plan = make_plan(ctx, studio)
        print(f"Kế hoạch: {plan}")
        studio.post(plan, before_click=lambda: None, dry_run=True)
    except StepFailure as exc:
        print(f"✖ {exc.reason}" + (f" (ảnh chụp: {exc.screenshot})" if exc.screenshot else ""))
        return 1
    print("✔ Đã dừng trước nút Post/Schedule. Xem tab TikTok Studio trong Chrome của tool rồi đóng tab đó.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_check_post.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tiktok/check_post.py backend/tests/test_check_post.py
git commit -m "check_post: dry run of posting that stops before the Post/Schedule click

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Giao diện tool — 2 nút, dòng kết quả, xác nhận Thử lại

**Files:**
- Modify: `frontend/src/api-client.ts`
- Modify: `frontend/src/components/job-detail-panel.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `POST /api/jobs/{id}/post` (Task 4); trường `post` và `source.product_id` trong JSON job (Task 1).
- Produces: `api.postOnTikTok(id, mode)`, `postResult(job)`, `type PostMode`.

- [ ] **Step 1: Sửa `frontend/src/api-client.ts`**

Thêm sau dòng `export type JobGate = …`:

```ts
export type PostMode = "now" | "schedule";
```

Trong `interface Job`, sửa `source` và thêm `post`:

```ts
  source: { url: string; title: string; description: string; candidates: string[]; product_id: string } | null;
  post: { mode: PostMode | null; scheduled_for: string | null; submitted_at: string | null; done_at: string | null };
```

Thay `STEPS` và `stepsFor`:

```ts
export const STEPS = [
  "fetch_source", "cutout", "upscale", "prompt", "flow_generate", "flow_download", "enhance", "export", "hashtags",
  "send_telegram", "tiktok_draft", "tiktok_post",
];
/** Only link jobs read TikTok, only Telegram jobs send the result back, and posting shows once asked for. */
export const stepsFor = (job: Job) =>
  STEPS.filter((s) => (s !== "fetch_source" || job.source) && (s !== "send_telegram" || job.telegram)
    && (s !== "tiktok_post" || job.post.mode));
```

Trong `STEP_LABELS`, thêm `tiktok_post: "Đăng TikTok",` sau `tiktok_draft`.

Trong object `api`, thêm sau `cancel`:

```ts
  postOnTikTok: (id: string, mode: PostMode) => post<Job>(`/api/jobs/${id}/post`, { mode }),
```

Thêm cuối file:

```ts
const WEEKDAYS = ["Chủ nhật", "thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy"];
const pad = (n: number) => String(n).padStart(2, "0");

/** "✅ Đã đăng TikTok lúc 10:32" / "🗓 Đã lên lịch TikTok: 19:00 Chủ nhật 18/10"; null until TikTok has the post. */
export function postResult(job: Job): string | null {
  const { mode, scheduled_for, done_at } = job.post;
  if (!done_at) return null;
  if (mode === "schedule" && scheduled_for) {
    const d = new Date(scheduled_for); // no offset in the string: read as local time, like the backend wrote it
    return `🗓 Đã lên lịch TikTok: ${pad(d.getHours())}:${pad(d.getMinutes())} ${WEEKDAYS[d.getDay()]} `
      + `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
  }
  const d = new Date(done_at);
  return `✅ Đã đăng TikTok lúc ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
```

- [ ] **Step 2: Sửa `frontend/src/components/job-detail-panel.tsx`**

Sửa import đầu file:

```tsx
import { api, displayName, fileUrl, GATE_LABELS, postResult, STATUS_LABELS, STEP_LABELS, type Job } from "../api-client";
```

Trong `ErrorPanel`, thay hàm `retry`:

```tsx
  const retry = () => {
    if (err.step === "flow_generate" && !window.confirm("Thử lại bước sinh video sẽ gửi lại lên Flow và tốn credit. Tiếp tục?")) return;
    if (err.step === "tiktok_post" && job.post.submitted_at
      && !window.confirm("Tool đã bấm Post/Schedule trước đó. Kiểm tra TikTok Studio trước: thử lại có thể đăng video 2 lần. Tiếp tục?")) return;
    run(() => api.retry(job.id, err.step));
  };
```

Thay `DonePanel`:

```tsx
function DonePanel({ job, onChange }: Props) {
  const { busy, error, run } = useJobAction(onChange);
  const result = postResult(job);
  const canPost = Boolean(job.source) && !job.post.mode;
  return (
    <div className="review">
      <video className="video" src={fileUrl(job, "final-4k60.mp4")} controls loop playsInline />
      <p className="muted">Đã xuất: <code>{job.export_path}</code></p>
      {result && <p className="post-result">{result}</p>}
      <div className="actions">
        {canPost && (
          <>
            <button className="btn btn-primary" disabled={busy}
              onClick={() => run(() => api.postOnTikTok(job.id, "now"))}>📤 Đăng ngay</button>
            <button className="btn" disabled={busy}
              onClick={() => run(() => api.postOnTikTok(job.id, "schedule"))}>🗓 Lên lịch</button>
          </>
        )}
        <button className={canPost ? "btn" : "btn btn-primary"} onClick={() => api.openExportDir()}>Mở thư mục xuất</button>
      </div>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}
```

Trong `JobDetailPanel`, thay dòng `else if (job.status === "done") body = <DonePanel job={job} />;` bằng:

```tsx
  else if (job.status === "done") body = <DonePanel job={job} onChange={onChange} />;
```

- [ ] **Step 3: Thêm style (`frontend/src/styles.css`)**

Thêm sau dòng `.review { … }`:

```css
.post-result { font-weight: 600; margin: 0; }
```

- [ ] **Step 4: Build, xác nhận không lỗi kiểu**

Run: `cd frontend && npm run build`
Expected: `tsc -b` không lỗi, Vite in `✓ built in …`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api-client.ts frontend/src/components/job-detail-panel.tsx frontend/src/styles.css
git commit -m "UI: Đăng ngay / Lên lịch on finished link jobs, the result line, a careful retry

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Sửa phần "Luồng xử lý"**

Thêm sau mục 12 (Lưu nháp TikTok) của danh sách đánh số:

~~~markdown
13. **Đăng TikTok (khi bạn bấm):** job tạo từ link có 2 nút **📤 Đăng ngay** và **🗓 Lên lịch**, trên tool và trong một tin Telegram riêng ngay sau tên + hashtag. Tool tải video lên TikTok Studio, điền tên + hashtag (chọn trong gợi ý của TikTok để thành hashtag thật), gắn link sản phẩm theo ID, bật nhãn AI, chọn Now hoặc khung giờ trống kế tiếp, bấm Post/Schedule, rồi kiểm tra bài trên trang Content.
~~~

- [ ] **Step 2: Thêm mục mới ngay trước `## Lưu nháp TikTok (tuỳ chọn)`**

~~~markdown
## Đăng TikTok (ngay hoặc lên lịch)

Cần: Chrome của tool đã đăng nhập TikTok bằng tài khoản bán hàng, và sản phẩm có trong showcase/shop của tài khoản đó (tool gắn link bằng ID sản phẩm lấy từ link TikTok Shop).

- Bấm **📤 Đăng ngay** hoặc **🗓 Lên lịch** ở khung "Xong" của job, hoặc trên tin "📤 Đăng video này lên TikTok?" của bot. Bấm là chạy, không hỏi lại. Mỗi video chỉ đăng một lần (làm lại video từ bước Xuất file thì đăng lại được).
- **Lên lịch** đọc trang Content của TikTok Studio, lấy giờ của bài muộn nhất (tính cả bài đã lên lịch), rồi chọn khung kế tiếp trong `tiktok.schedule_slots` (mặc định 7, 9, 11, …, 23h), cách bây giờ ít nhất `tiktok.schedule_lead_min` phút; hết khung trong ngày thì sang 7h hôm sau. TikTok chỉ cho lên lịch trước tối đa 30 ngày.
- Xong thì tool hiện "✅ Đã đăng TikTok lúc 10:32" hoặc "🗓 Đã lên lịch TikTok: 19:00 Chủ nhật 18/10". Trên Telegram, tin "Đang" và tin có 2 nút được sửa thành kết quả, kèm một tin mới báo đã đăng (có giờ nếu lên lịch).
- Không tìm thấy sản phẩm khi Add link: tool dừng, không đăng. Thêm sản phẩm vào showcase rồi bấm **Thử lại**.
- Tool chỉ coi là đã đăng khi thấy bài trên trang Content. Đã bấm Post/Schedule mà không thấy bài thì job báo lỗi và tool **không tự bấm lại**: vào TikTok Studio kiểm tra, chưa có bài thì bấm **Thử lại** (tool hỏi lại vì có thể đăng 2 lần).

Chạy thử mọi thao tác trừ cú bấm cuối (video được tải vào form nhưng không đăng; xem xong thì đóng tab đó). Chạy lúc tool không có job nào đang chạy:

```bash
cd backend && ../.venv/bin/python -m app.tiktok.check_post <job-id> [--schedule]
```
~~~

- [ ] **Step 3: Sửa bảng "Tuỳ chỉnh"**

Trong dòng `config.yaml`, thay `…, Telegram, lưu nháp TikTok |` bằng `…, Telegram, lưu nháp TikTok, khung giờ đăng TikTok |`.

- [ ] **Step 4: Chạy toàn bộ test và build**

Run: `cd backend && ../.venv/bin/python -m pytest -q`
Expected: toàn bộ pass (151 test cũ + các test mới).

Run: `cd frontend && npm run build`
Expected: build xong, không lỗi.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "README: posting or scheduling on TikTok

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Chạy thử trên TikTok thật (cần người dùng đồng ý)

Không có code. Làm theo thứ tự, mỗi bước dừng lại chờ người dùng.

- [ ] **Step 1: Hỏi người dùng** có cho chạy thử bây giờ không. Kiểm tra trước: `curl -s http://127.0.0.1:8765/api/jobs` không có job `running`/`queued`. Chọn một job đã xong mà sản phẩm có trong showcase, ví dụ sản phẩm `1737383451447231991` (dép JOLY) nếu còn job của nó trong `jobs/`.
- [ ] **Step 2: Chạy thử Đăng ngay rồi Lên lịch** (không bấm Post/Schedule):

```bash
cd backend && ../.venv/bin/python -m app.tiktok.check_post <job-id>
cd backend && ../.venv/bin/python -m app.tiktok.check_post <job-id> --schedule
```

Expected: mỗi lệnh in `✔ Đã dừng trước nút Post/Schedule`; trong tab (nền) thấy mô tả có hashtag màu (thật), link sản phẩm, nhãn AI bật, When to post đúng (với `--schedule`: ngày giờ đúng khung tính ra). Báo kết quả cho người dùng; nhờ họ xem tab rồi đóng (hoặc đóng giúp bằng một script tìm tab qua `window.name`, không kéo Chrome lên trước). Lỗi thì sửa selector trong `tiktok-selectors.yaml`, chạy lại.
- [ ] **Step 3: Hỏi người dùng khởi động lại tool** (`./scripts/start.sh`) để nạp code mới, chỉ khi không có job nào đang chạy.
- [ ] **Step 4: Lần đăng thật đầu tiên do người dùng bấm** (trên tool hoặc Telegram). Sau đó xem `jobs/<id>/log.txt` cùng họ: nếu TikTok có hộp hỏi lại sau cú bấm mà tool chưa biết, thêm tên nút vào `confirm_post_buttons` và ghi lại vào spec §12.
