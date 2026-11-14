"use client";

import Link from "next/link";
import { useLang } from "@/context/LangContext";

type Props = {
  href?: string;
  compact?: boolean;
};

/** MarketMind wordmark + chart-mind mark. */
export function BrandLogo({ href = "/", compact = false }: Props) {
  const { t } = useLang();
  return (
    <Link href={href} className={`brand${compact ? " brand-compact" : ""}`} aria-label={t("brand")}>
      <span className="brand-mark" aria-hidden>
        <svg viewBox="0 0 40 40" width="28" height="28" fill="none">
          <rect width="40" height="40" rx="12" className="brand-mark-bg" />
          <path
            className="brand-mark-bars"
            d="M10 28V18.5h3.2V28H10Zm8.4 0V12h3.2v16h-3.2Zm8.4 0V20.5H30V28h-3.2Z"
            fill="currentColor"
          />
          <circle className="brand-mark-node" cx="28.4" cy="13.2" r="2.4" fill="currentColor" />
          <path
            className="brand-mark-arc"
            d="M20.2 14.5c2.2-2.6 5.4-3.6 8.2-3"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            fill="none"
          />
        </svg>
      </span>
      <span className="brand-word">
        <span className="brand-name">{t("brand")}</span>
        {!compact && <span className="brand-tag">Retail Intelligence</span>}
      </span>
    </Link>
  );
}
