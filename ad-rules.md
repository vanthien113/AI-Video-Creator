# Quy tắc viết prompt quảng cáo

File này được gửi nguyên văn cho Claude mỗi lần viết prompt. Sửa thoải mái theo phong cách shop của bạn.
Các quy tắc bám theo hướng dẫn nội dung của TikTok Shop:
- Người giới thiệu **xuất hiện rõ mặt trên màn hình** và chủ động giới thiệu sản phẩm được gắn link.
- Sản phẩm được mang, mặc hoặc dùng trong chuyển động.
- Có lời nói về tính năng chính, nhiều góc quay và cỡ cảnh khác nhau.
- Không dùng cảnh tĩnh hoặc cảnh lặp lại.
- Không giới thiệu sản phẩm nào khác ngoài sản phẩm được gắn link.

Số liệu giữ chân người xem của shop: mất 1/3 người xem ở giây 1 và 2/3 ở giây 2, đúng lúc video mở bằng cảnh rộng hoặc cắt sang mặt người mẫu nói mà **không thấy sản phẩm**. Vì vậy sản phẩm phải chiếm khung hình ngay từ khung đầu tiên và có mặt trong mọi cảnh. Mặt người mẫu chỉ xuất hiện cùng khung với sản phẩm.

## Ngôn ngữ và độ dài
- Viết prompt bằng **tiếng Anh** (Veo hiểu tiếng Anh tốt nhất). Riêng lời nói trong video viết bằng **tiếng Việt** có dấu, đặt trong ngoặc kép.
- 130–200 từ (tính cả các câu bắt buộc), một đoạn liền, không gạch đầu dòng. Mỗi câu bắt buộc chỉ viết một lần, không lặp lại cụm mô tả giống nhau ở từng cảnh. Chia cảnh theo mốc giây ngay trong đoạn văn: "0–2s: … 2–6s: … 6–10s: …".
- Câu đầu tiên của prompt mô tả **khung hình đầu tiên**, viết rõ: "The very first frame is already a tight close-up of …".

## Cấu trúc 10 giây (bắt buộc)
- **0–2s, hook:** khung đầu tiên đã là cận cảnh sản phẩm **đang được dùng**, sản phẩm chiếm phần lớn khung hình. Ngay trong giây đầu phải có một chuyển động lớn, dễ thấy (bàn chân từ trên hạ xuống đặt vào khung, máy lia nhanh theo bước chân, tay nhấc và bẻ cong đế…). Không bắt đầu bằng sản phẩm đã nằm yên trên chân. Câu hook bắt đầu ngay trong cảnh này.
- **2–6s, người mẫu giới thiệu:** người mẫu **xuất hiện rõ mặt**, nhìn vào máy và nói. Mặt và sản phẩm nằm **trong cùng khung hình**, sản phẩm chiếm ít nhất 1/4 khung. Ví dụ: ngồi trên bậc thềm, cầm một chiếc giày hay dép nâng lên cạnh mặt hoặc trước ngực, xoay cho máy thấy, bẻ cong đế, chỉ tay vào chi tiết có trong thông tin sản phẩm (đế, chất liệu, khóa, đường may, vân). Người mẫu nói câu tính năng.
- **6–10s, mang và chốt:** người mẫu mang sản phẩm, bước vài bước về phía máy, máy hạ thấp ngang mắt cá chân. Nói câu chốt ngắn. **Khung hình cuối là cận cảnh sản phẩm trên chân**, người mẫu vẫn ở trong khung.
- Sản phẩm có mặt rõ trong **mọi cảnh, suốt 10 giây**. Không có khoảnh khắc nào chỉ thấy mặt, phong cảnh hoặc khung trống.
- Hành động nối liền giữa các cảnh, không có lúc đứng yên chờ chuyển cảnh.

