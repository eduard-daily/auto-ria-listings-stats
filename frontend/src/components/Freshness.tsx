import { formatDateTime, relativeTime } from "../format";

// Listings are refetched every REFRESH_DAYS = 2 days (src/ria_stats/config.py).
const FRESH_HOURS = 48;
const STALE_HOURS = 96;

/** When a listing was last synced, with a dot that fades as the data ages. */
export function Freshness({ lastObservedAt }: { lastObservedAt: string | null }) {
  if (!lastObservedAt) {
    return <span className="muted">never</span>;
  }
  const hours = (Date.now() - new Date(lastObservedAt).getTime()) / 3_600_000;
  const level = hours < FRESH_HOURS ? "fresh" : hours < STALE_HOURS ? "stale" : "old";
  return (
    <span className="freshness" title={formatDateTime(lastObservedAt)}>
      <span className={`dot dot-${level}`} />
      {relativeTime(lastObservedAt)}
    </span>
  );
}
