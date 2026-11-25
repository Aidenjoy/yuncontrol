"use client"

import { useState } from "react"
import { useTranslations } from "next-intl"
import { ChevronDown } from "lucide-react"
import type { ErrorObject } from "ajv"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
  FieldError,
  FieldSet,
  FieldLegend,
} from "@/components/ui/field"
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuCheckboxItem,
} from "@/components/ui/dropdown-menu"
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  emptyItem,
  initialValue,
  itemSchema,
  parseItems,
  patchItem,
  resolveNode,
  validateItem,
  type CatalogItem,
  type Entry,
  type NodeSchema,
} from "@/features/plugin-catalog/editor"

type Props = {
  entry: Entry | "new" | "import"
  categories: string[]
  onClose: () => void
  onSave: (items: CatalogItem[]) => Promise<void>
}
const basic = [
  "id",
  "displayName",
  "name",
  "summary",
  "latestVersion",
  "categories",
]
const installation = ["package", "repository"]

/** Preserve partially typed list separators while keeping the underlying JSON value as an array. */
function ArrayInput({
  value,
  onChange,
  id,
  invalid,
  disabled,
}: {
  value: string[]
  onChange: (value: string[]) => void
  id: string
  invalid: boolean
  disabled: boolean
}) {
  const [text, setText] = useState(value.join(", "))
  return (
    <Input
      id={id}
      value={text}
      disabled={disabled}
      aria-invalid={invalid}
      onChange={(event) => {
        setText(event.target.value)
        onChange(
          event.target.value
            .split(/[,，\n]/)
            .map((s) => s.trim())
            .filter(Boolean),
        )
      }}
    />
  )
}

