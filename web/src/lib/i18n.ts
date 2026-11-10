export type Lang = "ar" | "en";

const strings = {
  brand: { en: "MarketMind", ar: "MarketMind" },
  nav_home: { en: "Home", ar: "البداية" },
  nav_upload: { en: "Upload", ar: "رفع ملف" },
  nav_store: { en: "Store", ar: "المتجر" },
  nav_groups: { en: "Groups", ar: "المجموعات" },
  nav_profile: { en: "Profile", ar: "ملف زبون" },
  nav_products: { en: "Products", ar: "المنتجات" },
  nav_project: { en: "Project", ar: "تفاصيل المشروع" },
  lang_en: { en: "English", ar: "English" },
  lang_ar: { en: "العربية", ar: "العربية" },
  demo_badge: {
    en: "Sample UK retail dataset (GBP) — not your live shop.",
    ar: "بيانات تجريبية من متجر بريطاني تاريخي (جنيه إسترليني) — مش متجرك الحقيقي.",
  },
  hero_title: {
    en: "Know your customers with calm clarity",
    ar: "اعرف زبائنك بهدوء ووضوح",
  },
  hero_sub: {
    en: "See who buys, how often they return, what they purchase, and practical next steps — from a demo or your own file.",
    ar: "شوف مين بيشتري، قد إيه بيرجع، إيه بيشتري، وخطوات عملية — من العرض أو من ملفك.",
  },
  cta_explore: { en: "Explore analytics", ar: "استكشف التحليلات" },
  cta_upload: { en: "Upload a file", ar: "ارفع ملف" },
  understand_file: { en: "Understand this file", ar: "افهم الملف ده" },
  ask_assistant: { en: "Ask about this file", ar: "اسأل عن الملف ده" },
  assistant_placeholder: {
    en: "e.g. How many customers? What needs fixing?",
    ar: "مثال: كام زبون؟ إيه محتاج يتصلح؟",
  },
  send: { en: "Send", ar: "ابعت" },
  next_analytics: {
    en: "Explore customer analytics",
    ar: "استكشف تحليلات الزباين",
  },
  returning_help: {
    en: "Returning customer: more than one distinct order in this file.",
    ar: "الزبون الراجع: عنده أكتر من طلب مميز في الملف ده.",
  },
  what_this_means: { en: "What this may mean", ar: "ممكن يعني إيه" },
  suggested_steps: { en: "Suggested next steps", ar: "خطوات مقترحة" },
  provisional: {
    en: "Provisional heuristic — not approved policy",
    ar: "اقتراح مؤقت — مش سياسة معتمدة",
  },
  preview_title: { en: "What you can do", ar: "تقدر تعمل إيه" },
  card_store: {
    en: "Store overview",
    ar: "نظرة على المتجر",
  },
  card_store_body: {
    en: "Sales, orders, customers, and factual insights from the demo sample.",
    ar: "مبيعات وطلبات وزباين وملحوظات واقعية من العينة التجريبية.",
  },
  card_groups: { en: "Customer groups", ar: "مجموعات الزباين" },
  card_groups_body: {
    en: "Who buys often, who spends more, who has gone quiet.",
    ar: "مين بيشتري كتير، مين بيصرف أكتر، ومين سكت.",
  },
  card_profile: { en: "Customer profile", ar: "ملف الزبون" },
  card_profile_body: {
    en: "Purchase history, group, and a clearly labeled demo spend estimate.",
    ar: "تاريخ الشراء والمجموعة وتقدير مصروف تجريبي موسم بوضوح.",
  },
  card_products: { en: "Products", ar: "المنتجات" },
  card_products_body: {
    en: "Historical product sales. Category charts only when your file has a category column.",
    ar: "مبيعات المنتجات التاريخية. رسوم التصنيف بس لو ملفك فيه عمود تصنيف.",
  },
  footer_note: {
    en: "Demo currency is GBP. No FX conversion. Forecasts are demo-trained only.",
    ar: "عملة العرض جنيه إسترليني. مفيش تحويل عملة. التوقعات متدربة على العينة التجريبية فقط.",
  },
  loading: { en: "Loading…", ar: "بيحمّل…" },
  error: { en: "Something went wrong", ar: "حصل خطأ" },
  sales: { en: "Eligible sales", ar: "مبيعات مؤهلة" },
  orders: { en: "Orders", ar: "الطلبات" },
  customers: { en: "Customers", ar: "الزباين" },
  aov: { en: "Avg order value", ar: "متوسط قيمة الطلب" },
  returning: { en: "Returning customers", ar: "زبائن راجعين" },
  open_group: { en: "View customers", ar: "عرض الزباين" },
  estimate_title: { en: "90-day spend estimate", ar: "تقدير مصروف ٩٠ يوم" },
  facts_title: { en: "Historical facts", ar: "حقائق تاريخية" },
  no_category: {
    en: "No category chart: demo data has no category field. Upload a file with a mapped category column to enable it.",
    ar: "مفيش رسم تصنيف: بيانات العرض مفيهاش عمود تصنيف. ارفع ملف فيه عمود تصنيف مربوط عشان يظهر.",
  },
  upload_how: {
    en: "How we handle uploads",
    ar: "إزاي بنتعامل مع الملفات المرفوعة",
  },
  upload_title: { en: "Upload · ask · clean · analyse", ar: "ارفع · اسأل · نظّف · حلّل" },
  upload_sub: {
    en: "File-specific questions, deterministic cleaning (manual for client-owned blanks), then an analyst dashboard with decision suggestions.",
    ar: "أسئلة مرتبطة بملفك، تنظيف واضح (يدوي للفراغات المحسومة عندك)، بعدين لوحة محلّل باقتراحات قرار.",
  },
  accept: { en: "Accept", ar: "موافق" },
  reject: { en: "Reject", ar: "رفض" },
  adjust_apply: {
    en: "Apply on export",
    ar: "تطبيق الاقتراح عند التصدير",
  },
  adjust_note: {
    en: "Adjust note (optional — does not change values)",
    ar: "ملاحظة تعديل (اختيارية — مش بتغيّر القيم)",
  },
  adjust_hint: {
    en: "Adjust = include/exclude only. Rule parameters are fixed by policy; nothing invents values.",
    ar: "التعديل = قبول/رفض التطبيق فقط. القواعد ثابتة من السياسة؛ مش هنتخمّن قيم.",
  },
  export: { en: "Export cleaned CSV", ar: "صدّر CSV بعد التنظيف" },
  discard: { en: "Discard upload", ar: "امسح الرفع" },
  unresolved: { en: "Unresolved rows (not filled in)", ar: "صفوف ناقصة (مش هنتخمّنها)" },
  project_title: { en: "Project details", ar: "تفاصيل المشروع" },
  source_label: { en: "Data source", ar: "مصدر البيانات" },
  source_demo: { en: "Demo data", ar: "بيانات العرض" },
  source_upload: { en: "My uploaded file", ar: "ملفي المرفوع" },
  currency_select: { en: "Currency of amounts in this file", ar: "عملة المبالغ في الملف ده" },
  date_format_select: {
    en: "Invoice date format",
    ar: "صيغة تاريخ الفاتورة",
  },
  date_format_confirm: {
    en: "Confirm date format",
    ar: "تأكيد صيغة التاريخ",
  },
  forecast_unavailable: {
    en: "Store-specific forecast not available",
    ar: "توقع خاص بالمتجر مش متاح",
  },
  retrospective_only: {
    en: "Retrospective comparison only",
    ar: "مقارنة لاحقة فقط",
  },
  use_upload_for_analysis: {
    en: "Use this upload for analysis pages",
    ar: "استخدم الرفع ده لصفحات التحليل",
  },
  unsupported_upload: {
    en: "This view is not available for uploaded data yet.",
    ar: "العرض ده لسه مش متاح للملفات المرفوعة.",
  },
  back_to_supported: {
    en: "Back to store overview",
    ar: "ارجع لنظرة المتجر",
  },
  th_invoice: { en: "Invoice", ar: "فاتورة" },
  th_stock: { en: "Stock", ar: "منتج" },
  th_qty: { en: "Qty", ar: "كمية" },
  th_price: { en: "Price", ar: "سعر" },
  th_customer: { en: "Customer", ar: "زبون" },
  th_issues: { en: "Issues", ar: "مشاكل" },
  th_step: { en: "Step", ar: "الخطوة" },
  th_reason: { en: "Reason", ar: "السبب" },
  th_before: { en: "Before", ar: "قبل" },
  th_after: { en: "After", ar: "بعد" },
  th_removed: { en: "Removed", ar: "اتشال" },
} as const;

export type StringKey = keyof typeof strings;

export function t(key: StringKey, lang: Lang): string {
  return strings[key][lang];
}

export const NAV: { href: string; key: StringKey }[] = [
  { href: "/", key: "nav_home" },
  { href: "/upload", key: "nav_upload" },
  { href: "/store", key: "nav_store" },
  { href: "/groups", key: "nav_groups" },
  { href: "/profile", key: "nav_profile" },
  { href: "/products", key: "nav_products" },
];
