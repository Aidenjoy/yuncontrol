"use client"

import { useTranslations } from "next-intl"
import { ArrowRightIcon, CheckIcon, DownloadIcon } from "lucide-react"
import { SlideFrame } from "@/components/onboarding/reference/components/slide-frame"
import { Button } from "@/components/onboarding/reference/components/ui/button"
import { onboarding } from "@/components/onboarding/reference/lib/onboarding"

export function CompleteSlide({ onExperience, showDownload = false }: {
  onExperience: (trigger: HTMLButtonElement) => void
  /** Hidden by default: the desktop download page is not published yet. */
  showDownload?: boolean
}) {
  const t = useTranslations("app")
  return (
    <SlideFrame
      id="complete"
      title={"You are\nall set."} englishTitle
      titleSuffix={<CheckIcon className="completion-check" strokeWidth={2.1} />}
      description={`点击「立刻体验」，\n开始使用 ${t("name")}。`}
      actions={<>
        <Button size="lg" onClick={(event) => onExperience(event.currentTarget)}>立刻体验<ArrowRightIcon data-icon="inline-end" /></Button>
        {showDownload
          ? <Button variant="outline" size="lg" asChild><a href={onboarding.downloadsUrl} target="_blank" rel="noreferrer"><DownloadIcon data-icon="inline-start" />下载桌面程序</a></Button>
          : null}
      </>}
    />
  )
}
