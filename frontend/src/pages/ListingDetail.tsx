import { type ReactNode, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type ListingDetail as ListingDetailData, type RunOut } from "../api";
import { Freshness } from "../components/Freshness";
import { Gallery } from "../components/Gallery";
import { PriceChart } from "../components/PriceChart";
import { PriceDelta } from "../components/PriceDelta";
import { StatusPill } from "../components/StatusPill";
import { formatDateTime, formatMileage, formatMoney, formatSiteDateTime } from "../format";
import { useFetch } from "../useFetch";

type Refresh = { kind: "idle" } | { kind: "running" } | { kind: "ok" | "warn" | "error"; message: string };

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children ?? "—"}</dd>
    </>
  );
}

const yesNo = (value: boolean | null) => (value == null ? "—" : value ? "yes" : "no");

export function ListingDetail() {
  const { autoId } = useParams();
  const { data, error, loading, reload } = useFetch<ListingDetailData>(`/api/listings/${autoId}`);
  const [refresh, setRefresh] = useState<Refresh>({ kind: "idle" });

  async function refreshListing() {
    setRefresh({ kind: "running" });
    try {
      const run = await api<RunOut>(`/api/listings/${autoId}/refresh`, { method: "POST" });
      reload();
      setRefresh(
        run.status === "completed"
          ? { kind: "ok", message: "Fetched from AUTO.RIA just now." }
          : { kind: "warn", message: `Run ${run.status}${run.errors ? `: ${run.errors}` : ""}` },
      );
    } catch (e) {
      const busy = e instanceof ApiError && e.status === 409;
      setRefresh({ kind: "error", message: busy ? "Another update is running. Try again in a moment." : (e as Error).message });
    }
  }

  if (loading && !data) return <p className="muted">Loading…</p>;
  if (error?.message === "unknown listing") {
    return (
      <p>
        No listing with id {autoId}. <Link to="/">Back to listings</Link>
      </p>
    );
  }
  if (!data) return <p className="error">Could not load the listing: {error?.message}</p>;

  const latest = [...data.snapshots].reverse().find((s) => s.fetch_ok);
  const observations = [...data.snapshots].reverse();

  return (
    <>
      <Link to="/" className="back">
        ← Listings
      </Link>
      <div className="detail-head">
        <div>
          <h1 className="page-title">
            {data.brand} {data.model} {data.year} <StatusPill status={data.status} />
          </h1>
          <div className="muted">
            {[data.modification, data.city].filter(Boolean).join(" · ") || "—"}
          </div>
        </div>
        <div className="actions">
          {data.link && (
            <a className="btn" href={data.link} target="_blank" rel="noreferrer">
              View on AUTO.RIA ↗
            </a>
          )}
          <button className="btn" onClick={refreshListing} disabled={refresh.kind === "running"}>
            {refresh.kind === "running" ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>
      {(refresh.kind === "ok" || refresh.kind === "warn" || refresh.kind === "error") && (
        <p className={`notice notice-${refresh.kind}`}>{refresh.message}</p>
      )}

      <div className="detail-grid">
        <div className="detail-main">
          {data.photos.length > 0 && <Gallery photos={data.photos} />}
          <div className="box">
            <div className="box-header">Price history</div>
            <div className="price-summary">
              <div>
                <div className="price-now">{formatMoney(data.price, data.currency)}</div>
                {data.currency && data.currency !== "USD" && (
                  <div className="muted small">≈ {formatMoney(data.price_usd, "USD")}</div>
                )}
              </div>
              <PriceDelta price={data.price} firstPrice={data.first_price} currency={data.currency} changes={data.price_changes} />
              <span className="muted small">
                {data.price_changes === 0
                  ? "No price change since first seen"
                  : `${data.price_changes} ${data.price_changes === 1 ? "change" : "changes"} since first seen at ${formatMoney(data.first_price, data.currency)}`}
              </span>
            </div>
            <PriceChart snapshots={data.snapshots} currency={data.currency} />
          </div>

          {data.description && (
            <div className="box">
              <div className="box-header">Description</div>
              <p className="description">{data.description}</p>
            </div>
          )}

          <div className="box">
            <div className="box-header">Observations ({observations.length})</div>
            <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Observed</th>
                  <th>Run</th>
                  <th className="num">Price</th>
                  <th className="num">Mileage</th>
                  <th>In search</th>
                  <th>Fetch</th>
                  <th>Status id</th>
                </tr>
              </thead>
              <tbody>
                {observations.map((s) => (
                  <tr key={s.run_id}>
                    <td>{formatDateTime(s.observed_at)}</td>
                    <td>#{s.run_id}</td>
                    <td className="num">{formatMoney(s.listed_price, s.listed_currency)}</td>
                    <td className="num">{formatMileage(s.mileage_k_km)}</td>
                    <td>{s.in_search ? "yes" : "no"}</td>
                    <td>{s.fetch_ok ? "ok" : <span className="error">failed{s.http_status ? ` (HTTP ${s.http_status})` : ""}</span>}</td>
                    <td>{s.status_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        </div>

        <aside className="detail-side">
          <div className="box">
            <div className="box-header">Details</div>
            <dl className="facts facts-compact">
              <Fact label="Last synced">
                <Freshness lastObservedAt={data.last_observed_at} />
              </Fact>
              <Fact label="Mileage">{formatMileage(data.mileage_k_km)}</Fact>
              <Fact label="Generation">{data.generation}</Fact>
              <Fact label="Equipment">{data.equipment}</Fact>
              <Fact label="Body">{data.body_type}</Fact>
              <Fact label="Fuel">{data.fuel_label}</Fact>
              <Fact label="Gearbox">{data.gearbox}</Fact>
              <Fact label="Drive">{data.drive}</Fact>
              <Fact label="Colour">{data.color}</Fact>
              <Fact label="Location">{[data.city, data.region].filter(Boolean).join(", ")}</Fact>
              <Fact label="Seller">
                {data.dealer_name || data.dealer_type || "private"}
                {data.seller_ria_id ? ` (#${data.seller_ria_id})` : ""}
              </Fact>
              <Fact label="VIN">
                <code>{data.vin}</code>
              </Fact>
              <Fact label="Plate">{data.plate}</Fact>
              <Fact label="Posted">{formatSiteDateTime(data.posted_at)}</Fact>
              <Fact label="First seen">{formatDateTime(data.first_seen_at)}</Fact>
              <Fact label="Expires">{formatSiteDateTime(latest?.expire_date ?? null)}</Fact>
              <Fact label="AUTO.RIA id">{data.ria_auto_id}</Fact>
            </dl>
          </div>

          <div className="box">
            <div className="box-header">Status flags</div>
            <dl className="facts facts-compact">
              <Fact label="Derived status">
                <StatusPill status={data.status} />
              </Fact>
              <Fact label="active">{yesNo(latest?.active ?? null)}</Fact>
              <Fact label="is_sold">{yesNo(latest?.is_sold ?? null)}</Fact>
              <Fact label="from_archive">{yesNo(latest?.from_archive ?? null)}</Fact>
              <Fact label="on_moderation">{yesNo(latest?.on_moderation ?? null)}</Fact>
              <Fact label="status_id">{latest?.status_id ?? "—"}</Fact>
              <Fact label="status_id5_type">{latest?.status_id5_type ?? "—"}</Fact>
            </dl>
            <p className="muted small box-note">
              The derived status is provisional: AUTO.RIA's status codes are not decoded yet, so these raw flags
              from the latest successful fetch are shown too.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
