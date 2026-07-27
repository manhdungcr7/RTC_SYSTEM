import { useEffect, useState } from "react";

import * as api from "../../services/api";

interface FilmFrame {
  n: number;
  thumb_url: string;
}

interface Props {
  video: string;
  around: number;
  selectedN: number;
  onSelect: (n: number) => void;
}

export function FilmstripPanel({ video, around, selectedN, onSelect }: Props) {
  const [frames, setFrames] = useState<FilmFrame[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch(api.filmstripUrl(video, around, 10))
      .then((r) => r.json())
      .then((data: { frames: FilmFrame[] }) => {
        if (!cancelled) setFrames(data.frames);
      })
      .catch(() => {
        if (!cancelled) setFrames([]);
      });
    return () => {
      cancelled = true;
    };
  }, [video, around]);

  if (frames.length === 0) return null;

  return (
    <div className="filmstrip">
      {frames.map((f) => (
        <img
          key={f.n}
          src={f.thumb_url}
          className={f.n === selectedN ? "filmstrip-frame selected" : "filmstrip-frame"}
          onClick={() => onSelect(f.n)}
          alt={`frame ${f.n}`}
        />
      ))}
    </div>
  );
}
