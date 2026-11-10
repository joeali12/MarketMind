"""Deterministic safe intents for Gemini.

Privacy default: questions with identifiers / pasted rows never reach the provider.
Supported intents send a fixed server template plus allowlisted aggregates.
When the privacy gate passes, a short privacy-cleared user ask may also be included
so Gemini can explain the correct computed answer for that question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SafeIntent:
    id: str
    template_en: str
    template_ar: str


# Fixed templates — no user-authored content
SAFE_INTENTS: dict[str, SafeIntent] = {
    "explain_file_profile": SafeIntent(
        id="explain_file_profile",
        template_en=(
            "In plain language, explain what this uploaded file appears to contain "
            "using only the aggregate file and structure facts in CONTEXT_JSON."
        ),
        template_ar=(
            "اشرح بلغة بسيطة إيه اللي ظاهر إن الملف ده يحتويه "
            "باستخدام حقائق الملف والبنية المجمّعة في CONTEXT_JSON فقط."
        ),
    ),
    "explain_counts": SafeIntent(
        id="explain_counts",
        template_en=(
            "Summarize the server-computed row, customer, product, invoice, and "
            "eligible-spend counts from CONTEXT_JSON. Do not invent numbers."
        ),
        template_ar=(
            "لخّص أعداد الصفوف والزبائن والمنتجات والفواتير والمصروف المؤهل "
            "المحسوبة في CONTEXT_JSON. متخترعش أرقام."
        ),
    ),
    "explain_findings": SafeIntent(
        id="explain_findings",
        template_en=(
            "Explain the listed data-quality findings in CONTEXT_JSON for a small "
            "retailer. Critical values are never invented."
        ),
        template_ar=(
            "اشرح ملاحظات جودة البيانات المدرجة في CONTEXT_JSON لتاجر صغير. "
            "القيم الحرجة مش بتتولَّد."
        ),
    ),
    "explain_cleaning_impact": SafeIntent(
        id="explain_cleaning_impact",
        template_en=(
            "Explain the estimated impact of the listed cleaning proposals using "
            "only CONTEXT_JSON aggregates. Suggestions are not guarantees."
        ),
        template_ar=(
            "اشرح الأثر التقديري لاقتراحات التنظيف المدرجة من CONTEXT_JSON فقط. "
            "الاقتراحات مش ضمان."
        ),
    ),
    "explain_segments": SafeIntent(
        id="explain_segments",
        template_en=(
            "Explain the computed customer segment aggregates in CONTEXT_JSON. "
            "Do not invent segment labels or customer identities."
        ),
        template_ar=(
            "اشرح مجاميع شرائح الزبائن المحسوبة في CONTEXT_JSON. "
            "متخترعش أسماء شرائح أو هويات زبائن."
        ),
    ),
    "suggest_next_step": SafeIntent(
        id="suggest_next_step",
        template_en=(
            "Suggest practical next steps for the shop owner based only on "
            "CONTEXT_JSON aggregates and confirmation flags. Frame as suggestions, "
            "not approved policy."
        ),
        template_ar=(
            "اقترح خطوات عملية لتاجر المحل بناءً على مجاميع CONTEXT_JSON "
            "وأعلام التأكيد فقط. اعتبرها اقتراحات مش سياسة معتمدة."
        ),
    ),
    "explain_top_product_units": SafeIntent(
        id="explain_top_product_units",
        template_en=(
            "Answer which product sold the most by units using only product_leaders "
            "in CONTEXT_JSON. Lead with the product name and units, then a short reason."
        ),
        template_ar=(
            "جاوب إيه أعلى منتج بالكمية من product_leaders في CONTEXT_JSON فقط. "
            "ابدأ باسم المنتج والكمية، بعدين سبب مختصر."
        ),
    ),
    "explain_top_product_revenue": SafeIntent(
        id="explain_top_product_revenue",
        template_en=(
            "Answer which product earned the most eligible spend using only "
            "product_leaders in CONTEXT_JSON. Lead with the name, spend, and currency."
        ),
        template_ar=(
            "جاوب إيه أعلى منتج بالإيراد المؤهل من product_leaders في CONTEXT_JSON فقط. "
            "ابدأ بالاسم والمبلغ والعملة."
        ),
    ),
    "explain_top_category": SafeIntent(
        id="explain_top_category",
        template_en=(
            "Explain the top category from CONTEXT_JSON if present; otherwise say "
            "category mapping is missing."
        ),
        template_ar=(
            "اشرح أعلى تصنيف من CONTEXT_JSON لو موجود؛ وإلا قول إن ربط التصنيف ناقص."
        ),
    ),
}


# Conservative signals that the user message may contain personal / row data.
# Presence blocks Gemini entirely (grounded answer may still be returned).
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s\-()]{7,}\d)")
_INVOICE_RE = re.compile(r"\bINV[-_]?\d+", re.I)
_CUSTOMER_ID_RE = re.compile(
    r"(?:\bCUST[-_]?\d+\b|\bC-\d{2,}\b|\bcustomer\s*id\b)",
    re.I,
)
_ROW_PASTE_RE = re.compile(
    r"(?:\t.+\t)|(?:\n.+,{2,}.+\n)|(?:^\s*\d+\s*,\s*[^,\n]+,\s*[^,\n]+,)",
    re.M,
)


def user_text_blocks_provider(question: str) -> str | None:
    """Return a safe reason code if the user text must not trigger Gemini."""
    if not question or not question.strip():
        return "empty_question"
    text = question.strip()
    if _EMAIL_RE.search(text):
        return "user_text_email"
    if _PHONE_RE.search(text):
        return "user_text_phone"
    if _INVOICE_RE.search(text):
        return "user_text_invoice"
    if _CUSTOMER_ID_RE.search(text):
        return "user_text_customer_id"
    if _ROW_PASTE_RE.search(text) or text.count("\n") >= 3 and text.count(",") >= 6:
        return "user_text_row_paste"
    if len(text) > 500:
        return "user_text_too_long"
    return None


def resolve_safe_intent(intent_id: str | None, *, lang: str) -> SafeIntent | None:
    if not intent_id:
        return None
    intent = SAFE_INTENTS.get(intent_id)
    if not intent:
        return None
    return intent


def template_for(intent: SafeIntent, *, lang: str) -> str:
    return intent.template_ar if lang == "ar" else intent.template_en
