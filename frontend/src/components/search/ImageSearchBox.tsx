import { useRef, useState } from "react";

interface Props {
  onSearch: (file: File) => void;
  loading: boolean;
}

// Tìm theo ảnh (image-to-image, nhánh DINOv3) — người dùng upload 1 ảnh NGOÀI
// (vd screenshot, ảnh mẫu BTC đưa) thay vì gõ mô tả bằng chữ. Khác nút "🔍 Tìm
// ảnh giống" trong FrameDetailModal (đó là tìm giống 1 frame ĐÃ CÓ trong kết quả).
export function ImageSearchBox({ onSearch, loading }: Props) {
  const [preview, setPreview] = useState<string | null>(null);
  const fileRef = useRef<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    fileRef.current = file;
    setPreview(URL.createObjectURL(file));
  };

  const submit = () => {
    if (fileRef.current) onSearch(fileRef.current);
  };

  const clear = () => {
    fileRef.current = null;
    setPreview(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="image-search-box">
      <span className="image-search-title">Tìm theo ảnh (upload ảnh ngoài — DINOv3)</span>
      <div className="image-search-row">
        <input ref={inputRef} type="file" accept="image/*" onChange={onPick} />
        {preview && (
          <>
            <img src={preview} className="image-search-preview" alt="preview" />
            <button type="button" onClick={clear}>✕ Bỏ</button>
          </>
        )}
        <button type="button" onClick={submit} disabled={loading || !preview}>
          {loading ? "Đang tìm..." : "Tìm ảnh giống"}
        </button>
      </div>
    </div>
  );
}
