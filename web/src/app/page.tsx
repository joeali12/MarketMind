"use client";

import Link from "next/link";
import { useLang } from "@/context/LangContext";

const COPY = {
  ar: {
    brand: "MarketMind",
    headline: "فاهم عملاء متجرك من ملف مبيعات واحد",
    support:
      "ارفع CSV أو Excel، راجع التنظيف، واسأل المساعد بالعربي أو الإنجليزي — تجزئة وCLV للمتاجر الصغيرة.",
    cta: "يلا جرب",
    howTitle: "كيف تستخدمه",
    howLead: "ثلاث خطوات من الملف إلى لوحة التحليل.",
    steps: [
      {
        n: "01",
        title: "ارفع ملفك",
        body: "CSV أو Excel من نقطة البيع. نساعدك في الورقة والأعمدة عند الحاجة.",
      },
      {
        n: "02",
        title: "راجع التنظيف",
        body: "اقتراحات واضحة لما يُصلح وما يبقى فجوة — بلا اختراع أرقام أو تواريخ.",
      },
      {
        n: "03",
        title: "اكتشف واسأل",
        body: "لوحات المتجر والمنتجات والمجموعات، ومساعد يعمل على جلسة الرفع.",
      },
    ],
    whyTitle: "ليه المشروع مهم",
    whyLead:
      "متاجر مصر والمنطقة تملك بيانات يومية، لكن التحليل غالباً معقد أو مبني لأسواق أخرى.",
    whyBody:
      "MarketMind مشروع تخرج يقرّب ذكاء التجزئة: RFM، تجزئة K-Means، وتقدير إنفاق مؤهل خلال ٩٠ يوماً — بواجهة ثنائية اللغة تبدأ من ملفك.",
    finalTitle: "جاهز تجرب على بياناتك؟",
    finalCta: "يلا جرب",
    foot: "مشروع تخرج · المنتج على Vercel · Streamlit للنسخة الأكاديمية فقط",
  },
  en: {
    brand: "MarketMind",
    headline: "Understand your store’s customers from one sales file",
    support:
      "Upload CSV or Excel, review cleaning, and chat in Arabic or English — segmentation and CLV for SME retailers.",
    cta: "يلا جرب",
    howTitle: "How to use it",
    howLead: "Three steps from file to insight.",
    steps: [
      {
        n: "01",
        title: "Upload your file",
        body: "CSV or Excel from POS or your store. We’ll help pick the sheet and columns when needed.",
      },
      {
        n: "02",
        title: "Review cleaning",
        body: "Clear proposals for what to fix and what stays a gap — no invented IDs, dates, or quantities.",
      },
      {
        n: "03",
        title: "Explore and ask",
        body: "Store, products, and groups dashboards, plus an assistant scoped to your upload session.",
      },
    ],
    whyTitle: "Why it matters",
    whyLead:
      "Retailers across Egypt and the region sit on daily sales data, but analytics are often heavy or built for other markets.",
    whyBody:
      "MarketMind is a graduation product that brings retail intelligence closer: RFM, K-Means segments, and eligible spend in the next 90 days — bilingual UI that starts from your file.",
    finalTitle: "Ready to try it on your data?",
    finalCta: "يلا جرب",
    foot: "Graduation project · product UI on Vercel · Streamlit is academic PDF only",
  },
} as const;

function LandingVisual() {
  return (
    <svg
      className="landing-visual"
      viewBox="0 0 640 360"
      width={640}
      height={360}
      role="img"
      aria-hidden
    >
      <defs>
        <linearGradient id="lv-panel" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#eff4ff" />
        </linearGradient>
        <linearGradient id="lv-bar" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#3525cd" />
          <stop offset="100%" stopColor="#6b5ef0" />
        </linearGradient>
      </defs>
      <rect x="24" y="28" width="592" height="304" rx="20" fill="url(#lv-panel)" stroke="#c7c4d8" strokeWidth="1" />
      <rect x="56" y="56" width="152" height="16" rx="4" fill="#0b1c30" opacity="0.12" />
      <rect x="56" y="84" width="96" height="8" rx="4" fill="#3525cd" opacity="0.35" />
      <g className="landing-visual-bars">
        <rect x="72" y="210" width="40" height="72" rx="6" fill="url(#lv-bar)" opacity="0.45" />
        <rect x="128" y="168" width="40" height="114" rx="6" fill="url(#lv-bar)" opacity="0.7" />
        <rect x="184" y="140" width="40" height="142" rx="6" fill="url(#lv-bar)" />
        <rect x="240" y="186" width="40" height="96" rx="6" fill="url(#lv-bar)" opacity="0.55" />
      </g>
      <path
        className="landing-visual-line"
        d="M320 250c28-42 52-68 78-78s52 6 78 28 48 38 72 22"
        fill="none"
        stroke="#4f46e5"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx="476" cy="222" r="6" fill="#3525cd" />
      <rect x="320" y="56" width="244" height="100" rx="12" fill="#e2dfff" />
      <rect x="340" y="78" width="128" height="10" rx="3" fill="#0b1c30" opacity="0.2" />
      <rect x="340" y="100" width="184" height="8" rx="3" fill="#3525cd" opacity="0.35" />
      <rect x="340" y="120" width="104" height="8" rx="3" fill="#4f46e5" opacity="0.45" />
      <g className="landing-visual-nodes">
        <circle cx="560" cy="88" r="9" fill="#3525cd" />
        <circle cx="528" cy="118" r="6" fill="#6b5ef0" />
        <path
          d="M528 118c10-16 22-26 32-30"
          stroke="#3525cd"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
        />
      </g>
    </svg>
  );
}

/** Product landing — brand-first entry before upload. */
export default function HomePage() {
  const { lang } = useLang();
  const t = COPY[lang === "ar" ? "ar" : "en"];

  return (
    <main className="landing">
      <section className="landing-hero" aria-labelledby="landing-brand">
        <div className="landing-hero-glow" aria-hidden />
        <div className="landing-hero-inner">
          <p id="landing-brand" className="landing-brand">
            {t.brand}
          </p>
          <h1 className="landing-headline">{t.headline}</h1>
          <p className="landing-support">{t.support}</p>
          <div className="landing-cta-row">
            <Link href="/upload" className="btn btn-cta landing-cta">
              {t.cta}
            </Link>
          </div>
          <div className="landing-hero-visual">
            <LandingVisual />
          </div>
        </div>
      </section>

      <section className="landing-section" aria-labelledby="how-title">
        <div className="landing-section-inner">
          <header className="landing-section-head">
            <h2 id="how-title" className="landing-section-title">
              {t.howTitle}
            </h2>
            <p className="landing-section-lead">{t.howLead}</p>
          </header>
          <ol className="landing-steps">
            {t.steps.map((step) => (
              <li key={step.n} className="landing-step">
                <span className="landing-step-n" aria-hidden>
                  {step.n}
                </span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="landing-section landing-why" aria-labelledby="why-title">
        <div className="landing-section-inner landing-why-inner">
          <h2 id="why-title" className="landing-section-title">
            {t.whyTitle}
          </h2>
          <p className="landing-section-lead">{t.whyLead}</p>
          <p className="landing-why-body">{t.whyBody}</p>
        </div>
      </section>

      <section className="landing-final" aria-labelledby="final-title">
        <h2 id="final-title">{t.finalTitle}</h2>
        <Link href="/upload" className="btn btn-cta landing-cta">
          {t.finalCta}
        </Link>
      </section>

      <p className="landing-foot">{t.foot}</p>
    </main>
  );
}
