import { useEffect, useRef, useState } from "react";
import type { PhotoOut } from "../api";

/** The selected photo large, a strip of thumbnails, and a full-size viewer with keyboard navigation. */
export function Gallery({ photos }: { photos: PhotoOut[] }) {
  const [index, setIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const current = photos[index];
  const label = `${index + 1} / ${photos.length}`;
  const step = (delta: number) => setIndex((i) => (i + delta + photos.length) % photos.length);

  return (
    <div className="box">
      <div className="box-header">Photos ({photos.length})</div>
      <button className="gallery-main" onClick={() => setOpen(true)} aria-label="View full size">
        <img src={current.url} alt={`Photo ${label}`} />
        <span className="gallery-count">{label}</span>
      </button>
      {photos.length > 1 && (
        <div className="gallery-strip">
          {photos.map((photo, i) => (
            <button key={photo.id} className="gallery-thumb" aria-current={i === index} onClick={() => setIndex(i)} aria-label={`Photo ${i + 1}`}>
              <img src={photo.url} alt="" loading="lazy" decoding="async" />
            </button>
          ))}
        </div>
      )}

      <dialog
        ref={dialogRef}
        className="lightbox"
        onClose={() => setOpen(false)}
        onClick={(event) => event.target === event.currentTarget && setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") step(-1);
          if (event.key === "ArrowRight") step(1);
        }}
      >
        <img src={current.url} alt={`Photo ${label}`} />
        <div className="lightbox-bar">
          <button className="btn" onClick={() => step(-1)} aria-label="Previous photo">
            ←
          </button>
          <span>{label}</span>
          <button className="btn" onClick={() => step(1)} aria-label="Next photo">
            →
          </button>
          <button className="btn" onClick={() => setOpen(false)}>
            Close
          </button>
        </div>
      </dialog>
    </div>
  );
}
