import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, friendlyError } from "../api/client";

export type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

/** Minimal data-fetching hook (no external lib). Re-runs when `deps` change. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): {
  state: AsyncState<T>;
  reload: () => void;
} {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const alive = useRef(true);

  const run = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fnRef.current();
      if (alive.current) setState({ data, loading: false, error: null });
      return data;
    } catch (e) {
      const msg = e instanceof ApiError ? friendlyError(e) : String(e);
      if (alive.current) setState({ data: null, loading: false, error: msg });
      return undefined;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    alive.current = true;
    run();
    return () => { alive.current = false; };
  }, [run]);

  return { state, reload: run };
}

/** Small toast system — one line of feedback for every mutation. */
let pushToast: ((t: { kind: "ok" | "err"; text: string }) => void) | null = null;
export function registerToast(fn: typeof pushToast) { pushToast = fn; }
export function toastOk(text: string) { pushToast?.({ kind: "ok", text }); }
export function toastErr(text: string) { pushToast?.({ kind: "err", text }); }

/** Wrap a mutation: shows toast + rethrows nothing; returns ok flag. */
export async function mutate<T>(fn: () => Promise<T>, okMsg?: string): Promise<T | undefined> {
  try {
    const r = await fn();
    if (okMsg) toastOk(okMsg);
    return r;
  } catch (e) {
    toastErr(e instanceof ApiError ? friendlyError(e) : String(e));
    return undefined;
  }
}
