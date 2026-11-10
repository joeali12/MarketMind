"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, formatMoney } from "@/lib/api";
import { DemoBadge } from "@/components/DemoBadge";
import { SourceBadge } from "@/components/SourceSelector";
import { BarSeriesChart } from "@/components/charts/BarSeriesChart";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

type Seg = {
  cluster_id: number;
  label_en: string;
  n_customers: number;
  share: number;
  spend_share?: number;
  monetary_sum?: number;
  recency_mean: number;
  frequency_mean: number;
  monetary_mean_gbp?: number;
  monetary_mean?: number;
  monetary_median_gbp?: number;
  monetary_median?: number;
};

const AR_LABELS: Record<string, string> = {
  "Recent high-spend": "صرف عالي وقريب",
  "Lapsed low-spend": "سكت ومصروفه قليل",
  "Recent higher-spend (upload)": "صرف أعلى وقريب (رفع)",
  "Quieter lower-spend (upload)": "أهدأ ومصروف أقل (رفع)",
  "More frequent (upload)": "أكتر تكرار (رفع)",
  "Other (upload)": "أخرى (رفع)",
};

export default function GroupsPage() {
  const { t, lang } = useLang();
  const { ready, mode, sessionId, currencyCode } = useDataSource();
  const [segments, setSegments] = useState<Seg[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [isUpload, setIsUpload] = useState(false);

  useEffect(() => {
    if (!ready) return;
    setErr(null);
    const load =
      mode === "upload" && sessionId
        ? api.uploadSegments(sessionId)
        : api.segments();
    load
      .then((d) => {
        setSegments((d.segments as Seg[]) || []);
        setIsUpload(d.demo === false);
      })
      .catch((e) => setErr(String(e.message || e)));
  }, [ready, mode, sessionId]);

  const moneyCode = isUpload ? currencyCode : "GBP";
  const unit =
    moneyCode && moneyCode !== "UNSPECIFIED"
      ? moneyCode
      : lang === "ar"
        ? "عملة المصدر"
        : "source currency";
  const groupBars = segments.map((s) => ({
    key: String(s.cluster_id),
    label:
      lang === "ar"
        ? AR_LABELS[s.label_en] || s.label_en.replace(" (upload)", "")
        : s.label_en.replace(" (upload)", ""),
    value: Number(
      s.monetary_sum ??
        Number(s.monetary_mean ?? s.monetary_mean_gbp ?? 0) * s.n_customers
    ),
    secondary: s.n_customers,
  }));

  return (
    <main className="main">
      {isUpload ? <SourceBadge /> : <DemoBadge />}
      <h1 className="page-title display">{t("card_groups")}</h1>
      <p className="page-sub">{t("card_groups_body")}</p>
      {err && <p className="muted">{err}</p>}
      <section className="band">
        <BarSeriesChart
          title={lang === "ar" ? "مقارنة مصروف المجموعات" : "Group spend comparison"}
          subtitle={
            lang === "ar"
              ? "مجموع المصروف المؤهل للمجموعة · العدد في التلميح"
              : "Group eligible spend total · customer count in tooltip"
          }
          unit={unit}
          data={groupBars}
          emptyText={
            lang === "ar" ? "مفيش مجموعات للعرض." : "No groups to chart yet."
          }
          secondaryUnit={lang === "ar" ? "زبون" : "customers"}
        />
      </section>
      <div className="grid-2">
        {segments.map((s) => {
          const mean = Number(s.monetary_mean ?? s.monetary_mean_gbp ?? 0);
          return (
            <article key={s.cluster_id} className="card">
              <div className="icon" aria-hidden>
                {s.cluster_id}
              </div>
              <h3>
                {lang === "ar" ? AR_LABELS[s.label_en] || s.label_en : s.label_en}
              </h3>
              <p>
                {s.n_customers.toLocaleString()}{" "}
                {lang === "ar" ? "زبون" : "customers"} · {(s.share * 100).toFixed(0)}%
              </p>
              <ul className="muted" style={{ paddingInlineStart: "1.1rem" }}>
                <li>
                  {lang === "ar" ? "متوسط الأيام من آخر شراء" : "Avg days since purchase"}:{" "}
                  {s.recency_mean.toFixed(0)}
                </li>
                <li>
                  {lang === "ar" ? "متوسط تكرار الشراء" : "Avg purchase frequency"}:{" "}
                  {s.frequency_mean.toFixed(1)}
                </li>
                <li>
                  {lang === "ar" ? "متوسط المصروف السابق" : "Avg past spend"}:{" "}
                  {formatMoney(mean, lang, moneyCode)}
                </li>
              </ul>
              <Link className="btn btn-primary btn-sm" href={`/groups/${s.cluster_id}`}>
                {t("open_group")}
              </Link>
            </article>
          );
        })}
      </div>
    </main>
  );
}
