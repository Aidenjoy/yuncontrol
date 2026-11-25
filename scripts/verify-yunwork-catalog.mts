/** Real YunWork catalog/index/cache integration against a disposable local YunControl server. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const source = process.env.YUNWORK_MARKET_SOURCE
const base = process.env.YUNCONTROL_TEST_URL ?? 'http://127.0.0.1:18008'
if (!source || new URL(base).hostname !== '127.0.0.1') throw new Error('Set YUNWORK_MARKET_SOURCE and use a disposable localhost test server')
const { DefaultCatalogService } = await import(pathToFileURL(`${source}/src/catalog/service.ts`).href)
const { createRestrictedHttpClient, createCachedCatalogHttpClient } = await import(pathToFileURL(`${source}/src/network/restricted-http.ts`).href)
const headers = JSON.parse(readFileSync(process.env.YUNCONTROL_TEST_AUTH_FILE!, 'utf8'))
async function request(path: string, method = 'GET', body?: unknown) {
  const response = await fetch(`${base}/api/v2${path}`, { method, headers: { ...headers, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  assert.ok(response.ok, `${method} ${path}: ${response.status} ${await response.clone().text()}`)
  return response.json()
}

// Only the network transport is injected: upstream URL validation, schemas,
// provider adapter, complete-index scan, and both cache layers run unchanged.
let networkRequests = 0
const http = createCachedCatalogHttpClient(createRestrictedHttpClient({
  resolveAddress: async () => ({ address: '93.184.216.34', family: 4 }),
  request: async (url: URL, signal: AbortSignal) => {
    assert.equal(url.origin, 'https://control.example.com')
    networkRequests++
    const response = await fetch(base + url.pathname + url.search, { signal })
    return { statusCode: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) }
  },
}))
const manifest = await request('/plugins/config')
const record = { sourceRecordId: '8faf4efc-84d7-4d08-81cb-a873c04cf817', adapterId: 'market.standard-http-v1', providerId: manifest.providerId, registrationKind: 'user-added', manifestUrl: 'https://control.example.com/api/v2/plugins/config', manifest, enabled: true, order: 0 }
const service = new DefaultCatalogService({ load: async () => [record] }, http)
const signal = new AbortController().signal
const item = { id: 'yuncontrol-integration-probe', name: 'yuncontrol-integration-probe', displayName: 'YunControl Probe', summary: 'Local integration fixture', latestVersion: '1.0.0', package: { registry: 'npm', name: 'yuncontrol-integration-probe' }, categories: ['tools'] }
const created = await request('/admin/plugins', 'POST', { item })
assert.equal(created.status, 'draft')
function count(index: any) {
  return service.queryCatalog(index, { q: 'YunControl Probe', category: ['tools'], limit: 50 }).flatMap((page: any) => page.snapshot?.items ?? page.items ?? []).length
}
let index = await service.scanCatalog(signal, { force: true })
assert.ok(index)
assert.equal(count(index), 0)
await request(`/admin/plugins/${created.id}`, 'PATCH', { status: 'published' })
index = await service.scanCatalog(signal, { force: true })
assert.equal(count(index), 1)
const networkAfterPublish = networkRequests
await request(`/admin/plugins/${created.id}`, 'PATCH', { status: 'draft' })
const rawPage = await request('/plugins/search?q=YunControl%20Probe')
assert.equal(rawPage.items.length, 0)
const cached = await service.scanCatalog(signal)
assert.equal(networkRequests, networkAfterPublish)
assert.equal(count(cached), 1)
index = await service.scanCatalog(signal, { force: true })
assert.equal(count(index), 0)
assert.ok(networkRequests > networkAfterPublish)
await request(`/admin/plugins/${created.id}`, 'DELETE')
console.log(JSON.stringify({ draft: 0, published: 1, cachedBeforeRefresh: 1, unpublishedAfterRefresh: 0, networkRequests, adapter: 'real YunWork standard-http-v1 + full index + HTTP cache', transport: 'injected localhost test transport; public TLS not exercised' }, null, 2))
