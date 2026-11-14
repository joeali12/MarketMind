"use client";

import Link from "next/link";
import { useLang } from "@/context/LangContext";

const COPY = {
  ar: {
    brand: "MarketMind",
    headline: "فاهم عملاء متجرك من ملف مبيعات واحد",
    support:
      "ارفع الـ CSV أو الإكسل، راجع التنظيف، واسأل المساعد بالعربي أو الإنجليزي — تحليل تجزئة وCLV للمتاجر الصغيرة.",
    cta: "يلا جرب",
    howTitle: "كيف تستخدمه",
    howLead: "ثلاث خطوات من الملف إلى لوحة التحليل.",
    steps: [
      {
        n: "١",
        title: "ارفع ملفك",
        body: "CSV أو Excel من نقطة البيع أو المتجر. نساعدك في اختيار الورقة والأعمدة إن لزم.",
      },
      {
        n: "٢",
        title: "راجع التنظيف",
        body: "اقتراحات واضحة لما يُصلح وما يبقى فجوة — بدون اختراع أرقام أو تواريخ.",
      },
      {
        n: "٣",
        title: "اكتشف واسأل",
        body: "لوحة المتجر والمنتجات والمجموعات، ومحادثة تفهم أوامرك على جلسة الرفع.",
      },
    ],
    whyTitle: "ليه المشروع مهم",
    whyLead:
      "متاجر مصر والمنطقة تملك بيانات يومية، لكن التحليل غالباً معقد أو مخصص لأسواق أخرى.",
    whyBody:
      "MarketMind مشروع تخرج يقرّب ذكاء التجزئة: RFM وتجزئة K-Means وتقدير إنفاق مؤهل خلال ٩٠ يوماً — بواجهة ثنائية اللغة تبدأ من ملفك أنت.",
    finalTitle: "جاهز تجرب على بياناتك؟",
    finalCta: "يلا جرب",
    foot: "مشروع تخرج · واجهة المنتج على Vercel · Streamlit للنسخة الأكاديمية فقط",
  },
  en: {
    brand: "MarketMind",
    headline: "Understand your store’s customers from one sales file",
    support:
      "Upload CSV or Excel, review cleaning, and chat in Arabic or English — segmentation and CLV built for SME retailers.",
    cta: "Let’s try",
    howTitle: "How to use it",
    howLead: "Three steps from file to insight.",
    steps: [
      {
        n: "1",
        title: "Upload your file",
        body: "CSV or Excel from POS or your store. We’ll help pick the sheet and columns when needed.",
      },
      {
        n: "2",
        title: "Review cleaning",
        body: "Clear proposals for what to fix and what stays a gap — no invented IDs, dates, or quantities.",
      },
      {
        n: "3",
        title: "Explore and ask",
        body: "Store, products, and groups dashboards, plus an assistant that runs on your upload session.",
      },
    ],
    whyTitle: "Why it matters",
    whyLead:
      "Retailers across Egypt and the region sit on daily sales data, but analytics are often heavy or built for other markets.",
    whyBody:
      "MarketMind is a graduation product that brings retail intelligence closer: RFM, K-Means segments, and eligible spend in the next 90 days — bilingual UI that starts from your file.",
    finalTitle: "Ready to try it on your data?",
    finalCta: "Let’s try",
    foot: "Graduation project · product UI on Vercel · Streamlit is academic PDF only",
  },
} as const;

function LandingVisual() {
  return (
    <svg
      className="landing-visual"
      viewBox="0 0 640 360"
      role="img"
      aria-hidden
    >
      <defs>
        <linearGradient id="lv-panel" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#e8f2ee" stopOpacity="0.9" />
        </linearGradient>
        <linearGradient id="lv-bar" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#005338" />
          <stop offset="100%" stopColor="#1a9a6c" />
        </linearGradient>
      </defs>
      <rect x="24" y="28" width="592" height="304" rx="28" fill="url(#lv-panel)" />
      <rect x="56" y="56" width="140" height="18" rx="9" fill="#0b1c30" opacity="0.12" />
      <rect x="56" y="88" width="88" height="10" rx="5" fill="#005338" opacity="0.35" />
      <g className="landing-visual-bars">
        <rect x="72" y="210" width="36" height="72" rx="8" fill="url(#lv-bar)" opacity="0.55" />
        <rect x="124" y="168" width="36" height="114" rx="8" fill="url(#lv-bar)" opacity="0.75" />
        <rect x="176" y="140" width="36" height="142" rx="8" fill="url(#lv-bar)" />
        <rect x="228" y="186" width="36" height="96" rx="8" fill="url(#lv-bar)" opacity="0.65" />
      </g>
      <path
        className="landing-visual-line"
        d="M320 250c28-42 52-68 78-78s52 6 78 28 48 38 72 22"
        fill="none"
        stroke="#c59a3b"
        strokeWidth="3.5"
        strokeLinecap="round"
      />
      <circle cx="476" cy="222" r="7" fill="#c59a3b" />
      <rect x="320" y="56" width="244" height="96" rx="16" fill="#0b1c30" opacity="0.06" />
      <rect x="340" y="76" width="120" height="12" rx="6" fill="#0b1c30" opacity="0.18" />
      <rect x="340" y="100" width="180" height="10" rx="5" fill="#005338" opacity="0.28" />
      <rect x="340" y="122" width="96" height="10" rx="5" fill="#c59a3b" opacity="0.45" />
      <g className="landing-visual-nodes">
        <circle cx="560" cy="88" r="10" fill="#005338" />
        <circle cx="528" cy="120" r="7" fill="#1a9a6c" />
        <path
          d="M528 120c10-18 22-28 32-32"
          stroke="#005338"
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
          <h2 id="how-title" className="landing-section-title">
            {t.howTitle}
          </h2>
          <p className="landing-section-lead">{t.howLead}</p>
          <ol className="landing-steps">
            {t.steps.map((step) => (
              <li key={step.n} className="landing-step">
                <span className="landing-step-n" aria-hidden>
                  {step.n}
                </span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
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
