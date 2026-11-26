"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuth } from "@/components/auth/auth-context"
import { PageHeader } from "@/components/pages/page-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Field, FieldLabel } from "@/components/ui/field"
import { apiClient } from "@/lib/api"

type CatalogItem = { id: string; name: string; displayName: string; summary: string; latestVersion: string; package?: { registry: "npm"; name: string }; categories?: string[]; keywords?: string[] }
type Entry = { id: string; status: "draft" | "published"; item: CatalogItem }
type CatalogPage = { items: Entry[]; total: number }
const example: CatalogItem = { id: "my-plugin", name: "dsh-plugin-example", displayName: "我的插件", summary: "插件说明", latestVersion: "1.0.0", package: { registry: "npm", name: "dsh-plugin-example" }, categories: ["tools"] }

/** Manage the standard catalog metadata; installation remains entirely in YunWork. */
export function PluginsPage() {
  const { session } = useAuth()
  const token = session?.accessToken
  const [page, setPage] = useState<CatalogPage>({ items: [], total: 0 })
  const [q, setQ] = useState("")
  const [category, setCategory] = useState("")
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [editor, setEditor] = useState<Entry | "new" | "import" | null>(null)
  const [text, setText] = useState("")
  const [remove, setRemove] = useState<Entry | null>(null)
  const load = useCallback(async () => {
    if (!token) return
    const params = new URLSearchParams({ q, category, offset: String(offset), limit: "25" })
    setPage(await apiClient.get<CatalogPage>(`/admin/plugins?${params}`, { token, cache: "no-store" }))
  }, [token, q, category, offset])
  useEffect(() => {
    let active = true
    if (!token) return
    const params = new URLSearchParams({ q, category, offset: String(offset), limit: "25" })
    apiClient.get<CatalogPage>(`/admin/plugins?${params}`, { token, cache: "no-store" })
      .then(value => { if (active) { setPage(value); setError("") } })
      .catch(() => { if (active) setError("加载插件失败") })
    return () => { active = false }
  }, [token, q, category, offset])

  /** Keep failed operations visible and refresh from the server after every mutation. */
  async function mutate(action: () => Promise<unknown>) {
    if (busy) return
    setBusy(true); setError("")
    try { await action(); await load(); setEditor(null); setRemove(null) }
    catch (cause) { setError(cause instanceof Error ? cause.message : "操作失败") }
    finally { setBusy(false) }
  }

  /** Import standard provider pages or an items array; never accept publication flags. */
  async function save() {
    if (!token || !editor) return
    await mutate(async () => {
      const value = JSON.parse(text) as CatalogItem | CatalogItem[] | { items: CatalogItem[] }
      if (editor === "import") {
        const items = Array.isArray(value) ? value : "items" in value ? value.items : null
        if (!items) throw new Error("请输入标准目录页或插件数组")
        return apiClient.post("/admin/plugins/import", { items: items.map(item => ({ item })) }, { token })
      }
      return editor === "new"
        ? apiClient.post("/admin/plugins", { item: value }, { token })
        : apiClient.put(`/admin/plugins/${editor.id}`, { item: value }, { token })
    })
  }

  return <ScrollArea className="h-full w-full bg-background">
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-8 pb-16 pt-14">
      <PageHeader title="插件管理" description="管理云大师Agent插件目录。新插件默认不上架；仅上架插件会出现在自有市场中。" />
      {error ? <p role="alert" className="text-destructive">{error}</p> : null}
      <div className="flex flex-wrap gap-3">
        <Input aria-label="搜索插件" placeholder="搜索名称或说明" value={q} onChange={e => { setQ(e.target.value); setOffset(0) }} />
        <Input aria-label="插件分类" placeholder="分类，例如 tools" value={category} onChange={e => { setCategory(e.target.value); setOffset(0) }} />
        <Button disabled={busy} onClick={() => { setEditor("new"); setText(JSON.stringify(example, null, 2)) }}>新增插件</Button>
        <Button variant="outline" disabled={busy} onClick={() => { setEditor("import"); setText(JSON.stringify({ items: [example] }, null, 2)) }}>导入目录</Button>
      </div>
      <div className="divide-y rounded-lg border">
        {page.items.map(entry => <div key={entry.id} className="flex flex-wrap items-center gap-4 p-4">
          <div className="min-w-0 flex-1"><p className="font-medium">{entry.item.displayName}</p><p className="text-sm text-muted-foreground">{entry.item.package?.name ?? entry.item.name} · {entry.item.latestVersion}</p><p className="text-sm">{entry.item.summary}</p></div>
          <Field orientation="horizontal"><FieldLabel htmlFor={`plugin-${entry.id}`}>{entry.status === "published" ? "已上架" : "未上架"}</FieldLabel><Switch id={`plugin-${entry.id}`} checked={entry.status === "published"} disabled={busy} onCheckedChange={checked => token && void mutate(() => apiClient.patch(`/admin/plugins/${entry.id}`, { status: checked ? "published" : "draft" }, { token }))} /></Field>
          <Button variant="outline" disabled={busy} onClick={() => { setEditor(entry); setText(JSON.stringify(entry.item, null, 2)) }}>编辑</Button>
          <Button variant="destructive" disabled={busy} onClick={() => setRemove(entry)}>删除</Button>
        </div>)}
        {page.items.length === 0 ? <p className="p-6 text-muted-foreground">暂无插件</p> : null}
      </div>
      <div className="flex items-center justify-between"><span>共 {page.total} 个</span><div className="flex gap-2"><Button variant="outline" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 25))}>上一页</Button><Button variant="outline" disabled={offset + 25 >= page.total || busy} onClick={() => setOffset(offset + 25)}>下一页</Button></div></div>
    </div>
    <Dialog open={editor !== null} onOpenChange={open => { if (!open && !busy) setEditor(null) }}><DialogContent className="max-h-[90dvh] overflow-auto"><DialogHeader><DialogTitle>{editor === "import" ? "导入插件目录" : "插件资料"}</DialogTitle><DialogDescription>使用 YunWork 标准插件 JSON。插件 ID 创建后不能更改。导入更新已有资料，保留已有上架开关，新记录默认关闭。</DialogDescription></DialogHeader><Field><FieldLabel htmlFor="plugin-json">目录 JSON</FieldLabel><Textarea id="plugin-json" className="min-h-80 font-mono" value={text} onChange={e => setText(e.target.value)} /></Field>{error ? <p role="alert" className="text-destructive">{error}</p> : null}<Button disabled={busy} onClick={() => void save()}>保存</Button></DialogContent></Dialog>
    <Dialog open={remove !== null} onOpenChange={open => { if (!open && !busy) setRemove(null) }}><DialogContent><DialogHeader><DialogTitle>删除插件</DialogTitle><DialogDescription>确认删除「{remove?.item.displayName}」？删除后将立即从自有市场查询结果中移除，不会卸载用户已安装的插件。</DialogDescription></DialogHeader><Button variant="destructive" disabled={busy} onClick={() => token && remove && void mutate(() => apiClient.delete(`/admin/plugins/${remove.id}`, { token }))}>确认删除</Button></DialogContent></Dialog>
  </ScrollArea>
}
