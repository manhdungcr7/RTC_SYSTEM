# Knowledge — ví dụ cho AIC Visual Query Expert V2

Các JSON dưới đây là ví dụ biên soạn, không phải kết quả đo từ GPT hoặc kết quả xác nhận trên video. Không chứa video đáp án. Chỉ học cách chọn dấu hiệu, dịch và đặt từ khóa; không đưa chi tiết từ ví dụ vào đề khác. Quy tắc trong Instructions có ưu tiên cao hơn ví dụ.

## 1. Miếng thực phẩm màu cam, hỗn hợp gia vị, hỏi lượng nước tương

Chọn thao tác tách hạt khỏi cành và phủ hai mặt làm neo. Cảnh nêm có từ khóa nước tương nhưng không thêm định lượng, không khẳng định có phụ đề. Không tự gọi thực phẩm là cá hồi hoặc hạt là tiêu.

```json
{
  "original_query": "Một đầu bếp đang chuẩn bị một món ăn từ một miếng thực phẩm màu cam. Người này băm nhỏ một số nguyên liệu, tách các hạt nhỏ khỏi cành rồi trộn chúng thành hỗn hợp gia vị. Sau đó, nhiều loại gia vị được lần lượt thêm vào và hỗn hợp được phủ lên cả hai mặt của nguyên liệu chính trước khi thêm một chất lỏng. Trong quá trình nêm gia vị, lượng nước tương được sử dụng là bao nhiêu?",
  "context": {"vi": "Chế biến thực phẩm màu cam", "en": "Preparing an orange food piece"},
  "events": [
    {
      "vi": "Đầu bếp băm nguyên liệu, tách hạt nhỏ khỏi cành để trộn gia vị.",
      "en": "A chef chops ingredients and removes small seeds from stems for a seasoning mixture.",
      "anchor": true,
      "visual_keywords": ["băm nguyên liệu", "hạt nhỏ trên cành", "trộn gia vị"],
      "ocr": "",
      "asr": ""
    },
    {
      "vi": "Đầu bếp lần lượt thêm các gia vị vào hỗn hợp.",
      "en": "The chef adds seasonings to the mixture one by one.",
      "anchor": false,
      "visual_keywords": ["thêm gia vị", "hỗn hợp gia vị"],
      "ocr": "nước tương",
      "asr": "nước tương"
    },
    {
      "vi": "Đầu bếp phủ gia vị lên cả hai mặt miếng thực phẩm màu cam.",
      "en": "The chef coats both sides of an orange food piece with seasonings.",
      "anchor": true,
      "visual_keywords": ["thực phẩm màu cam", "phủ gia vị", "hai mặt"],
      "ocr": "",
      "asr": ""
    }
  ],
  "search_clauses": [
    "Đầu bếp băm nguyên liệu, tách hạt nhỏ khỏi cành để trộn gia vị.",
    "Đầu bếp lần lượt thêm các gia vị vào hỗn hợp.",
    "Đầu bếp phủ gia vị lên cả hai mặt miếng thực phẩm màu cam."
  ],
  "search_clauses_en": [
    "A chef chops ingredients and removes small seeds from stems for a seasoning mixture.",
    "The chef adds seasonings to the mixture one by one.",
    "The chef coats both sides of an orange food piece with seasonings."
  ],
  "distinctive_features": [
    "Miếng thực phẩm chính màu cam",
    "Băm nguyên liệu và tách hạt nhỏ khỏi cành",
    "Gia vị được thêm lần lượt",
    "Phủ hỗn hợp lên cả hai mặt",
    "Thêm chất lỏng sau khi phủ gia vị",
    "Cần xác minh lượng nước tương tại bước nêm"
  ],
  "possible_confusions": [
    "Chưa biết tên thực phẩm màu cam hoặc loại hạt",
    "Từ khóa nước tương dùng để tìm, không chứng minh có chữ trên màn hình",
    "Chất lỏng ở bước cuối chưa chắc là nước tương; không đoán định lượng"
  ],
  "ocr_queries": ["nước tương"],
  "asr_queries": ["nước tương"],
  "recommended_mode": "temporal",
  "max_gap_s": 120
}
```

## 2. Nồi thủy tinh, đũa, thức ăn đỏ xanh và 1,5 lít chất lỏng

Đề không yêu cầu riêng frame của từng lần thêm gia vị. Hai cảnh nhận diện mạnh làm chuỗi tìm kiếm; giữ các lượng gia vị khác trong ghi chú để kiểm tra sau. OCR định lượng ở đúng event đổ chất lỏng; không biến mọi số đo thành một truy vấn ghép.

