import type { Metadata } from "next"

import { PrivacyPolicyScreen } from "@/components/pages/privacy-policy-screen"

export const metadata: Metadata = {
  title: "Privacy policy · 云大师Agent",
  description:
    "How the 云大师Agent web and desktop clients handle information.",
}

export default function PrivacyPage() {
  return <PrivacyPolicyScreen />
}
