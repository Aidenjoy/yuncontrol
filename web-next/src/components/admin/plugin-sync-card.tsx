"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import { ChevronDown, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field"
import { Progress } from "@/components/ui/progress"
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible"
import { apiClient } from "@/lib/api"

type SyncState = {
  jobId: string | null
  status: "idle" | "running" | "completed" | "failed"
  source: string | null
  total: number
  processed: number
  created: number
  updated: number
  unchanged: number
  skipped: number
  failed: number
  errors: string[]
}

/** Compact metadata-only synchronization; recover progress without starting work on page load. */
export function PluginSyncCard({
  token,
  onComplete,
}: {
  token: string
  onComplete: () => Promise<void>
}) {
  const t = useTranslations("pluginAdmin")
  const [state, setState] = useState<SyncState | null>(null)
  const [starting, setStarting] = useState(false)
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [url, setUrl] = useState("https://deepseek1024.com/api/v2/plugins")
  const [error, setError] = useState("")
  const [pollError, setPollError] = useState("")
  const complete = useRef(onComplete)
  const startingRef = useRef(false)
  const lastJob = useRef<string | null>(null)
  complete.current = onComplete
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    /** Poll sequentially and refresh the page only once when a job finishes. */
    async function poll() {
      try {
        const next = await apiClient.get<SyncState>("/admin/plugins/sync", {
          token,
          cache: "no-store",
        })
        if (!active) return
        setState(next)
        setPollError("")
        if (
          next.jobId &&
          next.status !== "running" &&
          next.jobId !== lastJob.current
        ) {
          lastJob.current = next.jobId
          setExpanded(false)
          await complete.current()
        }
      } catch (cause) {
        if (active)
          setPollError(
            cause instanceof Error ? cause.message : t("sync.progressFailed"),
          )
      } finally {
        if (active) timer = setTimeout(() => void poll(), 2000)
      }
    }
    void poll()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [token, t])
  /** Guard rapid submissions; validate the address before dispatching the existing sync API. */
  async function start() {
    if (startingRef.current || !state || state.status === "running") return
    try {
      const parsed = new URL(url.trim())
      if (
        parsed.protocol !== "https:" ||
        parsed.username ||
        parsed.password ||
        parsed.hash ||
        (parsed.port && parsed.port !== "443")
      )
        throw new Error()
    } catch {
      setError(t("sync.urlInvalid"))
      return
    }
    startingRef.current = true
    setStarting(true)
    setError("")
    try {
      setState(
        await apiClient.post<SyncState>(
          "/admin/plugins/sync",
          { url: url.trim() },
          { token },
        ),
      )
      setOpen(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("sync.startFailed"))
    } finally {
      startingRef.current = false
      setStarting(false)
    }
  }
  return (
    <section className="rounded-lg border bg-card p-4">
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <div className="flex flex-wrap items-center gap-3">
          <RefreshCw className="size-4 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-medium">{t("sync.title")}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {state ? t(`sync.${state.status}`) : t("loading")}
              {state?.source
                ? ` · ${state.source === "custom" ? t("customSource") : state.source}`
                : " · 1024Store / dshfind / YunWork"}
            </p>
          </div>
          {state?.jobId ? (
            <CollapsibleTrigger asChild>
              <Button size="sm" variant="ghost">
                {t("sync.details")}
                <ChevronDown data-icon="inline-end" />
              </Button>
            </CollapsibleTrigger>
          ) : null}
          <Button
            variant="outline"
            disabled={!state || starting || state.status === "running"}
            onClick={() => {
              setError("")
              setOpen(true)
            }}
          >
            {state?.status === "running" ? t("sync.running") : t("sync.action")}
          </Button>
        </div>
        {state?.status === "running" ? (
          <div role="status" className="mt-3 flex flex-col gap-1">
            <Progress
              aria-label={t("sync.progress")}
              value={
                state.total
                  ? Math.min(100, (state.processed / state.total) * 100)
                  : 0
              }
            />
            <span className="text-xs text-muted-foreground">
              {t("sync.processed", {
                processed: state.processed,
                total: state.total,
              })}
            </span>
          </div>
        ) : null}
        <CollapsibleContent className="pt-3">
          {state ? (
            <div className="flex flex-wrap gap-x-5 gap-y-2 border-t pt-3 text-xs text-muted-foreground">
              {(
                [
                  "created",
                  "updated",
                  "unchanged",
                  "skipped",
                  "failed",
                ] as const
              ).map((key) => (
                <span key={key}>
                  {t(`sync.${key === "failed" ? "failedCount" : key}`, {
                    count: state[key],
                  })}
                </span>
              ))}
            </div>
          ) : null}
        </CollapsibleContent>
      </Collapsible>
      {state?.errors.map((message, index) => (
        <p key={index} role="alert" className="mt-2 text-xs text-destructive">
          {message}
        </p>
      ))}
      {error && !open ? (
        <p role="alert" className="mt-2 text-xs text-destructive">
          {error}
        </p>
      ) : null}
      {pollError ? (
        <p role="alert" className="mt-2 text-xs text-destructive">
          {pollError}
        </p>
      ) : null}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!starting) setOpen(next)
        }}
      >
        <DialogContent className="plugin-admin">
          <form
            className="flex flex-col gap-6"
            onSubmit={(event) => {
              event.preventDefault()
              void start()
            }}
          >
            <DialogHeader>
              <DialogTitle>{t("sync.title")}</DialogTitle>
              <DialogDescription>{t("sync.description")}</DialogDescription>
            </DialogHeader>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="plugin-catalog-url">
                  {t("sync.url")}
                </FieldLabel>
                <Input
                  id="plugin-catalog-url"
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  required
                  disabled={starting}
                  autoFocus
                />
                <FieldDescription>{t("sync.urlHint")}</FieldDescription>
              </Field>
            </FieldGroup>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={starting}
                onClick={() =>
                  setUrl("https://deepseek1024.com/api/v2/plugins")
                }
              >
                1024Store
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={starting}
                onClick={() => setUrl("https://api.dshfind.com/v1/catalog")}
              >
                dshfind
              </Button>
            </div>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={starting}
                onClick={() => setOpen(false)}
              >
                {t("cancel")}
              </Button>
              <Button type="submit" disabled={starting || !url.trim()}>
                {starting ? t("saving") : t("sync.fetch")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  )
}
