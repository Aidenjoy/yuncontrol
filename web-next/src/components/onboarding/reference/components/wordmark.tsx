"use client"

import { useTranslations } from "next-intl"

import { BrandMark } from "@/components/brand-mark"

export function Wordmark() {
  const t = useTranslations("app")
  return <span className="aa-wordmark hidden items-center gap-2 text-xl md:inline-flex"><BrandMark />{t("name")}</span>
}
