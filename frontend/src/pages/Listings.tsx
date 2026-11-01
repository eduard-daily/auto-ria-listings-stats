import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ListingRow, ModelOption, Status } from "../api";
import { Freshness } from "../components/Freshness";
import { PriceDelta } from "../components/PriceDelta";
import { StatusPill } from "../components/StatusPill";
import { formatDate, formatMileage, formatMoney } from "../format";
import { useFetch } from "../useFetch";

const TOGGLES: { status: Status; label: string }[] = [
  { status: "active", label: "Active" },
  { status: "sold", label: "Sold" },
  { status: "removed", label: "Removed" },
];

type SortKey = "posted_at" | "price_usd" | "mileage_k_km" | "year" | "last_observed_at";
const SORT_KEYS: SortKey[] = ["posted_at", "price_usd", "mileage_k_km", "year", "last_observed_at"];

// URL parameters of the filters; "Clear" removes them all and leaves the status toggles and sort alone.
const NUMERIC_PARAMS = ["price_min", "price_max", "year_min", "year_max"] as const;
type Draft = Record<(typeof NUMERIC_PARAMS)[number], string>;
const FILTER_PARAMS = ["model", "gearbox", ...NUMERIC_PARAMS];
const EMPTY_DRAFT: Draft = { price_min: "", price_max: "", year_min: "", year_max: "" };

