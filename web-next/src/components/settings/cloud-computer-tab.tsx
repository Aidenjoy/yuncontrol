"use client"

import * as React from "react"
import { Cloud, RefreshCw, Trash2 } from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { SettingsSection } from "@/components/settings/settings-section"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { cloudComputerApi, type CloudComputerStatus } from "@/features/cloud-computer/api"
import {
  provisioningProgress,
  resolveCloudComputerProgress,
  type CloudComputerProgress,
  type CloudComputerProgressStage,
} from "@/features/cloud-computer/progress"

const POLL_INTERVAL_MS = 2500

type BusyOperation = "enabling" | "disabling" | null

export function CloudComputerTab({
  token,
  onWorkspaceRefresh,
}: {
  token: string
  onWorkspaceRefresh: () => Promise<void> | void
}) {
  const t = useTranslations("pages.settings")
  const [progress, setProgress] = React.useState<CloudComputerProgress | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState<BusyOperation>(null)
  const [reloadVersion, setReloadVersion] = React.useState(0)
  const [closeOpen, setCloseOpen] = React.useState(false)
  const refreshWorkspaceRef = React.useRef(onWorkspaceRefresh)
  refreshWorkspaceRef.current = onWorkspaceRefresh

  React.useEffect(() => {
    if (!token) {
      setLoading(false)
      setError(t("cloudComputerLoadFailed"))
      return
    }

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const status = await cloudComputerApi.get(token)
        if (cancelled) return
        const next = await resolveCloudComputerProgress(token, status)
        if (cancelled) return
        setProgress(next)
        setError(next.status.error)
        setLoading(false)
        if (next.stage === "ready") {
          void Promise.resolve(refreshWorkspaceRef.current()).catch(() => {})
          return
        }
        if (next.stage !== "disabled" && next.stage !== "error") {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (cause) {
        if (cancelled) return
        setLoading(false)
        setError(errorMessage(cause, t("cloudComputerLoadFailed")))
      }
    }

    setLoading(true)
    setError(null)
    void poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [reloadVersion, t, token])

  const enable = async () => {
    if (busy) return
    setBusy("enabling")
    setError(null)
    setProgress((current) => provisioningProgress(current?.status ?? disabledStatus()))
    try {
      await cloudComputerApi.enable(token)
    } catch (cause) {
      setError(errorMessage(cause, t("cloudComputerEnableFailed")))
    } finally {
      setBusy(null)
      setReloadVersion((version) => version + 1)
    }
  }

  const disable = async () => {
    if (busy) return
    setBusy("disabling")
    setError(null)
    try {
      const status = await cloudComputerApi.disable(token)
      setProgress({ status, stage: "disabled", runtime: null })
      setCloseOpen(false)
      await refreshWorkspaceRef.current()
      toast.success(t("cloudComputerDisabled"))
    } catch (cause) {
      setError(errorMessage(cause, t("cloudComputerDisableFailed")))
    } finally {
      setBusy(null)
    }
  }

  const status = progress?.status ?? null
  const ready = progress?.stage === "ready"
  const pending = loading || busy !== null || (
    progress !== null && !["disabled", "ready", "error"].includes(progress.stage)
  )
  const description = statusDescription(t, progress, busy, loading)
  const switchDisabled = !token
    || !status?.configured
    || busy !== null
    || loading
    || (status.phase !== "disabled" && !ready)

  return (
    <div className="flex flex-col gap-4">
      <SettingsSection
        title={t("cloudComputer")}
        description={t("cloudComputerDescription")}
        action={(
          <Badge variant={progress?.stage === "error" || error ? "destructive" : "secondary"}>
            {pending ? <Spinner /> : null}
            {statusLabel(t, progress?.stage ?? null, busy, loading, error)}
          </Badge>
        )}
      >
        <FieldGroup>
          <Field orientation="horizontal" data-disabled={switchDisabled || undefined}>
            <FieldContent>
              <FieldLabel htmlFor="cloud-computer-enabled">{t("cloudComputerEnable")}</FieldLabel>
              <FieldDescription id="cloud-computer-description">{description}</FieldDescription>
            </FieldContent>
            <Switch
              id="cloud-computer-enabled"
              checked={ready}
              disabled={switchDisabled}
              aria-describedby="cloud-computer-description"
              onCheckedChange={(checked) => {
                if (checked) void enable()
                else setCloseOpen(true)
              }}
            />
          </Field>
        </FieldGroup>
      </SettingsSection>

      {status && !status.configured ? (
        <Alert>
          <Cloud />
          <AlertTitle>{t("cloudComputerNotConfiguredTitle")}</AlertTitle>
          <AlertDescription>{t("cloudComputerNotConfiguredDescription")}</AlertDescription>
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>{t("cloudComputerErrorTitle")}</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2 w-fit"
            disabled={busy !== null}
            onClick={() => setReloadVersion((version) => version + 1)}
          >
            <RefreshCw data-icon="inline-start" />
            {t("cloudComputerRetry")}
          </Button>
        </Alert>
      ) : null}

      <SettingsSection
        title={t("cloudComputerDataTitle")}
        description={t("cloudComputerDataDescription")}
      />

      <AlertDialog
        open={closeOpen}
        onOpenChange={(open) => {
          if (busy !== "disabling") setCloseOpen(open)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("cloudComputerDisableTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("cloudComputerDisableDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy === "disabling"}>
              {t("cloudComputerCancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={busy === "disabling"}
              onClick={(event) => {
                event.preventDefault()
                void disable()
              }}
            >
              {busy === "disabling" ? <Spinner /> : <Trash2 data-icon="inline-start" />}
              {t("cloudComputerDisableConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function disabledStatus(): CloudComputerStatus {
  return {
    configured: true,
    phase: "disabled",
    containerState: "missing",
    connectorId: null,
    displayName: "云电脑",
    updatedAt: null,
    error: null,
  }
}

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback
}

function statusLabel(
  t: ReturnType<typeof useTranslations>,
  stage: CloudComputerProgressStage | null,
  busy: BusyOperation,
  loading: boolean,
  error: string | null,
): string {
  if (busy === "enabling") return t("cloudComputerProvisioning")
  if (busy === "disabling") return t("cloudComputerDisabling")
  if (loading && !stage) return t("cloudComputerChecking")
  if (error || stage === "error") return t("cloudComputerError")
  if (stage === "ready") return t("cloudComputerOn")
  if (stage === "connector") return t("cloudComputerWaitingConnector")
  if (stage === "runtime") return t("cloudComputerWaitingRuntime")
  if (stage === "provisioning") return t("cloudComputerProvisioning")
  return t("cloudComputerOff")
}

function statusDescription(
  t: ReturnType<typeof useTranslations>,
  progress: CloudComputerProgress | null,
  busy: BusyOperation,
  loading: boolean,
): string {
  if (busy === "enabling") return t("cloudComputerEnablingDescription")
  if (busy === "disabling") return t("cloudComputerDisablingDescription")
  if (loading && !progress) return t("cloudComputerCheckingDescription")
  if (progress?.status.error) return progress.status.error
  switch (progress?.stage) {
    case "ready": return t("cloudComputerReadyDescription")
    case "connector": return t("cloudComputerConnectorDescription")
    case "runtime": return t("cloudComputerRuntimeDescription")
    case "provisioning": return t("cloudComputerProvisioningDescription")
    case "error": return t("cloudComputerErrorDescription")
    default: return t("cloudComputerDisabledDescription")
  }
}
