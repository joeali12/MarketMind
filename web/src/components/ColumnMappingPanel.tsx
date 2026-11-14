"use client";

import { useMemo, useState } from "react";
import { useLang } from "@/context/LangContext";

type MappingRow = {
  source_column: string;
  target?: string | null;
  confidence?: number;
  auto_apply?: boolean;
  needs_user_confirm?: boolean;
  ambiguous?: boolean;
  candidates?: string[];
  note_en?: string;
  note_ar?: string;
};

type Props = {
  sessionId: string;
  sourceColumns: string[];
  suggestions: MappingRow[];
  initialMapping?: Record<string, string>;
  sheets?: string[];
  selectedSheet?: string | null;
  needsSheetSelection?: boolean;
  onSheetSelected?: (sheet: string) => Promise<void>;
  onConfirmed: (mapping: Record<string, string>) => Promise<void>;
  busy?: boolean;
};

const CANONICAL_OPTIONS = [
  { id: "invoice", en: "Invoice / order ID", ar: "رقم فاتورة / طلب" },
  { id: "invoice_date", en: "Transaction date", ar: "تاريخ المعاملة" },
  { id: "customer_id", en: "Customer ID", ar: "رقم الزبون" },
  { id: "stock_code", en: "Product / SKU code", ar: "كود المنتج" },
  { id: "description", en: "Product name / description", ar: "اسم / وصف المنتج" },
  { id: "quantity", en: "Quantity", ar: "الكمية" },
  { id: "unit_price", en: "Unit selling price", ar: "سعر الوحدة" },
  { id: "line_amount", en: "Line total / revenue", ar: "إجمالي السطر / المبيعات" },
  { id: "category", en: "Category", ar: "التصنيف" },
  { id: "country", en: "Country", ar: "الدولة" },
  { id: "row_currency", en: "Currency column", ar: "عمود العملة" },
  { id: "ignore", en: "Ignore", ar: "تجاهل" },
];

export function ColumnMappingPanel({
  sessionId,
  sourceColumns,
  suggestions,
  initialMapping,
  sheets = [],
  selectedSheet,
  needsSheetSelection,
  onSheetSelected,
  onConfirmed,
  busy,
}: Props) {
  const { lang } = useLang();
  const seed = useMemo(() => {
    const m: Record<string, string> = { ...(initialMapping || {}) };
    for (const row of suggestions) {
      if (row.auto_apply && row.target && !m[row.target]) {
        m[row.target] = row.source_column;
      }
    }
    return m;
  }, [initialMapping, suggestions]);

  const [draft, setDraft] = useState<Record<string, string>>(seed);
  const [err, setErr] = useState<string | null>(null);

  // source → canon for selects
  const sourceToCanon = useMemo(() => {
    const inv: Record<string, string> = {};
    for (const [canon, src] of Object.entries(draft)) {
      if (src) inv[src] = canon;
    }
    return inv;
  }, [draft]);

  function setSourceMapping(source: string, canon: string) {
    setDraft((prev) => {
      const next = { ...prev };
      for (const [k, v] of Object.entries(next)) {
        if (v === source) delete next[k];
      }
      if (canon && canon !== "ignore") next[canon] = source;
      return next;
    });
  }

  async function confirm() {
    setErr(null);
    try {
      // Explicit empties so ignored auto-mapped fields are not restored by merge_user_mapping.
      const payload: Record<string, string> = { ...draft };
      for (const sug of suggestions) {
        const chosen = sourceToCanon[sug.source_column] || "ignore";
        const target = sug.target;
        if (chosen === "ignore" && target && target !== "ignore") {
          payload[target] = "";
        }
      }
      await onConfirmed(payload);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="band" data-testid="column-mapping-panel">
      <h2 className="section-title display">
        {lang === "ar" ? "ربط أعمدة الملف" : "Map file columns"}
      </h2>
      <p className="muted" style={{ fontSize: 14 }}>
        {lang === "ar"
          ? "أكد الأعمدة قبل التحليل. Amount/Total الغامض مش بيتفسّر كسعر وحدة من غير تأكيدك."
          : "Confirm columns before analysis. Ambiguous Amount/Total is never treated as unit price without your confirmation."}
      </p>

      {needsSheetSelection && sheets.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <label className="muted" style={{ display: "block", marginBottom: 6 }}>
            {lang === "ar" ? "ورقة الإكسل" : "Excel worksheet"}
          </label>
          <select
            data-testid="sheet-select"
            value={selectedSheet || ""}
            disabled={busy}
            onChange={(e) => {
              const v = e.target.value;
              if (v && onSheetSelected) void onSheetSelected(v);
            }}
          >
            <option value="">
              {lang === "ar" ? "اختار الورقة…" : "Select sheet…"}
            </option>
            {sheets.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>
              <th>{lang === "ar" ? "عمود الملف" : "File column"}</th>
              <th>{lang === "ar" ? "المعنى" : "Meaning"}</th>
              <th>{lang === "ar" ? "ملاحظة" : "Note"}</th>
            </tr>
          </thead>
          <tbody>
            {sourceColumns.map((col) => {
              const sug = suggestions.find((s) => s.source_column === col);
              const current = sourceToCanon[col] || "ignore";
              const options =
                sug?.ambiguous && sug.candidates?.length
                  ? [
                      ...CANONICAL_OPTIONS.filter((o) =>
                        ["unit_price", "line_amount", "ignore"].includes(o.id)
                      ),
                    ]
                  : CANONICAL_OPTIONS;
              return (
                <tr key={col}>
                  <td>
                    <code>{col}</code>
                    {sug?.ambiguous ? (
                      <span className="muted" style={{ marginInlineStart: 8 }}>
                        {lang === "ar" ? "غامض" : "ambiguous"}
                      </span>
                    ) : null}
                  </td>
                  <td>
                    <select
                      aria-label={`Map ${col}`}
                      value={current}
                      disabled={busy || Boolean(needsSheetSelection && !selectedSheet)}
                      onChange={(e) => setSourceMapping(col, e.target.value)}
                    >
                      {options.map((o) => (
                        <option key={o.id} value={o.id}>
                          {lang === "ar" ? o.ar : o.en}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="muted" style={{ fontSize: 13 }}>
                    {lang === "ar" ? sug?.note_ar : sug?.note_en}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {err && (
        <p className="muted" style={{ color: "var(--danger)" }}>
          {err}
        </p>
      )}
      <button
        type="button"
        className="btn btn-primary"
        style={{ marginTop: 14 }}
        data-testid="confirm-column-mapping"
        disabled={busy || Boolean(needsSheetSelection && !selectedSheet)}
        onClick={() => void confirm()}
      >
        {lang === "ar" ? "أكد الربط ومتابعة" : "Confirm mapping and continue"}
      </button>
      <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        session {sessionId.slice(0, 8)}…
      </p>
    </section>
  );
}
