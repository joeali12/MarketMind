import type { Metadata } from "next";
import { Cairo } from "next/font/google";
import { LangProvider } from "@/context/LangContext";
import { DataSourceProvider } from "@/context/DataSourceContext";
import { LangChrome } from "@/components/LangChrome";
import "./globals.css";

/** Bold, clear Arabic UI face — premium geometric sans (not Inter). */
const cairo = Cairo({
  subsets: ["arabic", "latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-cairo",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MarketMind — Retail Intelligence",
  description:
    "Graduation product for SME retailers: upload sales data, clean it, and explore segmentation & CLV in Arabic or English",
  icons: { icon: "/icon.svg", shortcut: "/icon.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ar" dir="rtl" className={cairo.variable} suppressHydrationWarning>
      <body className="chat-shell-body">
        <LangProvider>
          <DataSourceProvider>
            <LangChrome />
            {children}
          </DataSourceProvider>
        </LangProvider>
      </body>
    </html>
  );
}
