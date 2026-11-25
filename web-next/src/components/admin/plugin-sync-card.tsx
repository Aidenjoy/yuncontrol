"use client"

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
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

const labels = { idle: "尚未同步", running: "同步中", completed: "同步完成", failed: "同步未完成，可重试" }

/** Trigger metadata synchronization explicitly and recover shared progress after navigation. */
export function PluginSyncCard({ token, onComplete }: { token: string; onComplete: () => Promise<void> }) {
  const [state, setState] = useState<SyncState | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState("")
  const complete = useRef(onComplete)
  const startingRef = useRef(false)
  const lastJob = useRef<string | null>(null)
  complete.current = onComplete

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    /** Poll sequentially even after transient failures; never start a job on page load. */
    async function poll() {
      try {
        const next = await apiClient.get<SyncState>("/admin/plugins/sync", { token, cache: "no-store" })
        if (!active) return
        setState(next); setError("")
        if (next.jobId && next.status !== "running" && next.jobId !== lastJob.current) {
          lastJob.current = next.jobId
          await complete.current()
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "获取同步进度失败")
      } finally {
        if (active) timer = setTimeout(() => void poll(), 2000)
      }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [token])

  /** Guard rapid clicks locally; the server arbitrates duplicate starts across administrators. */
  async function start() {
    if (startingRef.current || !state || state.status === "running") return
    startingRef.current = true
    setStarting(true); setError("")
    try {
      setState(await apiClient.post<SyncState>("/admin/plugins/sync", {}, { token }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "启动同步失败")
    } finally {
      startingRef.current = false
      setStarting(false)
    }
  }

  return <Card>
    <CardHeader>
      <CardTitle>插件目录同步</CardTitle>
      <CardDescription>从 YunWork 的 1024Store、dshfind 同步元数据。新插件默认下架，保留已有上下架状态；不下载插件。</CardDescription>
    </CardHeader>
    <CardContent className="flex flex-col gap-3">
      <Button className="self-start" disabled={!state || starting || state.status === "running"} onClick={() => void start()}>
        {starting || state?.status === "running" ? "正在同步插件目录…" : "同步插件目录"}
      </Button>
      {state ? <div role="status" className="flex flex-col gap-2">
        <p>{labels[state.status]}{state.status === "running" && state.source ? ` · ${state.source}` : ""}</p>
        <Progress aria-label="当前已发现目录的同步进度" value={state.total ? Math.min(100, state.processed / state.total * 100) : 0} />
        <p className="text-sm">已处理 {state.processed} / 总数 {state.total} · 新增 {state.created} · 更新 {state.updated} · 未变 {state.unchanged} · 跳过 {state.skipped} · 失败 {state.failed}</p>
        {state.status === "running" ? <p className="text-xs text-muted-foreground">总数随各来源读取逐步汇总，离开页面后继续同步。</p> : null}
      </div> : null}
      {state?.errors.map((message, index) => <p key={index} role="alert" className="text-sm text-destructive">{message}</p>)}
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    </CardContent>
  </Card>
}