## Câu hook (bắt buộc)
- Tự nghĩ câu hook riêng cho sản phẩm này từ ảnh và thông tin sản phẩm, không theo khuôn hay câu mẫu nào: mỗi sản phẩm một cách mở đầu, một góc nhìn, một giọng điệu khác nhau.
- Câu hook tiếng Việt, ngắn (tối đa 10 từ, nói xong trong 2 giây), tự nhiên như người thật nói, bám vào điểm đáng chú ý nhất của chính sản phẩm này (kiểu dáng, màu, chất liệu, chi tiết, tính năng có trong thông tin sản phẩm hoặc ghi chú của shop). Không nêu công dụng mà thông tin sản phẩm không ghi.
- Hook phải khiến người xem muốn xem tiếp. Đổi qua lại giữa các kiểu: hỏi thẳng người xem, chạm đúng điều người mua lo (chỉ khi thông tin sản phẩm có tính năng giải quyết điều đó), chi tiết bất ngờ khi nhìn gần, so sánh vui, gọi đúng nhóm người sẽ mua. Tránh câu chỉ mô tả hoặc khen chung chung ("đẹp quá", "xinh xỉu").
- Tool gửi kèm các hook của những video gần đây: hook mới không được giống chúng về câu chữ, cách mở đầu, góc nhìn hay kiểu hook.

## Cách viết lời nói
- Người mẫu phải nói thẳng vào máy **với mặt rõ ràng trong ít nhất 3 giây**, và luôn có sản phẩm trong cùng khung hình đó. Viết theo dạng: `She says in Vietnamese, holding the product up beside her face: "..."` (thay hành động cho hợp sản phẩm).
- Ở cảnh chỉ quay sản phẩm (cận chân, cận chi tiết), lời nói là giọng của chính người mẫu đó, viết: `Her voice: "..."`.
- Tổng lời nói tối đa khoảng 25 từ cho 10 giây: hook, một câu tính năng, một câu chốt.
- Câu chốt mời bình luận một cách tự nhiên, ví dụ hỏi người xem chọn màu nào hay mang size mấy. Không nói giá, khuyến mãi, giỏ hàng hay link.

## Người và sản phẩm
- Có một người mẫu đang dùng sản phẩm: mang, mặc, bôi, cầm, mở hộp… tuỳ loại sản phẩm.
- Không bịa trải nghiệm cá nhân ("tôi dùng cả tháng rồi"), công dụng y tế hay thông số không có trong thông tin sản phẩm.
- Sản phẩm luôn rõ nét, đúng như ảnh. Viết rõ: "keep the product's exact shape, colors, logo and printed text unchanged".
- Không cho người mẫu xoay người hay đảo chân.

## Cảnh quay
- Tự nghĩ bối cảnh, hành động, ánh sáng và chuyển động máy riêng cho sản phẩm này, theo đúng phong cách và người sẽ mua nó. Không lặp lại bối cảnh của video gần đây.
- 3 cảnh nối nhau bằng cắt cảnh gọn, mỗi cảnh một góc máy và cỡ cảnh khác nhau. Giày dép: ưu tiên góc thấp ngang mắt cá chân, cận cảnh và trung cảnh từ đầu gối trở xuống. Cảnh toàn thân tối đa 2 giây.
- Luôn có chuyển động (người, sản phẩm hoặc máy quay). Không có cảnh đứng yên, không lặp lại.
- Bối cảnh đời thường, sạch đẹp, sáng, hợp với sản phẩm.

## Bố cục
- Video dọc 9:16, bố cục theo chiều dọc.
- Cảnh thật phủ kín khung hình từ mép trên xuống mép dưới. Viết rõ: "full-frame real scene edge to edge, no blank bands, borders or empty areas". Không yêu cầu chừa khoảng trống hay vùng trơn trong khung: model sẽ vẽ ra dải màu trống.
- Sản phẩm đặt ở vùng giữa khung hình, kể cả ở khung cuối (hạ máy xuống ngang mắt cá chân để giày dép không rơi xuống đáy khung). Tránh đặt sản phẩm ở 1/5 dưới cùng và sát mép phải: các vùng này bị che khi đăng, và góc dưới bên phải còn có logo.

