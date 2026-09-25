# Knowledge examples for AIC Visual Query Expert

File này chứa ví dụ tham khảo, không phải quy tắc hành vi. Không sao chép vật thể hoặc từ khóa của ví dụ sang đề mới nếu đầu vào không cung cấp chúng.

## 1. Món ăn có danh từ mơ hồ

Đầu vào:

Người phụ nữ lấy một thành phẩm từ đồ vật màu đỏ, tiếp tục cho nguyên liệu vào. Thành phẩm màu trắng, nở lớn hơn ban đầu, giống các sợi que dính với nhau và được bày trên vật liệu màu trắng.

Đầu ra:

```json
{
  "original_query": "Người phụ nữ lấy một thành phẩm từ đồ vật màu đỏ, tiếp tục cho nguyên liệu vào. Thành phẩm màu trắng, nở lớn hơn ban đầu, giống các sợi que dính với nhau và được bày trên vật liệu màu trắng.",
  "context": {"vi": "Một phụ nữ chế biến món ăn bằng dụng cụ nấu màu đỏ", "en": "A woman prepares food using a red cooking appliance"},
  "events": [
    {"vi": "Người phụ nữ lấy một miếng thức ăn dạng lưới khỏi dụng cụ nấu màu đỏ", "en": "A woman removes a lattice-like food piece from a red cooking appliance", "anchor": true, "visual_keywords": ["phụ nữ", "dụng cụ đỏ", "miếng dạng lưới"], "ocr": "", "asr": ""},
    {"vi": "Miếng thức ăn nở phồng, chuyển thành màu trắng với các que nhỏ dính thành lưới", "en": "The food expands into a white puffed lattice made of connected thin sticks", "anchor": false, "visual_keywords": ["màu trắng", "nở phồng", "lưới que nhỏ"], "ocr": "", "asr": ""},
    {"vi": "Nhiều miếng thức ăn trắng dạng lưới được bày trên đĩa hoặc khay trắng", "en": "Several white lattice-like food pieces are arranged on a white plate or tray", "anchor": true, "visual_keywords": ["nhiều miếng trắng", "đĩa trắng", "bày món"], "ocr": "", "asr": ""}
  ],
  "search_clauses": ["phụ nữ lấy thức ăn dạng lưới khỏi dụng cụ nấu màu đỏ", "thức ăn nở phồng màu trắng giống các que nhỏ dính thành lưới", "nhiều miếng thức ăn trắng dạng lưới trên đĩa trắng"],
  "search_clauses_en": ["woman removes lattice-like food from a red cooking appliance", "food expands into a white puffed lattice of connected thin sticks", "several white lattice-like food pieces on a white plate"],
  "distinctive_features": ["dụng cụ nấu màu đỏ", "thức ăn trắng nở phồng dạng lưới", "đĩa hoặc khay trắng"],
  "possible_confusions": ["chưa đủ bằng chứng để gọi tên chính xác món ăn", "đồ vật đỏ có thể là nồi, chảo hoặc máy làm bánh"],
  "ocr_queries": [],
  "asr_queries": [],
  "recommended_mode": "temporal",
  "max_gap_s": 120
}
```

Điểm quan trọng: không đoán tên món; chuyển các danh từ “thành phẩm/đồ vật” thành mô tả màu, hình dạng, hành động và quan hệ không gian có thể nhìn thấy.

## 2. Bài giảng có OCR và ASR

Đầu vào:

Một giáo viên nam đứng bên trái màn hình. Slide hướng dẫn chấm điểm có phần a nói cấu trúc bài nghị luận gồm mở bài, thân bài và kết bài. Bài giảng yêu cầu phân tích nhân vật. Tác giả được giới thiệu gắn bó với đề tài miền núi nào?

Xử lý đúng:

- Tạo sự kiện giáo viên cạnh slide hướng dẫn chấm điểm và sự kiện slide giới thiệu tác giả/tác phẩm nếu chúng là hai đoạn kế tiếp.
- Dùng OCR ngắn `mở bài thân bài kết bài`, `phân tích nhân vật`.
- Dùng ASR `duyên nợ gắn bó với đề tài miền núi` nếu câu này nhiều khả năng chỉ được nói.
- Không tự trả lời tên miền núi; không thêm tác giả hoặc tác phẩm không có trong đề.

## 3. Chuỗi bốn khoảnh khắc

Nếu đầu vào đánh dấu E1–E4 của con lân đỏ biểu diễn trên cột trụ:

- Giữ đúng bốn sự kiện và đúng thứ tự.
- Không gộp E2/E3 chỉ vì cùng có con lân đỏ.
- Chọn hai neo là hai khoảnh khắc có hình học rõ nhất, chẳng hạn E1 treo hai chân trước gần cột cuối cao nhất và E4 lần đầu ngậm thanh trụ.

## 4. Một cảnh đơn

Đầu vào chỉ mô tả một bé gái mặc áo bơi hoa lá trả lời phỏng vấn cạnh hồ bơi.

Xử lý đúng:

- Chọn `search`, một sự kiện, `anchor=false`, `max_gap_s=null`.
- Ưu tiên `áo bơi hoa lá`, `bé gái`, `cạnh hồ bơi` hơn các từ chung như `trả lời`.
- Nếu phần sau cho thấy bé bơi với mũ tím và thứ tự đó quan trọng để tìm đúng video, chuyển thành hai sự kiện và dùng `temporal`.

## 5. Đề có dấu nháy trong nội dung

Đầu vào (hai thẻ là ranh giới, không thuộc đề):

```text
<de_bai>
Đoạn clip có người cầm biển ghi "HOA" cạnh bó hoa vàng.
</de_bai>
```

Đầu ra hợp lệ:

```json
{
  "original_query": "Đoạn clip có người cầm biển ghi \"HOA\" cạnh bó hoa vàng.",
  "context": {"vi": "Người cầm biển cạnh bó hoa", "en": "A person with a sign beside a bouquet"},
  "events": [
    {"vi": "Một người cầm biển ghi HOA cạnh bó hoa vàng", "en": "A person holds a sign reading HOA beside a yellow flower bouquet", "anchor": false, "visual_keywords": ["người cầm biển", "chữ HOA", "bó hoa vàng"], "ocr": "HOA", "asr": ""}
  ],
  "search_clauses": ["Một người cầm biển ghi HOA cạnh bó hoa vàng"],
  "search_clauses_en": ["A person holds a sign reading HOA beside a yellow flower bouquet"],
  "distinctive_features": ["biển ghi HOA", "bó hoa vàng"],
  "possible_confusions": [],
  "ocr_queries": ["HOA"],
  "asr_queries": [],
  "recommended_mode": "search",
  "max_gap_s": null
}
```

Nếu người dùng bọc toàn đề trong một cặp dấu nháy, chỉ bỏ hai dấu bao ngoài; vẫn giữ dấu nháy quanh `HOA` trong `original_query` và escape đúng JSON.
