# Quy tắc viết prompt quảng cáo

File này được gửi nguyên văn cho Claude mỗi lần viết prompt. Sửa thoải mái theo phong cách shop của bạn.
Các quy tắc bám theo hướng dẫn nội dung của TikTok Shop: có người dùng sản phẩm, nhiều góc quay, có lời nói, không cảnh tĩnh.

## Ngôn ngữ và độ dài
- Viết prompt bằng **tiếng Anh** (Veo hiểu tiếng Anh tốt nhất). Riêng lời nói của người trong video viết bằng **tiếng Việt**, đặt trong ngoặc kép.
- 90–160 từ, một đoạn liền, không gạch đầu dòng.

## Câu hook (bắt buộc)
- 2 giây đầu là câu hook do người trong video nói thẳng vào camera, kèm hình ảnh mở đầu có chuyển động mạnh (cận cảnh, máy lia nhanh vào sản phẩm).
- Câu hook tiếng Việt, tối đa 12 từ, đánh vào nỗi đau hoặc lợi ích rõ nhất của sản phẩm, dạng câu hỏi hoặc lời gọi thẳng. Ví dụ: "Chị em nào đi làm cả ngày mà hay đau chân thì xem ngay!"
- Viết đúng câu hook trong prompt theo dạng: `She says in Vietnamese: "..."`.

## Người và sản phẩm
- Có một người mẫu xuất hiện rõ trên màn hình và **đang dùng sản phẩm**: mang, mặc, bôi, cầm, mở hộp... tuỳ loại sản phẩm.
- Sau câu hook, người mẫu nói thêm 1 câu ngắn tiếng Việt về 1–2 tính năng chính nhìn thấy được hoặc có trong thông tin sản phẩm.
- Không bịa trải nghiệm cá nhân ("tôi dùng cả tháng rồi"), công dụng y tế hay thông số không có trong thông tin sản phẩm.
- Sản phẩm luôn rõ nét, đúng như ảnh. Viết rõ: "keep the product's exact shape, colors, logo and printed text unchanged".

## Cảnh quay
- 2–3 cảnh nối nhau bằng cắt cảnh gọn, mỗi cảnh một góc máy và cỡ cảnh khác nhau. Ví dụ: cận cảnh sản phẩm lúc hook → toàn thân khi đang dùng → cận chi tiết chất liệu.
- Luôn có chuyển động: người đi lại, xoay sản phẩm, máy dolly hoặc orbit. Không có cảnh đứng yên, không lặp lại.
- Bối cảnh đời thường nhưng sạch đẹp, hợp với sản phẩm (ví dụ: giày → vỉa hè quán cà phê, văn phòng; mỹ phẩm → bàn trang điểm). Ánh sáng tự nhiên, mềm.

## Âm thanh
- Lời nói tiếng Việt rõ ràng, giọng tự nhiên, thân thiện. Nhạc nền nhẹ, nhỏ hơn giọng nói.

## Điều cấm
- Không có chữ, phụ đề, watermark, logo khác trong video.
- Không mô tả giá tiền, khuyến mãi.
- Không nội dung bạo lực, người nổi tiếng, thương hiệu khác.
- Không để ảnh tĩnh hay khung hình đứng yên chiếm phần lớn video.

## Định dạng
- Video dọc 9:16 cho TikTok/Reels, bố cục theo chiều dọc.

## Phần tóm tắt cho người duyệt
- Câu đầu tiên của `summary` là: `Hook: "<câu hook>"`. Sau đó 2–3 câu tiếng Việt giải thích ý tưởng.
