"use client";

import { useEffect, useRef } from "react";
import { useLang } from "@/context/LangContext";

export type ChatMsg = { role: "user" | "assistant"; text: string; meta?: string };

type Props = {
  open: boolean;
  onClose: () => void;
  label: string;
  chat: ChatMsg[];
  question: string;
  onQuestionChange: (v: string) => void;
  onSend: () => void;
  onQuickReply?: (text: string) => void;
  quickReplies?: string[];
  busy?: boolean;
  emptyHint?: string;
};

export function AssistantModal({
  open,
  onClose,
  label,
  chat,
  question,
  onQuestionChange,
  onSend,
  onQuickReply,
  quickReplies = [],
  busy,
  emptyHint,
}: Props) {
  const { t, lang } = useLang();
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    endRef.current?.scrollIntoView({ behavior: "smooth" });
    const id = window.setTimeout(() => inputRef.current?.focus(), 120);
    return () => window.clearTimeout(id);
  }, [open, chat.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="assistant-backdrop" role="presentation" onClick={onClose}>
      <div
        className="assistant-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="assistant-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="assistant-modal-head">
          <div>
            <h2 id="assistant-modal-title" className="assistant-modal-title">
              {t("ask_assistant")}
            </h2>
            <p className="muted assistant-modal-label">{label}</p>
            <p className="muted" style={{ fontSize: 11, margin: "4px 0 0" }}>
              {lang === "ar"
                ? "اسأل بحرية. لما الذكاء الاصطناعي يكون متاح، السؤال بيتبعت لـ Gemini مع مجاميع محسوبة فقط — من غير صفوف خام أو أرقام شخصية."
                : "Ask freely. When AI assist is on, your question may go to Gemini with server aggregates only — never raw rows or personal IDs."}
            </p>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onClose}
            aria-label={lang === "ar" ? "إغلاق" : "Close"}
          >
            ✕
          </button>
        </header>

        <div className="assistant-modal-body">
          {chat.length === 0 && (
            <p className="muted">
              {emptyHint ||
                (lang === "ar"
                  ? "المساعد هيكلمك في العملة والتاريخ والتنظيف هنا."
                  : "The assistant walks currency, dates, and cleaning here.")}
            </p>
          )}
          {chat.map((m, i) => (
            <div
              key={i}
              className={
                m.role === "user" ? "assistant-bubble user" : "assistant-bubble bot"
              }
            >
              <strong>
                {m.role === "user"
                  ? lang === "ar"
                    ? "أنت"
                    : "You"
                  : "MarketMind"}
              </strong>
              <p style={{ whiteSpace: "pre-wrap" }}>{m.text}</p>
              {m.meta && <span className="muted">{m.meta}</span>}
            </div>
          ))}
          <div ref={endRef} />
        </div>

        {quickReplies.length > 0 && (
          <div className="assistant-quick">
            {quickReplies.map((q) => (
              <button
                key={q}
                type="button"
                className="assistant-chip"
                disabled={busy}
                onClick={() => onQuickReply?.(q)}
              >
                {q}
              </button>
            ))}
          </div>
        )}

        <footer className="assistant-modal-foot">
          <input
            ref={inputRef}
            className="input"
            placeholder={t("assistant_placeholder")}
            value={question}
            disabled={busy}
            onChange={(e) => onQuestionChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSend();
            }}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !question.trim()}
            onClick={onSend}
          >
            {t("send")}
          </button>
        </footer>
      </div>
    </div>
  );
}
