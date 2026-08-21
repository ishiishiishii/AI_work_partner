import type { Metadata } from "next";
import Link from "next/link";
import { RepSwitcher } from "@/components/RepSwitcher";
import { RepProvider } from "@/lib/repContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Work Partner",
  description: "FastAPI + Next.js + Supabase development environment",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>
        <RepProvider>
          <nav className="app-nav">
            <Link href="/dashboard">ダッシュボード</Link>
            <Link href="/customers">顧客一覧</Link>
            <Link href="/products">商品カタログ</Link>
            <RepSwitcher />
          </nav>
          {children}
        </RepProvider>
      </body>
    </html>
  );
}
