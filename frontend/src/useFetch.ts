import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { useUpdates } from "./updates";

export function useFetch<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const { version } = useUpdates(); // an update elsewhere in the app reloads every page's data

  const load = useCallback(() => {
    setLoading(true);
    api<T>(path)
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [path, version]);

  useEffect(load, [load]);
  return { data, error, loading, reload: load };
}
