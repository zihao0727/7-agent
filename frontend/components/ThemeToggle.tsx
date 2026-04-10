"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
      title={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
    >
      <Sun
        className="pointer-events-none absolute left-1/2 top-1/2 h-[1.2rem] w-[1.2rem] -translate-x-1/2 -translate-y-1/2 rotate-0 scale-100 opacity-100 transition-all dark:-rotate-90 dark:scale-0 dark:opacity-0"
        aria-hidden
      />
      <Moon
        className="pointer-events-none absolute left-1/2 top-1/2 h-[1.2rem] w-[1.2rem] -translate-x-1/2 -translate-y-1/2 rotate-90 scale-0 opacity-0 transition-all dark:rotate-0 dark:scale-100 dark:opacity-100"
        aria-hidden
      />
      <span className="sr-only">切换主题</span>
    </button>
  );
}
