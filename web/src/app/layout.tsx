import type { Metadata } from "next";
import { LangProvider } from "@/context/LangContext";
import { DataSourceProvider } from "@/context/DataSourceContext";
import { LangChrome } from "@/components/LangChrome";
import "./globals.css";

export const metadata: Metadata = {
  title: "MarketMind",
  description:
    "Calm retail customer analytics — upload your file and talk through it",
  icons: { icon: "/icon.svg", shortcut: "/icon.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ar" dir="rtl" suppressHydrationWarning>
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
