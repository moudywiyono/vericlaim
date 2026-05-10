import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import NavLinks from "@/components/NavLinks";

const geist = Geist({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "VeriClaim — Officer Dashboard",
  description: "Insurance claims review dashboard for officers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geist.className} min-h-screen`} style={{ background: "var(--bg)", color: "var(--text)" }}>
        <div className="flex h-screen overflow-hidden">
          <aside className="w-56 flex flex-col shrink-0"
            style={{ background: "var(--sidebar-bg)", color: "var(--sidebar-text)" }}>
            <div className="px-5 py-5 border-b" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 bg-blue-500 rounded-md flex items-center justify-center text-xs font-bold text-white">V</div>
                <span className="font-semibold text-sm text-white">VeriClaim</span>
              </div>
              <p className="text-xs mt-1" style={{ color: "var(--sidebar-text)" }}>Officer Dashboard</p>
            </div>

            <NavLinks />

            <div className="px-5 py-4 border-t" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
              <p className="text-xs" style={{ color: "var(--sidebar-text)", opacity: 0.5 }}>Officer</p>
            </div>
          </aside>

          <main className="flex-1 overflow-y-auto" style={{ background: "var(--bg)" }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
