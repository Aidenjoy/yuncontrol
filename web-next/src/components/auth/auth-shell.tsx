"use client"

import { BrandMark } from "@/components/brand-mark"

import { LocaleSwitcher } from "@/components/locale-switcher"

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh flex-col overflow-y-auto bg-background">
      {/* Top nav */}
      <header className="flex shrink-0 items-center justify-between px-8 py-5">
        <span className="aa-wordmark hidden items-center gap-2 text-xl md:inline-flex"><BrandMark className="mr-2" />云大师Agent</span>
        <nav className="flex items-center gap-4 text-sm text-muted-foreground">
          <LocaleSwitcher size="sm" variant="ghost" className="text-foreground" />
        </nav>
      </header>

      {/* Centered content */}
      <main className="flex flex-1 shrink-0 items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          {children}
        </div>
      </main>
    </div>
  )
}
