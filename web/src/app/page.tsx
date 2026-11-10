"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLang } from "@/context/LangContext";

/** Entry is the upload + assistant conversation — no marketing nav. */
export default function HomePage() {
  const router = useRouter();
  const { lang } = useLang();

  useEffect(() => {
    router.replace("/upload");
  }, [router]);

  return (
    <main className="main">
      <p className="muted" style={{ textAlign: "center", marginTop: 48 }}>
        {lang === "ar" ? "بيحوّلك لرفع الملف…" : "Taking you to upload…"}
      </p>
    </main>
  );
}
