"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const LINKS = [
  { href: "/",        label: "Overview"     },
  { href: "/review",  label: "Review Queue" },
  { href: "/history", label: "History"      },
];

export default function NavLinks() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const from = searchParams.get("from");

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    // Detail page (/review/CLM-xxx) belongs to whichever tab it was opened from
    if (pathname.startsWith("/review/")) {
      if (href === "/history") return from === "history";
      if (href === "/review")  return from !== "history";
    }
    return pathname.startsWith(href);
  };

  return (
    <nav className="flex-1 px-3 py-4 space-y-1">
      {LINKS.map(({ href, label }) => {
        const active = isActive(href);
        return (
          <Link key={href} href={href}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors"
            style={{
              background: active ? "rgba(255,255,255,0.12)" : "transparent",
              color: active ? "#ffffff" : "var(--sidebar-text)",
              fontWeight: active ? 600 : 400,
            }}>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
