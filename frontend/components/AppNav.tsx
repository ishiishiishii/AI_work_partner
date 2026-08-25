"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { QuickAddFab } from "@/components/QuickAddFab";
import { RepSwitcher } from "@/components/RepSwitcher";

export function AppNav() {
  const pathname = usePathname();

  if (pathname === "/login") {
    return null;
  }

  return (
    <>
      <nav className="app-nav">
        <Link href="/dashboard">ダッシュボード</Link>
        <Link href="/customers">顧客一覧</Link>
        <Link href="/products">商品カタログ</Link>
        <Link href="/affinity">得意分野</Link>
        <RepSwitcher />
      </nav>
      <QuickAddFab />
    </>
  );
}
