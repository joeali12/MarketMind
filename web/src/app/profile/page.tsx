"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api, formatMoney } from "@/lib/api";
import { DemoBadge } from "@/components/DemoBadge";
import { SourceBadge } from "@/components/SourceSelector";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

function ProfileInner() {
  const { t, lang } = useLang();
  const sp = useSearchParams();
  const { ready, mode, sessionId, currencyCode } = useDataSource();
  const [ids, setIds] = useState<{ customer_id: number }[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    setIds([]);
    setSelected(null);
    setProfile(null);
    setError(null);
    const load =
      mode === "upload" && sessionId
        ? api.uploadCustomers(sessionId)
        : api.customers();
    load.then((d) => {
      const list = (d.customers as { customer_id: number }[]) || [];
      setIds(list);
      const q = sp.get("id");
      const requested = q ? Number(q) : null;
      const initial =
        requested != null && list.some((c) => c.customer_id === requested)
          ? requested
          : list[0]?.customer_id;
      if (initial) setSelected(initial);
      else setSelected(null);
    }).catch((e) => setError(String(e.message || e)));
  }, [ready, sp, mode, sessionId]);

  useEffect(() => {
    if (!ready || !selected) {
      setProfile(null);
      return;
    }
    const load =
      mode === "upload" && sessionId
        ? api.uploadCustomer(sessionId, selected)
        : api.customer(selected);
    load.then(setProfile).catch((e) => {
      setProfile(null);
      setError(String(e.message || e));
    });
  }, [ready, selected, mode, sessionId]);

  const customer = (profile?.customer || {}) as Record<string, unknown>;
  const estimate = (profile?.estimate || {}) as Record<string, unknown>;
  const forecast = (profile?.forecast || {}) as Record<string, unknown>;
  const retrospective = (profile?.retrospective_actual || {}) as Record<string, unknown>;
  const isUpload = Boolean(profile && profile.demo === false);
  const moneyCode = isUpload ? currencyCode || (profile?.currency_code as string) : "GBP";

  const products = (profile?.products_bought || []) as {
    description: string;
    quantity: number;
    spend_gbp?: number;
    spend?: number;
  }[];
  const history = (profile?.purchase_history || []) as {
    invoice_date: string;
    description: string;
    line_amount_gbp?: number;
    line_amount?: number;
  }[];

  const suggested = estimate.suggested_action;
  const suggestedText =
    typeof suggested === "string"
      ? suggested
      : suggested && typeof suggested === "object"
        ? lang === "ar"
          ? String((suggested as { label_ar?: string }).label_ar || "")
          : String((suggested as { label_en?: string }).label_en || "")
        : "";

  return (
    <main className="main">
      {isUpload ? <SourceBadge /> : <DemoBadge />}
      <h1 className="page-title display">{t("card_profile")}</h1>
      <p className="page-sub">{t("card_profile_body")}</p>
      {error && <p className="muted">{error}</p>}

      <label className="muted" htmlFor="cust">
        {isUpload
          ? lang === "ar"
            ? "اختر زبون من ملفك"
            : "Choose a customer from your upload"
          : lang === "ar"
            ? "اختر زبون من العينة التجريبية"
            : "Choose a demo customer"}
      </label>
      <div style={{ margin: "8px 0 24px" }}>
        <select
          id="cust"
          className="select"
          value={selected ?? ""}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {ids.map((c) => (
            <option key={c.customer_id} value={c.customer_id}>
              {c.customer_id}
            </option>
          ))}
        </select>
      </div>

      {profile && (
        <div className="grid-2">
          <section className="facts-box">
            <h2 style={{ marginTop: 0 }}>{t("facts_title")}</h2>
            <p>
              ID {String(customer.customer_id)} · {String(customer.segment_label || "")}
            </p>
            {customer.prediction_cutoff != null && (
              <p className="muted" style={{ fontSize: 13 }}>
                {lang === "ar" ? "حد التوقع" : "Prediction cutoff"}:{" "}
                {String(customer.prediction_cutoff)}
              </p>
            )}
            <ul className="muted">
              <li>
                {lang === "ar" ? "أيام من آخر شراء" : "Days since purchase"}:{" "}
                {String(customer.recency)}
              </li>
              <li>
                {lang === "ar" ? "عدد مرات الشراء" : "Purchase frequency"}:{" "}
                {String(customer.frequency)}
              </li>
              <li>
                {lang === "ar" ? "مصروف سابق" : "Past spend"}:{" "}
                {formatMoney(
                  Number(customer.monetary ?? customer.monetary_gbp ?? 0),
                  lang,
                  moneyCode
                )}
              </li>
            </ul>
            <h3>{lang === "ar" ? "منتجات اشتريت قبل كده" : "Products bought before"}</h3>
            <p className="muted" style={{ fontSize: 13 }}>
              {lang === "ar"
                ? "سلوك تاريخي فقط — مش ضمان للاحتياج الجاي"
                : "Historical behaviour only — not a guarantee of future need"}
            </p>
            <ul>
              {products.slice(0, 8).map((p, i) => (
                <li key={i}>
                  {p.description || "—"} ·{" "}
                  {formatMoney(Number(p.spend ?? p.spend_gbp ?? 0), lang, moneyCode)}
                </li>
              ))}
            </ul>
          </section>

          <section className="estimate-box">
            <h2 style={{ marginTop: 0 }}>{t("estimate_title")}</h2>
            {isUpload && (!estimate || Object.keys(estimate).length === 0) ? (
              <>
                <p className="muted">{t("forecast_unavailable")}</p>
                <p className="muted" style={{ fontSize: 13 }}>
                  {lang === "ar"
                    ? String(forecast.reason_ar || "")
                    : String(forecast.reason_en || "")}
                </p>
              </>
            ) : estimate && Object.keys(estimate).length > 0 ? (
              <>
                <p className="muted">
                  {lang === "ar"
                    ? String(estimate.label_ar || "")
                    : String(estimate.label_en || "")}
                </p>
                <p
                  className="value positive"
                  style={{ fontSize: "2rem", fontWeight: 700 }}
                >
                  {formatMoney(
                    Number(
                      estimate.predicted_spend_90d ??
                        estimate.predicted_spend_90d_gbp ??
                        0
                    ),
                    lang,
                    isUpload
                      ? moneyCode || String(estimate.currency_code || null)
                      : "GBP"
                  )}
                </p>
                <p className="muted" style={{ fontSize: 13 }}>
                  forecast_scope:{" "}
                  {String(
                    estimate.forecast_scope ||
                      (isUpload ? "upload_store_chronological" : "demo_only")
                  )}
                </p>
                {isUpload && (
                  <p className="muted" style={{ fontSize: 12 }}>
                    {lang === "ar"
                      ? String(estimate.limitations_ar || "")
                      : String(estimate.limitations_en || "")}
                  </p>
                )}
                {suggestedText && (
                  <p className="muted">
                    {estimate.actions_approved
                      ? suggestedText
                      : `${suggestedText} (${
                          lang === "ar" ? "مؤقت — مش معتمد" : "provisional — not approved"
                        })`}
                  </p>
                )}
              </>
            ) : (
              <p className="muted">{t("loading")}</p>
            )}
          </section>
        </div>
      )}

      {retrospective && retrospective.target_spend_90d_actual_gbp != null && (
        <section className="band">
          <h2 className="display" style={{ marginTop: 0, fontSize: "1.2rem" }}>
            {t("retrospective_only")}
          </h2>
          <p className="muted" style={{ fontSize: 13 }}>
            {lang === "ar"
              ? String(retrospective.label_ar || "")
              : String(retrospective.label_en || "")}
          </p>
          <p>
            {formatMoney(
              Number(retrospective.target_spend_90d_actual_gbp || 0),
              lang,
              "GBP"
            )}
          </p>
        </section>
      )}

      {history.length > 0 && (
        <section className="band">
          <h2 className="display" style={{ marginTop: 0, fontSize: "1.3rem" }}>
            {lang === "ar" ? "آخر مشتريات (عند حد التوقع)" : "Recent purchases (as of cutoff)"}
          </h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{lang === "ar" ? "التاريخ" : "Date"}</th>
                  <th>{lang === "ar" ? "المنتج" : "Product"}</th>
                  <th>{lang === "ar" ? "مبلغ" : "Amount"}</th>
                </tr>
              </thead>
              <tbody>
                {history
                  .slice()
                  .reverse()
                  .slice(0, 20)
                  .map((h, i) => (
                    <tr key={i}>
                      <td>{h.invoice_date}</td>
                      <td>{h.description || "—"}</td>
                      <td>
                        {formatMoney(
                          Number(h.line_amount ?? h.line_amount_gbp ?? 0),
                          lang,
                          moneyCode
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<main className="main">…</main>}>
      <ProfileInner />
    </Suspense>
  );
}
