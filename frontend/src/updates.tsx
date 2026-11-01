import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import { api, ApiError, type UpdateOut } from "./api";

export type UpdateKind = "update" | "force";
export interface Notice {
  kind: "ok" | "warn" | "error";
  text: string;
}

interface Updates {
  /** Bumped after every update; data hooks reload when it changes. */
  version: number;
  busy: UpdateKind | null;
  notice: Notice | null;
  run: (kind: UpdateKind) => Promise<void>;
  dismiss: () => void;
}

const ENDPOINTS: Record<UpdateKind, string> = { update: "/api/update", force: "/api/discovery/force" };

function summarize(result: UpdateOut): Notice {
  const runs = [...result.discoveries, ...(result.collection ? [result.collection] : [])];
  const { downloaded, failed, remaining } = result.photos;
  if (runs.length === 0 && downloaded === 0 && failed === 0 && remaining === 0) {
    return { kind: "ok", text: "Nothing to do: no discovery is due and nothing is waiting for a fetch." };
  }

  const parts: string[] = [];
  for (const d of result.discoveries) parts.push(`discovery found ${d.ids_returned ?? 0} listings`);
  if (result.collection) parts.push(`fetched details with ${result.collection.requests_used} requests`);
  if (downloaded > 0) parts.push(`downloaded ${downloaded} photos`);
  let text = `Update finished: ${parts.join(", ") || "nothing new"}.`;
  if (remaining > 0) text += ` ${remaining} photos are left for the next update.`;
  if (failed > 0) {
    return { kind: "warn", text: `${text} ${failed} photos could not be downloaded and will be retried.` };
  }

  const limited = runs.find((run) => run.status === "rate_limited");
  if (limited) {
    return { kind: "warn", text: `${text} Stopped early by the AUTO.RIA rate limit; try again in an hour.` };
  }
  const withErrors = runs.find((run) => run.errors);
  if (withErrors) return { kind: "warn", text: `${text} Some requests failed: ${withErrors.errors}` };
  return { kind: "ok", text };
}

const UpdatesContext = createContext<Updates | null>(null);

export function UpdatesProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<UpdateKind | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const run = useCallback(async (kind: UpdateKind) => {
    setBusy(kind);
    setNotice(null);
    try {
      setNotice(summarize(await api<UpdateOut>(ENDPOINTS[kind], { method: "POST" })));
    } catch (e) {
      const busyElsewhere = e instanceof ApiError && e.status === 409;
      setNotice({
        kind: "error",
        text: busyElsewhere ? "Another update is running. Try again in a moment." : `Update failed: ${(e as Error).message}`,
      });
    } finally {
      setBusy(null);
      setVersion((v) => v + 1);
    }
  }, []);

  const value = useMemo(() => ({ version, busy, notice, run, dismiss: () => setNotice(null) }), [version, busy, notice, run]);
  return <UpdatesContext.Provider value={value}>{children}</UpdatesContext.Provider>;
}

export function useUpdates(): Updates {
  const value = useContext(UpdatesContext);
  if (!value) throw new Error("useUpdates must be used inside UpdatesProvider");
  return value;
}
