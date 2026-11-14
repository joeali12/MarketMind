"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearPersistedSource,
  isUploadSessionGoneError,
  readPersistedSource,
  writePersistedSource,
  type DataSourceMode,
  type PersistedSource,
} from "@/lib/dataSource";

type Ctx = {
  ready: boolean;
  mode: DataSourceMode;
  sessionId: string | null;
  filename: string | null;
  currencyCode: string | null;
  dateFormat: string | null;
  dateFormatConfirmed: boolean;
  hasCategoryMapped: boolean;
  categoryColumn: string | null;
  setDemo: () => void;
  setUpload: (patch: Partial<PersistedSource> & { sessionId: string }) => void;
  updateUpload: (patch: Partial<PersistedSource>) => void;
  clearUpload: () => void;
};

const DataSourceContext = createContext<Ctx | null>(null);

async function sessionStillAlive(sessionId: string): Promise<boolean> {
  try {
    const res = await fetch(
      `/api/upload/${encodeURIComponent(sessionId)}/overview`,
      { cache: "no-store" }
    );
    if (res.ok) return true;
    if (res.status === 404) return false;
    // Other errors: treat as gone so dashboard can show demo rather than hang
    const text = await res.text();
    return !isUploadSessionGoneError(text);
  } catch (e) {
    return !isUploadSessionGoneError(e);
  }
}

export function DataSourceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PersistedSource>({ mode: "demo" });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const persisted = readPersistedSource();
      if (persisted.mode === "upload" && persisted.sessionId) {
        const alive = await sessionStillAlive(persisted.sessionId);
        if (cancelled) return;
        if (!alive) {
          clearPersistedSource();
          setState({ mode: "demo" });
          setReady(true);
          return;
        }
      }
      if (cancelled) return;
      setState(persisted);
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setDemo = useCallback(() => {
    const next: PersistedSource = { mode: "demo" };
    writePersistedSource(next);
    setState(next);
  }, []);

  const setUpload = useCallback(
    (patch: Partial<PersistedSource> & { sessionId: string }) => {
      const next: PersistedSource = {
        mode: "upload",
        sessionId: patch.sessionId,
        filename: patch.filename ?? state.filename ?? null,
        currencyCode: patch.currencyCode ?? state.currencyCode ?? null,
        dateFormat: patch.dateFormat ?? state.dateFormat ?? null,
        dateFormatConfirmed:
          patch.dateFormatConfirmed ?? state.dateFormatConfirmed ?? false,
        hasCategoryMapped:
          patch.hasCategoryMapped ?? state.hasCategoryMapped ?? false,
        categoryColumn: patch.categoryColumn ?? state.categoryColumn ?? null,
      };
      writePersistedSource(next);
      setState(next);
    },
    [state]
  );

  const updateUpload = useCallback(
    (patch: Partial<PersistedSource>) => {
      if (state.mode !== "upload" || !state.sessionId) return;
      const next: PersistedSource = { ...state, ...patch, mode: "upload" };
      writePersistedSource(next);
      setState(next);
    },
    [state]
  );

  const clearUpload = useCallback(() => {
    clearPersistedSource();
    setState({ mode: "demo" });
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      ready,
      mode: state.mode,
      sessionId: state.sessionId || null,
      filename: state.filename || null,
      currencyCode: state.currencyCode || null,
      dateFormat: state.dateFormat || null,
      dateFormatConfirmed: Boolean(state.dateFormatConfirmed),
      hasCategoryMapped: Boolean(state.hasCategoryMapped),
      categoryColumn: state.categoryColumn || null,
      setDemo,
      setUpload,
      updateUpload,
      clearUpload,
    }),
    [ready, state, setDemo, setUpload, updateUpload, clearUpload]
  );

  return (
    <DataSourceContext.Provider value={value}>{children}</DataSourceContext.Provider>
  );
}

export function useDataSource() {
  const ctx = useContext(DataSourceContext);
  if (!ctx) throw new Error("useDataSource outside provider");
  return ctx;
}
