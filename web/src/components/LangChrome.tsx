"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandLogo } from "@/components/BrandLogo";
import { useLang } from "@/context/LangContext";
import { useDataSource } from "@/context/DataSourceContext";

/** Single site chrome: brand, context nav, language. */
export function LangChrome() {
  const { t, lang, setLang } = useLang();
  const { mode, sessionId, currencyCode } = useDataSource();
  const pathname = usePathname();
  const uploadActive = mode === "upload" && Boolean(sessionId);

  const links = uploadActive
    ? [
        { href: "/upload", label: lang === "ar" ? "الرفع" : "Upload" },
        { href: "/store", label: lang === "ar" ? "لوحة التحليل" : "Dashboard" },
        { href: "/products", label: lang === "ar" ? "المنتجات" : "Products" },
        { href: "/groups", label: lang === "ar" ? "المجموعات" : "Groups" },
      ]
    : [{ href: "/upload", label: lang === "ar" ? "ارفع ملف" : "Upload" }];

  return (
    <header className="lang-chrome">
      <div className="lang-chrome-inner">
        <BrandLogo compact={uploadActive} />
        <nav
          className="lang-chrome-nav"
          aria-label={lang === "ar" ? "تنقل" : "Navigation"}
        >
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={pathname === l.href || pathname.startsWith(l.href + "/") ? "is-active" : undefined}
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="lang-chrome-end">
          {uploadActive && (
            <span className="source-pill muted">
              <span
                className="dot"
                style={{
                  display: "inline-block",
                  width: 8,
                  height: 8,
                  borderRadius: 999,
                  background: "var(--emerald)",
                  marginInlineEnd: 6,
                }}
                aria-hidden
              />
              {lang === "ar" ? "ملفك" : "Your file"}
              {currencyCode && currencyCode !== "UNSPECIFIED"
                ? ` · ${currencyCode}`
                : ""}
            </span>
          )}
          <div className="lang-switch" role="group" aria-label="Language">
            <button
              type="button"
              aria-pressed={lang === "en"}
              onClick={() => setLang("en")}
            >
              EN
            </button>
            <button
              type="button"
              aria-pressed={lang === "ar"}
              onClick={() => setLang("ar")}
            >
              عربي
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
