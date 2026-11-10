"use client";

import Link from "next/link";
import { useLang } from "@/context/LangContext";

export function SiteFooter() {
  const { t } = useLang();
  return (
    <footer className="footer">
      <div className="footer-inner">
        <p style={{ margin: 0 }}>{t("footer_note")}</p>
        <Link href="/project">{t("nav_project")}</Link>
      </div>
    </footer>
  );
}
