import { readFileSync, writeFileSync } from 'node:fs'

// Generated local copy keeps the Web bundle inside its Turbopack root.
const source = new URL(
  '../../server/agent_server/core/plugin_schemas/catalog-provider-page.schema.json',
  import.meta.url,
)
const target = new URL(
  '../src/features/plugin-catalog/catalog.schema.json',
  import.meta.url,
)
const content = readFileSync(source, 'utf8')
if (process.argv.includes('--check')) {
  if (readFileSync(target, 'utf8') !== content)
    throw new Error(
      'Plugin schema is stale. Run node scripts/sync-plugin-schema.mjs',
    )
} else {
  writeFileSync(target, content)
}
