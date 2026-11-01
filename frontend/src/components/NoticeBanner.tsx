import { useUpdates } from "../updates";

export function NoticeBanner() {
  const { notice, dismiss } = useUpdates();
  if (!notice) return null;
  return (
    <div className={`notice notice-${notice.kind} notice-row`} role="status">
      <span>{notice.text}</span>
      <button className="notice-close" onClick={dismiss} aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}
