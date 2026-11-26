"use client"

import { useTranslations } from "next-intl"

import { runtimeLabel } from "./session-utils"

/**
 * Runtime labels for a React tree. Only the yunwork entry is a product brand, so
 * it follows the UI language while the other runtime names stay as they are.
 */
export function useRuntimeLabel() {
  const t = useTranslations("app")
  const brandName = t("name")
  return (runtime: string) => runtimeLabel(runtime, { brandName })
}
