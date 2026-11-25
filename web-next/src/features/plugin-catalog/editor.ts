import Ajv2020 from "ajv/dist/2020"
import type { ErrorObject } from "ajv"
import schema from "./catalog.schema.json" with { type: "json" }

export type CatalogItem = {
  id: string
  name: string
  displayName: string
  summary: string
  latestVersion?: string
  categories?: string[]
  package?: { registry: "npm"; name: string }
  media?: { icon: { url: string; alt?: string } }
  [key: string]: unknown
}
export type Entry = {
  id: string
  status: "draft" | "published"
  item: CatalogItem
  origins?: Record<string, { url?: string }>
}
export type NodeSchema = {
  type?: string
  const?: string
  enum?: string[]
  properties?: Record<string, NodeSchema>
  required?: string[]
  items?: NodeSchema
  allOf?: NodeSchema[]
  $ref?: string
  maxLength?: number
}
const definitions = schema.$defs as unknown as Record<string, NodeSchema>

/** Resolve this catalog's local references and allOf constraints without creating a second schema. */
export function resolveNode(node: NodeSchema): NodeSchema {
  if (node.$ref) return resolveNode(definitions[node.$ref.split("/").at(-1)!]!)
  if (node.allOf)
    return Object.assign({}, ...node.allOf.map(resolveNode)) as NodeSchema
  return node
}
export const itemSchema = resolveNode(definitions.item!)
const ajv = new Ajv2020({ allErrors: true, strict: false })
ajv.addFormat("uri", (value: string) => {
  try {
    return Boolean(new URL(value).protocol)
  } catch {
    return false
  }
})
ajv.addFormat(
  "date-time",
  (value: string) =>
    /^\d{4}-\d\d-\d\d[tT]\d\d:\d\d:\d\d(?:\.\d+)?(?:[zZ]|[+-]\d\d:\d\d)$/.test(
      value,
    ) && Number.isFinite(Date.parse(value)),
)
ajv.addSchema(schema)
const validate = ajv.compile({ $ref: `${schema.$id}#/$defs/item` })

/** Keep extension keys intact; backend-incompatible fields are reported, never silently removed. */
export function validateItem(item: unknown): ErrorObject[] {
  validate(item)
  const errors = [...(validate.errors ?? [])]
  if (item && typeof item === "object" && !Array.isArray(item)) {
    const repo = (item as CatalogItem).repository as
      { url?: string; subdirectory?: string } | undefined
    if (repo?.url) {
      try {
        const url = new URL(repo.url)
        const parts = url.pathname.split("/").filter(Boolean)
        if (
          url.search ||
          url.hash ||
          (url.hostname === "github.com" && parts.length !== 2)
        )
          throw new Error()
      } catch {
        errors.push({
          keyword: "repository",
          instancePath: "/repository/url",
          schemaPath: "",
          params: {},
        })
      }
    }
    if (repo?.subdirectory) {
      try {
        if (
          repo.subdirectory
            .split("/")
            .some(
              (part) =>
                !part ||
                [".", ".."].includes(decodeURIComponent(part)) ||
                /[\\/]/.test(decodeURIComponent(part)),
            )
        )
          throw new Error()
      } catch {
        errors.push({
          keyword: "repository",
          instancePath: "/repository/subdirectory",
          schemaPath: "",
          params: {},
        })
      }
    }
    if ((item as CatalogItem).installSource) {
      try {
        if (!repo?.url || new URL(repo.url).hostname !== "github.com")
          throw new Error()
      } catch {
        errors.push({
          keyword: "repository",
          instancePath: "/installSource",
          schemaPath: "",
          params: {},
        })
      }
    }
  }
  return errors
}

/** Patch just one field, preserving all other known and unknown keys including nested data. */
export function patchItem(
  item: CatalogItem,
  path: string[],
  value: unknown,
): CatalogItem {
  const next = structuredClone(item)
  let node: Record<string, unknown> = next
  for (const key of path.slice(0, -1)) {
    if (!node[key] || typeof node[key] !== "object" || Array.isArray(node[key]))
      node[key] = {}
    node = node[key] as Record<string, unknown>
  }
  const key = path.at(-1)!
  if (value === undefined) delete node[key]
  else node[key] = value
  return next
}

/** Parse single items and existing batch envelopes losslessly; never coerce unknown fields. */
export function parseItems(text: string, batch: boolean): CatalogItem[] {
  const raw: unknown = JSON.parse(text)
  const object =
    raw && typeof raw === "object" && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : null
  const values = batch
    ? Array.isArray(raw)
      ? raw
      : object?.items
    : [object && "id" in object ? raw : (object?.item ?? raw)]
  if (
    !Array.isArray(values) ||
    !values.length ||
    values.length > (batch ? 200 : 1)
  )
    throw new Error("shape")
  return values.map((value) => {
    const candidate =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : null
    const item =
      candidate && "id" in candidate
        ? candidate
        : (candidate?.item ?? candidate)
    if (!item || typeof item !== "object" || Array.isArray(item))
      throw new Error("shape")
    return item as CatalogItem
  })
}

/** Seed only required schema fields; optional sections remain absent until enabled. */
export function initialValue(node: NodeSchema): unknown {
  const resolved = resolveNode(node)
  if (resolved.const !== undefined) return resolved.const
  if (resolved.type === "object")
    return Object.fromEntries(
      (resolved.required ?? []).map((key) => [
        key,
        initialValue(resolved.properties![key]!),
      ]),
    )
  if (resolved.type === "array") return []
  return ""
}
export function emptyItem(): CatalogItem {
  return {
    ...(initialValue(itemSchema) as CatalogItem),
    package: { registry: "npm", name: "" },
  }
}
