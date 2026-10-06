import { createContext, useContext, useEffect, useState } from "react";
import { api, auth, ApiError } from "../api/client";
import type { Identity, Enums } from "../api/types";

interface AppState {
  identity: Identity | null;
  enums: Enums | null;
  busy: boolean;
  can: (perm: string) => boolean;
  logout: () => void;
  reloadIdentity: () => void;
}

const Ctx = createContext<AppState>(null as unknown as AppState);
export const useApp = () => useContext(Ctx);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [enums, setEnums] = useState<Enums | null>(null);
  const [busy, setBusy] = useState<boolean>(!!auth.apiKey);

  const load = async () => {
    if (!auth.apiKey) { setIdentity(null); return; }
    setBusy(true);
    try {
      const me = await api.me();
      setIdentity(me);
      try { setEnums(await api.enums()); } catch { /* non-critical */ }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) auth.clear();
      setIdentity(null);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const value: AppState = {
    identity,
    enums,
    busy,
    can: (perm: string) => !!identity?.permissions.includes(perm),
    logout: () => { auth.clear(); setIdentity(null); },
    reloadIdentity: load,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
