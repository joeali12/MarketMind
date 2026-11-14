"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DemoBadge } from "@/components/DemoBadge";
import { SourceBadge } from "@/components/SourceSelector";
import { BarSeriesChart } from "@/components/charts/BarSeriesChart";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

type Prod = {
  stock_code: string;
  description: string;
  spend_gbp?: number;
  spend?: number;
  quantity: number;
  orders: number;
};

type Trend = { month: string; spend_gbp?: number; spend?: number };
type Cat = { category: string | null; spend: number; quantity: number; orders: number };

export default function ProductsPage() {
  const { t, lang } = useLang();
  const { ready, mode, sessionId, currencyCode } = useDataSource();
  const [products, setProducts] = useState<Prod[]>([]);
  const [trend, setTrend] = useState<Trend[]>([]);
  const [categories, setCategories] = useState<Cat[]>([]);
  const [categoryAvailable, setCategoryAvailable] = useState(false);
  const [reason, setReason] = useState("");
  const [source, setSource] = useState<"demo" | "upload">("demo");
  const unit =
    source === "demo"
      ? "GBP"
      : currencyCode && currencyCode !== "UNSPECIFIED"
        ? currencyCode
        : lang === "ar"
          ? "عملة المصدر"
          : "source currency";

  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!ready) return;
      setLoadError(null);
      if (mode === "upload" && sessionId) {
        try {
          const d = await api.uploadProducts(sessionId);
          if (cancelled) return;
          setSource("upload");
          setProducts((d.products as Prod[]) || []);
          setTrend((d.monthly_trend as Trend[]) || []);
          setCategories((d.categories as Cat[]) || []);
          setCategoryAvailable(Boolean(d.category_available));
          setReason(
            lang === "ar"
              ? String(d.category_omitted_reason_ar || "")
              : String(d.category_omitted_reason_en || "")
          );
        } catch (e) {
          if (cancelled) return;
          // Keep upload mode visible — never silently show demo badge/data.
          setSource("upload");
          setProducts([]);
          setTrend([]);
          setCategories([]);
          setCategoryAvailable(false);
          setReason("");
          setLoadError(e instanceof Error ? e.message : String(e));
        }
        return;
      }

      const d = await api.products();
      if (cancelled) return;
      setSource("demo");
      setProducts((d.products as Prod[]) || []);
      setTrend((d.monthly_trend as Trend[]) || []);
      setCategories([]);
      setCategoryAvailable(false);
      setReason(
        lang === "ar"
          ? String(d.category_omitted_reason_ar || "")
          : String(d.category_omitted_reason_en || "")
      );
    }
    load().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [lang, ready, mode, sessionId]);

  return (
    <main className="main">
      {source === "upload" ? <SourceBadge /> : <DemoBadge />}
      <h1 className="page-title display">{t("card_products")}</h1>
      <p className="page-sub">{t("card_products_body")}</p>
      {loadError && (
        <p className="muted" role="alert" style={{ marginTop: 8 }}>
          {lang === "ar"
            ? `تعذر تحميل منتجات الملف المرفوع: ${loadError}`
            : `Could not load products for the uploaded file: ${loadError}`}
        </p>
      )}

      <section className="band-muted band">
        <h2 className="section-title display">
          {lang === "ar" ? "تصنيف المنتجات" : "Product categories"}
        </h2>
        {!categoryAvailable && (
          <p className="muted" style={{ marginBottom: 0 }}>
            {reason || t("no_category")}
          </p>
        )}
        {categoryAvailable && (
          <>
            <BarSeriesChart
              title={lang === "ar" ? "مصروف التصنيف" : "Category spend"}
              subtitle={
                lang === "ar"
                  ? "من عمود التصنيف المربوط · تاريخي فقط"
                  : "From mapped category column · historical only"
              }
              unit={unit}
              data={categories.map((c) => ({
                key: String(c.category),
                label: String(c.category ?? "—"),
                value: c.spend,
                secondary: c.orders,
              }))}
              emptyText={reason || t("no_category")}
              secondaryUnit={lang === "ar" ? "طلبات" : "orders"}
            />
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>{lang === "ar" ? "التصنيف" : "Category"}</th>
                    <th>{lang === "ar" ? "مصروف" : "Spend"}</th>
                    <th>{lang === "ar" ? "كمية" : "Qty"}</th>
                    <th>{lang === "ar" ? "طلبات" : "Orders"}</th>
                  </tr>
                </thead>
                <tbody>
                  {categories.map((c) => (
                    <tr key={String(c.category)}>
                      <td>{c.category ?? "—"}</td>
                      <td>{c.spend.toFixed(0)}</td>
                      <td>{c.quantity.toFixed(0)}</td>
                      <td>{c.orders}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="band">
        <BarSeriesChart
          title={
            lang === "ar" ? "اتجاه المبيعات الشهري (تاريخي)" : "Monthly sales trend (historical)"
          }
          unit={unit}
          data={trend.map((m) => ({
            key: m.month,
            label: m.month,
            value: Number(m.spend_gbp ?? m.spend ?? 0),
          }))}
          emptyText={
            lang === "ar" ? "مفيش اتجاه شهري متاح." : "No monthly trend available."
          }
          minBarsForTrend={2}
          insufficientText={
            lang === "ar"
              ? "فترات مش كفاية لرسم اتجاه."
              : "Not enough periods for a trend chart."
          }
        />
      </section>

      <div className="table-wrap" style={{ marginTop: 24 }}>
        <table>
          <thead>
            <tr>
              <th>{lang === "ar" ? "الكود" : "Code"}</th>
              <th>{lang === "ar" ? "الوصف" : "Description"}</th>
              <th>{source === "demo" ? "£" : lang === "ar" ? "مصروف" : "Spend"}</th>
              <th>{lang === "ar" ? "الكمية" : "Qty"}</th>
              <th>{lang === "ar" ? "الطلبات" : "Orders"}</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.stock_code + (p.description || "")}>
                <td>{p.stock_code}</td>
                <td>{p.description || "—"}</td>
                <td>{Number(p.spend_gbp ?? p.spend ?? 0).toFixed(0)}</td>
                <td>{p.quantity.toFixed(0)}</td>
                <td>{p.orders}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
