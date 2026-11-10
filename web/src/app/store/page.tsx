"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, formatMoney } from "@/lib/api";
import { DemoBadge } from "@/components/DemoBadge";
import { SourceBadge } from "@/components/SourceSelector";
import { BarSeriesChart } from "@/components/charts/BarSeriesChart";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

type TrendRange = "3m" | "6m" | "12m" | "all";

export default function StorePage() {
  const { t, lang } = useLang();
  const { mode, sessionId, currencyCode, ready } = useDataSource();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [products, setProducts] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<TrendRange>("6m");

  useEffect(() => {
    if (!ready) return;
    setData(null);
    setProducts(null);
    setErr(null);
    setLoading(true);
    const isUpload = mode === "upload" && sessionId;
    const loadOverview = isUpload
      ? api.uploadOverview(sessionId as string)
      : api.overview();
    const loadProducts = isUpload
      ? api.uploadProducts(sessionId as string)
      : api.products();
    Promise.all([loadOverview, loadProducts.catch(() => null)])
      .then(([ov, prod]) => {
        setData(ov);
        setProducts(prod);
      })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [mode, sessionId, ready]);

  const metrics = (data?.metrics || {}) as Record<string, number | string | null>;
  const evidence = (data?.evidence_insights || []) as {
    id: string;
    title_en: string;
    title_ar: string;
    evidence_en: string;
    evidence_ar: string;
    caveat_en?: string;
    caveat_ar?: string;
  }[];
  const isUpload = Boolean(data && data.demo === false);
  const sales = Number(metrics.sales ?? metrics.sales_gbp ?? 0);
  const aov = Number(metrics.average_order_value ?? metrics.average_order_value_gbp ?? 0);
  const displayCurrency = isUpload
    ? currencyCode || (data?.currency_code as string) || null
    : "GBP";
  const currencyLabel =
    displayCurrency && displayCurrency !== "UNSPECIFIED"
      ? displayCurrency
      : lang === "ar"
        ? "عملة المصدر"
        : "source currency";
  const deepDives = (data?.optional_deep_dives || []) as {
    id: string;
    href?: string;
    title_en: string;
    title_ar: string;
    why_en: string;
    why_ar: string;
  }[];
  const steps = (data?.suggested_next_steps || []) as {
    rank: number;
    title_en: string;
    title_ar: string;
    evidence_en: string;
    evidence_ar: string;
    uncertainty_en: string;
    uncertainty_ar: string;
  }[];
  const forecast = (data?.forecast || {}) as Record<string, unknown>;
  const defs = (data?.definitions || {}) as Record<string, string>;
  const meaning = (data?.what_this_may_mean || {}) as { en?: string; ar?: string };

  const filteredTrend = useMemo(() => {
    const trend = (data?.monthly_trend || []) as {
      month: string;
      spend?: number;
      spend_gbp?: number;
      orders: number;
    }[];
    if (range === "all") return trend;
    const n = range === "3m" ? 3 : range === "6m" ? 6 : 12;
    return trend.slice(-n);
  }, [data?.monthly_trend, range]);

  const trendBars = filteredTrend.map((m) => ({
    key: m.month,
    label: m.month,
    value: Number(m.spend ?? m.spend_gbp ?? 0),
    secondary: m.orders,
  }));

  const productRows = (
    ((products?.products || products?.items || []) as Record<string, unknown>[]) || []
  )
    .slice(0, 6)
    .map((p, idx) => ({
      key: String(p.stock_code || p.product_name || p.description || idx),
      name: String(p.product_name || p.name || p.description || "—"),
      units: Number(p.quantity || p.units || 0),
      spend: Number(p.spend || p.eligible_spend || 0),
    }));

  const returning = Number(metrics.returning_customer_share || 0);

  return (
    <main className="main">
      {isUpload ? <SourceBadge /> : <DemoBadge />}
      <h1 className="page-title display">{t("card_store")}</h1>
      <p className="page-sub">
        {isUpload
          ? lang === "ar"
            ? "مساحة تحليل لمتجرك: أرقام من ملفك، رسوم واضحة، واقتراحات قرار — من غير بيانات وهمية."
            : "Analytics workspace for your store: real upload numbers, clear charts, and decision suggestions — no fake metrics."
          : t("card_store_body")}
      </p>

      {loading && <p className="muted">{t("loading")}</p>}
      {err && (
        <p className="muted" style={{ color: "var(--danger)" }}>
          {t("error")}: {err}
          {mode === "upload" && (
            <>
              {" "}
              <Link href="/upload">{lang === "ar" ? "ارجع للرفع" : "Back to upload"}</Link>
            </>
          )}
        </p>
      )}
      {!loading && !err && !data && (
        <p className="muted">
          {lang === "ar" ? "مفيش بيانات للعرض." : "No data to display."}
        </p>
      )}

      {data && (
        <>
          <div className="grid-4" data-testid="store-kpi-row">
            <div className="kpi kpi-accent">
              <div className="label">{t("sales")}</div>
              <div className="value">
                {formatMoney(sales, lang, displayCurrency)}
              </div>
            </div>
            <div className="kpi">
              <div className="label">{t("orders")}</div>
              <div className="value">{Number(metrics.orders || 0).toLocaleString()}</div>
            </div>
            <div className="kpi">
              <div className="label">{t("customers")}</div>
              <div className="value">
                {Number(metrics.customers || 0).toLocaleString()}
              </div>
            </div>
            <div className="kpi">
              <div className="label">{t("aov")}</div>
              <div className="value">{formatMoney(aov, lang, displayCurrency)}</div>
            </div>
          </div>

          <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
            {t("returning")}: {(returning * 100).toFixed(1)}% —{" "}
            {lang === "ar"
              ? defs.returning_customer_ar || t("returning_help")
              : defs.returning_customer_en || t("returning_help")}
          </p>

          <div className="dash-grid">
            <section className="band dash-span-2" data-testid="store-trend-card">
              <div className="band-head">
                <h2 className="display" style={{ fontSize: "1.2rem" }}>
                  {lang === "ar" ? "اتجاه المصروف" : "Sales trend"}
                </h2>
                <div className="range-switch" role="group" aria-label={lang === "ar" ? "المدى" : "Range"}>
                  {(
                    [
                      ["3m", lang === "ar" ? "٣ شهور" : "3M"],
                      ["6m", lang === "ar" ? "٦ شهور" : "6M"],
                      ["12m", lang === "ar" ? "١٢ شهر" : "12M"],
                      ["all", lang === "ar" ? "الكل" : "All"],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      aria-pressed={range === id}
                      onClick={() => setRange(id)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <BarSeriesChart
                title={lang === "ar" ? "اتجاه المصروف الشهري" : "Monthly eligible spend"}
                subtitle={
                  lang === "ar"
                    ? `وحدة المصروف: ${currencyLabel} · التلميح يعرض الطلبات`
                    : `Spend unit: ${currencyLabel} · tooltip shows orders`
                }
                unit={isUpload ? currencyLabel : "GBP"}
                data={trendBars}
                emptyText={
                  lang === "ar" ? "مفيش اتجاه شهري متاح." : "No monthly trend available."
                }
                insufficientText={
                  lang === "ar"
                    ? "فترات مش كفاية لرسم اتجاه مفيد."
                    : "Not enough periods for a useful trend chart."
                }
                minBarsForTrend={2}
                secondaryUnit={lang === "ar" ? "طلبات" : "orders"}
              />
            </section>

            <section className="band" data-testid="store-products-card">
              <div className="band-head">
                <h2 className="display" style={{ fontSize: "1.15rem" }}>
                  {lang === "ar" ? "أداء المنتجات" : "Product performance"}
                </h2>
                <Link href="/products" style={{ fontSize: 13 }}>
                  {lang === "ar" ? "عرض الكل" : "View all"}
                </Link>
              </div>
              {productRows.length === 0 ? (
                <p className="muted">
                  {lang === "ar"
                    ? "مفيش ترتيب منتجات متاح للملف ده."
                    : "No product ranking available for this source."}
                </p>
              ) : (
                <ul className="product-rank-list">
                  {productRows.map((p) => (
                    <li key={p.key}>
                      <span>{p.name}</span>
                      <span className="muted">
                        {p.units.toLocaleString()} {lang === "ar" ? "وحدة" : "units"}
                        {" · "}
                        {formatMoney(p.spend, lang, displayCurrency)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="band" data-testid="store-evidence-insights">
              <h2 className="display" style={{ marginTop: 0, fontSize: "1.15rem" }}>
                {lang === "ar" ? "إيه اللي اتغيّر / إيه اللي يهم" : "What changed / what to consider"}
              </h2>
              {evidence.length > 0 ? (
                evidence.slice(0, 4).map((i) => (
                  <article key={i.id} className="insight-card">
                    <strong>{lang === "ar" ? i.title_ar : i.title_en}</strong>
                    <p className="muted" style={{ margin: 0, fontSize: 14 }}>
                      {lang === "ar" ? i.evidence_ar : i.evidence_en}
                    </p>
                    <p className="muted" style={{ margin: "6px 0 0", fontSize: 12 }}>
                      {lang === "ar" ? i.caveat_ar : i.caveat_en}
                    </p>
                  </article>
                ))
              ) : (
                <p className="muted">
                  {lang === "ar"
                    ? String(data.caveat_ar || data.caveat_en || "")
                    : String(data.caveat_en || "")}
                </p>
              )}
              {(meaning.en || meaning.ar) && (
                <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
                  {lang === "ar" ? meaning.ar : meaning.en}
                </p>
              )}
            </section>
          </div>

          {steps.length > 0 && (
            <section className="band" data-testid="store-suggested-steps">
              <h2 className="display" style={{ marginTop: 0, fontSize: "1.2rem" }}>
                {lang === "ar" ? "اقتراحات قرار (مؤقتة)" : "Decision suggestions (provisional)"}
              </h2>
              <p className="muted" style={{ fontSize: 13 }}>
                {t("provisional")}
              </p>
              <ol>
                {steps.map((s) => (
                  <li key={s.rank} style={{ marginBottom: 10 }}>
                    <strong>{lang === "ar" ? s.title_ar : s.title_en}</strong>
                    <div className="muted" style={{ fontSize: 13 }}>
                      {lang === "ar" ? s.evidence_ar : s.evidence_en}
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {lang === "ar" ? s.uncertainty_ar : s.uncertainty_en}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {isUpload && deepDives.length > 0 && (
            <section className="band" data-testid="store-optional-deep-dives">
              <h2 className="display" style={{ marginTop: 0, fontSize: "1.15rem" }}>
                {lang === "ar" ? "تحليل أعمق (اختياري)" : "Optional deeper analysis"}
              </h2>
              <ul style={{ margin: 0, paddingInlineStart: "1.2rem" }}>
                {deepDives.map((d) => (
                  <li key={d.id} style={{ marginBottom: 8 }}>
                    <strong>{lang === "ar" ? d.title_ar : d.title_en}</strong>
                    <div className="muted" style={{ fontSize: 13 }}>
                      {lang === "ar" ? d.why_ar : d.why_en}
                    </div>
                    {d.href && (
                      <Link href={d.href}>
                        {lang === "ar" ? "افتح لو حابب" : "Open if useful"}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {isUpload && (
            <section className="band">
              <h2 className="display" style={{ marginTop: 0, fontSize: "1.2rem" }}>
                {forecast.available
                  ? lang === "ar"
                    ? "تقدير ٩٠ يوم (خاص بالرفع)"
                    : "90-day estimate (this upload)"
                  : t("forecast_unavailable")}
              </h2>
              {forecast.available ? (
                <>
                  <p className="muted">
                    {lang === "ar"
                      ? String(forecast.label_ar || "")
                      : String(forecast.label_en || "")}
                  </p>
                  <p className="muted" style={{ fontSize: 12 }}>
                    {lang === "ar"
                      ? String(forecast.limitations_ar || "")
                      : String(forecast.limitations_en || "")}
                  </p>
                </>
              ) : (
                <p className="muted">
                  {lang === "ar"
                    ? String(forecast.reason_ar || "")
                    : String(forecast.reason_en || "")}
                </p>
              )}
            </section>
          )}

          <p className="muted" style={{ marginTop: 16 }}>
            <Link href="/groups">{t("nav_groups")}</Link>
            {" · "}
            <Link href="/products">{t("nav_products")}</Link>
            {" · "}
            <Link href="/profile">{t("nav_profile")}</Link>
          </p>
        </>
      )}
    </main>
  );
}
