import type { Metadata } from "next"

import { PrivacyPolicyScreen } from "@/components/pages/privacy-policy-screen"

export const metadata: Metadata = {
  title: "Privacy policy · YunDaShi Agent",
  description:
    "How the YunDaShi Agent web and desktop clients handle information.",
}

export default function PrivacyPage() {
  return <PrivacyPolicyScreen />
}
