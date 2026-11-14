"use client";

import { useEffect, useState } from "react";
import { useLang } from "@/context/LangContext";

export type GapSuggestion = {
  suggested: string | number | null;
  allowed: boolean;
  reason_en?: string;
  reason_ar?: string;
};

export type GapRow = {
  row_index: number;
  invoice?: string | null;
  stock_code?: string | null;
  description?: string | null;
  quantity?: number | null;
  unit_price?: number | null;
  customer_id?: number | null;
  invoice_date?: string | null;
  issues?: string[];
  suggestions?: Record<string, GapSuggestion>;
};

type Props = {
  sessionId: string;
  rows: GapRow[];
  profileConfirmed: boolean;
  gapFillPreference: "manual" | "smart" | null;
  onConfirmProfile: (ok: boolean) => Promise<void>;
  onSetPreference: (pref: "manual" | "smart") => Promise<void>;
  onSaved: (nextRows: GapRow[]) => void;
  busy?: boolean;
};

const EDIT_FIELDS = [
  "invoice_date",
  "quantity",
  "unit_price",
  "customer_id",
  "description",
] as const;

/** Gaps table: calendar date only — never show Timestamp midnight clocks. */
function formatGapDate(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const trimmed = String(value).trim();
  const m = trimmed.match(/^(\d{4}-\d{2}-\d{2})/);
  if (m) return m[1];
  return trimmed.replace(/\s+\d{1,2}:\d{2}(:\d{2})?(\.\d+)?$/, "").trim() || trimmed;
}

