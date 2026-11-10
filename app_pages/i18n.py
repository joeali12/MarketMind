"""Bilingual Arabic/English strings and language helpers for MarketMind."""

from __future__ import annotations

from typing import Any

import streamlit as st

LANG_KEY = "mm_lang"
SUPPORTED = ("ar", "en")

# Canonical English segment labels from model metadata → display keys
SEGMENT_LABEL_KEYS = {
    "Recent high-spend": "segment.recent_high",
    "Lapsed low-spend": "segment.lapsed_low",
    "Recent lower-spend": "segment.recent_lower",
    "Older higher-spend": "segment.older_higher",
}

STRINGS: dict[str, dict[str, str]] = {
    # --- Language switcher ---
    "lang.label": {
        "en": "Language",
        "ar": "اللغة",
    },
    # Always show native script so the other language stays discoverable
    "lang.ar": {"en": "العربية", "ar": "العربية"},
    "lang.en": {"en": "English", "ar": "English"},
    # --- Navigation ---
    "nav.section_main": {"en": "Main tasks", "ar": "المهام الأساسية"},
    "nav.section_project": {"en": "More details", "ar": "تفاصيل إضافية"},
    "nav.home": {"en": "Home", "ar": "البداية"},
    "nav.groups": {"en": "Customer groups", "ar": "مجموعات الزباين"},
    "nav.profile": {"en": "Customer profile", "ar": "ملف الزبون"},
    "nav.overview": {"en": "Store dashboard", "ar": "لوحة المتجر"},
    "nav.validation": {"en": "Upload data", "ar": "رفع البيانات"},
    "nav.quality": {"en": "Prediction quality", "ar": "جودة التوقع"},
    # --- Shared chrome ---
    "shared.simple_terms": {"en": "In simple terms", "ar": "ببساطة"},
    "shared.learn_more": {"en": "Learn more", "ar": "اعرف أكتر"},
    "shared.next": {"en": "Continue", "ar": "كمّل"},
    # --- Segments (canonical names only) ---
    "segment.recent_high": {
        "en": "Recent high-spend",
        "ar": "يشترون حديثاً وصرفهم أعلى",
    },
    "segment.lapsed_low": {
        "en": "Lapsed low-spend",
        "ar": "منقطعون منذ فترة وصرفهم أقل",
    },
    "segment.recent_lower": {
        "en": "Recent lower-spend",
        "ar": "يشترون حديثاً وصرفهم أقل",
    },
    "segment.older_higher": {
        "en": "Older higher-spend",
        "ar": "اشتروا من فترة وصرفهم أعلى",
    },
    # --- Home ---
    "home.badge": {"en": "Demo with sample data", "ar": "تجربة ببيانات نموذجية"},
    "home.title": {
        "en": "Know your customers",
        "ar": "اعرف زباينك",
    },
    "home.subtitle": {
        "en": "See who shops with you, how they buy, and a calm estimate of spend over the next 90 days.",
        "ar": "شوف مين بيشتري، إزاي بيشتري، وتقدير هادي لصرف ٩٠ يوماً الجايين.",
    },
    "home.note": {
        "en": "Four simple steps: check a file, open the store summary, browse groups, then open a customer.",
        "ar": "أربع خطوات بسيطة: افحص ملف، افتح ملخص المتجر، شوف المجموعات، بعدين افتح ملف زبون.",
    },
    "home.demo_warning_title": {
        "en": "Demo with sample shop data — not your live shop",
        "ar": "تجربة ببيانات نموذجية — مش محلك الحالي",
    },
    "home.demo_warning_body": {
        "en": (
            "Uses the public UCI Online Retail II dataset (2009–2011). "
            "Upload only checks file structure; it does **not** import your customers into predictions."
        ),
        "ar": (
            "بيستخدم بيانات UCI Online Retail II العامة (2009–2011). "
            "رفع الملف بيفحص الشكل فقط؛ **ما بيستوردش** زباينك للتوقع."
        ),
    },
    "home.cta_upload_title": {"en": "Upload data", "ar": "رفع البيانات"},
    "home.cta_upload_cap": {
        "en": "Check that a transaction file has the expected columns.",
        "ar": "اتأكد إن ملف المعاملات فيه الأعمدة المتوقعة.",
    },
    "home.cta_upload_btn": {"en": "Check a file", "ar": "افحص ملف"},
    "home.cta_dash_title": {"en": "Store dashboard", "ar": "لوحة المتجر"},
    "home.cta_dash_cap": {
        "en": "A short summary of the sample store and time period.",
        "ar": "ملخص قصير عن متجر المثال والفترة الزمنية.",
    },
    "home.cta_dash_btn": {"en": "Open dashboard", "ar": "افتح اللوحة"},
    "home.cta_groups_title": {"en": "Customer groups", "ar": "مجموعات الزباين"},
    "home.cta_groups_cap": {
        "en": "Who buys often and recently? Who has gone quiet?",
        "ar": "مين بيشتري كتير وحديث؟ ومين اختفى؟",
    },
    "home.cta_groups_btn": {"en": "Browse groups", "ar": "شوف المجموعات"},
    "home.cta_profile_title": {"en": "Customer profile", "ar": "ملف الزبون"},
    "home.cta_profile_cap": {
        "en": "Past shopping, group, and next-90-day spend estimate.",
        "ar": "الشراء السابق، المجموعة، وتقدير صرف ٩٠ يوماً.",
    },
    "home.cta_profile_btn": {"en": "Open a customer", "ar": "افتح زبوناً"},
    "home.what_title": {
        "en": "What does this demo show?",
        "ar": "إيه اللي بيوضّحه المثال؟",
    },
    "home.what_body": {
        "en": (
            "- **Customer groups:** based on how recently they bought, how often, and how much they spent before.\n"
            "- **Spend estimate:** a rough guess of eligible purchases over the next 90 days."
        ),
        "ar": (
            "- **مجموعات الزباين:** حسب حداثة الشراء، وعدد مرات الشراء، والصرف السابق.\n"
            "- **توقع الصرف:** تقدير تقريبي لمشتريات مؤهلة خلال ٩٠ يوماً."
        ),
    },
    "home.what_not": {
        "en": (
            "It does **not** predict which products a customer will need, guarantee future spend, "
            "or give approved marketing advice. Product suggestions would need a separate analysis later."
        ),
        "ar": (
            "التطبيق **ما بيتوقعش** المنتجات اللي هيحتاجها الزبون، ولا بيضمن الصرف المستقبلي، "
            "ولا بيقدّم نصيحة تسويقية معتمدة. اقتراح المنتجات محتاج تحليل منفصل لاحقاً."
        ),
    },
    "home.about_expander": {"en": "About the sample data", "ar": "عن البيانات النموذجية"},
    "home.about_period": {
        "en": "Sample period: **{start} to {end}**. Estimates use **{currency}** over **{days} days**.",
        "ar": "فترة المثال: **{start} إلى {end}**. التوقع بعملة **{currency}** ولمدة **{days} يوم**.",
    },
    "home.link_overview": {"en": "Data overview", "ar": "نظرة على البيانات"},
    "home.link_quality": {"en": "Is the estimate accurate?", "ar": "هل التوقع دقيق؟"},
    "home.artifacts_error_title": {
        "en": "Saved models are missing",
        "ar": "ملفات النموذج غير جاهزة",
    },
    "home.artifacts_error_body": {
        "en": "Predictions cannot run until the saved model files are available.",
        "ar": "لا يمكن عرض التوقعات حتى تتوفر ملفات النموذج المحفوظة.",
    },
    # --- Groups page ---
    "groups.badge": {"en": "Customer groups", "ar": "مجموعات الزباين"},
    "groups.title": {"en": "Customer groups", "ar": "مجموعات الزباين"},
    "groups.subtitle": {
        "en": "See how customers differ in recent shopping, how often they buy, and how much they spent.",
        "ar": "شوف اختلاف الزباين في حداثة الشراء، وعدد مرات الشراء، وحجم الصرف السابق.",
    },
    "groups.note": {
        "en": (
            "Names describe the average pattern in each group. An individual customer can differ. "
            "These are descriptive labels, not approved marketing personas."
        ),
        "ar": (
            "الأسماء بتوصف متوسط سلوك المجموعة. الزبون الواحد ممكن يختلف. "
            "دي أوصاف مساعدة، مش شخصيات تسويقية معتمدة."
        ),
    },
    "groups.count_caption": {
        "en": "Showing **{n}** groups from the training sample.",
        "ar": "معروض **{n}** مجموعات من عينة التدريب.",
    },
    "groups.browse": {"en": "Browse groups", "ar": "تصفّح المجموعات"},
    "groups.help_browse": {
        "en": "Select a group. Works with keyboard and click.",
        "ar": "اختار مجموعة. الاشتغال بالكيبورد أو الضغط.",
    },
    "groups.share": {
        "en": "Share of training customers: **{share:.1%}** · **{n:,}** customers",
        "ar": "نسبة المجموعة من زباين العينة: **{share:.1%}** · عدد الزباين: **{n:,}**",
    },
    "groups.metric_recency": {
        "en": "Avg. days since last purchase",
        "ar": "متوسط الأيام منذ آخر شراء",
    },
    "groups.metric_recency_help": {
        "en": "Fewer days means the group bought more recently on average.",
        "ar": "عدد أيام أقل يعني إن المجموعة اشترت مؤخراً في المتوسط.",
    },
    "groups.metric_frequency": {
        "en": "Avg. number of invoices",
        "ar": "متوسط عدد الفواتير",
    },
    "groups.metric_frequency_help": {
        "en": "Average count of separate purchases recorded per customer in the group.",
        "ar": "متوسط عدد مرات الشراء المسجّلة لكل زبون في المجموعة.",
    },
    "groups.metric_monetary": {
        "en": "Avg. past spend ({currency})",
        "ar": "متوسط الصرف السابق ({currency})",
    },
    "groups.metric_monetary_help": {
        "en": "Average eligible past spend per customer in the group.",
        "ar": "متوسط قيمة المشتريات المؤهلة السابقة لكل زبون في المجموعة.",
    },
    "groups.meaning_title": {
        "en": "What do these measures mean?",
        "ar": "إيه معنى المقاييس دي؟",
    },
    "groups.meaning_body": {
        "en": (
            "- **Days since last purchase:** how long ago they typically bought (lower = more recent).\n"
            "- **Number of invoices:** how often they typically buy.\n"
            "- **Past spend:** how much eligible spend they typically had in the observation period."
        ),
        "ar": (
            "- **الأيام منذ آخر شراء:** من كام يوم تقريباً اشتروا (الأقل = أحدث).\n"
            "- **عدد الفواتير:** كام مرة تقريباً بيشتروا.\n"
            "- **الصرف السابق:** متوسط المشتريات المؤهلة في فترة الملاحظة."
        ),
    },
    "groups.all_table": {"en": "All groups (table)", "ar": "كل المجموعات (جدول)"},
    "groups.missing_title": {"en": "Group profiles missing", "ar": "ملفات المجموعات ناقصة"},
    "groups.missing_body": {
        "en": "Segment profiles file not found.",
        "ar": "ملف ملخص المجموعات غير موجود.",
    },
    "groups.tech_defs": {
        "en": "Optional technical definitions",
        "ar": "تعريفات تقنية اختيارية",
    },
    "groups.tech_k": {
        "en": "Optional technical details: comparing group counts",
        "ar": "تفاصيل تقنية اختيارية: مقارنة عدد المجموعات",
    },
    "groups.viz_title": {
        "en": "Simplified map of shopping patterns",
        "ar": "خريطة مبسّطة لأنماط الشراء",
    },
    "groups.viz_cap": {
        "en": "Customers with similar shopping patterns appear nearer each other. This picture can hide some differences.",
        "ar": "الزباين المتشابهين في الشراء بيظهروا أقرب لبعض. الصورة دي ممكن تخفي بعض الاختلافات.",
    },
    "groups.viz_tech": {
        "en": "Technical chart details",
        "ar": "تفاصيل تقنية للرسم",
    },
    "groups.hier_tech": {
        "en": "Optional technical details: alternative grouping method",
        "ar": "تفاصيل تقنية اختيارية: طريقة تجميع بديلة",
    },
    "groups.action_warn_title": {
        "en": "Suggested actions are provisional only",
        "ar": "أي اقتراح إجراء مؤقت فقط",
    },
    "groups.action_warn_body": {
        "en": (
            "Any suggested actions on the customer profile are provisional heuristics (decision D7). "
            "They are not approved business policy and not causal recommendations."
        ),
        "ar": (
            "أي اقتراح إجراء في ملف الزبون هو تخمين مؤقت فقط (قرار D7). "
            "مش سياسة عمل معتمدة ومش توصية مؤكدة."
        ),
    },
    "groups.next_profile": {"en": "Open a customer profile", "ar": "افتح ملف زبون"},
    # --- Profile page ---
    "profile.badge": {"en": "Sample customer", "ar": "زبون من المثال"},
    "profile.title": {"en": "Customer profile", "ar": "ملف الزبون"},
    "profile.subtitle": {
        "en": "Choose a sample customer to review past shopping and the estimated spend for the next 90 days.",
        "ar": "اختار زبوناً من المثال، وراجع مشترياته السابقة وتقدير صرفه خلال الـ٩٠ يوم الجايين.",
    },
    "profile.note": {
        "en": "The estimate is a helpful guess from historical sample data — not a promise of future sales.",
        "ar": "التقدير تخمين مفيد من بيانات تاريخية — مش وعد بمبيعات مستقبلية.",
    },
    "profile.demo_mode_title": {"en": "Demo mode", "ar": "وضع التجربة"},
    "profile.demo_mode_body": {
        "en": "Using precomputed Online Retail II customer tables.",
        "ar": "بنستخدم جداول زبائن Online Retail II الجاهزة.",
    },
    "profile.tables_missing_title": {
        "en": "Customer tables missing",
        "ar": "جداول الزباين ناقصة",
    },
    "profile.tables_missing_body": {
        "en": "Train models first to build demo tables.",
        "ar": "شغّل التدريب أولاً لبناء جداول التجربة.",
    },
    "profile.select_title": {"en": "Choose a customer", "ar": "اختار زبوناً"},
    "profile.table_label": {
        "en": "Which sample period?",
        "ar": "أنهي فترة من المثال؟",
    },
    "profile.table_train": {"en": "Earlier period", "ar": "الفترة الأقدم"},
    "profile.table_test": {"en": "Later period", "ar": "الفترة الأحدث"},
    "profile.table_help": {
        "en": "The earlier period helped build the estimate. The later period is used to check it.",
        "ar": "الفترة الأقدم ساعدت في بناء التقدير. الفترة الأحدث بتستخدم للفحص.",
    },
    "profile.cutoff_caption": {
        "en": (
            "Looking at purchases on/before **{cutoff}**. "
            "Estimated spend = eligible positive purchases in the next **{days} days** "
            "(not net revenue after refunds). Units: **{currency}**."
        ),
        "ar": (
            "بنبص على المشتريات حتى **{cutoff}**. "
            "توقع الصرف = مشتريات موجبة مؤهلة خلال **{days} يوماً** الجايين "
            "(مش صافي الإيراد بعد المرتجعات). العملة: **{currency}**."
        ),
    },
    "profile.customer_id": {"en": "Customer ID", "ar": "رقم الزبون"},
    "profile.customer_help": {
        "en": "An anonymized ID from the public sample dataset.",
        "ar": "رقم مجهّل من بيانات المثال العامة.",
    },
    "profile.past_title": {"en": "Past shopping pattern", "ar": "نمط الشراء السابق"},
    "profile.recency": {"en": "Days since last purchase", "ar": "أيام منذ آخر شراء"},
    "profile.recency_help": {
        "en": "Fewer days means a more recent purchase.",
        "ar": "عدد أيام أقل يعني شراء أحدث.",
    },
    "profile.frequency": {"en": "Number of invoices", "ar": "عدد الفواتير"},
    "profile.frequency_help": {
        "en": "Count of separate purchases on/before the date above.",
        "ar": "عدد مرات الشراء حتى التاريخ أعلاه.",
    },
    "profile.monetary": {"en": "Past eligible spend ({currency})", "ar": "الصرف السابق المؤهل ({currency})"},
    "profile.monetary_help": {
        "en": "Eligible spend recorded before the estimate date.",
        "ar": "المشتريات المؤهلة المسجّلة قبل تاريخ التقدير.",
    },
    "profile.outlook_title": {
        "en": "Group and 90-day spend estimate",
        "ar": "المجموعة وتقدير صرف ٩٠ يوماً",
    },
    "profile.group": {"en": "Customer group", "ar": "مجموعة الزبون"},
    "profile.group_help": {
        "en": "Descriptive label from group averages — not an approved persona.",
        "ar": "وصف من متوسطات المجموعة — مش شخصية تسويقية معتمدة.",
    },
    "profile.pred": {"en": "Estimated spend (next 90 days)", "ar": "تقدير الصرف (٩٠ يوماً)"},
    "profile.pred_help": {
        "en": "Eligible positive spend estimate from the saved model.",
        "ar": "تقدير المشتريات الموجبة المؤهلة من النموذج المحفوظ.",
    },
    "profile.pred_explain": {
        "en": (
            "This estimate answers: roughly how much eligible spend might this customer "
            "have in the next 90 days? It does not say which products they will buy."
        ),
        "ar": (
            "التقدير ده بيجاوب: تقريباً الزبون ده ممكن يصرف كام في المشتريات المؤهلة خلال ٩٠ يوماً؟ "
            "مش بيقول هيشتري أنهي منتجات."
        ),
    },
    "profile.actual_compare": {
        "en": "For comparison only — actual eligible spend in that later period: **{value} {currency}**",
        "ar": "للمقارنة فقط — الصرف الفعلي المؤهل في الفترة اللاحقة: **{value} {currency}**",
    },
    "profile.actual_note": {
        "en": "Shown only for the historical demo. It was not available when the estimate was made.",
        "ar": "معروض بس في المثال التاريخي. ما كانش معروف وقت عمل التقدير.",
    },
    "profile.action_title": {
        "en": "Provisional suggested action",
        "ar": "اقتراح إجراء مؤقت",
    },
    "profile.action_warn_title": {
        "en": "Provisional heuristics only",
        "ar": "تخمين مؤقت فقط",
    },
    "profile.action_warn_body": {
        "en": (
            "Marketing actions are provisional heuristics (decision D7). "
            "They are not approved business policy and not causal recommendations."
        ),
        "ar": (
            "أي اقتراح تسويقي تخمين مؤقت فقط (قرار D7). "
            "مش سياسة عمل معتمدة ومش توصية مؤكدة."
        ),
    },
    "profile.action_none": {"en": "No action mapping available.", "ar": "مفيش اقتراح مرتبط."},
    "profile.context_title": {"en": "Keep in mind", "ar": "خلي بالك"},
    "profile.context_body": {
        "en": (
            "- Estimate date: **{cutoff}**\n"
            "- Based only on purchases on/before that date\n"
            "- Historical 2009–2011 giftware sample — not a revenue guarantee"
        ),
        "ar": (
            "- تاريخ التقدير: **{cutoff}**\n"
            "- مبني على المشتريات حتى التاريخ ده بس\n"
            "- بيانات هدايا تاريخية 2009–2011 — مش ضمان إيراد"
        ),
    },
    "profile.manual_expander": {
        "en": "Optional: try your own example numbers",
        "ar": "اختياري: جرّب أرقامك",
    },
    "profile.manual_cap": {
        "en": "Enter a shopping pattern to see how the saved model responds. This does not retrain it.",
        "ar": "دخل نمط شراء وشوف رد النموذج المحفوظ. ده مش بيعيد التدريب.",
    },
    "profile.manual_predict": {"en": "Estimate", "ar": "احسب التقدير"},
    "profile.next_quality": {"en": "See prediction quality", "ar": "شوف جودة التوقع"},
    "profile.inference_failed": {"en": "Could not run the estimate", "ar": "مقدرناش نعمل التقدير"},
    "profile.invalid_input": {"en": "Invalid input", "ar": "مدخل غير صالح"},
    "profile.table_unavailable": {
        "en": "Selected sample table is unavailable.",
        "ar": "جدول الفترة المختارة غير متاح.",
    },
    # Heuristic action translations (canonical English → display)
    "action.recent_high": {
        "en": "Consider retention / thank-you offers for recent high spenders (heuristic only).",
        "ar": "ممكن تفكّر في عرض شكر/احتفاظ للزبون اللي بيشتري حديثاً وبصرف أعلى (تخمين مؤقت فقط).",
    },
    "action.lapsed_low": {
        "en": "Consider cautious re-engagement; expected spend may be low (heuristic only).",
        "ar": "ممكن تفكّر في تواصل حذر لإعادة التفاعل؛ الصرف المتوقع ممكن يكون قليل (تخمين مؤقت فقط).",
    },
    # --- Overview ---
    "overview.badge": {"en": "Store dashboard", "ar": "لوحة المتجر"},
    "overview.title": {"en": "Store dashboard", "ar": "لوحة المتجر"},
    "overview.subtitle": {
        "en": "A short summary of the sample store and time window.",
        "ar": "ملخص قصير عن متجر المثال والفترة الزمنية.",
    },
    "overview.note": {
        "en": "This page is for project context. Everyday use starts with customer groups and a customer profile.",
        "ar": "الصفحة دي لسياق المشروع. الاستخدام اليومي يبدأ بمجموعات الزباين وملف الزبون.",
    },
    "overview.cleaned": {"en": "Cleaned rows", "ar": "صفوف بعد التنظيف"},
    "overview.train_cust": {"en": "Training customers", "ar": "زبائن التدريب"},
    "overview.test_cust": {"en": "Evaluation customers", "ar": "زبائن التقييم"},
    "overview.dates_title": {"en": "Dates used", "ar": "التواريخ المستخدمة"},
    "overview.meta_missing": {"en": "Model metadata missing. Run training first.", "ar": "بيانات النموذج ناقصة. شغّل التدريب أولاً."},
    "overview.next_groups": {"en": "Browse customer groups", "ar": "شوف مجموعات الزباين"},
    "overview.currency_cap": {
        "en": "Units: **{currency}** (UCI description; no FX). Estimates are eligible positive spend, not net revenue after refunds.",
        "ar": "العملة: **{currency}** (وصف UCI؛ بدون تحويل). التقدير لمشتريات موجبة مؤهلة، مش صافي بعد المرتجعات.",
    },
    "overview.cutoff_title": {
        "en": "Dates covered by this project",
        "ar": "الفترة التي تغطيها البيانات",
    },
    "overview.cutoff_body": {
        "en": (
            "The dataset runs from {dmin} to {dmax}. "
            "The model learns from purchases up to **{train}**; "
            "we check estimates using data up to **{test}**. "
            "Each estimate looks ahead **{days} days**."
        ),
        "ar": (
            "البيانات من {dmin} إلى {dmax}. "
            "النموذج يتعلم من مشتريات حتى **{train}**، "
            "ونفحصه على فترة أحدث حتى **{test}**. "
            "كل توقع يغطي **{days} يوماً**."
        ),
    },
    # --- Validation ---
    "validation.badge": {"en": "Upload check only", "ar": "فحص رفع فقط"},
    "validation.title": {"en": "Upload data", "ar": "رفع البيانات"},
    "validation.subtitle": {
        "en": "Check columns only. This does not import the file into predictions.",
        "ar": "فحص الأعمدة فقط. ده **ما بيستوردش** الملف في التوقعات.",
    },
    "validation.note": {
        "en": "Upload checks structure in this session only. It does not train a model or change demo predictions.",
        "ar": "الرفع بيفحص الشكل في الجلسة دي بس. مش بيدرب نموذج ومش بيغيّر توقعات المثال.",
    },
    "validation.required": {"en": "Required columns", "ar": "الأعمدة المطلوبة"},
    "validation.upload": {"en": "Validate an upload", "ar": "افحص ملفاً مرفوعاً"},
    "validation.upload_cap": {
        "en": "CSV or Excel with the required headers. Not saved to a database.",
        "ar": "CSV أو Excel بالأعمدة المطلوبة. مش بيتخزن في قاعدة بيانات.",
    },
    "validation.file": {"en": "Transaction file", "ar": "ملف المعاملات"},
    "validation.ok": {"en": "Structure looks OK", "ar": "شكل الملف سليم"},
    "validation.bad": {"en": "Structure problem", "ar": "مشكلة في شكل الملف"},
    "validation.rows": {"en": "Rows detected", "ar": "عدد الصفوف"},
    "validation.read_fail": {"en": "Could not read file", "ar": "مقدرناش نقرأ الملف"},
    "validation.quality": {"en": "Sample file health", "ar": "صحة ملف المثال"},
    "validation.recon": {"en": "Cleaning steps (project sample)", "ar": "خطوات التنظيف (عينة المشروع)"},
    "validation.next": {"en": "Continue to data overview", "ar": "كمّل لنظرة البيانات"},
    # --- Quality ---
    "quality.badge": {"en": "Prediction quality", "ar": "جودة التوقع"},
    "quality.title": {"en": "Prediction quality", "ar": "جودة التوقع"},
    "quality.subtitle": {
        "en": "How close were the estimates to actual spend in a later sample period?",
        "ar": "قد إيه التقديرات كانت قريبة من الصرف الفعلي في فترة لاحقة من المثال؟",
    },
    "quality.note": {
        "en": "Lower typical error is usually better. The fit score is not a “percent correct.”",
        "ar": "كل ما الخطأ النموذجي قلّ كل ما كان أفضل عادةً. درجة المطابقة مش «نسبة صح».",
    },
    "quality.how_title": {"en": "How to read this page", "ar": "إزاي تقرأ الصفحة"},
    "quality.how_body": {
        "en": (
            "The model learned from earlier shopping history, then we checked estimates against "
            "a later 90-day period starting at **{cutoff}**."
        ),
        "ar": (
            "النموذج اتعلم من تاريخ شراء أقدم، وبعدين فحصنا التقديرات على فترة ٩٠ يوماً لاحقة "
            "تبدأ من **{cutoff}**."
        ),
    },
    "quality.mae": {"en": "Typical miss (average error)", "ar": "الخطأ المتوسط المعتاد"},
    "quality.rmse": {"en": "Score that weighs large misses more", "ar": "مقياس يركّز على الأخطاء الكبيرة"},
    "quality.r2": {"en": "Fit comparison score", "ar": "درجة مقارنة المطابقة"},
    "quality.compare": {
        "en": "Compared with a simple average guess",
        "ar": "مقارنة مع تخمين بالمتوسط البسيط",
    },
    "quality.limits": {"en": "Limitations", "ar": "الحدود"},
    "quality.limits_body": {
        "en": (
            "- Sample is 2009–2011 UK giftware; today’s behavior may differ.\n"
            "- Many customers spent **zero** in the 90-day window, which affects error scores.\n"
            "- Estimates are **eligible positive spend**, not net revenue after refunds.\n"
            "- Currency **{currency}** from the UCI description; no FX conversion.\n"
            "- Suggested actions are provisional only (not approved policy).\n"
            "- The demo does not analyze your own shop data."
        ),
        "ar": (
            "- العينة من متجر هدايا بريطاني 2009–2011؛ سلوك النهارده ممكن يختلف.\n"
            "- كتير من الزباين صرفهم كان **صفر** خلال ٩٠ يوماً، وده بيأثر على مقاييس الخطأ.\n"
            "- التقدير لـ**مشتريات موجبة مؤهلة**، مش صافي بعد المرتجعات.\n"
            "- العملة **{currency}** حسب وصف UCI؛ بدون تحويل عملة.\n"
            "- اقتراحات الإجراءات مؤقتة فقط (مش سياسة معتمدة).\n"
            "- التجربة ما بتحلّلش بيانات محلك."
        ),
    },
    "quality.baseline": {"en": "Simple average guess", "ar": "تخمين بالمتوسط البسيط"},
    "quality.model_gb": {"en": "Gradient boosting", "ar": "نموذج التدرج المعزز"},
    "quality.model_rf": {"en": "Random forest", "ar": "الغابة العشوائية"},
    "quality.model_ridge": {"en": "Ridge", "ar": "نموذج ريدج"},
    "quality.model_mean": {"en": "Mean baseline", "ar": "متوسط الصرف البسيط"},
    "quality.tech": {"en": "Optional technical details", "ar": "تفاصيل تقنية اختيارية"},
}


