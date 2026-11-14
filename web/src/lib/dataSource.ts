export const UPLOAD_SESSION_KEY = "mm_data_source";

export type DataSourceMode = "demo" | "upload";

export type PersistedSource = {
  mode: DataSourceMode;
  sessionId?: string | null;
  filename?: string | null;
  currencyCode?: string | null;
  dateFormat?: string | null;
  dateFormatConfirmed?: boolean;
  hasCategoryMapped?: boolean;
  categoryColumn?: string | null;
};

export function readPersistedSource(): PersistedSource {
  if (typeof window === "undefined") return { mode: "demo" };
  try {
    const raw = window.sessionStorage.getItem(UPLOAD_SESSION_KEY);
    if (!raw) {
      // Migrate legacy upload-only key if present
      const legacy = window.sessionStorage.getItem("mm_upload_session");
      if (legacy) {
        const parsed = JSON.parse(legacy) as {
          sessionId?: string;
          hasCategoryMapped?: boolean;
          categoryColumn?: string | null;
        };
        if (parsed.sessionId) {
          return {
            mode: "upload",
            sessionId: parsed.sessionId,
            hasCategoryMapped: Boolean(parsed.hasCategoryMapped),
            categoryColumn: parsed.categoryColumn || null,
          };
        }
      }
      return { mode: "demo" };
    }
    const data = JSON.parse(raw) as PersistedSource;
    if (data.mode === "upload" && data.sessionId) return data;
    return { mode: "demo" };
  } catch {
    return { mode: "demo" };
  }
}

export function writePersistedSource(data: PersistedSource): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(UPLOAD_SESSION_KEY, JSON.stringify(data));
  if (data.mode === "upload" && data.sessionId) {
    window.sessionStorage.setItem(
      "mm_upload_session",
      JSON.stringify({
        sessionId: data.sessionId,
        hasCategoryMapped: Boolean(data.hasCategoryMapped),
        categoryColumn: data.categoryColumn || null,
      })
    );
  } else {
    window.sessionStorage.removeItem("mm_upload_session");
  }
}

export function clearPersistedSource(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(UPLOAD_SESSION_KEY);
  window.sessionStorage.removeItem("mm_upload_session");
}


/** True when the API no longer has this browser's upload session (common on serverless /tmp). */
export function isUploadSessionGoneError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err ?? "");
  const lower = msg.toLowerCase();
  return (
    lower.includes("upload session not found") ||
    lower.includes("session not found or expired") ||
    lower.includes("not found or expired")
  );
}
