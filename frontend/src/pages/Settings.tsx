import { useEffect, useState } from "react";
import { api, type Settings as SettingsValues, type SettingsOut } from "../api";
import { useFetch } from "../useFetch";

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const NUMBER_FIELDS = ["refresh_days", "max_requests", "max_photos_per_listing"] as const;
type NumberField = (typeof NUMBER_FIELDS)[number];

interface Draft {
  numbers: Record<NumberField, string>;
  hours: number[];
  enabled: boolean;
}

function toDraft(v: SettingsValues): Draft {
  return {
    numbers: {
      refresh_days: String(v.refresh_days),
      max_requests: String(v.max_requests),
      max_photos_per_listing: String(v.max_photos_per_listing),
    },
    hours: v.run_hours,
    enabled: v.scheduler_enabled,
  };
}

function Row({ title, help, children }: { title: string; help: string; children: React.ReactNode }) {
  return (
    <div className="action-row">
      <div>
        <strong>{title}</strong>
        <p className="muted small">{help}</p>
      </div>
      {children}
    </div>
  );
}

export function Settings() {
  const { data, error, loading } = useFetch<SettingsOut>("/api/settings");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (data) setDraft(toDraft(data.values));
  }, [data]);

  if (loading && !data) return <p className="muted">Loading…</p>;
  if (!data || !draft) return <p className="error">Could not load settings: {error?.message}</p>;

  const { limits, defaults } = data;
  const problems: string[] = [];
  const numbers = {} as Record<NumberField, number>;
  for (const field of NUMBER_FIELDS) {
    const value = Number(draft.numbers[field]);
    const [low, high] = limits[field];
    numbers[field] = value;
    if (draft.numbers[field].trim() === "" || !Number.isInteger(value) || value < low || value > high) {
      problems.push(`${field.replaceAll("_", " ")} must be a whole number from ${low} to ${high}`);
    }
  }
  if (draft.hours.length === 0) problems.push("pick at least one hour");

  const changed = JSON.stringify(toDraft(data.values)) !== JSON.stringify(draft);

  const edit = (patch: Partial<Draft>) => {
    setDraft({ ...draft, ...patch });
    setMessage(null);
  };

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const body: SettingsValues = {
        ...numbers,
        run_hours: draft.hours,
        scheduler_enabled: draft.enabled,
      };
      const saved = await api<SettingsOut>("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setDraft(toDraft(saved.values));
      setMessage({ ok: true, text: "Saved. The scheduler follows now; everything else applies from the next run." });
    } catch (e) {
      setMessage({ ok: false, text: `Could not save: ${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  };

  const numberInput = (field: NumberField) => (
    <input
      className="input"
      type="number"
      inputMode="numeric"
      min={limits[field][0]}
      max={limits[field][1]}
      value={draft.numbers[field]}
      aria-label={field}
      onChange={(e) => edit({ numbers: { ...draft.numbers, [field]: e.target.value } })}
    />
  );

  return (
    <>
      <h1 className="page-title">Settings</h1>
      <div className="stack">
        <div className="box">
          <div className="box-header">Schedule</div>
          <Row
            title="Scheduled sync"
            help="Runs an update by itself at the hours below. Switch it off to pause it; the Update button still works."
          >
            <label className="check">
              <input type="checkbox" checked={draft.enabled} onChange={(e) => edit({ enabled: e.target.checked })} />
              {draft.enabled ? "On" : "Off"}
            </label>
          </Row>
          <Row
            title="Hours"
            help="A run starts at the beginning of each selected hour (Kyiv time). A run fetches at most the request cap, so more hours means a cycle finishes sooner."
          >
            <div className="hour-grid" role="group" aria-label="Hours">
              {HOURS.map((h) => (
                <button
                  key={h}
                  type="button"
                  className={`hour${draft.hours.includes(h) ? " hour-on" : ""}`}
                  aria-pressed={draft.hours.includes(h)}
                  onClick={() => edit({ hours: draft.hours.includes(h) ? draft.hours.filter((x) => x !== h) : [...draft.hours, h].sort((a, b) => a - b) })}
                >
                  {String(h).padStart(2, "0")}
                </button>
              ))}
            </div>
          </Row>
        </div>

        <div className="box">
          <div className="box-header">Collection</div>
          <Row
            title="Refresh interval (days)"
            help={`Every listing is fetched again once this many calendar days have passed since the last search. Default ${defaults.refresh_days}. It changes when the next refresh is due; nothing is refetched now.`}
          >
            {numberInput("refresh_days")}
          </Row>
          <Row
            title="API requests per run"
            help={`A run stops after this many AUTO.RIA requests (search and details together). The free plan allows 30 per hour. Default ${defaults.max_requests}.`}
          >
            {numberInput("max_requests")}
          </Row>
          <Row
            title="Photos per listing"
            help={`Only the cover and the first photos up to this number are saved. It applies when a listing is fetched for the first time; listings already recorded keep what they have, and raising it does not bring back photos left out. Default ${defaults.max_photos_per_listing}.`}
          >
            {numberInput("max_photos_per_listing")}
          </Row>
        </div>

        <div className="settings-actions">
          <button className="btn btn-primary" disabled={saving || !changed || problems.length > 0} onClick={save}>
            {saving ? "Saving…" : "Save"}
          </button>
          {problems.length > 0 && <span className="error small">{problems[0]}</span>}
          {message && <span className={message.ok ? "muted small" : "error small"}>{message.text}</span>}
        </div>
      </div>
    </>
  );
}
