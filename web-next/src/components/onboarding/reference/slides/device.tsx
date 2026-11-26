import { useTranslations } from 'next-intl'
import { useState } from "react"
import { ArrowRightIcon, CheckIcon } from "lucide-react"
import { AgentSetupContent } from "@/components/agent-setup-content"
import { SlideFrame } from "@/components/onboarding/reference/components/slide-frame"
import { Button } from "@/components/onboarding/reference/components/ui/button"
import { onboarding, type SlideProps } from "@/components/onboarding/reference/lib/onboarding"

export function DeviceSlide({ connector, onNext, demo = false }: SlideProps & { connector: { id: string; name: string }; demo?: boolean }) {
  const t = useTranslations('agentReminder')
  const brand = useTranslations('app')
  // A replayed guide has no device to read, so the panel is illustrative and
  // never leaves the button disabled waiting on a request.
  const [busy, setBusy] = useState(!demo)
  return (
    <SlideFrame
      id="device"
      title={t('deviceConnected', { name: connector.name })}
      titleSuffix={<CheckIcon className="completion-check" strokeWidth={2.1} />}
      description={t('deviceDescription')}
      sideContent={<section className="onboarding-agent-panel" aria-labelledby="agent-setup-title">
        <h2 id="agent-setup-title">{t('configureAgent')}</h2>
        {demo
          ? <>
            <ul className="agent-list" aria-label={t('guideDemoAgentsLabel')}>
              {[brand('shortName'), ...onboarding.agents].map((name) => <li key={name}>{name}</li>)}
            </ul>
            <p className="text-sm leading-6 text-muted-foreground">{t('guideDemoAgents')}</p>
          </>
          : <AgentSetupContent connector={connector} presentation="onboarding" onContinue={onNext} onSkip={onNext} onBusyChange={setBusy} />}
      </section>}
      actions={<Button data-onboarding-next size="lg" disabled={busy} onClick={onNext}>{t('next')}<ArrowRightIcon data-icon="inline-end" /></Button>}
    />
  )
}
