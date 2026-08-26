"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { QuickAddFab } from "@/components/QuickAddFab";
import { RepSwitcher } from "@/components/RepSwitcher";
import { useRep } from "@/lib/repContext";

const ICON_PROPS = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const LINKS = [
  {
    href: "/dashboard",
    label: "ダッシュボード",
    icon: (
      <svg {...ICON_PROPS}>
        <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
        <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
        <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
        <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
      </svg>
    ),
  },
  {
    href: "/customers",
    label: "顧客一覧",
    icon: (
      <svg {...ICON_PROPS}>
        <circle cx="12" cy="8" r="3.2" />
        <path d="M5 20c0-3.6 3.1-6.2 7-6.2s7 2.6 7 6.2" />
      </svg>
    ),
  },
  {
    href: "/products",
    label: "商品カタログ",
    icon: (
      <svg {...ICON_PROPS}>
        <path d="M3.5 7.2 12 3.5l8.5 3.7L12 11 3.5 7.2Z" />
        <path d="M3.5 7.2v9.6L12 20.5l8.5-3.7V7.2" />
        <path d="M12 11v9.5" />
      </svg>
    ),
  },
  {
    href: "/affinity",
    label: "得意分野",
    icon: (
      <svg {...ICON_PROPS}>
        <path d="M12 3.2 14.6 9l6.4.6-4.9 4.2 1.5 6.2L12 16.9l-5.6 3.1 1.5-6.2-4.9-4.2L9.4 9 12 3.2Z" />
      </svg>
    ),
  },
];

export function AppNav() {
  const pathname = usePathname();
  const { selectedRep } = useRep();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const repInitial = selectedRep?.rep_name?.charAt(0) || "A";

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
          <span className="app-nav__brand app-header__brand">AI WORK PARTNER</span>
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
          <span className="app-sidebar__logo" aria-hidden="true">
            {repInitial}
          </span>
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
              <span className="app-sidebar__icon">{link.icon}</span>
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="app-sidebar__footer">
          <span className="app-sidebar__status-dot" aria-hidden="true" />
          SYSTEM ONLINE
        </div>
      </aside>

      <QuickAddFab />
    </>
  );
}
