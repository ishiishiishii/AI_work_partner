"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { QuickAddFab } from "@/components/QuickAddFab";
import { RepSwitcher } from "@/components/RepSwitcher";

const LINKS = [
  { href: "/dashboard", label: "ダッシュボード" },
  { href: "/customers", label: "顧客一覧" },
  { href: "/products", label: "商品カタログ" },
  { href: "/affinity", label: "得意分野" },
];

export function AppNav() {
  const pathname = usePathname();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // ページ遷移したら自動でサイドバーを閉じる
  useEffect(() => {
    setIsSidebarOpen(false);
  }, [pathname]);

  if (pathname === "/login") {
    return null;
  }

  return (
    <>
      <header className="app-header">
        <div className="app-header__inner">
          <button
            type="button"
            className="app-header__menu-button"
            aria-label="メニューを開く"
            aria-expanded={isSidebarOpen}
            onClick={() => setIsSidebarOpen(true)}
          >
            <span />
            <span />
            <span />
          </button>
          <span className="app-nav__brand">AI WORK PARTNER</span>
          <RepSwitcher />
        </div>
      </header>

      <div
        className={`app-sidebar-overlay${isSidebarOpen ? " is-open" : ""}`}
        onClick={() => setIsSidebarOpen(false)}
        aria-hidden="true"
      />

      <aside className={`app-sidebar${isSidebarOpen ? " is-open" : ""}`}>
        <div className="app-sidebar__header">
          <span className="app-nav__brand">AI WORK PARTNER</span>
          <button
            type="button"
            className="app-sidebar__close"
            aria-label="メニューを閉じる"
            onClick={() => setIsSidebarOpen(false)}
          >
            ×
          </button>
        </div>
        <nav className="app-sidebar__links">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={pathname?.startsWith(link.href) ? "is-active" : undefined}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </aside>

      <QuickAddFab />
    </>
  );
}
