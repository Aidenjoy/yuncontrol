"use client"

import { useCallback, useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { ExternalLink, Pencil, Plus, Trash2 } from "lucide-react"

import { useAuth } from "@/components/auth/auth-context"
import { PageHeader } from "@/components/pages/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { releasesApi } from "@/features/releases/api"
import {
  RELEASE_PLATFORMS,
  type ReleasePlatform,
  type ReleaseRecord,
  type ReleaseWrite,
} from "@/features/releases/types"

/** Platform identifiers stay untranslated; the visible names follow the locale. */
const PLATFORM_LABEL_KEY = {
  "desktop-macos-arm64": "platformMacArm64",
  "desktop-macos-x64": "platformMacX64",
  "desktop-windows": "platformWindows",
  android: "platformAndroid",
  ios: "platformIos",
} as const satisfies Record<ReleasePlatform, string>

const EMPTY_FORM: ReleaseWrite = {
  platform: "desktop-macos-arm64",
  version: "",
  downloadUrl: "",
  fileName: "",
  notes: "",
  published: false,
}

function errorText(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause)
}

/** Administrator registry: one row per platform/version, published or draft. */
export function ReleaseFilesPage() {
  const { session } = useAuth()
  const t = useTranslations("admin.releases")
  const token = session?.accessToken ?? ""
  const [records, setRecords] = useState<ReleaseRecord[]>([])
  const [total, setTotal] = useState(0)
  const [platform, setPlatform] = useState<"all" | ReleasePlatform>("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<ReleaseRecord | "new" | null>(null)
  const [deleting, setDeleting] = useState<ReleaseRecord | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async (): Promise<ReleaseRecord[]> => {
    if (!token) return []
    setLoading(true)
    try {
      // Six platforms exist, so pull them all once and filter locally: the
      // occupied set decides which platforms the "add" form may still offer.
      const page = await releasesApi.list(token, {})
      setRecords(page.items)
      setTotal(page.total)
      setError(null)
      return page.items
    } catch (cause) {
      setError(t("loadFailed", { message: errorText(cause) }))
      return []
    } finally {
      setLoading(false)
    }
  }, [token, t])

  useEffect(() => {
    void load()
  }, [load])

  const save = async (form: ReleaseWrite) => {
    setBusy(true)
    try {
      if (editing === "new") await releasesApi.create(token, form)
      else if (editing) await releasesApi.update(token, editing.id, form)
      setEditing(null)
      await load()
      return null
    } catch (cause) {
      // A taken platform is a normal state, so answer in the reader's language
      // instead of surfacing the API's English detail. Refresh first: another
      // administrator may have registered it after this page loaded.
      if (cause instanceof ApiError && cause.status === 409) {
        const fresh = await load()
        const existing = fresh.find(
          (record) => record.platform === form.platform,
        )
        return existing
          ? t("duplicateVersion", { version: existing.version })
          : t("duplicate")
      }
      return errorText(cause)
    } finally {
      setBusy(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleting) return
    setBusy(true)
    try {
      await releasesApi.remove(token, deleting.id)
      setDeleting(null)
      await load()
    } catch (cause) {
      setError(t("loadFailed", { message: errorText(cause) }))
    } finally {
      setBusy(false)
    }
  }

  const label = (value: ReleasePlatform) =>
    value in PLATFORM_LABEL_KEY ? t(PLATFORM_LABEL_KEY[value]) : value
  const taken = new Set(records.map((record) => record.platform))
  // Each platform holds one record, so only untouched platforms can be added.
  const availablePlatforms = RELEASE_PLATFORMS.filter(
    (value) => !taken.has(value),
  )
  const visible =
    platform === "all"
      ? records
      : records.filter((record) => record.platform === platform)

  return (
    <ScrollArea className="@container/page h-full w-full bg-background">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-8 pb-16 pt-14 @min-[68rem]/page:pt-8">
        <PageHeader title={t("title")} description={t("description")}>
          <Button
            size="sm"
            onClick={() => setEditing("new")}
            disabled={!token || !availablePlatforms.length}
            title={
              availablePlatforms.length ? undefined : t("allPlatformsTaken")
            }
          >
            <Plus data-icon="inline-start" />
            {t("new")}
          </Button>
        </PageHeader>

        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={platform}
            onValueChange={(value) =>
              setPlatform(value as "all" | ReleasePlatform)
            }
          >
            <SelectTrigger className="h-9 w-44" aria-label={t("platform")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">{t("allPlatforms")}</SelectItem>
                {RELEASE_PLATFORMS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {label(value)}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <span className="text-sm text-muted-foreground tabular-nums">
            {total}
          </span>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>

        <div className="overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("platform")}</TableHead>
                <TableHead>{t("version")}</TableHead>
                <TableHead>{t("file")}</TableHead>
                <TableHead>{t("status")}</TableHead>
                <TableHead>{t("updated")}</TableHead>
                <TableHead className="text-right">{t("actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((record) => (
                <TableRow key={record.id}>
                  <TableCell className="whitespace-nowrap">
                    {label(record.platform as ReleasePlatform)}
                  </TableCell>
                  <TableCell className="font-medium tabular-nums">
                    {record.version}
                  </TableCell>
                  <TableCell className="max-w-[18rem]">
                    <a
                      href={record.downloadUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 truncate text-sm text-muted-foreground hover:text-foreground hover:underline"
                      title={record.downloadUrl}
                    >
                      <span className="truncate">
                        {record.fileName || record.downloadUrl}
                      </span>
                      <ExternalLink className="size-3 shrink-0" />
                    </a>
                  </TableCell>
                  <TableCell>
                    <Badge variant={record.published ? "default" : "secondary"}>
                      {t(record.published ? "published" : "draft")}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                    {new Date(record.updatedAt).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t("editTitle")}
                        onClick={() => setEditing(record)}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t("deleteTitle")}
                        onClick={() => setDeleting(record)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {!visible.length ? (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    {loading ? t("saving") : t("empty")}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>

        <p className="text-xs text-muted-foreground">
          {t("publicEndpoint", {
            platform: "desktop-macos-arm64",
            version: "2.2.0",
          })}
        </p>
      </div>

      {editing ? (
        <ReleaseFormDialog
          key={editing === "new" ? "new" : editing.id}
          record={editing === "new" ? null : editing}
          platforms={
            editing === "new"
              ? availablePlatforms
              : RELEASE_PLATFORMS.includes(editing.platform as ReleasePlatform)
                ? RELEASE_PLATFORMS.filter(
                    (value) => value === editing.platform,
                  )
                : availablePlatforms
          }
          busy={busy}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      ) : null}

      <Dialog
        open={Boolean(deleting)}
        onOpenChange={(open) => {
          if (!open && !busy) setDeleting(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("deleteTitle")}</DialogTitle>
            <DialogDescription>
              {deleting
                ? t("deleteConfirm", {
                    platform: label(deleting.platform as ReleasePlatform),
                    version: deleting.version,
                  })
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleting(null)}
              disabled={busy}
            >
              {t("cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => void confirmDelete()}
              disabled={busy}
            >
              {busy ? t("deleting") : t("deleteTitle")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ScrollArea>
  )
}

function ReleaseFormDialog({
  record,
  platforms,
  busy,
  onClose,
  onSave,
}: {
  record: ReleaseRecord | null
  /** Platforms this form may offer: untouched ones when adding. */
  platforms: ReleasePlatform[]
  busy: boolean
  onClose: () => void
  onSave: (form: ReleaseWrite) => Promise<string | null>
}) {
  const t = useTranslations("admin.releases")
  const [form, setForm] = useState<ReleaseWrite>(
    record
      ? {
          platform: record.platform as ReleasePlatform,
          version: record.version,
          downloadUrl: record.downloadUrl,
          fileName: record.fileName,
          notes: record.notes,
          published: record.published,
        }
      : { ...EMPTY_FORM, platform: platforms[0] ?? EMPTY_FORM.platform },
  )
  const [error, setError] = useState<string | null>(null)
  const complete = Boolean(
    form.version.trim() && form.downloadUrl.trim() && form.fileName.trim(),
  )

  const submit = async () => {
    if (!complete) {
      setError(t("invalid"))
      return
    }
    const failure = await onSave({
      ...form,
      version: form.version.trim(),
      downloadUrl: form.downloadUrl.trim(),
      fileName: form.fileName.trim(),
      notes: form.notes.trim(),
    })
    setError(failure)
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose()
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t(record ? "editTitle" : "createTitle")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="grid gap-2">
            <Label htmlFor="release-platform">{t("platform")}</Label>
            <Select
              value={form.platform}
              onValueChange={(value) =>
                setForm({ ...form, platform: value as ReleasePlatform })
              }
              disabled={Boolean(
                record &&
                RELEASE_PLATFORMS.includes(record.platform as ReleasePlatform),
              )}
            >
              <SelectTrigger id="release-platform" className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {platforms.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(PLATFORM_LABEL_KEY[value])}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {record ? t("platformLocked") : t("platformOnceHint")}
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="release-version">{t("version")}</Label>
            <Input
              id="release-version"
              value={form.version}
              onChange={(event) =>
                setForm({ ...form, version: event.currentTarget.value })
              }
              placeholder="2.2.0"
              className="code-mono"
              spellCheck={false}
            />
            <p className="text-xs text-muted-foreground">{t("versionHint")}</p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="release-url">{t("downloadUrl")}</Label>
            <Input
              id="release-url"
              value={form.downloadUrl}
              onChange={(event) =>
                setForm({ ...form, downloadUrl: event.currentTarget.value })
              }
              placeholder="https://dl.example.com/yundashi-2.2.0.dmg"
              className="code-mono"
              spellCheck={false}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="release-file">{t("fileName")}</Label>
            <Input
              id="release-file"
              value={form.fileName}
              onChange={(event) =>
                setForm({ ...form, fileName: event.currentTarget.value })
              }
              placeholder="yundashi-2.2.0.dmg"
              className="code-mono"
              spellCheck={false}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="release-notes">{t("notes")}</Label>
            <Textarea
              id="release-notes"
              value={form.notes}
              onChange={(event) =>
                setForm({ ...form, notes: event.currentTarget.value })
              }
              rows={3}
            />
          </div>

          <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
            <div className="min-w-0">
              <Label htmlFor="release-published">{t("published")}</Label>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("publishedHint")}
              </p>
            </div>
            <Switch
              id="release-published"
              checked={form.published}
              onCheckedChange={(checked) =>
                setForm({ ...form, published: checked })
              }
            />
          </div>

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {t("cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !complete}>
            {busy ? t("saving") : t("save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
