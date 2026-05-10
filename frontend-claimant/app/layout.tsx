import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import NavLinks from "@/components/NavLinks";
import Link from "next/link";

const geist = Geist({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "VeriClaim — File a Claim",
  description: "Submit your insurance claim with photos, documents, and a voice statement",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geist.className} min-h-screen`}
        style={{ background: "var(--bg)", color: "var(--text)" }}>
        <header className="sticky top-0 z-50 border-b bg-white"
          style={{ borderColor: "var(--border)" }}>
          <div className="max-w-5xl mx-auto px-5 py-3.5 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-xs">V</div>
              <span className="font-semibold text-sm" style={{ color: "var(--text)" }}>VeriClaim</span>
            </Link>
            <NavLinks />
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
