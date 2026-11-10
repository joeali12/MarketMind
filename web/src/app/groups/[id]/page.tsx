"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, formatMoney } from "@/lib/api";
import { DemoBadge } from "@/components/DemoBadge";
import { SourceBadge } from "@/components/SourceSelector";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

type Cust = {
  customer_id: number;
  recency: number;
  frequency: number;
  monetary_gbp?: number;
  monetary?: number;
  segment_label: string;
};

export default function GroupCustomersPage() {
  const params = useParams();
  const id = Number(params.id);
  const { t, lang } = useLang();
  const { ready, mode, sessionId, currencyCode } = useDataSource();
  const [rows, setRows] = useState<Cust[]>([]);
  const [total, setTotal] = useState(0);
  const [isUpload, setIsUpload] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || !Number.isFinite(id)) return;
    setRows([]);
    setTotal(0);
    setError(null);
    const load =
      mode === "upload" && sessionId
        ? api.uploadSegmentCustomers(sessionId, id)
        : api.segmentCustomers(id);
    load.then((d) => {
      setRows((d.customers as Cust[]) || []);
      setTotal(Number(d.total || 0));
      setIsUpload(d.demo === false);
    }).catch((e) => setError(String(e.message || e)));
  }, [ready, id, mode, sessionId]);

  const moneyCode = isUpload ? currencyCode : "GBP";

  return (
    <main className="main">
      {isUpload ? <SourceBadge /> : <DemoBadge />}
      <p>
        <Link href="/groups">{t("nav_groups")}</Link>
      </p>
      <h1 className="page-title display">
        {lang === "ar" ? `زبائن المجموعة ${id}` : `Group ${id} customers`}
      </h1>
      <p className="page-sub">
        {total}{" "}
        {isUpload
          ? lang === "ar"
            ? "زبون من ملفك المرفوع"
            : "customers from your upload"
          : lang === "ar"
            ? "زبون في العينة التجريبية"
            : "customers in demo sample"}
      </p>
      {error && <p className="muted">{error}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{lang === "ar" ? "الحداثة" : "Recency"}</th>
              <th>{lang === "ar" ? "التكرار" : "Frequency"}</th>
              <th>{lang === "ar" ? "المصروف" : "Monetary"}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.customer_id}>
                <td>{r.customer_id}</td>
                <td>{r.recency}</td>
                <td>{r.frequency}</td>
                <td>
                  {formatMoney(Number(r.monetary ?? r.monetary_gbp ?? 0), lang, moneyCode)}
                </td>
                <td>
                  <Link href={`/profile?id=${r.customer_id}`}>{t("nav_profile")}</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
