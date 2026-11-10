"use client";

import Link from "next/link";
import { useDataSource } from "@/context/DataSourceContext";
import { useLang } from "@/context/LangContext";

export function SourceSelector() {
  const { t, lang } = useLang();
  const {
    mode,
    sessionId,
    filename,
    currencyCode,
    hasCategoryMapped,
    categoryColumn,
    dateFormat,
    dateFormatConfirmed,
    setDemo,
    setUpload,
  } = useDataSource();

  return (
    <div className="source-bar" role="group" aria-label={t("source_label")}>
      <span className="source-label">{t("source_label")}</span>
      <button
        type="button"
        className={`source-chip${mode === "demo" ? " is-active" : ""}`}
        aria-pressed={mode === "demo"}
        onClick={setDemo}
      >
        {t("source_demo")}
      </button>
      {sessionId ? (
        <button
          type="button"
          className={`source-chip${mode === "upload" ? " is-active" : ""}`}
          aria-pressed={mode === "upload"}
          onClick={() =>
            setUpload({
              sessionId,
              filename,
              currencyCode,
              dateFormat,
              dateFormatConfirmed,
              hasCategoryMapped,
              categoryColumn,
            })
          }
          title={filename || sessionId.slice(0, 8)}
        >
          {t("source_upload")}
          {currencyCode && currencyCode !== "UNSPECIFIED"
            ? ` · ${currencyCode}`
            : ""}
        </button>
      ) : (
        <Link href="/upload" className="source-chip">
          {lang === "ar" ? "ارفع ملف للتحليل" : "Upload a file to analyse"}
        </Link>
      )}
      {mode === "upload" && sessionId && (
        <span className="muted" style={{ fontSize: 13 }}>
          {filename || `${sessionId.slice(0, 8)}…`}
        </span>
      )}
    </div>
  );
}

export function SourceBadge() {
  const { lang } = useLang();
  const { mode, filename, currencyCode } = useDataSource();
  if (mode === "demo") return null;
  return (
    <span className="badge badge-upload">
      {lang === "ar"
        ? `ملف مرفوع${filename ? `: ${filename}` : ""} · ${
            currencyCode && currencyCode !== "UNSPECIFIED"
              ? currencyCode
              : "عملة المصدر (اختَر العملة)"
          } — مش بيانات العرض`
        : `Uploaded file${filename ? `: ${filename}` : ""} · ${
            currencyCode && currencyCode !== "UNSPECIFIED"
              ? currencyCode
              : "source currency (select currency)"
          } — not demo data`}
    </span>
  );
}