```json
{
  "original_query": "Một người đang đổ 1 nguyên liệu vào trong 1 nồi thủy tinh, sau đó, sử dụng 1 đôi đũa để đảo nguyên liệu màu đỏ có chút màu xanh lá cây. Sau khi, nguyên liệu đã biến đổi màu, người đàn ông đổ thêm 1.5L nguyên liệu dạng lỏng, 1/2 muỗng (cà phê) nguyên liệu trắng có vị mặn, 1/2 muỗng nguyên liệu trắng có vị ngọt, 2 muỗng hạt nguyên liệu có vị từ xương hầm",
  "context": {"vi": "Nấu ăn trong nồi thủy tinh", "en": "Cooking in a glass pot"},
  "events": [
    {
      "vi": "Người đàn ông dùng đũa đảo nguyên liệu đỏ xen xanh lá trong nồi thủy tinh.",
      "en": "A man stirs red and green ingredients with chopsticks in a glass pot.",
      "anchor": true,
      "visual_keywords": ["nồi thủy tinh", "đũa", "nguyên liệu đỏ xanh", "đảo nguyên liệu"],
      "ocr": "",
      "asr": ""
    },
    {
      "vi": "Sau khi nguyên liệu đổi màu, người đàn ông đổ 1,5 lít chất lỏng vào nồi thủy tinh.",
      "en": "After the ingredients change color, the man pours 1.5 liters of liquid into the glass pot.",
      "anchor": true,
      "visual_keywords": ["đổ chất lỏng", "nồi thủy tinh", "nguyên liệu đổi màu"],
      "ocr": "1,5 lít",
      "asr": ""
    }
  ],
  "search_clauses": [
    "Người đàn ông dùng đũa đảo nguyên liệu đỏ xen xanh lá trong nồi thủy tinh.",
    "Sau khi nguyên liệu đổi màu, người đàn ông đổ 1,5 lít chất lỏng vào nồi thủy tinh."
  ],
  "search_clauses_en": [
    "A man stirs red and green ingredients with chopsticks in a glass pot.",
    "After the ingredients change color, the man pours 1.5 liters of liquid into the glass pot."
  ],
  "distinctive_features": [
    "Ban đầu đổ nguyên liệu vào nồi thủy tinh",
    "Dùng đũa đảo nguyên liệu đỏ xen xanh lá",
    "Nguyên liệu đổi màu trước khi thêm 1,5 lít chất lỏng",
    "Sau đó thêm 1/2 muỗng cà phê nguyên liệu trắng vị mặn",
    "Thêm 1/2 muỗng nguyên liệu trắng vị ngọt",
    "Thêm 2 muỗng hạt nguyên liệu vị xương hầm"
  ],
  "possible_confusions": [
    "Không đoán tên chất lỏng hoặc nguyên liệu đỏ xanh",
    "1,5 lít là từ khóa thử OCR từ dữ kiện đề, chưa xác nhận cách viết trên màn hình",
    "Nếu chữ trong video dùng 1.5L, thử biến thể đó riêng, không ghép hai cách viết vào một truy vấn"
  ],
  "ocr_queries": ["1,5 lít"],
  "asr_queries": [],
  "recommended_mode": "temporal",
  "max_gap_s": 120
}
```

## 3. Hai mẹ con và phỏng vấn — không suy ra người con là trẻ nhỏ

Giữ quan hệ gia đình, nhưng bản dịch không gán tuổi/giới. Người đi ngang hậu cảnh nằm trong chính câu tìm kiếm, không chỉ trong danh sách đặc điểm.

