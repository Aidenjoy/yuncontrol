"use client"

import * as React from "react"
import { createPortal } from "react-dom"
import { useTranslations } from "next-intl"
import { X } from "lucide-react"

import { App as Onboarding } from "@/components/onboarding/reference/app"
import "@/components/onboarding/reference/styles/onboarding.css"
import type { ConnectorView } from "@/features/dashboard/types"

/**
 * Replayable walkthrough of the onboarding flow from inside the app.
 *
 * The guide is presentation only: the device it shows is a fixture, no request
 * is made, and closing it never records progress, so it can be opened again as
 * often as needed.
 */
export function OnboardingGuideOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useTranslations("agentReminder")
  const [mounted, setMounted] = React.useState(false)
  // Bumped on every open so the flow restarts at the welcome slide.
  const [run, setRun] = React.useState(0)
  // Held in a ref: a parent re-render must not restart the flow mid-walkthrough.
  const closeRef = React.useRef(onClose)
  closeRef.current = onClose

  React.useEffect(() => { setMounted(true) }, [])

  React.useEffect(() => {
    if (!open) return
    setRun((value) => value + 1)
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") closeRef.current() }
    document.addEventListener("keydown", onKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  if (!mounted || !open) return null

  const connector: ConnectorView = {
    id: "onboarding-guide",
    userId: "onboarding-guide",
    name: t("guideDemoDevice"),
    deviceOs: "macos",
    connectorKind: "desktop",
    status: "online",
    lastSeenAt: null,
    createdAt: "",
    updatedAt: "",
  }

  return createPortal(
    <div className="fixed inset-0 z-[100] bg-background" role="dialog" aria-modal="true" aria-label={t("guideTitle")}>
      <div className="onboarding-viewport h-full">
        <Onboarding
          key={run}
          demo
          connector={connector}
          token=""
          userId="onboarding-guide"
          initialPage={0}
          onPageChange={() => undefined}
          onComplete={onClose}
        />
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label={t("guideClose")}
        className="absolute right-4 top-4 z-10 flex size-9 items-center justify-center rounded-full border border-border/60 bg-background/80 text-muted-foreground backdrop-blur transition hover:text-foreground"
      >
        <X className="size-4" />
      </button>
    </div>,
    document.body,
  )
}
