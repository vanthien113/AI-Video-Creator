# Quy tắc viết prompt quảng cáo

File này được gửi nguyên văn cho Claude mỗi lần viết prompt. Sửa thoải mái theo phong cách shop của bạn.
Các quy tắc bám theo hướng dẫn nội dung: có người dùng sản phẩm, nhiều góc quay, có lời nói, không cảnh tĩnh.

## Ngôn ngữ và độ dài
- Viết prompt bằng **tiếng Anh** (Veo hiểu tiếng Anh tốt nhất). Riêng lời nói của người trong video viết bằng **tiếng Việt** có dấu, đặt trong ngoặc kép.
- 90–160 từ, một đoạn liền, không gạch đầu dòng.

## Câu hook (bắt buộc)
- 2 giây đầu là câu hook do người trong video nói thẳng vào camera, kèm hình ảnh mở đầu có chuyển động mạnh (cận cảnh, máy lia nhanh vào sản phẩm).
- Tự nghĩ câu hook riêng cho sản phẩm này từ ảnh và thông tin sản phẩm, không theo khuôn hay câu mẫu nào: mỗi sản phẩm một cách mở đầu, một góc nhìn, một giọng điệu khác nhau.
- Câu hook tiếng Việt, ngắn (tối đa 12 từ), tự nhiên như người thật nói, bám vào điểm đáng chú ý nhất của chính sản phẩm này (kiểu dáng, màu, chất liệu, chi tiết, tính năng có trong thông tin sản phẩm hoặc ghi chú của shop). Không nêu công dụng mà thông tin sản phẩm không ghi.
- Tool gửi kèm các hook của những video gần đây: hook mới không được giống chúng về câu chữ, cách mở đầu hay góc nhìn.
- Viết đúng câu hook trong prompt theo dạng: `She says in Vietnamese: "..."`.

## Người và sản phẩm
- Có một người mẫu xuất hiện rõ trên màn hình và **đang dùng sản phẩm**: mang, mặc, bôi, cầm, mở hộp... tuỳ loại sản phẩm.
- Sau câu hook, người mẫu nói thêm 1 câu ngắn tiếng Việt về 1–2 tính năng chính nhìn thấy được hoặc có trong thông tin sản phẩm.
- Không bịa trải nghiệm cá nhân ("tôi dùng cả tháng rồi"), công dụng y tế hay thông số không có trong thông tin sản phẩm.
- Sản phẩm luôn rõ nét, đúng như ảnh. Viết rõ: "keep the product's exact shape, colors, logo and printed text unchanged".

## Cảnh quay
- Tự nghĩ kịch bản riêng cho sản phẩm này, không theo khuôn nào: bối cảnh, thứ tự cảnh, hành động của người mẫu, cách máy quay chuyển động và ánh sáng đều chọn theo đúng loại sản phẩm, phong cách và người sẽ mua nó.
- 2–3 cảnh nối nhau bằng cắt cảnh gọn, mỗi cảnh một góc máy và cỡ cảnh khác nhau.
- Luôn có chuyển động (người, sản phẩm hoặc máy quay). Không có cảnh đứng yên, không lặp lại.
- Bối cảnh đời thường, sạch đẹp, hợp với sản phẩm.
- Không cho người mẫu xoay người hay đảo chân

## Âm thanh
- Lời nói tiếng Việt rõ ràng, giọng tự nhiên, thân thiện. Nhạc nền nhẹ, nhỏ hơn giọng nói.

## Điều cấm
- Không có chữ, phụ đề, watermark, logo khác trong video.
- Không viết tên ứng dụng hay nền tảng (TikTok, Reels, Shorts...) trong prompt. Viết rõ: "clean original footage with no on-screen text, watermarks, app logos or usernames".
- Không mô tả giá tiền, khuyến mãi.
- Không nội dung bạo lực, người nổi tiếng, thương hiệu khác.
- Không để ảnh tĩnh hay khung hình đứng yên chiếm phần lớn video.

## Định dạng
- Video dọc 9:16, bố cục theo chiều dọc.

## Phần tóm tắt cho người duyệt
- Câu đầu tiên của `summary` là: `Hook: "<câu hook>"`. Sau đó 2–3 câu tiếng Việt giải thích ý tưởng.