```json
{
  "original_query": "Đoạn phim bắt đầu với cảnh hai mẹ con cầm điện thoại trò chuyện, sau đó chuyển sang cảnh người con trả lời phỏng vấn, phía sau có một phụ nữ da đen đang bước qua.",
  "context": {"vi": "Hai mẹ con trong đoạn phim", "en": "A mother and her offspring"},
  "events": [
    {
      "vi": "Hai mẹ con cầm điện thoại và trò chuyện với nhau.",
      "en": "A mother and her offspring talk while holding a phone.",
      "anchor": true,
      "visual_keywords": ["hai người", "điện thoại", "trò chuyện"],
      "ocr": "",
      "asr": ""
    },
    {
      "vi": "Người con trả lời phỏng vấn, một phụ nữ da đen đi ngang phía sau.",
      "en": "The person being interviewed speaks while a Black woman walks past behind them.",
      "anchor": true,
      "visual_keywords": ["phỏng vấn", "phụ nữ da đen", "đi ngang hậu cảnh"],
      "ocr": "",
      "asr": ""
    }
  ],
  "search_clauses": [
    "Hai mẹ con cầm điện thoại và trò chuyện với nhau.",
    "Người con trả lời phỏng vấn, một phụ nữ da đen đi ngang phía sau."
  ],
  "search_clauses_en": [
    "A mother and her offspring talk while holding a phone.",
    "The person being interviewed speaks while a Black woman walks past behind them."
  ],
  "distinctive_features": [
    "Mở đầu hai mẹ con cầm điện thoại trò chuyện",
    "Chuyển sang phỏng vấn người con",
    "Một phụ nữ da đen đi ngang hậu cảnh của cảnh phỏng vấn"
  ],
  "possible_confusions": [
    "Người con chưa được mô tả tuổi hoặc giới, không mặc định là trẻ nhỏ",
    "Không rõ một hay cả hai người cầm điện thoại",
    "Không suy ra quan hệ giữa người đi ngang và người được phỏng vấn"
  ],
  "ocr_queries": [],
  "asr_queries": [],
  "recommended_mode": "temporal",
  "max_gap_s": 120
}
```

## 4. Một cảnh có nhiều chi tiết — không dựng chuỗi giả

Các chi tiết dưới đây cùng xuất hiện. Chỉ một event và mode search. Không tự gọi đồ vật đỏ là máy làm bánh hoặc vật liệu trắng là đĩa.

```json
{
  "original_query": "Trong một cảnh, một phụ nữ lấy thành phẩm trắng nở phồng có dạng các sợi que dính nhau từ đồ vật màu đỏ; cạnh đó có các thành phẩm đặt trên vật liệu màu trắng.",
  "context": {"vi": "Phụ nữ lấy thành phẩm trắng", "en": "A woman removing a white product"},
  "events": [
    {
      "vi": "Phụ nữ lấy thành phẩm trắng nở phồng, dạng sợi que dính nhau, từ đồ vật đỏ.",
      "en": "A woman removes a puffed white product shaped like connected stick-like strands from a red object.",
      "anchor": false,
      "visual_keywords": ["phụ nữ", "đồ vật đỏ", "thành phẩm trắng", "sợi que dính nhau"],
      "ocr": "",
      "asr": ""
    }
  ],
  "search_clauses": ["Phụ nữ lấy thành phẩm trắng nở phồng, dạng sợi que dính nhau, từ đồ vật đỏ."],
  "search_clauses_en": ["A woman removes a puffed white product shaped like connected stick-like strands from a red object."],
  "distinctive_features": [
    "Thành phẩm trắng và nở phồng",
    "Hình dạng các sợi que dính nhau",
    "Lấy ra từ đồ vật màu đỏ",
    "Các thành phẩm bên cạnh đặt trên vật liệu trắng"
  ],
  "possible_confusions": [
    "Chưa biết tên thành phẩm hay công dụng đồ vật đỏ",
    "Vật liệu trắng chưa chắc là đĩa",
    "Thành phẩm trắng không chứng minh có quá trình đổi màu"
  ],
  "ocr_queries": [],
  "asr_queries": [],
  "recommended_mode": "search",
  "max_gap_s": null
}
```

## 5. E1–E4 được yêu cầu rõ — giữ đủ bốn mốc

Giữ tư thế và điều kiện thời điểm. Quy tắc thường chọn 2–3 cảnh không áp dụng cho đề yêu cầu từng mốc riêng. Một chuỗi truy vấn không tự xác nhận đúng khoảnh khắc đầu tiên/hoàn tất; người dùng còn phải xem lại ứng viên.

