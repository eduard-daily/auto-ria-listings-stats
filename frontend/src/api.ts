// Types mirror src/ria_stats/schemas.py. Timestamps are ISO strings: our own ones are UTC
// (ending in Z), dates that come from AUTO.RIA are site local time without a timezone.

export type Status = "pending" | "active" | "sold" | "removed";

export interface ModelOption {
  brand_id: number;
  brand: string;
  model_id: number;
  model: string;
  listings: number;
}

export interface ListingRow {
  ria_auto_id: number;
  model_id: number;
  brand: string;
  model: string;
  title: string | null;
  year: number | null;
  gearbox: string | null;
  link: string | null;
  city: string | null;
  region: string | null;
  status: Status;
  currency: string | null;
  price: number | null; // in the seller's currency
  price_usd: number | null; // as converted at the last fetch; for sorting across currencies
  first_price: number | null;
  price_changes: number;
  mileage_k_km: number | null;
  posted_at: string | null; // site local time
  first_seen_at: string;
  last_observed_at: string | null;
  cover_photo: string | null; // URL of the downloaded cover photo
}

export interface PhotoOut {
  id: number;
  url: string;
  is_cover: boolean;
  position: number;
}

export interface Snapshot {
  observed_at: string;
  run_id: number;
  in_search: boolean;
  fetch_ok: boolean;
  http_status: number | null;
  listed_currency: string | null;
  listed_price: number | null;
  price_usd: number | null;
  price_eur: number | null;
  price_uah: number | null;
  mileage_k_km: number | null;
  update_date: string | null;
  expire_date: string | null;
  sold_date: string | null;
  active: boolean | null;
  is_sold: boolean | null;
  from_archive: boolean | null;
  on_moderation: boolean | null;
  status_id: number | null;
  status_id5_type: number | null;
}

export interface ListingDetail extends ListingRow {
  vin: string | null;
  plate: string | null;
  generation: string | null;
  modification: string | null;
  equipment: string | null;
  body_type: string | null;
  fuel_label: string | null;
  drive: string | null;
  color: string | null;
  description: string | null;
  seller_ria_id: number | null;
  dealer_type: string | null;
  dealer_name: string | null;
  last_in_search_at: string | null;
  photos: PhotoOut[]; // downloaded ones, cover first
  snapshots: Snapshot[];
}

export interface RunOut {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  trigger: "manual" | "scheduled";
  requests_used: number;
  errors: string | null;
}

export interface DiscoveryRunOut extends RunOut {
  model: string;
  search_total: number | null;
  ids_returned: number | null;
}

export interface PhotosOut {
  downloaded: number;
  gone: number;
  failed: number;
  remaining: number;
}

export interface UpdateOut {
  discoveries: DiscoveryRunOut[];
  collection: RunOut | null;
  photos: PhotosOut;
}

export interface Stats {
  update_running: boolean;
  pending_fetch: number;
  listings_by_status: Record<Status, number>;
  snapshots: number;
  requests_total: number;
  photos: Record<"pending" | "ok" | "gone" | "failed", number>;
  discovery_runs: DiscoveryRunOut[];
  collection_runs: RunOut[];
}

export interface Settings {
  refresh_days: number;
  run_hours: number[];
  scheduler_enabled: boolean;
  max_requests: number;
  max_photos_per_listing: number;
}

export interface SettingsOut {
  values: Settings;
  defaults: Settings;
  limits: Record<string, [number, number]>; // setting -> [smallest, largest]
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // the body was not JSON; keep the status text
    }
    throw new ApiError(response.status, detail);
  }
  return response.json();
}
