export function formatMoney(value: number | null, currency: string | null): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency ?? "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatMileage(thousandKm: number | null): string {
  return thousandKm == null ? "—" : `${thousandKm}k km`;
}

/** Dates from AUTO.RIA carry no timezone; only the day is shown, so none is needed. */
export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** AUTO.RIA dates have no timezone: parsed as local time, they display with the same clock. */
export function formatSiteDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export function formatDateTime(isoUtc: string): string {
  return new Date(isoUtc).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

export function relativeTime(isoUtc: string, now = Date.now()): string {
  const seconds = Math.round((new Date(isoUtc).getTime() - now) / 1000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit);
  }
  return "just now";
}
