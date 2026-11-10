"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AssistantModal, type ChatMsg } from "@/components/AssistantModal";
import {
  UnresolvedGapsPanel,
  type GapRow,
} from "@/components/UnresolvedGapsPanel";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

type Proposal = {
  id: string;
  title_en: string;
  title_ar: string;
  reason_en: string;
  reason_ar: string;
  rows_affected: number;
  default_accepted?: boolean;
  destructive?: boolean;
  estimated_impact?: {
    rows_removed_estimate?: number;
    eligible_spend_delta?: number;
  };
};

type Validation = {
  ok?: boolean;
  message?: string;
  detected_category_column?: string | null;
  missing_columns?: string[];
  mappable_columns?: string[];
  columns?: string[];
  date_format?: {
    needs_confirmation?: boolean;
    message_en?: string;
    message_ar?: string;
  };
};

type Profile = Record<string, unknown>;
type AssistantAction = {
  type: string;
  currency_code?: string;
  date_format?: string;
  confirm?: boolean;
  confirmed?: boolean;
  preference?: string;
  proposal_id?: string;
  accepted?: boolean;
  field?: string;
  // refresh_after_mutation handled by sendAssistantText
};

export default function UploadPage() {
  const { t, lang } = useLang();
  const router = useRouter();
  const dataSource = useDataSource();
  const { setUpload, clearUpload, updateUpload } = dataSource;
  const [policy, setPolicy] = useState<Record<string, unknown> | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [progress, setProgress] = useState<string>("");
  const [progressStage, setProgressStage] = useState(0);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [categoryColumn, setCategoryColumn] = useState<string>("");
  const [currencyCode, setCurrencyCode] = useState<string>("UNSPECIFIED");
  const [dateFormat, setDateFormat] = useState<string>("");
  const [dateConfirmed, setDateConfirmed] = useState(false);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const [unresolved, setUnresolved] = useState<GapRow[]>([]);
  const [baseline, setBaseline] = useState<Record<string, unknown> | null>(null);
  const [anomaly, setAnomaly] = useState<Record<string, unknown> | null>(null);
  const [assistantLabel, setAssistantLabel] = useState("");
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [question, setQuestion] = useState("");
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [profileConfirmed, setProfileConfirmed] = useState(false);
  const [gapFillPreference, setGapFillPreference] = useState<
    "manual" | "smart" | null
  >(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.uploadPolicy().then(setPolicy).catch(() => setPolicy(null));
    fetch("/api/upload/assistant/status")
      .then((r) => r.json())
      .then((j) =>
        setAssistantLabel(lang === "ar" ? j.label_ar : j.label_en)
      )
      .catch(() => undefined);
  }, [lang]);

  // Rehydrate local upload UI from sessionStorage when navigating back
  useEffect(() => {
    if (!dataSource.ready || hydrated || sessionId) return;
    if (dataSource.mode !== "upload" || !dataSource.sessionId) {
      setHydrated(true);
      return;
    }
    let cancelled = false;
    const sid = dataSource.sessionId;
    (async () => {
      try {
        setSessionId(sid);
        setFilename(dataSource.filename);
        if (dataSource.currencyCode) setCurrencyCode(dataSource.currencyCode);
        if (dataSource.dateFormat) setDateFormat(dataSource.dateFormat);
        setDateConfirmed(Boolean(dataSource.dateFormatConfirmed));
        if (dataSource.categoryColumn) setCategoryColumn(dataSource.categoryColumn);
        const val = await fetch(
          `/api/upload/validate?session_id=${encodeURIComponent(sid)}`,
          { method: "POST" }
        );
        const valJson = await val.json();
        if (!cancelled && val.ok) {
          setValidation(valJson.validation as Validation);
        }
        await refreshProfile(sid);
        if (!cancelled) await loadProposals(sid);
      } catch {
        if (!cancelled) {
          // Session expired — clear stale source so UI matches demo fallback
          clearUpload();
          setSessionId(null);
        }
      } finally {
        if (!cancelled) setHydrated(true);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot hydrate from persisted source
  }, [dataSource.ready, dataSource.mode, dataSource.sessionId, hydrated, sessionId]);

  const policyLines = useMemo(() => {
    if (!policy) return [];
    return lang === "ar"
      ? [
          `أنواع مسموحة: ${(policy.allowed_extensions as string[])?.join(", ")}`,
          `حد أقصى: ${Number(policy.max_bytes) / (1024 * 1024)} ميجابايت`,
          `معاينة لحد ${policy.max_preview_rows} صف`,
          "تخزين مؤقت ساعتين — منغير لوجات لمحتوى الملف",
          "مش بنقول إن فيه تشفير أو عزل متعدد المستأجرين",
        ]
      : [
          `Allowed: ${(policy.allowed_extensions as string[])?.join(", ")}`,
          `Max size: ${Number(policy.max_bytes) / (1024 * 1024)} MB`,
          `Preview up to ${policy.max_preview_rows} rows`,
          "Temp storage 2h — no file-content logging",
          "No encryption / multi-tenant claims in this MVP",
        ];
  }, [policy, lang]);

  async function refreshProfile(sid: string) {
    const res = await fetch(`/api/upload/${sid}/profile`);
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "Profile failed");
    setProfile(j);
    return j;
  }

  async function loadProposals(sid: string) {
    const propRes = await fetch(
      `/api/upload/cleaning-proposals?session_id=${encodeURIComponent(sid)}`,
      { method: "POST" }
    );
    const propJson = await propRes.json();
    if (!propRes.ok) throw new Error(propJson.detail || "Proposals failed");
    const list = (propJson.proposals as Proposal[]) || [];
    setProposals(list);
    setUnresolved((propJson.unresolved_preview as GapRow[]) || []);
    setBaseline(propJson.baseline || null);
    setAnomaly(propJson.anomaly_review || null);
    const next: Record<string, boolean> = {};
    list.forEach((p) => {
      next[p.id] = p.destructive ? false : Boolean(p.default_accepted);
    });
    setAccepted(next);
  }

  async function saveSettings(
    sid: string,
    patch: { currency?: string; date_format?: string; confirm?: boolean }
  ) {
    const res = await fetch("/api/upload/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sid,
        currency_code: patch.currency,
        date_format: patch.date_format,
        confirm_date_format: Boolean(patch.confirm),
      }),
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "Settings failed");
    setCurrencyCode(j.currency_code || "UNSPECIFIED");
    setDateFormat(j.date_format || "");
    setDateConfirmed(Boolean(j.date_format_confirmed));
    updateUpload({
      currencyCode: j.currency_code,
      dateFormat: j.date_format,
      dateFormatConfirmed: Boolean(j.date_format_confirmed),
    });
    return j;
  }

  function analysisReady(): boolean {
    if (!sessionId) return false;
    if (currencyCode === "UNSPECIFIED") return false;
    if (validation?.date_format?.needs_confirmation && !dateConfirmed) return false;
    return true;
  }

  function openDashboard() {
    if (!sessionId || !analysisReady()) return;
    updateUpload({
      currencyCode,
      dateFormat: dateFormat || null,
      dateFormatConfirmed: dateConfirmed,
      hasCategoryMapped: Boolean(categoryColumn),
      categoryColumn: categoryColumn || null,
    });
    router.push("/store");
  }

  async function onFile(file: File | null) {
    if (!file || busy) return;
    setBusy(true);
    setErr(null);
    setStatus("");
    setProgressStage(1);
    setProgress(lang === "ar" ? "١) بيقرا الملف…" : "1) Reading the file…");
    setChat([]);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const up = await fetch("/api/upload", { method: "POST", body: fd });
      const upJson = await up.json();
      if (!up.ok) throw new Error(upJson.detail || "Upload failed");
      setProgressStage(2);
      setProgress(
        lang === "ar"
          ? "٢) بيطابق الأعمدة ويتأكد من التواريخ…"
          : "2) Matching columns and checking dates…"
      );
      setSessionId(upJson.session_id);
      setFilename(upJson.filename || file.name);
      setCurrencyCode("UNSPECIFIED");
      setDateFormat("");
      setDateConfirmed(false);
      setProfileConfirmed(false);
      setGapFillPreference(null);
      setUpload({
        sessionId: upJson.session_id,
        filename: upJson.filename || file.name,
        currencyCode: null,
        dateFormat: null,
        dateFormatConfirmed: false,
        hasCategoryMapped: false,
        categoryColumn: null,
      });

      const val = await fetch(
        `/api/upload/validate?session_id=${encodeURIComponent(upJson.session_id)}`,
        { method: "POST" }
      );
      const valJson = await val.json();
      if (!val.ok) throw new Error(valJson.detail || "Validate failed");
      setValidation(valJson.validation as Validation);
      const suggested =
        (valJson.validation as Validation)?.detected_category_column || "";
      setCategoryColumn(suggested || "");

      setProgressStage(3);
      setProgress(
        lang === "ar"
          ? "٣) بيدوّر على القيم الناقصة أو غير المتسقة…"
          : "3) Finding missing or inconsistent values…"
      );
      const prof = await refreshProfile(upJson.session_id);
      setProgressStage(4);
      setProgress(
        lang === "ar"
          ? "٤) بيجهّز ملخص الزباين والمنتجات…"
          : "4) Preparing customer and product summary…"
      );
      await loadProposals(upJson.session_id);
      setProgressStage(0);
      setProgress("");
      setStatus(
        lang === "ar"
          ? "تم الرفع — المساعد هيقرأ ملفك ويسأل أسئلة مرتبطة بيه، بعدين تنظيف، بعدين لوحة التحليل."
          : "Uploaded — the assistant will ask file-specific questions, then cleaning, then your analysis dashboard."
      );
      const rows = Number(prof?.row_count || 0);
      const needsDate = Boolean(
        (valJson.validation as Validation)?.date_format?.needs_confirmation
      );
      setChat([
        {
          role: "assistant",
          text:
            lang === "ar"
              ? `تمام، استلمت «${upJson.filename || file.name}» (~${rows.toLocaleString()} صف). دوري محلّل بيانات للملف ده: أفهمه، أسألك أسئلة تسهّل التحليل، أنضّف معاك، وبعدين أديك إحاطة وقرارات مقترحة.\n\nالأرقام من السيرفر. أي قيمة محسومة عندك بس (رقم زبون/تاريخ غامض) هنطلب تملاها يدوي.\n\nأول حاجة: المبالغ بعملة إيه؟ ردّ بـ EGP أو GBP أو USD… (مش بهزر العملة).${
                  needsDate
                    ? "\nبعدها هنأكّد صيغة التاريخ في الملف ده، وبعدين فراغات التنظيف."
                    : "\nبعدين نراجع فراغات التنظيف في الملف ده."
                }`
              : `Got «${upJson.filename || file.name}» (~${rows.toLocaleString()} rows). I’m your data analyst for this file: understand it, ask clarifying questions, clean with you, then brief you with decision suggestions.\n\nNumbers come from the server. Client-owned blanks (customer IDs / ambiguous dates) stay manual.\n\nFirst: what currency are the amounts in? Reply EGP, GBP, USD… (I never guess).${
                  needsDate
                    ? "\nThen we’ll confirm this file’s date format, then cleaning gaps."
                    : "\nThen we’ll review cleaning gaps in this file."
                }`,
        },
      ]);
      setQuickReplies(["EGP", "GBP", "USD", "EUR", "SAR", "AED"]);
      setModalOpen(true);
    } catch (e) {
      setErr(String((e as Error).message || e));
      setProgress("");
      setProgressStage(0);
    } finally {
      setBusy(false);
      setProgressStage(0);
    }
  }

  async function applyAssistantActions(actions: AssistantAction[], sid: string) {
    let needRefresh = false;
    for (const a of actions) {
      if (a.type === "set_currency" && a.currency_code) {
        setCurrencyCode(a.currency_code);
        await saveSettings(sid, { currency: a.currency_code });
        needRefresh = true;
      } else if (a.type === "set_date_format" && a.date_format) {
        setDateFormat(a.date_format);
        await saveSettings(sid, {
          date_format: a.date_format,
          confirm: Boolean(a.confirm),
        });
        needRefresh = true;
      } else if (a.type === "set_proposal" && a.proposal_id) {
        setAccepted((prev) => ({
          ...prev,
          [a.proposal_id!]: Boolean(a.accepted),
        }));
      } else if (a.type === "confirm_profile") {
        setProfileConfirmed(Boolean(a.confirmed));
      } else if (a.type === "set_gap_fill_preference" && a.preference) {
        const pref = String(a.preference);
        if (pref === "manual" || pref === "smart") {
          setGapFillPreference(pref);
        }
      }
    }
    if (needRefresh) {
      await refreshProfile(sid);
      await loadProposals(sid);
    }
  }

  async function discard() {
    if (!sessionId) return;
    await fetch(`/api/upload/session?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
    setSessionId(null);
    setFilename(null);
    setValidation(null);
    setProfile(null);
    setProposals([]);
    setUnresolved([]);
    setBaseline(null);
    setAnomaly(null);
    setCategoryColumn("");
    setCurrencyCode("UNSPECIFIED");
    setDateFormat("");
    setDateConfirmed(false);
    setProfileConfirmed(false);
    setGapFillPreference(null);
    setChat([]);
    setQuickReplies([]);
    setModalOpen(false);
    clearUpload();
    setStatus(lang === "ar" ? "اتمسحت الجلسة" : "Session discarded");
  }

  async function confirmProfile(ok: boolean) {
    if (!sessionId) return;
    setBusy(true);
    try {
      const res = await fetch("/api/upload/confirm-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, confirmed: ok }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || "Confirm failed");
      setProfileConfirmed(Boolean(j.profile_confirmed));
      if (ok) {
        setChat((c) => [
          ...c,
          {
            role: "assistant",
            text:
              lang === "ar"
                ? "تمام — الملخص اتأكد. الصفوف الناقصة: تحب ملء ذكي من أنماط الملف ولا ملء يدوي؟"
                : "Great — summary confirmed. For missing rows: smart fill from file patterns, or manual?",
          },
        ]);
        setQuickReplies(
          lang === "ar" ? ["ملء ذكي", "ملء يدوي"] : ["smart fill", "manual fill"]
        );
        setModalOpen(true);
      }
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function setGapPref(pref: "manual" | "smart") {
    if (!sessionId) return;
    setBusy(true);
    try {
      const res = await fetch("/api/upload/gap-fill-preference", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, preference: pref }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || "Preference failed");
      setGapFillPreference(pref);
      setChat((c) => [
        ...c,
        {
          role: "assistant",
          text:
            pref === "smart"
              ? lang === "ar"
                ? "وضع الملء الذكي شغال. راجع الاقتراحات في الجدول واحفظ بعد الموافقة. رقم الزبون والتاريخ يدوي فقط."
                : "Smart-fill mode on. Review suggestions in the table and save after approval. Customer IDs and dates stay manual-only."
              : lang === "ar"
                ? "وضع الملء اليدوي شغال. اكتب في الجدول واحفظ في ملف الجلسة."
                : "Manual-fill mode on. Type in the table and save to the session file.",
        },
      ]);
      setModalOpen(true);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function sendAssistantText(raw: string) {
    if (!sessionId || !raw.trim()) return;
    setBusy(true);
    const q = raw.trim();
    const history = chat.slice(-6).map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      text: m.text.slice(0, 400),
    }));
    setChat((c) => [...c, { role: "user", text: q }]);
    setQuestion("");
    try {
      const res = await fetch("/api/upload/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          question: q,
          lang,
          history,
        }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || "Assistant failed");
      const actions = (j.actions || []) as AssistantAction[];
      if (actions.length) {
        await applyAssistantActions(actions, sessionId);
      }
      if (
        j.data_mutated ||
        actions.some((a) => a.type === "refresh_after_mutation")
      ) {
        await refreshProfile(sessionId);
        await loadProposals(sessionId);
      }
      const mode = String(j.mode || "grounded_facts");
      // Discreet status only — never dump citation keys / provider IDs into the bubble
      const statusBit =
        mode === "gemini"
          ? lang === "ar"
            ? "بمساعدة ذكاء اصطناعي"
            : "AI-assisted"
          : j.fallback_used
            ? lang === "ar"
              ? "من التحليل المحسوب"
              : "From computed analysis"
            : undefined;
      setAssistantLabel(
        lang === "ar" ? "مساعد MarketMind" : "MarketMind assistant"
      );
      const answerText = String(
        j.answer || (lang === "ar" ? j.answer_ar : j.answer_en)
      )
        .replace(/gemini-2\.5-flash/gi, "")
        .replace(/context_keys[\s\S]*/gi, "")
        .trim();
      setChat((c) => [
        ...c,
        {
          role: "assistant",
          text: answerText,
          meta: statusBit,
        },
      ]);
      setQuickReplies(
        Array.isArray(j.quick_replies) ? (j.quick_replies as string[]) : []
      );
    } catch (e) {
      setChat((c) => [
        ...c,
        { role: "assistant", text: String((e as Error).message || e) },
      ]);
      setQuickReplies([]);
    } finally {
      setBusy(false);
    }
  }

  async function askAssistant() {
    await sendAssistantText(question);
  }

  const structure = (profile?.structure || {}) as Record<string, unknown>;
  const findings = (profile?.findings || []) as {
    id: string;
    title_en: string;
    title_ar: string;
    count: number;
    detail_en?: string;
    severity?: string;
  }[];
  const classification = (profile?.classification || {}) as Record<string, string>;
  const previewRows = (profile?.preview_rows || []) as Record<string, unknown>[];
  const mappings = ((profile?.column_mappings as { mappings?: unknown[] })?.mappings ||
    []) as {
    source_column: string;
    target: string | null;
    confidence: number;
    needs_user_confirm: boolean;
  }[];

  return (
    <main className="main upload-chat-main">
      <h1 className="page-title display">{t("upload_title")}</h1>
      <p className="page-sub">
        {lang === "ar"
          ? "التسلسل بسيط: ارفع → أسئلة ذكية عن ملفك → تنظيف (يدوي لما القرار عندك) → لوحة محلّل باقتراحات قرار."
          : "Simple sequence: upload → smart questions about your file → clean (manual when only you know) → analyst dashboard with decision suggestions."}
      </p>

      <section className="band">
        <h2 className="display" style={{ marginTop: 0, fontSize: "1.2rem" }}>
          {t("upload_how")}
        </h2>
        <ul className="muted">
          {policyLines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <input
          className="input-file"
          type="file"
          accept=".csv,.xlsx"
          disabled={busy}
          onChange={(e) => onFile(e.target.files?.[0] || null)}
        />
        {progress && (
          <div
            className="upload-progress"
            role="status"
            aria-live="polite"
            aria-busy={busy}
          >
            <p className="muted" style={{ margin: 0 }}>
              {progress}
            </p>
            <div
              className={`upload-progress-bar${progressStage ? " is-active" : ""}`}
              aria-hidden
            />
          </div>
        )}
        {status && <p className="muted">{status}</p>}
        {err && (
          <p className="muted" style={{ color: "var(--danger)" }}>
            {t("error")}: {err}
          </p>
        )}
        {sessionId && (
          <p className="muted">
            {filename} · {sessionId.slice(0, 8)}…{" "}
            <button type="button" className="btn btn-ghost btn-sm" onClick={discard}>
              {t("discard")}
            </button>
          </p>
        )}
      </section>

      {profile && (
        <section className="band">
          <h2 className="display" style={{ marginTop: 0, fontSize: "1.2rem" }}>
            {t("understand_file")}
          </h2>
          <p className="muted">
            {lang === "ar" ? classification.phrase_ar : classification.phrase_en}
          </p>
          <div className="grid-4" style={{ marginTop: 12 }}>
            <div className="kpi">
              <div className="label">{lang === "ar" ? "صفوف" : "Rows"}</div>
              <div className="value">{Number(profile.row_count || 0).toLocaleString()}</div>
            </div>
            <div className="kpi">
              <div className="label">{lang === "ar" ? "زبائن" : "Customers"}</div>
              <div className="value">
                {Number(structure.unique_customers || 0).toLocaleString()}
              </div>
            </div>
            <div className="kpi">
              <div className="label">{lang === "ar" ? "منتجات" : "Products"}</div>
              <div className="value">
                {Number(structure.unique_products || 0).toLocaleString()}
              </div>
            </div>
            <div className="kpi">
              <div className="label">{lang === "ar" ? "فواتير" : "Invoices"}</div>
              <div className="value">
                {Number(structure.unique_invoices || 0).toLocaleString()}
              </div>
            </div>
          </div>
          {findings.length > 0 && (
            <ul className="muted" style={{ marginTop: 16 }}>
              {findings.map((f) => (
                <li key={f.id}>
                  <strong>{lang === "ar" ? f.title_ar : f.title_en}</strong>: {f.count}
                  {f.detail_en ? ` — ${lang === "ar" ? "" : f.detail_en}` : ""}
                </li>
              ))}
            </ul>
          )}
          {mappings.some((m) => m.needs_user_confirm) && (
            <p className="muted" style={{ fontSize: 13 }}>
              {lang === "ar"
                ? "في ربط أعمدة ضعيف الثقة — مش بيتطبّق لوحده."
                : "Some column mappings are low-confidence and are never applied silently."}
            </p>
          )}
          {previewRows.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    {Object.keys(previewRows[0]).map((k) => (
                      <th key={k}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewRows.slice(0, 5).map((r, i) => (
                    <tr key={i}>
                      {Object.keys(previewRows[0]).map((k) => (
                        <td key={k}>{String(r[k] ?? "—")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {sessionId && (
        <section className="band">
          <h2 className="display" style={{ marginTop: 0, fontSize: "1.2rem" }}>
            {lang === "ar" ? "حالة الجلسة" : "Session status"}
          </h2>
          <p className="muted" style={{ fontSize: 14, margin: 0 }}>
            {lang === "ar" ? "العملة" : "Currency"}:{" "}
            <strong>
              {currencyCode === "UNSPECIFIED"
                ? lang === "ar"
                  ? "لسه (من المساعد)"
                  : "pending (via assistant)"
                : currencyCode}
            </strong>
            {" · "}
            {lang === "ar" ? "التاريخ" : "Dates"}:{" "}
            <strong>
              {dateConfirmed
                ? dateFormat || "ok"
                : validation?.date_format?.needs_confirmation
                  ? lang === "ar"
                    ? "محتاج تأكيد (من المساعد)"
                    : "needs confirm (via assistant)"
                  : dateFormat || "—"}
            </strong>
            {proposals.length > 0 && (
              <>
                {" · "}
                {lang === "ar" ? "تنظيف" : "Cleaning"}:{" "}
                <strong>
                  {Object.values(accepted).filter(Boolean).length}/{proposals.length}{" "}
                  {lang === "ar" ? "مقبول" : "accepted"}
                </strong>
              </>
            )}
          </p>
          {baseline && (
            <p className="muted" style={{ fontSize: 13 }}>
              {lang === "ar" ? "قبل" : "Baseline"}: {String(baseline.rows)} rows ·{" "}
              {Number(baseline.eligible_spend ?? 0).toFixed(0)}{" "}
              {currencyCode !== "UNSPECIFIED"
                ? currencyCode
                : String(baseline.amount_unit_en || "")}
            </p>
          )}
          {anomaly && anomaly.available ? (
            <p className="muted" style={{ fontSize: 13 }}>
              {lang === "ar" ? String(anomaly.note_ar) : String(anomaly.note_en)} ·{" "}
              {lang === "ar" ? "صفوف موسومة" : "flagged"}: {String(anomaly.flagged_rows)}
            </p>
          ) : null}
          <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", gap: 10 }}>
            <button
              type="button"
              className="btn"
              disabled={!analysisReady()}
              onClick={openDashboard}
            >
              {lang === "ar"
                ? "خلّص التنظيف وافتح لوحة التحليل"
                : "Finish cleaning and open my dashboard"}
            </button>
            {!analysisReady() && (
              <p className="muted" style={{ margin: 0, fontSize: 13, flexBasis: "100%" }}>
                {lang === "ar"
                  ? "محتاج عملة مؤكدة وصيغة تاريخ (لو التاريخ غامض) قبل فتح اللوحة."
                  : "Confirm currency and date format (when dates are ambiguous) before opening the dashboard."}
              </p>
            )}
            {analysisReady() && unresolved.length > 0 && (
              <p className="muted" style={{ margin: 0, fontSize: 13, flexBasis: "100%" }}>
                {lang === "ar"
                  ? `فيه ${unresolved.length} صف ناقص لسه — املأ المحسوم عندك يدوي، أو افتح اللوحة والفراغات ظاهرة للمراجعة.`
                  : `${unresolved.length} unresolved rows remain — fill client-owned blanks manually, or open the dashboard with gaps still visible for review.`}
              </p>
            )}
          </div>
        </section>
      )}

      {sessionId && unresolved.length > 0 && (
        <UnresolvedGapsPanel
          sessionId={sessionId}
          rows={unresolved}
          profileConfirmed={profileConfirmed}
          gapFillPreference={gapFillPreference}
          onConfirmProfile={confirmProfile}
          onSetPreference={setGapPref}
          onSaved={(next) => {
            setUnresolved(next);
            if (sessionId) loadProposals(sessionId).catch(() => undefined);
          }}
          busy={busy}
        />
      )}

      {sessionId && (
        <button
          type="button"
          className="assistant-fab"
          onClick={() => setModalOpen(true)}
        >
          {lang === "ar" ? "افتح المساعد" : "Open assistant"}
        </button>
      )}

      <AssistantModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        label={assistantLabel}
        chat={chat}
        question={question}
        onQuestionChange={setQuestion}
        onSend={askAssistant}
        onQuickReply={(text) => sendAssistantText(text)}
        quickReplies={quickReplies}
        busy={busy}
      />
    </main>
  );
}
