import type { Status } from "../api";

export function StatusPill({ status }: { status: Status }) {
  return <span className={`pill pill-${status}`}>{status}</span>;
}
