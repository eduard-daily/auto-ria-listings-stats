import { useState } from "react";
import type { DiscoveryRunOut, RunOut, Stats as StatsData } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatDateTime } from "../format";
import { useUpdates } from "../updates";
import { useFetch } from "../useFetch";

const REQUESTS_PER_RUN = 28; // MAX_REQUESTS in src/ria_stats/config.py

interface RunRow {
  key: string;
  kind: "Discovery" | "Details";
  run: RunOut;
  result: string;
}

function duration(run: RunOut): string {
  if (!run.finished_at) return "—";
  return `${Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)} s`;
}

function runRows(discoveries: DiscoveryRunOut[], collections: RunOut[]): RunRow[] {
  const rows: RunRow[] = [
    ...discoveries.map((run) => ({
      key: `d${run.id}`,
      kind: "Discovery" as const,
      run,
      result: run.ids_returned == null ? "—" : `${run.ids_returned} listings found`,
    })),
    ...collections.map((run) => ({ key: `c${run.id}`, kind: "Details" as const, run, result: "" })),
  ];
  return rows.sort((a, b) => b.run.started_at.localeCompare(a.run.started_at));
}

export function Stats() {
  const { data, error, loading } = useFetch<StatsData>("/api/stats");
  const { busy, run } = useUpdates();
  const [confirming, setConfirming] = useState(false);

  if (loading && !data) return <p className="muted">Loading…</p>;
  if (!data) return <p className="error">Could not load stats: {error?.message}</p>;

  const { listings_by_status: by } = data;
  const inSearch = by.active + by.pending;
  const forceRequests = inSearch + 1;
  const rows = runRows(data.discovery_runs, data.collection_runs);
  const truncated = data.discovery_runs.length === 50 || data.collection_runs.length === 50;

  return (
    <>
      <h1 className="page-title">Stats</h1>
      <div className="stack">
        <div className="box">
          <div className="box-header">Updates</div>
          <div className="action-row">
            <div>
              <strong>Update</strong>
              <p className="muted small">
                What a scheduled run does: a discovery if one is due, then fetches details for listings not yet fetched in
                this cycle, and downloads photos. {data.update_running ? "An update is running right now." : `${data.pending_fetch} listings are waiting.`}
              </p>
            </div>
            <button className="btn btn-primary" disabled={busy !== null || data.update_running} onClick={() => run("update")}>
              {busy === "update" ? "Updating…" : "Update"}
            </button>
          </div>
          <div className="action-row">
            <div>
              <strong>Force re-discovery</strong>
              <p className="muted small">
                Searches AUTO.RIA now, even if a discovery ran recently, and starts a new cycle in which every listing is
                fetched again.
              </p>
            </div>
            <button className="btn" disabled={busy !== null || data.update_running} onClick={() => setConfirming(true)}>
              {busy === "force" ? "Running…" : "Force re-discovery"}
            </button>
          </div>
        </div>

        <div className="box">
          <div className="box-header">Overview</div>
          <dl className="facts">
            <dt>Active listings</dt>
            <dd>{by.active}</dd>
            <dt>Sold</dt>
            <dd>{by.sold}</dd>
            <dt>Removed</dt>
            <dd>{by.removed}</dd>
            <dt>Waiting for a fetch</dt>
            <dd>{data.pending_fetch}</dd>
            <dt>Snapshots</dt>
            <dd>{data.snapshots}</dd>
            <dt>Photos downloaded</dt>
            <dd>{data.photos.ok}</dd>
            <dt>Photos waiting</dt>
            <dd>{data.photos.pending + data.photos.failed}</dd>
            <dt>API requests used</dt>
            <dd>{data.requests_total}</dd>
          </dl>
        </div>

        <div className="box">
          <div className="box-header">Runs{truncated ? " (latest 50 of each kind)" : ""}</div>
          <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Kind</th>
                <th>Trigger</th>
                <th>Status</th>
                <th className="num">Requests</th>
                <th className="num">Took</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ key, kind, run: r, result }) => (
                <tr key={key}>
                  <td>{formatDateTime(r.started_at)}</td>
                  <td>{kind}</td>
                  <td>{r.trigger}</td>
                  <td>
                    <span className={`pill pill-run-${r.status}`}>{r.status.replace(/_/g, " ")}</span>
                  </td>
                  <td className="num">{r.requests_used}</td>
                  <td className="num">{duration(r)}</td>
                  <td className="small" title={r.errors ?? undefined}>
                    {r.errors ? <span className="error">{r.errors.split("\n")[0]}</span> : result}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirming}
        title="Force re-discovery?"
        confirmLabel="Run re-discovery"
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          run("force");
        }}
      >
        <p>
          This searches AUTO.RIA now and starts a new refresh cycle. All {inSearch} listings in search become pending
          again and will be fetched: about {forceRequests} requests in total, which takes {Math.ceil(forceRequests / REQUESTS_PER_RUN)}{" "}
          runs of {REQUESTS_PER_RUN} requests. This run does the first {REQUESTS_PER_RUN}.
        </p>
      </ConfirmDialog>
    </>
  );
}