/** Schema-driven field controls: fixed-value selectors, optional objects, text and string arrays. */
function SchemaField({
  node,
  path,
  value,
  required,
  item,
  update,
  errors,
  categories,
  locked,
  disabled,
}: {
  node: NodeSchema
  path: string[]
  value: unknown
  required: boolean
  item: CatalogItem
  update: (path: string[], value: unknown) => void
  errors: ErrorObject[]
  categories: string[]
  locked: boolean
  disabled: boolean
}) {
  const t = useTranslations("pluginAdmin")
  const [customCategory, setCustomCategory] = useState("")
  const schema = resolveNode(node)
  const key = path.join("_")
  const label = t.has(`fields.${key}`) ? t(`fields.${key}`) : path.join(".")
  const id = `plugin-field-${path.join("-")}`
  const fieldErrors = errors.filter((error) => {
    const location = `${error.instancePath}${error.keyword === "required" ? `/${error.params.missingProperty}` : ""}`
    return (
      location === `/${path.join("/")}` ||
      (location.startsWith(`/${path.join("/")}/`) && schema.type !== "object")
    )
  })
  const invalid = fieldErrors.length > 0
  const fieldError = invalid
    ? t.has(`validation.${fieldErrors[0]!.keyword}`)
      ? t(`validation.${fieldErrors[0]!.keyword}`)
      : t("validation.invalid")
    : ""
  if (schema.type === "object") {
    const enabled = value !== undefined
    const object =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : {}
    return (
      <FieldSet className="rounded-lg border p-4" disabled={disabled}>
        <div className="flex items-center justify-between gap-3">
          <FieldLegend className="mb-0">{label}</FieldLegend>
          {!required ? (
            <Switch
              aria-label={label}
              checked={enabled}
              disabled={disabled}
              onCheckedChange={(checked) =>
                update(path, checked ? initialValue(schema) : undefined)
              }
            />
          ) : null}
        </div>
        {enabled ? (
          <FieldGroup className="gap-4">
            {Object.entries(schema.properties ?? {}).map(([name, child]) => (
              <SchemaField
                key={name}
                node={child}
                path={[...path, name]}
                value={object[name]}
                required={schema.required?.includes(name) ?? false}
                item={item}
                update={update}
                errors={errors}
                categories={categories}
                locked={locked}
                disabled={disabled}
              />
            ))}
          </FieldGroup>
        ) : (
          <p className="text-xs text-muted-foreground">
            {t("optionalSection")}
          </p>
        )}
      </FieldSet>
    )
  }
  if (path[0] === "categories") {
    const selected = Array.isArray(value) ? (value as string[]) : []
    const options = [...new Set([...categories, ...selected, "tools"])].sort()
    return (
      <Field data-invalid={invalid}>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              id={id}
              variant="outline"
              className="h-9 justify-between"
              disabled={disabled}
              aria-invalid={invalid}
            >
              {selected.length
                ? t("selectedCategories", { count: selected.length })
                : t("chooseCategories")}
              <ChevronDown data-icon="inline-end" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="max-h-64 overflow-y-auto">
            <DropdownMenuGroup>
              {options.map((option) => (
                <DropdownMenuCheckboxItem
                  key={option}
                  checked={selected.includes(option)}
                  onSelect={(event) => event.preventDefault()}
                  onCheckedChange={(checked) =>
                    update(
                      path,
                      checked
                        ? [...selected, option]
                        : selected.filter((v) => v !== option),
                    )
                  }
                >
                  {option}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <div className="flex flex-wrap gap-1">
          {selected.map((option) => (
            <Badge key={option} variant="secondary">
              {option}
            </Badge>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            aria-label={t("customCategory")}
            value={customCategory}
            disabled={disabled}
            onChange={(event) => setCustomCategory(event.target.value)}
          />
          <Button
            variant="outline"
            type="button"
            disabled={disabled || !customCategory.trim()}
            onClick={() => {
              update(path, [...new Set([...selected, customCategory.trim()])])
              setCustomCategory("")
            }}
          >
            {t("add")}
          </Button>
        </div>
        <FieldDescription>{t("categoryHint")}</FieldDescription>
        {fieldError ? <FieldError>{fieldError}</FieldError> : null}
      </Field>
    )
  }
  const choices =
    schema.enum ?? (schema.const !== undefined ? [schema.const] : null)
  const readOnly = locked && path.join(".") === "id"
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={id}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </FieldLabel>
      {choices ? (
        <Select
          value={typeof value === "string" ? value : ""}
          disabled={disabled}
          onValueChange={(next) => update(path, next)}
        >
          <SelectTrigger id={id} aria-invalid={invalid} className="h-9 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {choices.map((choice) => (
                <SelectItem key={choice} value={choice}>
                  {choice}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      ) : schema.type === "array" ? (
        <ArrayInput
          id={id}
          value={Array.isArray(value) ? (value as string[]) : []}
          onChange={(next) => update(path, next)}
          invalid={invalid}
          disabled={disabled}
        />
      ) : path[0] === "summary" || path[0] === "description" ? (
        <Textarea
          id={id}
          value={typeof value === "string" ? value : ""}
          disabled={disabled}
          required={required}
          aria-invalid={invalid}
          maxLength={schema.maxLength}
          rows={path[0] === "description" ? 5 : 3}
          onChange={(event) =>
            update(
              path,
              !required && !event.target.value ? undefined : event.target.value,
            )
          }
        />
      ) : (
        <Input
          id={id}
          value={typeof value === "string" ? value : ""}
          disabled={disabled || readOnly}
          required={required}
          aria-invalid={invalid}
          maxLength={schema.maxLength}
          className="h-9"
          onChange={(event) =>
            update(
              path,
              !required && !event.target.value ? undefined : event.target.value,
            )
          }
        />
      )}
      {readOnly ? (
        <FieldDescription>{t("immutableId")}</FieldDescription>
      ) : null}
      {schema.type === "array" ? (
        <FieldDescription>{t("arrayHint")}</FieldDescription>
      ) : null}
      {fieldError ? (
        <FieldError id={`${id}-error`}>{fieldError}</FieldError>
      ) : null}
    </Field>
  )
}

/** Lossless form/JSON editing in a responsive drawer; publication remains a separate action. */
export function PluginEditor({ entry, categories, onClose, onSave }: Props) {
  const t = useTranslations("pluginAdmin")
  const batch = entry === "import"
  const editing = typeof entry === "object" ? entry : null
  const [items, setItems] = useState<CatalogItem[]>([
    editing?.item ?? emptyItem(),
  ])
  const [index, setIndex] = useState(0)
  const [mode, setMode] = useState(batch ? "json" : "form")
  const [text, setText] = useState(
    batch ? '{"items": []}' : JSON.stringify(items[0], null, 2),
  )
  const [error, setError] = useState("")
  const [errors, setErrors] = useState<ErrorObject[]>([])
  const [saving, setSaving] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const item = items[index]!
  /** Parse before leaving JSON mode; invalid text stays visible and is never overwritten. */
  function switchMode(next: string) {
    if (next === mode) return
    setError("")
    if (next === "form") {
      try {
        const parsed = parseItems(text, batch)
        setItems(parsed)
        setIndex(0)
        setErrors([])
      } catch {
        setError(t("jsonInvalid"))
        return
      }
    } else setText(JSON.stringify(batch ? { items } : item, null, 2))
    setMode(next)
  }
  /** Save only valid items, with immutable edit identities and no publication payload. */
  async function save() {
    if (saving) return
    setError("")
    let values = items
    try {
      if (mode === "json") values = parseItems(text, batch)
    } catch {
      setError(t("jsonInvalid"))
      return
    }
    if (editing && values[0]?.id !== editing.item.id) {
      setError(t("immutableId"))
      return
    }
    if (new Set(values.map((value) => value.id)).size !== values.length) {
      setError(t("duplicateIds"))
      return
    }
    for (const [position, value] of values.entries()) {
      const issues = validateItem(value)
      if (issues.length) {
        setItems(values)
        setIndex(position)
        setErrors(issues)
        setAdvanced(true)
        setError(t("validationFailed", { index: position + 1 }))
        return
      }
    }
    setErrors([])
    setSaving(true)
    try {
      await onSave(values)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("saveFailed"))
    } finally {
      setSaving(false)
    }
  }
  /** Update only the edited path and keep unknown nested fields from JSON intact. */
  function update(path: string[], value: unknown) {
    setItems((current) =>
      current.map((entry, position) =>
        position === index ? patchItem(entry, path, value) : entry,
      ),
    )
    setErrors([])
  }
  const fields = (names: string[]) =>
    names.map((name) => (
      <SchemaField
        key={name}
        node={itemSchema.properties![name]!}
        path={[name]}
        value={item[name]}
        required={itemSchema.required?.includes(name) ?? false}
        item={item}
        update={update}
        errors={errors}
        categories={categories}
        locked={Boolean(editing)}
        disabled={saving}
      />
    ))
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <SheetContent
        className="plugin-admin gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-2xl"
        showCloseButton={!saving}
      >
        <SheetHeader className="border-b pr-14">
          <SheetTitle>
            {batch ? t("import") : editing ? t("edit") : t("new")}
          </SheetTitle>
          <SheetDescription>{t("editorHint")}</SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-6">
          <Tabs value={mode} onValueChange={switchMode}>
            <TabsList>
              <TabsTrigger value="form">{t("formMode")}</TabsTrigger>
              <TabsTrigger value="json">{t("jsonMode")}</TabsTrigger>
            </TabsList>
          </Tabs>
          <form
            id="plugin-editor-form"
            noValidate
            className="mt-5 flex flex-col gap-6"
            onSubmit={(event) => {
              event.preventDefault()
              void save()
            }}
          >
            {mode === "json" ? (
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="plugin-json">{t("jsonMode")}</FieldLabel>
                  <Textarea
                    id="plugin-json"
                    className="min-h-80 font-mono"
                    spellCheck={false}
                    disabled={saving}
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                  />
                  <FieldDescription>{t("jsonHint")}</FieldDescription>
                </Field>
                <Button
                  variant="outline"
                  type="button"
                  disabled={saving}
                  onClick={() => switchMode("form")}
                >
                  {t("parseJson")}
                </Button>
              </FieldGroup>
            ) : (
              <>
                {batch ? (
                  <Select
                    value={String(index)}
                    onValueChange={(value) => {
                      setIndex(Number(value))
                      setErrors([])
                    }}
                  >
                    <SelectTrigger aria-label={t("chooseItem")}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {items.map((value, position) => (
                          <SelectItem key={position} value={String(position)}>
                            {position + 1}.{" "}
                            {value.displayName || value.id || t("untitled")}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                ) : null}
                <FieldSet>
                  <FieldLegend>{t("basic")}</FieldLegend>
                  <FieldGroup className="gap-4">{fields(basic)}</FieldGroup>
                </FieldSet>
                <FieldSet>
                  <FieldLegend>{t("installation")}</FieldLegend>
                  <FieldDescription>{t("installationHint")}</FieldDescription>
                  <FieldGroup className="gap-4">
                    {fields(installation)}
                  </FieldGroup>
                  {errors.some((issue) => issue.keyword === "anyOf") ? (
                    <FieldError>{t("validation.anyOf")}</FieldError>
                  ) : null}
                </FieldSet>
                <Collapsible open={advanced} onOpenChange={setAdvanced}>
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      type="button"
                      className="w-full justify-between"
                    >
                      {t("advanced")}
                      <ChevronDown data-icon="inline-end" />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-4">
                    <FieldGroup className="gap-4">
                      {fields(
                        Object.keys(itemSchema.properties!).filter(
                          (name) =>
                            !basic.includes(name) &&
                            !installation.includes(name),
                        ),
                      )}
                    </FieldGroup>
                  </CollapsibleContent>
                </Collapsible>
              </>
            )}
            <FieldSet className="rounded-lg border p-4">
              <FieldLegend>{t("publication")}</FieldLegend>
              <p className="text-sm">
                {editing?.status === "published"
                  ? t("publishedRetained")
                  : t("draftRetained")}
              </p>
              <FieldDescription>{t("publicationHint")}</FieldDescription>
            </FieldSet>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
            {errors.length ? (
              <ul className="list-inside list-disc text-sm text-destructive">
                {errors.map((issue, position) => (
                  <li key={position}>
                    {issue.instancePath || "/"}
                    {issue.params.additionalProperty
                      ? `/${issue.params.additionalProperty}`
                      : ""}
                    :{" "}
                    {t.has(`validation.${issue.keyword}`)
                      ? t(`validation.${issue.keyword}`)
                      : t("validation.invalid")}
                  </li>
                ))}
              </ul>
            ) : null}
          </form>
        </div>
        <SheetFooter className="flex-row justify-end border-t p-4">
          <Button
            variant="outline"
            type="button"
            disabled={saving}
            onClick={onClose}
          >
            {t("cancel")}
          </Button>
          <Button type="submit" form="plugin-editor-form" disabled={saving}>
            {saving ? t("saving") : t("save")}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