export function UnresolvedGapsPanel({
  sessionId,
  rows,
  profileConfirmed,
  gapFillPreference,
  onConfirmProfile,
  onSetPreference,
  onSaved,
  busy,
}: Props) {
  const { t, lang } = useLang();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [fillingKey, setFillingKey] = useState<string | null>(null);

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const r of rows) {
      for (const field of EDIT_FIELDS) {
        const key = `${r.row_index}:${field}`;
        const cur = r[field];
        if (cur != null) next[key] = String(cur);
      }
    }
    setDrafts((prev) => ({ ...next, ...prev }));
  }, [rows]);

  useEffect(() => {
    if (gapFillPreference !== "smart") return;
    const steps: { key: string; value: string }[] = [];
    for (const r of rows) {
      for (const field of r.issues || []) {
        const sug = r.suggestions?.[field];
        const cur = r[field as keyof GapRow];
        if (cur == null && sug?.allowed && sug.suggested != null) {
          steps.push({ key: `${r.row_index}:${field}`, value: String(sug.suggested) });
        }
      }
    }
    if (!steps.length) return;
    let cancelled = false;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    (async () => {
      if (reduce) {
        setDrafts((prev) => {
          const next = { ...prev };
          for (const step of steps) next[step.key] = step.value;
          return next;
        });
        return;
      }
      for (const step of steps) {
        if (cancelled) return;
        setFillingKey(step.key);
        setDrafts((prev) => ({ ...prev, [step.key]: step.value }));
        await new Promise((resolve) => setTimeout(resolve, 90));
      }
      if (!cancelled) setFillingKey(null);
    })();
    return () => {
      cancelled = true;
    };
  }, [gapFillPreference, rows]);

  function setCell(rowIndex: number, field: string, value: string) {
    setDrafts((d) => ({ ...d, [`${rowIndex}:${field}`]: value }));
  }

  async function applySmartToDrafts() {
    const steps: { key: string; value: string }[] = [];
    for (const r of rows) {
      for (const field of r.issues || []) {
        const sug = r.suggestions?.[field];
        if (sug?.allowed && sug.suggested != null) {
          steps.push({ key: `${r.row_index}:${field}`, value: String(sug.suggested) });
        }
      }
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setDrafts((prev) => {
        const next = { ...prev };
        for (const step of steps) next[step.key] = step.value;
        return next;
      });
    } else {
      for (const step of steps) {
        setFillingKey(step.key);
        setDrafts((prev) => ({ ...prev, [step.key]: step.value }));
        await new Promise((resolve) => setTimeout(resolve, 90));
      }
      setFillingKey(null);
    }
    setMsg(
      lang === "ar"
        ? "اتحطت الاقتراحات الذكية في الخانات — راجعها قبل الحفظ."
        : "Smart suggestions filled into cells — review before saving."
    );
  }

  async function savePatches(which: "draft" | "smart_all") {
    setSaving(true);
    setMsg("");
    try {
      let patches: {
        row_index: number;
        field: string;
        value: string | number;
        source: string;
      }[] = [];

      if (which === "smart_all") {
        const res = await fetch("/api/upload/gap-fill", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            patches: [],
            apply_all_smart: true,
          }),
        });
        const j = await res.json();
        if (!res.ok) throw new Error(j.detail || "Save failed");
        onSaved((j.unresolved_preview as GapRow[]) || []);
        setMsg(
          lang === "ar"
            ? `اتحفظ ${j.applied_count} تعديل ذكي في ملف الجلسة.`
            : `Saved ${j.applied_count} smart patches to the session file.`
        );
        return;
      }

      for (const r of rows) {
        for (const field of r.issues || []) {
          const key = `${r.row_index}:${field}`;
          const raw = (drafts[key] ?? "").trim();
          if (!raw) continue;
          const sug = r.suggestions?.[field];
          const isSmart =
            sug?.allowed &&
            sug.suggested != null &&
            String(sug.suggested) === raw;
          patches.push({
            row_index: r.row_index,
            field,
            value: ["quantity", "unit_price", "customer_id"].includes(field)
              ? Number(raw)
              : raw,
            source: isSmart ? "smart" : "manual",
          });
        }
      }
      if (!patches.length) {
        setMsg(lang === "ar" ? "مفيش قيم للحفظ." : "Nothing to save.");
        return;
      }
      const res = await fetch("/api/upload/gap-fill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, patches }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || "Save failed");
      onSaved((j.unresolved_preview as GapRow[]) || []);
      setMsg(
        lang === "ar"
          ? `اتحفظ ${j.applied_count} تعديل في ملف الجلسة.`
          : `Saved ${j.applied_count} patches to the session file.`
      );
    } catch (e) {
      setMsg(String((e as Error).message || e));
    } finally {
      setSaving(false);
    }
  }

  if (!rows.length) return null;

  return (
    <section className="band gap-panel">
      <h2 className="display" style={{ marginTop: 0, fontSize: "1.2rem" }}>
        {t("unresolved")}
      </h2>

      {!profileConfirmed && (
        <div className="gap-confirm">
          <p className="muted" style={{ marginTop: 0 }}>
            {lang === "ar"
              ? "بعد ما المساعد قرأ الملف: هل الملخص والمعلومات اللي طلّعها صح؟"
              : "After the assistant read the file: is the summary it extracted correct?"}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy || saving}
              onClick={() => onConfirmProfile(true)}
            >
              {lang === "ar" ? "صح كده" : "Yes, correct"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={busy || saving}
              onClick={() => onConfirmProfile(false)}
            >
              {lang === "ar" ? "مش صح" : "Not correct"}
            </button>
          </div>
        </div>
      )}

      {profileConfirmed && !gapFillPreference && (
        <div className="gap-confirm">
          <p className="muted" style={{ marginTop: 0 }}>
            {lang === "ar"
              ? "الصفوف الناقصة دي: تحب المساعد يقترح ملء ذكي متوافق مع بقية الملف (بس اللي عليه دليل — مش هيتخترع رقم زبون أو تاريخ)، ولا تملاها يدوي وتتحفظ؟"
              : "For these missing rows: should the assistant propose smart fills consistent with the rest of the file (evidence only — never invent customer IDs or dates), or fill manually and save?"}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy || saving}
              onClick={() => onSetPreference("smart")}
            >
              {lang === "ar" ? "ملء ذكي مقترح" : "Smart fill suggestions"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={busy || saving}
              onClick={() => onSetPreference("manual")}
            >
              {lang === "ar" ? "ملء يدوي" : "Manual fill"}
            </button>
          </div>
        </div>
      )}

      {profileConfirmed && gapFillPreference && (
        <>
          <p className="muted" style={{ fontSize: 13 }}>
            {lang === "ar"
              ? gapFillPreference === "smart"
                ? "وضع ذكي: الاقتراحات من أنماط الملف. رقم الزبون والتاريخ يدوي فقط. راجع قبل الحفظ."
                : "وضع يدوي: اكتب القيم واحفظها في ملف الجلسة. مش بنتولّد قيم لوحدنا."
              : gapFillPreference === "smart"
                ? "Smart mode: suggestions from file patterns. Customer ID and dates stay manual. Review before save."
                : "Manual mode: type values and save to the session file. Nothing is auto-invented."}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            {gapFillPreference === "smart" && (
              <>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={saving}
                  onClick={applySmartToDrafts}
                >
                  {lang === "ar" ? "حط الاقتراحات في الخانات" : "Fill suggestions into cells"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={saving}
                  onClick={() => savePatches("smart_all")}
                >
                  {lang === "ar" ? "احفظ كل الذكي المتاح" : "Save all allowed smart fills"}
                </button>
              </>
            )}
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={saving}
              onClick={() => savePatches("draft")}
            >
              {lang === "ar" ? "احفظ التعديلات في الملف" : "Save edits to file"}
            </button>
          </div>
        </>
      )}

      {msg && (
        <p className="muted" style={{ fontSize: 13 }}>
          {msg}
        </p>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("th_invoice")}</th>
              <th>{t("th_stock")}</th>
              <th>{t("th_qty")}</th>
              <th>{t("th_price")}</th>
              <th>{t("th_customer")}</th>
              <th>{lang === "ar" ? "تاريخ" : "Date"}</th>
              <th>{t("th_issues")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const canEdit = profileConfirmed && Boolean(gapFillPreference);
              const issues = new Set(r.issues || []);
              return (
                <tr key={r.row_index}>
                  <td>{r.invoice ?? "—"}</td>
                  <td>{r.stock_code ?? "—"}</td>
                  <td>
                    {canEdit && issues.has("quantity") ? (
                      <input
                        className={`input gap-input${fillingKey === `${r.row_index}:quantity` ? " is-filling" : ""}`}
                        value={drafts[`${r.row_index}:quantity`] ?? ""}
                        onChange={(e) => setCell(r.row_index, "quantity", e.target.value)}
                        placeholder={
                          r.suggestions?.quantity?.suggested != null
                            ? String(r.suggestions.quantity.suggested)
                            : ""
                        }
                        title={
                          lang === "ar"
                            ? r.suggestions?.quantity?.reason_ar
                            : r.suggestions?.quantity?.reason_en
                        }
                      />
                    ) : (
                      r.quantity ?? "—"
                    )}
                  </td>
                  <td>
                    {canEdit && issues.has("unit_price") ? (
                      <input
                        className={`input gap-input${fillingKey === `${r.row_index}:unit_price` ? " is-filling" : ""}`}
                        value={drafts[`${r.row_index}:unit_price`] ?? ""}
                        onChange={(e) =>
                          setCell(r.row_index, "unit_price", e.target.value)
                        }
                        placeholder={
                          r.suggestions?.unit_price?.suggested != null
                            ? String(r.suggestions.unit_price.suggested)
                            : ""
                        }
                        title={
                          lang === "ar"
                            ? r.suggestions?.unit_price?.reason_ar
                            : r.suggestions?.unit_price?.reason_en
                        }
                      />
                    ) : (
                      r.unit_price ?? "—"
                    )}
                  </td>
                  <td>
                    {canEdit && issues.has("customer_id") ? (
                      <input
                        className="input gap-input"
                        value={drafts[`${r.row_index}:customer_id`] ?? ""}
                        onChange={(e) =>
                          setCell(r.row_index, "customer_id", e.target.value)
                        }
                        placeholder={lang === "ar" ? "يدوي فقط" : "manual only"}
                        title={
                          lang === "ar"
                            ? r.suggestions?.customer_id?.reason_ar
                            : r.suggestions?.customer_id?.reason_en
                        }
                      />
                    ) : (
                      r.customer_id ?? "—"
                    )}
                  </td>
                  <td>
                    {canEdit && issues.has("invoice_date") ? (
                      <input
                        className="input gap-input"
                        value={
                          drafts[`${r.row_index}:invoice_date`] ??
                          (r.invoice_date ? formatGapDate(r.invoice_date) : "")
                        }
                        onChange={(e) =>
                          setCell(r.row_index, "invoice_date", e.target.value)
                        }
                        placeholder="YYYY-MM-DD"
                        title={
                          lang === "ar"
                            ? r.suggestions?.invoice_date?.reason_ar
                            : r.suggestions?.invoice_date?.reason_en
                        }
                      />
                    ) : (
                      formatGapDate(r.invoice_date)
                    )}
                  </td>
                  <td>
                    {(r.issues || []).join(", ")}
                    {gapFillPreference === "smart" &&
                      (r.issues || []).some(
                        (f) => r.suggestions?.[f]?.allowed && r.suggestions[f]?.suggested != null
                      ) && (
                        <div className="muted" style={{ fontSize: 11 }}>
                          {lang === "ar" ? "فيه اقتراح ذكي" : "smart suggestion"}
                        </div>
                      )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