def get_lang() -> str:
    lang = st.session_state.get(LANG_KEY, "ar")
    return lang if lang in SUPPORTED else "ar"


def set_lang(lang: str) -> None:
    if lang in SUPPORTED:
        st.session_state[LANG_KEY] = lang


def is_rtl() -> bool:
    return get_lang() == "ar"


def t(key: str, **kwargs: Any) -> str:
    """Translate a key for the active language; falls back to English then the key."""
    lang = get_lang()
    entry = STRINGS.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def translate_segment_label(canonical: str | None) -> str:
    if not canonical:
        return "—"
    key = SEGMENT_LABEL_KEYS.get(canonical)
    if key:
        return t(key)
    return canonical


def translate_action(english_action: str | None) -> str:
    if not english_action:
        return t("profile.action_none")
    lower = english_action.lower()
    if "retention" in lower or "thank-you" in lower:
        return t("action.recent_high")
    if "re-engagement" in lower or "expected spend may be low" in lower:
        return t("action.lapsed_low")
    return english_action


def format_model_name(raw: str | None) -> str:
    if not raw:
        return "—"
    return {
        "gradient_boosting": t("quality.model_gb"),
        "mean_baseline": t("quality.model_mean"),
        "random_forest": t("quality.model_rf"),
        "ridge": t("quality.model_ridge"),
    }.get(raw, raw.replace("_", " ").title())


def render_language_switcher() -> str:
    """Sidebar language control; persists in session_state across pages/reruns."""
    if LANG_KEY not in st.session_state:
        st.session_state[LANG_KEY] = "ar"
    with st.sidebar:
        st.segmented_control(
            t("lang.label"),
            options=list(SUPPORTED),
            format_func=lambda code: t(f"lang.{code}"),
            key=LANG_KEY,
            help="العربية / English",
        )
    return get_lang()
