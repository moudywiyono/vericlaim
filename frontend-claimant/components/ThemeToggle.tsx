"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return <div className="w-9 h-9" />;

  const isDark = theme === "dark";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label="Toggle theme"
      className="w-9 h-9 rounded-lg flex items-center justify-center text-lg transition-colors
        hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400"
    >
      {isDark ? "☀️" : "🌙"}
    </button>
  );
}
