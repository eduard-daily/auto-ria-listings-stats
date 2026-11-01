import type { Stats } from "../api";
import { useFetch } from "../useFetch";
import { useUpdates } from "../updates";

/** The normal update, as the scheduler would run it, with how many listings are waiting. */
export function UpdateButton() {
  const { busy, run } = useUpdates();
  const { data } = useFetch<Stats>("/api/stats");
  const waiting = data?.pending_fetch ?? 0;

  return (
    <div className="update-control">
      {waiting > 0 && !busy && <span className="muted small">{waiting} waiting</span>}
      <button className="btn btn-primary" disabled={busy !== null} onClick={() => run("update")}>
        {busy ? "Updating…" : "Update"}
      </button>
    </div>
  );
}