## Âm thanh
- Lời nói bắt đầu **ngay từ khung đầu tiên**, không có đoạn im lặng mở đầu. Viết rõ: "her voice starts at the very first frame, no silent intro".
- Giọng tiếng Việt to, rõ, nhịp nhanh, tươi, thân thiện.
- Rải lời nói đều theo cảnh: hook bắt đầu ở 0s và nói xong trước 2.5s, câu tính năng trong 2.5–6s, câu chốt trong 6.5–9.5s.
- Nhạc nền nhịp vui, nhỏ hơn giọng nói, chạy liên tục từ giây 0 tới giây 10, không ngắt giữa các cảnh và không tắt trước khi hết video. Viết rõ: "continuous background music from the first to the last frame, no silent gaps".

## Điều cấm
- Không có chữ, phụ đề, watermark, logo khác trong video.
- Không viết tên ứng dụng hay nền tảng (TikTok, Reels, Shorts...) trong prompt. Viết rõ: "clean original footage with no on-screen text, watermarks, app logos or usernames".
- Không mô tả giá tiền, khuyến mãi.
- Không nội dung bạo lực, người nổi tiếng, thương hiệu khác.
- Không mở đầu bằng: cảnh rộng, ảnh sản phẩm trên nền trắng hay nền studio, cận mặt người mẫu. Không dùng các cụm dễ ra cảnh rộng ở mở đầu: "push-in", "zoom in from", "wide shot", "establishing shot".
- Không có cảnh cận mặt mà không thấy sản phẩm. Không làm video chỉ có chân và giọng đọc mà không thấy mặt người giới thiệu.
- Không giới thiệu, nhắc tên hay làm nổi bật sản phẩm khác (quần áo, túi, phụ kiện của người mẫu) ngoài sản phẩm chính. Trang phục để trơn, màu trung tính, không logo.
- Không để người mẫu đi ra khỏi khung hình hay đi xa dần. Không kết thúc bằng khung trống hoặc cảnh rộng. Không dùng "walks away", "walks across the room", "exits the frame".
- Không để ảnh tĩnh hay khung hình đứng yên chiếm phần lớn video.

## Phần tóm tắt cho người duyệt
- Câu đầu tiên của `summary` là: `Hook: "<câu hook>"`. Sau đó 2–3 câu tiếng Việt giải thích ý tưởng, nêu rõ khung đầu tiên là gì và khung cuối là gì.

## Caption bài đăng (`caption`)
Caption được copy nguyên văn để đăng kèm video. Tool tự thêm hashtag phía sau.
- Tiếng Việt có dấu, viết như người thật nhắn tin: 1–2 câu, tối đa 150 ký tự. Viết hoa đúng chính tả như câu bình thường: hoa chữ đầu câu và tên riêng (EVA, PU…). Không Viết Hoa Mỗi Chữ như tên sản phẩm, không VIẾT HOA CẢ CÂU.
- Câu đầu cùng ý với câu hook trong video (viết gọn lại được, không cần chép nguyên văn), để người đọc thấy khớp với video đang xem.
- Câu sau nêu 1–2 điểm đáng tiền nhất có trong thông tin sản phẩm (chất liệu, đế, độ cao, tính năng), kèm lưu ý size nếu trang sản phẩm có (ví dụ "size 35–40", "chân bè lùi 1 size"). Có thể kết bằng một câu hỏi ngắn mời bình luận.
- Gọi đúng loại sản phẩm theo cách người mua hay tìm và đúng với sản phẩm trong ảnh (ví dụ "dép tổ ong độn đế", "giày búp bê đế bệt").
- Tối đa 1 emoji, hợp với sản phẩm.
- Chỉ dùng thông tin có trong thông tin sản phẩm hoặc nhìn thấy trong ảnh.
- Không có: hashtag, giá, khuyến mãi, "deal", "sale", mã hàng hay mã mẫu, tên shop, tên thương hiệu, năm ("2024", "mới về 2026"), từ phóng đại hoặc cam kết ("bán chạy", "hot", "hot trend", "siêu phẩm", "đảm bảo", "rẻ nhất", "số 1"), lời kêu gọi bấm link hay giỏ hàng, tên ứng dụng hay nền tảng.
- Không chép lại tên sản phẩm trên trang shop.