function toNumber(value: string | null): number | null {
  if (value == null || value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function inRange(value: number | null, min: number | null, max: number | null): boolean {
  if (min == null && max == null) return true;
  if (value == null) return false; // a listing without the value cannot satisfy a range
  return (min == null || value >= min) && (max == null || value <= max);
}

function compare(a: ListingRow, b: ListingRow, key: SortKey, direction: 1 | -1): number {
  const x = a[key];
  const y = b[key];
  if (x == null && y == null) return 0;
  if (x == null) return 1; // missing values go last in either direction
  if (y == null) return -1;
  return (x < y ? -1 : x > y ? 1 : 0) * direction;
}

function SortHeader(props: {
  label: string;
  column: SortKey;
  sort: SortKey;
  direction: 1 | -1;
  onSort: (column: SortKey) => void;
  numeric?: boolean;
}) {
  const active = props.sort === props.column;
  return (
    <th className={props.numeric ? "num" : undefined} aria-sort={active ? (props.direction === 1 ? "ascending" : "descending") : "none"}>
      <button className="sort" onClick={() => props.onSort(props.column)}>
        {props.label}
        <span className="sort-arrow">{active ? (props.direction === 1 ? "↑" : "↓") : ""}</span>
      </button>
    </th>
  );
}

function RangeFilter(props: {
  label: string;
  minValue: string;
  maxValue: string;
  onMin: (value: string) => void;
  onMax: (value: string) => void;
}) {
  return (
    <div className="filter">
      <span className="filter-label">{props.label}</span>
      <div className="range">
        <input className="input" inputMode="numeric" placeholder="from" aria-label={`${props.label} from`} value={props.minValue} onChange={(e) => props.onMin(e.target.value)} />
        <span className="muted">–</span>
        <input className="input" inputMode="numeric" placeholder="to" aria-label={`${props.label} to`} value={props.maxValue} onChange={(e) => props.onMax(e.target.value)} />
      </div>
    </div>
  );
}

export function Listings() {
  const [params, setParams] = useSearchParams();
  const latestParams = useRef(params);
  latestParams.current = params;
  // What is typed in the range boxes. It drives the filtering at once and reaches the URL a moment
  // later: writing every keystroke to the URL drops characters while typing.
  const [draft, setDraft] = useState<Draft>(() => ({
    price_min: params.get("price_min") ?? "",
    price_max: params.get("price_max") ?? "",
    year_min: params.get("year_min") ?? "",
    year_max: params.get("year_max") ?? "",
  }));
  const models = useFetch<ModelOption[]>("/api/models");
  const listings = useFetch<ListingRow[]>("/api/listings");

  const modelId = params.get("model");
  const gearbox = params.get("gearbox");
  const priceMin = toNumber(draft.price_min);
  const priceMax = toNumber(draft.price_max);
  const yearMin = toNumber(draft.year_min);
  const yearMax = toNumber(draft.year_max);
  const shown = new Set((params.get("status") ?? "active").split(",") as Status[]);
  const sortParam = params.get("sort") as SortKey;
  const sort: SortKey = SORT_KEYS.includes(sortParam) ? sortParam : "posted_at";
  const direction: 1 | -1 = params.get("dir") === "asc" ? 1 : params.get("dir") === "desc" ? -1 : sort === "posted_at" ? -1 : 1;
  const filtered = FILTER_PARAMS.some((name) => params.has(name)) || NUMERIC_PARAMS.some((name) => draft[name] !== "");

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(latestParams.current);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  useEffect(() => {
    if (NUMERIC_PARAMS.every((name) => draft[name] === (latestParams.current.get(name) ?? ""))) return;
    const timer = setTimeout(() => update(draft), 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- update only reads a ref
  }, [draft]);

  function toggle(status: Status) {
    const next = new Set(shown);
    if (next.has(status)) next.delete(status);
    else next.add(status);
    update({ status: [...next].join(",") || "none" });
  }

  function onSort(column: SortKey) {
    update({ sort: column, dir: column === sort && direction === 1 ? "desc" : column === sort ? "asc" : null });
  }

  function clearFilters() {
    const next = new URLSearchParams(latestParams.current);
    FILTER_PARAMS.forEach((name) => next.delete(name));
    setParams(next, { replace: true });
    setDraft(EMPTY_DRAFT);
  }

  if (listings.loading && !listings.data) return <p className="muted">Loading…</p>;
  if (listings.error || !listings.data) {
    return (
      <p className="error">
        Could not load listings: {listings.error?.message} <button onClick={listings.reload}>Retry</button>
      </p>
    );
  }

  const gearboxes = [...new Set(listings.data.map((row) => row.gearbox).filter((value): value is string => !!value))].sort();
  // Everything except the status toggles, so the toggles' counts follow the other filters.
  const matching = listings.data.filter(
    (row) =>
      (!modelId || String(row.model_id) === modelId) &&
      (!gearbox || row.gearbox === gearbox) &&
      inRange(row.price_usd, priceMin, priceMax) &&
      inRange(row.year, yearMin, yearMax),
  );
  const count = (status: Status) => matching.filter((row) => row.status === status || (status === "active" && row.status === "pending")).length;
  const rows = matching
    .filter((row) => shown.has(row.status) || (row.status === "pending" && shown.has("active")))
    .sort((a, b) => compare(a, b, sort, direction));

  return (
    <>
      <h1 className="page-title">Listings</h1>
      <div className="box">
        <div className="box-header filter-bar">
          <div className="toggles">
            {TOGGLES.map(({ status, label }) => (
              <button key={status} className="toggle" aria-pressed={shown.has(status)} onClick={() => toggle(status)}>
                {label} <span className="count">{count(status)}</span>
              </button>
            ))}
          </div>
          <span className="muted small">{rows.length} shown</span>
        </div>

        <div className="filters">
          <div className="filter">
            <span className="filter-label">Model</span>
            <select value={modelId ?? ""} onChange={(e) => update({ model: e.target.value })} aria-label="Model">
              <option value="">All models</option>
              {models.data?.map((option) => (
                <option key={option.model_id} value={option.model_id}>
                  {option.brand} {option.model}
                </option>
              ))}
            </select>
          </div>
          <div className="filter">
            <span className="filter-label">Gearbox</span>
            <select value={gearbox ?? ""} onChange={(e) => update({ gearbox: e.target.value })} aria-label="Gearbox">
              <option value="">Any</option>
              {gearboxes.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <RangeFilter label="Price, USD" minValue={draft.price_min} maxValue={draft.price_max} onMin={(v) => setDraft({ ...draft, price_min: v })} onMax={(v) => setDraft({ ...draft, price_max: v })} />
          <RangeFilter label="Year" minValue={draft.year_min} maxValue={draft.year_max} onMin={(v) => setDraft({ ...draft, year_min: v })} onMax={(v) => setDraft({ ...draft, year_max: v })} />
          {filtered && (
            <button className="link-button" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>

        {rows.length === 0 ? (
          <p className="empty muted">No listings match these filters.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Listing</th>
                <SortHeader label="Price" column="price_usd" sort={sort} direction={direction} onSort={onSort} numeric />
                <th className="num">Change</th>
                <SortHeader label="Mileage" column="mileage_k_km" sort={sort} direction={direction} onSort={onSort} numeric />
                <th>Status</th>
                <SortHeader label="Posted" column="posted_at" sort={sort} direction={direction} onSort={onSort} />
                <SortHeader label="Last synced" column="last_observed_at" sort={sort} direction={direction} onSort={onSort} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.ria_auto_id}>
                  <td>
                    <Link to={`/listings/${row.ria_auto_id}`} className="listing-title">
                      {row.brand} {row.model} {row.year}
                    </Link>
                    <div className="muted small">{[row.gearbox, row.city].filter(Boolean).join(" · ") || "—"}</div>
                  </td>
                  <td className="num">
                    {formatMoney(row.price, row.currency)}
                    {row.currency && row.currency !== "USD" && <div className="muted small">≈ {formatMoney(row.price_usd, "USD")}</div>}
                  </td>
                  <td className="num">
                    <PriceDelta price={row.price} firstPrice={row.first_price} currency={row.currency} changes={row.price_changes} />
                  </td>
                  <td className="num">{formatMileage(row.mileage_k_km)}</td>
                  <td>
                    <StatusPill status={row.status} />
                  </td>
                  <td>{formatDate(row.posted_at)}</td>
                  <td>
                    <Freshness lastObservedAt={row.last_observed_at} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
