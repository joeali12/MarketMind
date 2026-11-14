"use client";

import { useEffect, useMemo, useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AssistantModal, type ChatMsg } from "@/components/AssistantModal";
import {
  UnresolvedGapsPanel,
  type GapRow,
} from "@/components/UnresolvedGapsPanel";
import { ColumnMappingPanel } from "@/components/ColumnMappingPanel";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

function TrustCheck() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M3.5 8.2l2.8 2.8 6.2-6.5"
        stroke="var(--emerald)"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

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
  needs_user_mapping?: boolean;
  mapping_confirmed?: boolean;
  needs_sheet_selection?: boolean;
  sheets?: string[];
  multi_currency?: boolean;
  discovered_currencies?: string[];
  date_format?: {
    needs_confirmation?: boolean;
    message_en?: string;
    message_ar?: string;
    examples?: string[];
  };
  column_mapping?: {
    suggestions?: { mappings?: MappingSuggestion[] };
    effective_mapping?: Record<string, string>;
    needs_user_mapping?: boolean;
  };
};

type MappingSuggestion = {
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
  const [dragActive, setDragActive] = useState(false);
  const [dragReject, setDragReject] = useState(false);
  const [dropFeedback, setDropFeedback] = useState<string | null>(null);
  const [safeFillBackup, setSafeFillBackup] = useState(false);
  const [needsMapping, setNeedsMapping] = useState(false);
  const [mappingConfirmed, setMappingConfirmed] = useState(false);
  const [workbookSheets, setWorkbookSheets] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string | null>(null);
  const [mappingSuggestions, setMappingSuggestions] = useState<MappingSuggestion[]>(
    []
  );
  const [effectiveMapping, setEffectiveMapping] = useState<Record<string, string>>(
    {}
  );
  const [sourceColumns, setSourceColumns] = useState<string[]>([]);
  const [multiCurrencyCodes, setMultiCurrencyCodes] = useState<string[]>([]);
  const [currencyFilter, setCurrencyFilter] = useState<string>("");

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
          applyValidationPayload(valJson);
        }
        const prof = await refreshProfile(sid);
        if (!cancelled && prof) {
          if (Array.isArray(prof.workbook_sheets) && prof.workbook_sheets.length) {
            setWorkbookSheets(prof.workbook_sheets as string[]);
          }
          if (typeof prof.selected_sheet === "string") {
            setSelectedSheet(prof.selected_sheet as string);
          }
          if (prof.mapping_confirmed != null) {
            setMappingConfirmed(Boolean(prof.mapping_confirmed));
            setNeedsMapping(
              Boolean(prof.needs_user_mapping) && !Boolean(prof.mapping_confirmed)
            );
          }
          if (prof.column_mapping && typeof prof.column_mapping === "object") {
            setEffectiveMapping(prof.column_mapping as Record<string, string>);
          }
          if (prof.analysis_currency_filter) {
            setCurrencyFilter(String(prof.analysis_currency_filter));
          }
        }
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

  async function refreshSafeFillBackup(sid: string) {
    try {
      const res = await fetch(`/api/upload/${sid}/safe-fill-backup`);
      const j = await res.json();
      setSafeFillBackup(Boolean(res.ok && j.backup_available));
    } catch {
      setSafeFillBackup(false);
    }
  }

  async function restoreSafeFill() {
    if (!sessionId || !safeFillBackup) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/upload/restore-safe-fill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, confirm_restore: true }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.detail || "Restore failed");
      setUnresolved((j.unresolved_preview as GapRow[]) || []);
      if (j.profile) setProfile(j.profile as Profile);
      await loadProposals(sessionId);
      await refreshProfile(sessionId);
      setStatus(
        lang === "ar"
          ? "اترجع الملف من نسخة ما قبل الملء الآمن"
          : "Restored file from the pre-safe-fill backup"
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Restore failed");
    } finally {
      setBusy(false);
    }
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
    await refreshSafeFillBackup(sid);
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
    if (needsMapping && !mappingConfirmed) return false;
    if (workbookSheets.length > 1 && !selectedSheet) return false;
    if (currencyCode === "UNSPECIFIED") return false;
    if (validation?.date_format?.needs_confirmation && !dateConfirmed) return false;
    if (multiCurrencyCodes.length > 1 && !currencyFilter) return false;
    return true;
  }

  function applyValidationPayload(valJson: Record<string, unknown>) {
    const v = (valJson.validation || valJson) as Validation;
    setValidation(v);
    let cols = (v.columns as string[]) || (v.mappable_columns as string[]) || [];
    if (!cols.length) {
      const preview = (valJson.preview_rows as Record<string, unknown>[] | undefined) || [];
      if (preview[0]) cols = Object.keys(preview[0]);
    }
    if (cols.length) setSourceColumns(cols);
    const cm = v.column_mapping;
    const suggestions = cm?.suggestions?.mappings || [];
    if (suggestions.length) setMappingSuggestions(suggestions);
    if (cm?.effective_mapping) setEffectiveMapping(cm.effective_mapping);
    const need =
      Boolean(v.needs_user_mapping || cm?.needs_user_mapping) &&
      !Boolean(v.mapping_confirmed || valJson.mapping_confirmed);
    setNeedsMapping(need);
    setMappingConfirmed(Boolean(v.mapping_confirmed || valJson.mapping_confirmed));
    if (Array.isArray(v.sheets) && v.sheets.length) setWorkbookSheets(v.sheets);
    if (Array.isArray(valJson.workbook_sheets)) {
      setWorkbookSheets(valJson.workbook_sheets as string[]);
    }
    if (typeof valJson.selected_sheet === "string") {
      setSelectedSheet(valJson.selected_sheet);
    }
    if (v.needs_sheet_selection) setSelectedSheet(null);
    const discovered =
      (v.discovered_currencies as string[] | undefined) ||
      (valJson.discovered_currencies as string[] | undefined) ||
      [];
    if (Boolean(v.multi_currency) && Array.isArray(discovered) && discovered.length > 1) {
      setMultiCurrencyCodes(discovered.map(String));
    } else {
      setMultiCurrencyCodes([]);
    }
  }

  async function saveCurrencyFilter(code: string) {
    if (!sessionId) return;
    const res = await fetch("/api/upload/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        analysis_currency_filter: code,
      }),
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "Currency filter failed");
    setCurrencyFilter(code);
    await refreshProfile(sessionId);
  }

  async function confirmMapping(mapping: Record<string, string>) {
    if (!sessionId) return;
    const res = await fetch("/api/upload/mapping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, mapping, confirm: true }),
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "Mapping failed");
    setMappingConfirmed(Boolean(j.mapping_confirmed));
    setNeedsMapping(!j.mapping_confirmed);
    setEffectiveMapping(j.column_mapping || mapping);
    await refreshProfile(sessionId);
    await loadProposals(sessionId);
    if (j.mapping_confirmed) {
      if (!chat.length) {
        setChat([
          {
            role: "assistant",
            text:
              lang === "ar"
                ? "تم تأكيد ربط الأعمدة. العملة بتاعة المبالغ إيه؟ (EGP / GBP / USD…)"
                : "Column mapping confirmed. What currency are the amounts in? (EGP / GBP / USD…)",
          },
        ]);
        setQuickReplies(["EGP", "GBP", "USD", "EUR", "SAR", "AED"]);
      }
      setModalOpen(true);
    }
  }

  async function selectSheet(sheet: string) {
    if (!sessionId) return;
    const res = await fetch("/api/upload/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, selected_sheet: sheet }),
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "Sheet selection failed");
    setSelectedSheet(sheet);
    // Backend clears mapping on sheet change — mirror that locally.
    setMappingConfirmed(false);
    setNeedsMapping(true);
    setEffectiveMapping({});
    setMappingSuggestions([]);
    const val = await fetch(
      `/api/upload/validate?session_id=${encodeURIComponent(sessionId)}`,
      { method: "POST" }
    );
    const valJson = await val.json();
    if (val.ok) applyValidationPayload(valJson);
    await refreshProfile(sessionId);
  }

  async function openDashboard() {
    if (!sessionId || !analysisReady()) return;
    setBusy(true);
    setErr(null);
    try {
      const acceptedIds = Object.entries(accepted)
        .filter(([, on]) => on)
        .map(([id]) => id);
      if (acceptedIds.length) {
        const res = await fetch("/api/upload/accept-cleaning", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            accepted_ids: acceptedIds,
          }),
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(
            (j as { detail?: string }).detail || "Could not save cleaning choices"
          );
        }
      }
      updateUpload({
        currencyCode,
        dateFormat: dateFormat || null,
        dateFormatConfirmed: dateConfirmed,
        hasCategoryMapped: Boolean(categoryColumn),
        categoryColumn: categoryColumn || null,
      });
      router.push("/store");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not open dashboard");
    } finally {
      setBusy(false);
    }
  }

  function isAllowedUpload(file: File): boolean {
    const name = file.name.toLowerCase();
    return (
      name.endsWith(".csv") ||
      name.endsWith(".xlsx") ||
      name.endsWith(".xls") ||
      file.type.includes("csv") ||
      file.type.includes("sheet") ||
      file.type.includes("excel")
    );
  }

  function onDragEnter(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    setDragActive(true);
    setDragReject(false);
    setDropFeedback(null);
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    const items = e.dataTransfer?.items;
    if (items && items.length) {
      const item = items[0];
      const reject =
        item.kind === "file" &&
        item.type &&
        !(
          item.type.includes("csv") ||
          item.type.includes("sheet") ||
          item.type.includes("excel") ||
          item.type === ""
        );
      setDragReject(Boolean(reject));
    }
    setDragActive(true);
  }

  function onDragLeave(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget === e.target) {
      setDragActive(false);
      setDragReject(false);
    }
  }

  function onDropFile(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    setDragReject(false);
    if (busy) return;
    const file = e.dataTransfer?.files?.[0] || null;
    if (!file) return;
    if (!isAllowedUpload(file)) {
      setDropFeedback(
        lang === "ar"
          ? "الصيغة مش مدعومة — استخدم CSV أو Excel"
          : "Unsupported type — use CSV or Excel"
      );
      setDragReject(true);
      return;
    }
    setDropFeedback(
      lang === "ar" ? `تم استلام ${file.name}` : `Received ${file.name}`
    );
    void onFile(file);
  }

  async function onFile(file: File | null) {
    if (!file || busy) return;
    if (!isAllowedUpload(file)) {
      setErr(
        lang === "ar"
          ? "الصيغة مش مدعومة — استخدم CSV أو Excel"
          : "Unsupported type — use CSV or Excel"
      );
      return;
    }
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
      setNeedsMapping(Boolean(upJson.needs_user_mapping) || Boolean(upJson.needs_sheet_selection));
      setMappingConfirmed(Boolean(upJson.mapping_confirmed));
      setWorkbookSheets(
        Array.isArray(upJson.workbook_sheets) ? upJson.workbook_sheets : []
      );
      setSelectedSheet(upJson.selected_sheet || null);
      setMultiCurrencyCodes([]);
      setCurrencyFilter("");
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
      applyValidationPayload(valJson);
      const validationBody = (valJson.validation || {}) as Validation;
      // Sheet selection is a normal gate — not a hard upload failure.
      const awaitingSheet = Boolean(
        validationBody.needs_sheet_selection || upJson.needs_sheet_selection
      );
      if (!validationBody.ok && !awaitingSheet && !validationBody.needs_user_mapping) {
        throw new Error(
          validationBody.message || valJson.detail || "Validate failed"
        );
      }
      const suggested = validationBody.detected_category_column || "";
      setCategoryColumn(suggested || "");

      setProgressStage(3);
      setProgress(
        lang === "ar"
          ? "٣) بيدوّر على القيم الناقصة أو غير المتسقة…"
          : "3) Finding missing or inconsistent values…"
      );
      let prof: Profile | null = null;
      try {
        prof = await refreshProfile(upJson.session_id);
      } catch {
        prof = null;
      }
      setProgressStage(4);
      setProgress(
        lang === "ar"
          ? "٤) بيجهّز ملخص الزباين والمنتجات…"
          : "4) Preparing customer and product summary…"
      );
      if (!awaitingSheet) {
        try {
          await loadProposals(upJson.session_id);
        } catch {
          // Mapping/sheet may still be incomplete — proposals load after confirm.
        }
      }
      setProgressStage(0);
      setProgress("");
      setStatus(
        awaitingSheet
          ? lang === "ar"
            ? "اختار ورقة المبيعات من الملف، بعدين أكّد ربط الأعمدة."
            : "Select the sales worksheet, then confirm column mapping."
          : lang === "ar"
            ? "تم الرفع — المساعد هيقرأ ملفك ويسأل أسئلة مرتبطة بيه، بعدين تنظيف، بعدين لوحة التحليل."
            : "Uploaded — the assistant will ask file-specific questions, then cleaning, then your analysis dashboard."
      );
      const rows = Number(prof?.row_count || 0);
      const needsDate = Boolean(validationBody.date_format?.needs_confirmation);
      const intro =
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
            }`;
      setChat([{ role: "assistant", text: intro }]);
      setQuickReplies(["EGP", "GBP", "USD", "EUR", "SAR", "AED"]);
      // Keep mapping/sheet UI usable — do not cover it with the assistant backdrop.
      const gateMapping =
        awaitingSheet ||
        Boolean(validationBody.needs_user_mapping) ||
        Boolean(upJson.needs_user_mapping);
      setModalOpen(!gateMapping);
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

  const pipelineStage = progressStage || (profile ? 4 : sessionId ? 2 : 0);
  const wizardCurrent = !sessionId ? 1 : !profile ? 2 : unresolved.length > 0 ? 3 : 4;

  return (
    <main className="main upload-chat-main">
      <div className="wizard-steps" aria-label={lang === "ar" ? "خطوات المسار" : "Pipeline steps"}>
        {(
          lang === "ar"
            ? [
                ["1", "الرفع"],
                ["2", "فهم الملف"],
                ["3", "مراجعة التنظيف"],
                ["4", "لوحة التحليل"],
              ]
            : [
                ["1", "Upload"],
                ["2", "File understanding"],
                ["3", "Cleaning review"],
                ["4", "Dashboard"],
              ]
        ).map(([n, label], idx) => (
          <span
            key={n}
            className={`wiz${wizardCurrent === idx + 1 ? " is-current" : ""}`}
          >
            <span className="wiz-num">{n}</span>
            {label}
          </span>
        ))}
      </div>

      {!sessionId && (
        <header className="upload-hero">
          <div className="upload-hero-badge">
            <span className="dot" aria-hidden />
            {lang === "ar"
              ? "تحليلات تجزئة بسيطة · Simple & grounded retail analytics"
              : "Simple & grounded retail analytics · تحليلات مبيعات حقيقية"}
          </div>
          <h1 className="display" data-testid="upload-hero-title">
            {lang === "ar"
              ? "افهم زبائنك ومبيعاتك من غير تعقيد"
              : "Understand your customers and sales without the complexity"}
          </h1>
          <p>
            {lang === "ar"
              ? "ارفع تقرير مبيعات أو تصدير نقطة البيع (CSV / Excel). MarketMind يقرأ الأعمدة، يوضّح الفراغات، ويفتح لوحة تحليل مبنية على ملفك."
              : "Upload your sales report or POS export (CSV / Excel). MarketMind maps columns, surfaces gaps, and opens an analytics dashboard grounded in your file."}
          </p>
          <div className="upload-trust">
            <span>
              <TrustCheck />
              {lang === "ar" ? "من غير إعداد تقني معقّد" : "No complex technical setup"}
            </span>
            <span>
              <TrustCheck />
              {lang === "ar"
                ? "جلسة مؤقتة · من غير لوجات للمحتوى"
                : "Temporary session · no content logging"}
            </span>
            <span>
              <TrustCheck />
              {lang === "ar" ? "CSV و XLSX" : "CSV & XLSX"}
            </span>
          </div>
        </header>
      )}

      <div className="upload-layout">
        <section className="band">
          {!sessionId ? (
            <>
              <div
                className={[
                  "dropzone",
                  dragActive ? "is-drag" : "",
                  dragReject ? "is-drag-reject" : "",
                  busy ? "is-busy" : "",
                  dropFeedback && !dragReject ? "is-success" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onDragEnter={onDragEnter}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDropFile}
                data-testid="upload-dropzone"
              >
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  disabled={busy}
                  aria-label={lang === "ar" ? "اختر ملف المبيعات" : "Browse sales file"}
                  onChange={(e) => onFile(e.target.files?.[0] || null)}
                />
                <div className="dropzone-icon" aria-hidden>
                  {busy ? (
                    <span className="btn-spinner" />
                  ) : (
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden>
                      <path
                        d="M12 16V4m0 0l-4 4m4-4l4 4"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                      <path
                        d="M4 16.5V18a2 2 0 002 2h12a2 2 0 002-2v-1.5"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                      />
                    </svg>
                  )}
                </div>
                <div className="dropzone-cta">
                  {busy
                    ? lang === "ar"
                      ? "بيقرا الملف…"
                      : "Reading file…"
                    : lang === "ar"
                      ? "اختر ملف المبيعات (Browse sales file)"
                      : "Browse sales file (اختر ملف المبيعات)"}
                </div>
                <p className="muted" style={{ margin: 0 }}>
                  {lang === "ar"
                    ? "أو اسحب الملف هنا · CSV / XLSX لحد ٢٥ ميجا"
                    : "or drag and drop here · CSV / XLSX up to 25MB"}
                </p>
                <div className="format-pills" aria-hidden>
                  <span>.CSV</span>
                  <span>.XLSX</span>
                  <span>.XLS</span>
                </div>
                {dropFeedback && (
                  <p
                    className={`dropzone-feedback ${dragReject ? "is-error" : "is-ok"}`}
                    role="status"
                  >
                    {dropFeedback}
                  </p>
                )}
              </div>
              <div className="privacy-note">
                <TrustCheck />
                <div>
                  <strong>
                    {lang === "ar"
                      ? "مساحة تاجر خاصة لهذه الجلسة"
                      : "Private merchant workspace for this session"}
                  </strong>
                  <span className="muted">
                    {policyLines.length
                      ? policyLines.slice(0, 3).join(" · ")
                      : lang === "ar"
                        ? "تخزين مؤقت · من غير لوجات لمحتوى الملف · مش بنوعد بتشفير متعدد المستأجرين في الـ MVP."
                        : "Temporary storage · no file-content logging · no multi-tenant encryption claim in this MVP."}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <>
              <h2 className="section-title display">
                {lang === "ar" ? "ملف الجلسة" : "Session file"}
              </h2>
              <p className="muted" style={{ marginTop: 0 }}>
                {filename || sessionId.slice(0, 8)}
                {" · "}
                <button type="button" className="btn btn-ghost btn-sm" onClick={discard}>
                  {t("discard")}
                </button>
              </p>
              <label className="muted" style={{ display: "block", marginBottom: 8 }}>
                {lang === "ar" ? "ارفع ملف تاني" : "Upload a different file"}
              </label>
              <input
                className="input-file"
                type="file"
                accept=".csv,.xlsx,.xls"
                disabled={busy}
                onChange={(e) => onFile(e.target.files?.[0] || null)}
              />
            </>
          )}

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
        </section>

        <section className="band">
          <div className="band-head">
            <h2 className="section-title display">
              {lang === "ar" ? "مسار المعالجة" : "Processing pipeline"}
            </h2>
            {busy && (
              <span className="badge" style={{ borderColor: "var(--violet)", color: "var(--violet)" }}>
                {lang === "ar" ? "شغال…" : "Running…"}
              </span>
            )}
          </div>
          <ul className="pipeline-steps">
            {(
              lang === "ar"
                ? [
                    ["قراءة الملف", "اكتشاف الصفوف والأعمدة"],
                    ["فهم الأعمدة والتواريخ", "ربط الحقول القياسية"],
                    ["فحص الفراغات والتناقضات", "من غير اختراع قيم حرجة"],
                    ["تجهيز لوحة التحليل", "مبيعات · منتجات · زبائن"],
                  ]
                : [
                    ["Reading the file", "Detect rows and columns"],
                    ["Understanding columns & dates", "Map standard fields"],
                    ["Checking missing or inconsistent data", "Critical values are never invented"],
                    ["Preparing sales and customer analysis", "Sales · products · customers"],
                  ]
            ).map(([title, detail], idx) => {
              const step = idx + 1;
              const cls =
                pipelineStage > step
                  ? "is-done"
                  : pipelineStage === step || (busy && pipelineStage === step)
                    ? "is-active"
                    : pipelineStage === 0 && step === 1 && busy
                      ? "is-active"
                      : "";
              return (
                <li key={title} className={cls}>
                  <span className="step-mark" aria-hidden>
                    {pipelineStage > step ? "✓" : step}
                  </span>
                  <div>
                    <strong>{title}</strong>
                    <p className="muted">{detail}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      </div>

      {!sessionId && (
        <div className="feature-grid">
          {(
            lang === "ar"
              ? [
                  ["ربط أعمدة بسيط", "نتعرف على حقول الفاتورة والكمية والسعر والزبون من غير ما تعقّد الإعداد."],
                  ["مجموعات زبائن وصفية", "لما يكون فيه رقم زبون — مجموعات RFM من ملفك فقط، مش من عينة تانية."],
                  ["تنظيف صريح", "الفراغات الحرجة تفضل يدوي؛ الملء الذكي بس لما الدليل من نفس الملف."],
                ]
              : [
                  ["Simple column mapping", "We recognise invoice, quantity, price, and customer fields without a heavy setup."],
                  ["Descriptive customer groups", "When customer IDs exist — RFM groups from this file only, not another sample."],
                  ["Honest cleaning", "Critical blanks stay manual; smart fill only with same-file evidence."],
                ]
          ).map(([title, body]) => (
            <article key={title} className="band feature-card">
              <h3 className="display">{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      )}

      {sessionId && (needsMapping || (workbookSheets.length > 1 && !selectedSheet)) && (
        <ColumnMappingPanel
          sessionId={sessionId}
          sourceColumns={sourceColumns}
          suggestions={mappingSuggestions}
          initialMapping={effectiveMapping}
          sheets={workbookSheets}
          selectedSheet={selectedSheet}
          needsSheetSelection={workbookSheets.length > 1 && !selectedSheet}
          onSheetSelected={selectSheet}
          onConfirmed={confirmMapping}
          busy={busy}
        />
      )}

      {profile && (
        <section className="band">
          <h2 className="section-title display" data-testid="understand-file">
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
          <h2 className="section-title display">
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
          {multiCurrencyCodes.length > 1 && (
            <div
              data-testid="multi-currency-filter"
              style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}
            >
              <span className="muted" style={{ fontSize: 13 }}>
                {lang === "ar"
                  ? "الملف فيه أكثر من عملة — اختار عملة واحدة للإجماليات (مفيش تحويل سعر صرف):"
                  : "This file has multiple currencies — pick one for totals (no FX conversion):"}
              </span>
              {(() => {
                const currency = profile?.currency as
                  | {
                      exclusion?: {
                        blank_or_unknown_excluded?: number;
                        other_currency_excluded?: number;
                        reason_en?: string;
                        reason_ar?: string;
                      };
                    }
                  | undefined;
                const exclusion = currency?.exclusion;
                const excluded =
                  Number(exclusion?.blank_or_unknown_excluded || 0) +
                  Number(exclusion?.other_currency_excluded || 0);
                if (!currencyFilter || !excluded) return null;
                return (
                  <p className="muted" data-testid="currency-exclusion-note" style={{ flexBasis: "100%", fontSize: 13 }}>
                    {lang === "ar" ? exclusion?.reason_ar : exclusion?.reason_en}
                  </p>
                );
              })()}
              {multiCurrencyCodes.map((code) => (
                <button
                  key={code}
                  type="button"
                  className={currencyFilter === code ? "btn" : "btn btn-ghost"}
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    saveCurrencyFilter(code)
                      .catch((e) =>
                        setErr(e instanceof Error ? e.message : String(e))
                      )
                      .finally(() => setBusy(false));
                  }}
                >
                  {code}
                </button>
              ))}
            </div>
          )}
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
              className="btn btn-primary"
              disabled={!analysisReady() || busy}
              aria-busy={busy}
              onClick={() => void openDashboard()}
            >
              {busy && <span className="btn-spinner" aria-hidden />}
              {lang === "ar"
                ? "خلّص التنظيف وافتح لوحة التحليل"
                : "Finish cleaning and open my dashboard"}
            </button>
            {safeFillBackup && (
              <button
                type="button"
                className="btn-ghost"
                disabled={busy}
                data-testid="restore-safe-fill"
                onClick={() => void restoreSafeFill()}
              >
                {lang === "ar"
                  ? "ارجع نسخة ما قبل الملء الآمن"
                  : "Undo safe fills (restore backup)"}
              </button>
            )}
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
