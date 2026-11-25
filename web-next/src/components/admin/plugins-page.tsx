"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import {
  MoreHorizontal,
  Package,
  Plus,
  Upload,
  Search,
  ChevronLeft,
  ChevronRight,
} from "lucide-react"
import { useAuth } from "@/components/auth/auth-context"
import { PluginSyncCard } from "@/components/admin/plugin-sync-card"
import { PluginEditor } from "@/components/admin/plugin-editor"
import type { CatalogItem, Entry } from "@/features/plugin-catalog/editor"
import { PageHeader } from "@/components/pages/page-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table"
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { apiClient } from "@/lib/api"
import "./plugin-admin.css"

type CatalogPage = { items: Entry[]; total: number }
type Summary = {
  total: number
  published: number
  draft: number
  sourceCount: number
  categories: string[]
  sources: Record<string, string>
}
type Confirmation =
  | { kind: "delete"; entry: Entry }
  | { kind: "bulk"; status: "draft" | "published"; ids: string[] }

/** Server-paged administrator catalog; all publication operations remain explicit and confirmed. */
export function PluginsPage() {
  const t = useTranslations("pluginAdmin")
  const { session } = useAuth()
  const token = session?.accessToken
  const [page, setPage] = useState<CatalogPage>({ items: [], total: 0 })
  const [summary, setSummary] = useState<Summary | null>(null)
  const [q, setQ] = useState("")
  const [query, setQuery] = useState("")
  const [category, setCategory] = useState("all")
  const [source, setSource] = useState("all")
  const [status, setStatus] = useState("all")
  const [limit, setLimit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)
  const operation = useRef(false)
  const request = useRef(0)
  const [editor, setEditor] = useState<Entry | "new" | "import" | null>(null)
  const [details, setDetails] = useState<Entry | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(q)
      setOffset(0)
    }, 250)
    return () => clearTimeout(timer)
  }, [q])
  /** Load bounded records and independent SQL aggregates; discard responses from obsolete filters. */
  const load = useCallback(async () => {
    if (!token) return
    const id = ++request.current
    setLoading(true)
    setError("")
    const params = new URLSearchParams({
      q: query,
      limit: String(limit),
      offset: String(offset),
    })
    if (category !== "all") params.set("category", category)
    if (source !== "all") params.set("source", source)
    if (status !== "all") params.set("status", status)
    try {
      const [next, stats] = await Promise.all([
        apiClient.get<CatalogPage>(`/admin/plugins?${params}`, {
          token,
          cache: "no-store",
        }),
        apiClient.get<Summary>("/admin/plugins/summary", {
          token,
          cache: "no-store",
        }),
      ])
      if (id !== request.current) return
      if (offset && !next.items.length) {
        setOffset(Math.max(0, Math.ceil(next.total / limit) * limit - limit))
        return
      }
      setPage(next)
      setSummary(stats)
      setSelected(new Set())
    } catch (cause) {
      if (id === request.current)
        setError(cause instanceof Error ? cause.message : t("loadFailed"))
    } finally {
      if (id === request.current) setLoading(false)
    }
  }, [token, query, limit, offset, category, source, status, t])
  useEffect(() => {
    void load()
    return () => {
      request.current++
    }
  }, [load])
  /** Keep mutations serialized; failed writes remain visible without closing the editor. */
  async function mutate(action: () => Promise<unknown>, propagate = false) {
    if (operation.current) return
    operation.current = true
    setBusy(true)
    setNotice("")
    setError("")
    try {
      await action()
      await load()
      setNotice(t("saved"))
      setConfirmation(null)
      setEditor(null)
    } catch (cause) {
      if (propagate) throw cause
      setError(cause instanceof Error ? cause.message : t("saveFailed"))
    } finally {
      operation.current = false
      setBusy(false)
    }
  }
  /** Reuse existing create/edit/import contracts; publication is never sent with metadata. */
  async function save(items: CatalogItem[]) {
    if (!token || !editor) return
    await mutate(
      () =>
        editor === "import"
          ? apiClient.post(
              "/admin/plugins/import",
              { items: items.map((item) => ({ item })) },
              { token },
            )
          : editor === "new"
            ? apiClient.post("/admin/plugins", { item: items[0] }, { token })
            : apiClient.put(
                `/admin/plugins/${editor.id}`,
                { item: items[0] },
                { token },
              ),
      true,
    )
  }
  const sourceLabel = (key: string, url?: string) =>
    key === "manual"
      ? t("manual")
      : key === "1024store"
        ? "1024Store"
        : key === "dshfind"
          ? "dshfind"
          : (() => {
              try {
                return new URL(url || summary?.sources[key] || "").hostname
              } catch {
                return t("customSource")
              }
            })()
  const allSelected =
    page.items.length > 0 && page.items.every((entry) => selected.has(entry.id))
  const filter = (setter: (value: string) => void, value: string) => {
    setter(value)
    setOffset(0)
    setSelected(new Set())
  }
  return (
    <TooltipProvider>
      <div className="plugin-admin h-full overflow-y-auto bg-background text-foreground">
        <div className="flex w-full flex-col gap-4 p-6">
          <PageHeader title={t("title")} description={t("description")}>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setEditor("import")}
            >
              <Upload data-icon="inline-start" />
              {t("import")}
            </Button>
            <Button disabled={busy} onClick={() => setEditor("new")}>
              <Plus data-icon="inline-start" />
              {t("new")}
            </Button>
          </PageHeader>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            {(["total", "published", "draft", "sourceCount"] as const).map(
              (key) => (
                <div key={key} className="rounded-lg border bg-card p-4">
                  <p className="text-xs text-muted-foreground">
                    {t(`stats.${key}`)}
                  </p>
                  <p className="mt-1 text-2xl font-semibold tabular-nums">
                    {summary ? summary[key].toLocaleString() : "—"}
                  </p>
                </div>
              ),
            )}
          </div>
          {token ? <PluginSyncCard token={token} onComplete={load} /> : null}
          {error ? (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-destructive/30 p-3 text-sm text-destructive"
            >
              <span>{error}</span>
              <Button variant="outline" onClick={() => void load()}>
                {t("retry")}
              </Button>
            </div>
          ) : null}
          {notice ? (
            <p role="status" className="text-sm text-muted-foreground">
              {notice}
            </p>
          ) : null}
          <section className="min-w-0 rounded-lg border bg-card">
            <div className="flex flex-col gap-3 border-b p-4">
              <Tabs
                value={status}
                onValueChange={(value) => filter(setStatus, value)}
              >
                <TabsList variant="line">
                  <TabsTrigger value="all">{t("allPlugins")}</TabsTrigger>
                  <TabsTrigger value="published">{t("published")}</TabsTrigger>
                  <TabsTrigger value="draft">{t("draft")}</TabsTrigger>
                </TabsList>
              </Tabs>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative min-w-48 flex-1">
                  <Search
                    aria-hidden
                    className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground"
                  />
                  <Input
                    className="h-9 pl-9"
                    aria-label={t("search")}
                    placeholder={t("search")}
                    value={q}
                    onChange={(event) => setQ(event.target.value)}
                  />
                </div>
                <Select
                  value={category}
                  onValueChange={(value) => filter(setCategory, value)}
                >
                  <SelectTrigger
                    className="h-9 w-44"
                    aria-label={t("categoryFilter")}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="all">{t("allCategories")}</SelectItem>
                      {summary?.categories.map((value) => (
                        <SelectItem key={value} value={value}>
                          {value}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <Select
                  value={source}
                  onValueChange={(value) => filter(setSource, value)}
                >
                  <SelectTrigger
                    className="h-9 w-44"
                    aria-label={t("sourceFilter")}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="all">{t("allSources")}</SelectItem>
                      <SelectItem value="manual">{t("manual")}</SelectItem>
                      {Object.entries(summary?.sources ?? {}).map(
                        ([key, url]) => (
                          <SelectItem key={key} value={key}>
                            {sourceLabel(key, url)}
                          </SelectItem>
                        ),
                      )}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
              {selected.size ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="mr-2 text-sm">
                    {t("selected", { count: selected.size })}
                  </span>
                  <Button
                    variant="outline"
                    disabled={busy || loading}
                    onClick={() =>
                      setConfirmation({
                        kind: "bulk",
                        status: "published",
                        ids: [...selected],
                      })
                    }
                  >
                    {t("bulkPublish")}
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy || loading}
                    onClick={() =>
                      setConfirmation({
                        kind: "bulk",
                        status: "draft",
                        ids: [...selected],
                      })
                    }
                  >
                    {t("bulkUnpublish")}
                  </Button>
                </div>
              ) : null}
            </div>
            <Table aria-busy={loading}>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12 pl-4">
                    <Checkbox
                      aria-label={t("selectPage")}
                      checked={
                        allSelected
                          ? true
                          : selected.size
                            ? "indeterminate"
                            : false
                      }
                      disabled={busy || loading || !page.items.length}
                      onCheckedChange={(checked) =>
                        setSelected(
                          checked
                            ? new Set(page.items.map((entry) => entry.id))
                            : new Set(),
                        )
                      }
                    />
                  </TableHead>
                  <TableHead>{t("plugin")}</TableHead>
                  <TableHead>{t("categoryFilter")}</TableHead>
                  <TableHead>{t("sourceFilter")}</TableHead>
                  <TableHead>{t("publication")}</TableHead>
                  <TableHead className="w-12">
                    <span className="sr-only">{t("actions")}</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="h-32 text-center text-muted-foreground"
                      role="status"
                    >
                      {t("loading")}
                    </TableCell>
                  </TableRow>
                ) : error && !page.items.length ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="h-32 text-center text-muted-foreground"
                    >
                      {t("loadFailed")}
                    </TableCell>
                  </TableRow>
                ) : page.items.length ? (
                  page.items.map((entry) => (
                    <TableRow key={entry.id} className="h-16">
                      <TableCell className="pl-4">
                        <Checkbox
                          aria-label={t("selectPlugin", {
                            name: entry.item.displayName,
                          })}
                          disabled={busy}
                          checked={selected.has(entry.id)}
                          onCheckedChange={(checked) =>
                            setSelected((current) => {
                              const next = new Set(current)
                              if (checked) next.add(entry.id)
                              else next.delete(entry.id)
                              return next
                            })
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <Avatar className="size-9 rounded-lg">
                            <AvatarImage
                              src={entry.item.media?.icon.url}
                              alt=""
                            />
                            <AvatarFallback className="rounded-lg">
                              <Package className="size-4" />
                            </AvatarFallback>
                          </Avatar>
                          <div className="min-w-0">
                            <button
                              className="block max-w-[min(30vw,420px)] truncate text-left font-medium hover:underline"
                              onClick={() => setDetails(entry)}
                            >
                              {entry.item.displayName}
                            </button>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <p
                                  className="max-w-[min(35vw,520px)] truncate text-xs text-muted-foreground"
                                  tabIndex={0}
                                >
                                  {entry.item.summary}
                                </p>
                              </TooltipTrigger>
                              <TooltipContent className="max-w-sm break-words">
                                {entry.item.summary}
                              </TooltipContent>
                            </Tooltip>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex max-w-48 flex-wrap gap-1">
                          {entry.item.categories?.map((value) => (
                            <Badge key={value} variant="secondary">
                              {value}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-muted-foreground">
                          {Object.entries(entry.origins ?? {})
                            .map(([key, origin]) =>
                              sourceLabel(key, origin.url),
                            )
                            .join(" · ") || t("manual")}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Switch
                            className="catalog-switch"
                            aria-label={t("publicationFor", {
                              name: entry.item.displayName,
                            })}
                            checked={entry.status === "published"}
                            disabled={busy}
                            onCheckedChange={(checked) =>
                              token &&
                              void mutate(() =>
                                apiClient.patch(
                                  `/admin/plugins/${entry.id}`,
                                  { status: checked ? "published" : "draft" },
                                  { token },
                                ),
                              )
                            }
                          />
                          <span
                            className={
                              entry.status === "published"
                                ? "catalog-live text-xs"
                                : "text-xs text-muted-foreground"
                            }
                          >
                            {t(entry.status)}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              aria-label={t("actionsFor", {
                                name: entry.item.displayName,
                              })}
                              disabled={busy}
                            >
                              <MoreHorizontal />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuGroup>
                              <DropdownMenuItem
                                onSelect={() => setEditor(entry)}
                              >
                                {t("edit")}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onSelect={() => setDetails(entry)}
                              >
                                {t("details")}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                variant="destructive"
                                onSelect={() =>
                                  setConfirmation({ kind: "delete", entry })
                                }
                              >
                                {t("delete")}
                              </DropdownMenuItem>
                            </DropdownMenuGroup>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className="h-40 text-center">
                      <Package className="mx-auto mb-2 size-6 text-muted-foreground" />
                      <p>{t("empty")}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t("emptyHint")}
                      </p>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t p-4 text-sm">
              <span className="text-muted-foreground">
                {t("totalResults", { count: page.total })}
              </span>
              <div className="flex items-center gap-2">
                <Select
                  value={String(limit)}
                  onValueChange={(value) => {
                    setLimit(Number(value))
                    setOffset(0)
                    setSelected(new Set())
                  }}
                >
                  <SelectTrigger
                    className="h-9 w-28"
                    aria-label={t("pageSize")}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {[20, 50, 100].map((size) => (
                        <SelectItem key={size} value={String(size)}>
                          {t("perPage", { count: size })}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label={t("previous")}
                  disabled={busy || loading || offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                >
                  <ChevronLeft />
                </Button>
                <span className="tabular-nums">
                  {Math.floor(offset / limit) + 1} /{" "}
                  {Math.max(1, Math.ceil(page.total / limit))}
                </span>
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label={t("next")}
                  disabled={busy || loading || offset + limit >= page.total}
                  onClick={() => setOffset(offset + limit)}
                >
                  <ChevronRight />
                </Button>
              </div>
            </div>
          </section>
        </div>
        {editor ? (
          <PluginEditor
            key={typeof editor === "string" ? editor : editor.id}
            entry={editor}
            categories={summary?.categories ?? []}
            onClose={() => setEditor(null)}
            onSave={save}
          />
        ) : null}
        <Sheet
          open={Boolean(details)}
          onOpenChange={(open) => {
            if (!open) setDetails(null)
          }}
        >
          <SheetContent className="plugin-admin data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
            <SheetHeader>
              <SheetTitle>{details?.item.displayName}</SheetTitle>
              <SheetDescription>{t("details")}</SheetDescription>
            </SheetHeader>
            <div className="overflow-auto px-6 pb-6">
              <Badge variant="secondary">{t(details?.status ?? "draft")}</Badge>
              <p className="my-4 text-sm">{details?.item.summary}</p>
              <pre className="overflow-auto rounded-lg border bg-muted p-4 text-xs">
                {JSON.stringify(details?.item, null, 2)}
              </pre>
            </div>
          </SheetContent>
        </Sheet>
        <Dialog
          open={Boolean(confirmation)}
          onOpenChange={(open) => {
            if (!open && !busy) setConfirmation(null)
          }}
        >
          <DialogContent className="plugin-admin">
            <DialogHeader>
              <DialogTitle>
                {confirmation?.kind === "delete"
                  ? t("delete")
                  : t(
                      confirmation?.status === "published"
                        ? "bulkPublish"
                        : "bulkUnpublish",
                    )}
              </DialogTitle>
              <DialogDescription>
                {confirmation?.kind === "delete"
                  ? t("deleteConfirm", {
                      name: confirmation.entry.item.displayName,
                    })
                  : t("bulkConfirm", {
                      count: confirmation?.ids.length ?? 0,
                      status: t(confirmation?.status ?? "draft"),
                    })}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => setConfirmation(null)}
              >
                {t("cancel")}
              </Button>
              <Button
                variant={
                  confirmation?.kind === "delete" ? "destructive" : "default"
                }
                disabled={busy}
                onClick={() =>
                  token &&
                  confirmation &&
                  void mutate(() =>
                    confirmation.kind === "delete"
                      ? apiClient.delete(
                          `/admin/plugins/${confirmation.entry.id}`,
                          { token },
                        )
                      : apiClient.post(
                          "/admin/plugins/bulk",
                          {
                            ids: confirmation.ids,
                            status: confirmation.status,
                          },
                          { token },
                        ),
                  )
                }
              >
                {busy ? t("saving") : t("confirm")}
              </Button>
            </DialogFooter>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  )
}
