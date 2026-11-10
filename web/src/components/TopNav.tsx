"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { NAV } from "@/lib/i18n";
import { useLang } from "@/context/LangContext";

export function TopNav() {
  const { t, lang, setLang } = useLang();
  const pathname = usePathname();
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`site-header${stuck ? " is-stuck" : ""}`}>
      <div className="nav-inner">
        <Link href="/" className="brand" aria-label="MarketMind">
          <span className="brand-mark" aria-hidden>
            M
          </span>
          <span>{t("brand")}</span>
        </Link>
        <nav className="nav-links" aria-label="Main">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
            >
              {t(item.key)}
            </Link>
          ))}
          <Link
            href="/project"
            aria-current={pathname === "/project" ? "page" : undefined}
          >
            {t("nav_project")}
          </Link>
        </nav>
        <div className="nav-actions">
          <div className="lang-switch" role="group" aria-label="Language">
            <button
              type="button"
              aria-pressed={lang === "ar"}
              onClick={() => setLang("ar")}
            >
              {t("lang_ar")}
            </button>
            <button
              type="button"
              aria-pressed={lang === "en"}
              onClick={() => setLang("en")}
            >
              {t("lang_en")}
            </button>
          </div>
          <Link href="/store" className="btn btn-primary btn-sm">
            {t("cta_explore")}
          </Link>
        </div>
      </div>
    </header>
  );
}

export function MobileNav() {
  const { t } = useLang();
  const pathname = usePathname();
  return (
    <nav className="mobile-nav" aria-label="Mobile">
      {NAV.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="btn btn-ghost btn-sm"
          aria-current={pathname === item.href ? "page" : undefined}
        >
          {t(item.key)}
        </Link>
      ))}
    </nav>
  );
}
