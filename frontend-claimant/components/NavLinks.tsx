"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function NavLinks() {
  const pathname = usePathname();
  const isSubmit = pathname === "/submit";
  const isCheck  = pathname === "/check";

  return (
    <div className="flex items-center gap-2">
      <Link href="/submit"
        className="text-sm font-medium px-4 py-1.5 rounded-lg transition-colors"
        style={{
          background: isSubmit ? "#2563eb" : "transparent",
          color: isSubmit ? "#ffffff" : "var(--text-muted)",
          border: isSubmit ? "1px solid transparent" : "1px solid var(--border)",
        }}>
        File a Claim
      </Link>
      <Link href="/check"
        className="text-sm font-medium px-4 py-1.5 rounded-lg transition-colors"
        style={{
          background: isCheck ? "#2563eb" : "transparent",
          color: isCheck ? "#ffffff" : "var(--text-muted)",
          border: isCheck ? "1px solid transparent" : "1px solid var(--border)",
        }}>
        Check Progress
      </Link>
    </div>
  );
}
