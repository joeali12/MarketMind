"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DemoBadge } from "@/components/DemoBadge";
import { useLang } from "@/context/LangContext";

export default function ProjectPage() {
  const { t, lang } = useLang();
  const [data, setData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.project().then(setData).catch(() => setData(null));
  }, []);

  const model = (data?.model || {}) as Record<string, unknown>;
  const defs = (data?.definitions || {}) as Record<string, string>;
  const recon = (data?.cleaning_reconciliation || []) as Record<string, unknown>[];
  const metrics = (model.test_metrics || {}) as Record<string, number>;

  return (
    <main className="main">
      <DemoBadge />
      <h1 className="page-title display">{t("project_title")}</h1>
      <p className="page-sub">
        {lang === "ar"
          ? "تعريفات البيانات، سجل التنظيف، وتقييم الموديل على العينة التجريبية فقط."
          : "Data definitions, cleaning history, and model evaluation on the demo sample only."}
      </p>

      {data && (
        <>
          <section className="band">
            <h2 className="display" style={{ marginTop: 0, fontSize: "1.25rem" }}>
              {lang === "ar" ? "تعريفات" : "Definitions"}
            </h2>
            <ul className="muted">
              <li>{lang === "ar" ? defs.currency_ar || defs.currency_en : defs.currency_en}</li>
              <li>
                {lang === "ar"
                  ? defs.eligible_spend_ar || defs.eligible_spend_en
                  : defs.eligible_spend_en}
              </li>
              <li>{lang === "ar" ? defs.forecast_ar || defs.forecast_en : defs.forecast_en}</li>
            </ul>
          </section>

          <section className="band">
            <h2 className="display" style={{ marginTop: 0, fontSize: "1.25rem" }}>
              {lang === "ar" ? "جودة التوقع (تجريبي)" : "Prediction quality (demo)"}
            </h2>
            <p className="muted">
              {String(model.selected_regression_model || "")} · cutoff{" "}
              {String(model.test_cutoff || "")}
            </p>
            <div className="grid-3">
              <div className="kpi">
                <div className="label">MAE</div>
                <div className="value">{Number(metrics.mae || 0).toFixed(1)}</div>
              </div>
              <div className="kpi">
                <div className="label">RMSE</div>
                <div className="value">{Number(metrics.rmse || 0).toFixed(1)}</div>
              </div>
              <div className="kpi">
                <div className="label">R²</div>
                <div className="value">{Number(metrics.r2 || 0).toFixed(3)}</div>
              </div>
            </div>
            <p className="muted">
              actions_approved: {String(model.actions_approved)} ·{" "}
              {lang === "ar"
                ? "التوقعات مش متحقق منها لمتاجر مرفوعة"
                : "Forecasts are not validated for uploaded stores"}
            </p>
          </section>

          <section className="band">
            <h2 className="display" style={{ marginTop: 0, fontSize: "1.25rem" }}>
              {lang === "ar" ? "سجل تنظيف العرض" : "Demo cleaning history"}
            </h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t("th_step")}</th>
                    <th>{t("th_reason")}</th>
                    <th>{t("th_before")}</th>
                    <th>{t("th_after")}</th>
                    <th>{t("th_removed")}</th>
                  </tr>
                </thead>
                <tbody>
                  {recon.map((r, i) => (
                    <tr key={i}>
                      <td>{String(r.step)}</td>
                      <td>{String(r.reason)}</td>
                      <td>{String(r.rows_before)}</td>
                      <td>{String(r.rows_after)}</td>
                      <td>{String(r.rows_removed)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
