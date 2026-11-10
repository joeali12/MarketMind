"use client";

import { useLang } from "@/context/LangContext";

export function DemoBadge({ text }: { text?: string }) {
  const { t } = useLang();
  return <span className="badge">{text || t("demo_badge")}</span>;
}