```json
{
  "original_query": "Con lân màu đỏ đang biểu diễn trên các cột trụ. E1: Con lân treo hai chân trước vào phần dưới thân của hai trụ gần cuối (gần trụ cuối cùng cao nhất). E2: Con lân đứng thẳng sau khi di chuyển từ cuối dãy trụ về, hai chân đứng trên hai trụ khác nhau và một chân trước co lên. E3: Khoảnh khắc con lân hoàn tất động tác ngoảnh mặt theo hướng ngược lại. E4: Khoảnh khắc đầu tiên con lân ngậm một thanh trụ.",
  "context": {"vi": "Lân đỏ biểu diễn trên cột", "en": "Red lion dance on poles"},
  "events": [
    {
      "vi": "Lân đỏ treo hai chân trước vào thân dưới hai trụ gần cuối, cạnh trụ cuối cao nhất.",
      "en": "The red lion hooks its two front legs onto the lower shafts of two poles near the tallest final pole.",
      "anchor": true,
      "visual_keywords": ["lân đỏ", "hai chân trước treo", "thân dưới hai trụ", "trụ cuối cao nhất"],
      "ocr": "",
      "asr": ""
    },
    {
      "vi": "Lân đỏ trở về từ cuối dãy, đứng thẳng trên hai trụ khác nhau, một chân trước co lên.",
      "en": "Returning from the end of the row, the red lion stands upright on two different poles with one front leg raised.",
      "anchor": false,
      "visual_keywords": ["lân đỏ", "đứng thẳng", "hai trụ khác nhau", "một chân trước co"],
      "ocr": "",
      "asr": ""
    },
    {
      "vi": "Lân đỏ vừa hoàn tất ngoảnh mặt về hướng ngược lại.",
      "en": "The red lion has just completed turning its face in the opposite direction.",
      "anchor": false,
      "visual_keywords": ["lân đỏ", "ngoảnh mặt", "hướng ngược lại"],
      "ocr": "",
      "asr": ""
    },
    {
      "vi": "Khoảnh khắc đầu tiên lân đỏ ngậm một thanh trụ.",
      "en": "The first moment the red lion grips a pole bar in its mouth.",
      "anchor": true,
      "visual_keywords": ["lân đỏ", "ngậm thanh trụ", "khoảnh khắc đầu tiên"],
      "ocr": "",
      "asr": ""
    }
  ],
  "search_clauses": [
    "Lân đỏ treo hai chân trước vào thân dưới hai trụ gần cuối, cạnh trụ cuối cao nhất.",
    "Lân đỏ trở về từ cuối dãy, đứng thẳng trên hai trụ khác nhau, một chân trước co lên.",
    "Lân đỏ vừa hoàn tất ngoảnh mặt về hướng ngược lại.",
    "Khoảnh khắc đầu tiên lân đỏ ngậm một thanh trụ."
  ],
  "search_clauses_en": [
    "The red lion hooks its two front legs onto the lower shafts of two poles near the tallest final pole.",
    "Returning from the end of the row, the red lion stands upright on two different poles with one front leg raised.",
    "The red lion has just completed turning its face in the opposite direction.",
    "The first moment the red lion grips a pole bar in its mouth."
  ],
  "distinctive_features": [
    "Lân màu đỏ, biểu diễn trên các cột trụ",
    "E1 gần trụ cuối cao nhất, chân trước treo ở thân dưới hai trụ",
    "E2 sau khi di chuyển về từ cuối dãy, đứng trên hai trụ khác nhau",
    "E2 có một chân trước co lên",
    "E3 là thời điểm hoàn tất ngoảnh mặt, không phải đang quay",
    "E4 là thời điểm đầu tiên ngậm thanh trụ"
  ],
  "possible_confusions": ["Cần xem lại chuyển động để xác minh đầu tiên/hoàn tất, không suy ra từ một ảnh mẫu"],
  "ocr_queries": [],
  "asr_queries": [],
  "recommended_mode": "temporal",
  "max_gap_s": 120
}
```

## 6. Đề có dấu nháy trong nội dung

Đầu vào (hai thẻ chỉ dùng để bao đề):

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

Nếu người dùng đặt thêm một cặp dấu nháy quanh toàn đề, chỉ bỏ cặp bao ngoài; giữ dấu nháy quanh `HOA` và escape đúng JSON.

## Những sửa nghĩa cần tránh

- Bột được mô tả rõ là khô: dùng `flour`/`powder`, không mặc định `dough`/`batter`. Nếu đề chỉ nói bột, chưa đủ để khẳng định trạng thái.
- Cắt làm hai nhưng còn nối nhau: giữ `cut into two connected halves`, không rút thành hai miếng tách rời.
- Tách lõi khỏi lớp vỏ: mô tả lấy phần trong và giữ vỏ, không dịch thành bóc bỏ vỏ. Không thêm thìa/dao nếu đề chỉ nói công cụ.
- Người con: giữ quan hệ; chưa biết tuổi/giới thì không dùng young child, boy hoặc girl.
- Hỏi định lượng: chỉ tạo từ khóa đối tượng cần tìm, không đưa giá trị đoán vào OCR/ASR.
- Chi tiết không chắc: ghi chú để đối chiếu/thử riêng; không nhồi tên đoán hoặc các lựa chọn A/B/C vào câu encode chính.
