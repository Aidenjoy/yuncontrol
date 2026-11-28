import assert from "node:assert/strict"
import test from "node:test"
import { existsSync, readFileSync } from "node:fs"
import { registerHooks } from "node:module"
import { dirname, resolve } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import ts from "typescript"

const sourceRoot = fileURLToPath(new URL("../src/", import.meta.url))
const hooks = registerHooks({
  resolve(specifier, context, nextResolve) {
    const parent = context.parentURL?.startsWith("file:") ? fileURLToPath(context.parentURL) : ""
    if (specifier.startsWith("@/") || (parent.startsWith(sourceRoot) && specifier.startsWith("."))) {
      const base = specifier.startsWith("@/") ? resolve(sourceRoot, specifier.slice(2)) : resolve(dirname(parent), specifier)
      const found = [base, `${base}.ts`, `${base}/index.ts`].find((path) => existsSync(path) && path.endsWith(".ts"))
      if (found) return { url: pathToFileURL(found).href, shortCircuit: true }
    }
    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    if (url.startsWith(pathToFileURL(sourceRoot).href) && url.endsWith(".ts")) {
      return {
        format: "module",
        shortCircuit: true,
        source: ts.transpileModule(readFileSync(fileURLToPath(url), "utf8"), {
          compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
        }).outputText,
      }
    }
    return nextLoad(url, context)
  },
})
const { ApiClient } = await import("../src/lib/api/client.ts")
const { CloudComputerApi } = await import("../src/features/cloud-computer/api.ts")
const {
  isCloudRuntimeReady,
  provisioningProgress,
  resolveCloudComputerProgress,
} = await import("../src/features/cloud-computer/progress.ts")
hooks.deregister()

const status = (extra = {}) => ({
  configured: true,
  phase: "running",
  containerState: "running",
  connectorId: "conn_cloud",
  displayName: "云电脑",
  updatedAt: "2026-11-03T00:00:00Z",
  error: null,
  ...extra,
})

const runtime = (extra = {}) => ({
  connectorId: "conn_cloud",
  runtimeId: "rti_yunwork",
  runtimeType: "yunwork",
  displayName: "云大师 Agent",
  present: true,
  available: true,
  configured: true,
  active: true,
  status: "running",
  ...extra,
})

function runtimeHarness(options = {}) {
  const calls = []
  let connectorOnline = options.connectorOnline ?? true
  let runtimes = options.runtimes ?? [runtime()]
  const runtimeTypes = options.runtimeTypes ?? []
  return {
    calls,
    setConnectorOnline(value) { connectorOnline = value },
    setRuntimes(value) { runtimes = value },
    api: {
      async getConnector(token, connectorId) {
        calls.push({ action: "connector", token, connectorId })
        return { connector: { id: connectorId, status: connectorOnline ? "online" : "offline" } }
      },
      async discoverConnectorRuntimes(token, connectorId) {
        calls.push({ action: "discover", token, connectorId })
        return { connectorId, runtimes }
      },
      async discoverConnectorRuntimeTypes(token, connectorId) {
        calls.push({ action: "types", token, connectorId })
        return { connectorId, runtimeTypes }
      },
      async createConnectorRuntime(token, connectorId, payload) {
        calls.push({ action: "create", token, connectorId, payload })
        const created = runtime({ runtimeId: "rti_created", ...payload, configured: true })
        runtimes = [created]
        return created
      },
      async putConnectorRuntimeConfig(token, connectorId, runtimeId, config) {
        calls.push({ action: "configure", token, connectorId, runtimeId, config })
        const configured = runtime({ ...runtimes.find((item) => item.runtimeId === runtimeId), config, configured: true, active: false })
        runtimes = runtimes.map((item) => item.runtimeId === runtimeId ? configured : item)
        return configured
      },
      async setConnectorRuntimeActive(token, connectorId, runtimeId, active) {
        calls.push({ action: "activate", token, connectorId, runtimeId, active })
        const activated = runtime({
          ...runtimes.find((item) => item.runtimeId === runtimeId),
          active,
          status: active ? "running" : "stopped",
        })
        runtimes = runtimes.map((item) => item.runtimeId === runtimeId ? activated : item)
        return activated
      },
    },
  }
}

test("cloud computer API uses the authenticated v2 endpoint for all operations", async () => {
  const requests = []
  const client = new ApiClient({
    fetcher: async (input, init) => {
      requests.push({ url: input, method: init.method, authorization: init.headers.get("authorization"), body: init.body })
      return new Response(JSON.stringify(status()), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    },
  })
  const api = new CloudComputerApi(client)
  await api.get("access-token")
  await api.enable("access-token")
  await api.disable("access-token")
  assert.deepEqual(requests, [
    { url: "/api/v2/cloud-computer", method: "GET", authorization: "Bearer access-token", body: undefined },
    { url: "/api/v2/cloud-computer", method: "POST", authorization: "Bearer access-token", body: "{}" },
    { url: "/api/v2/cloud-computer", method: "DELETE", authorization: "Bearer access-token", body: undefined },
  ])
})

test("disabled, provisioning and error states do not touch Connector APIs", async () => {
  const h = runtimeHarness()
  assert.equal((await resolveCloudComputerProgress("token", status({ phase: "disabled" }), h.api)).stage, "disabled")
  assert.equal((await resolveCloudComputerProgress("token", status({ phase: "provisioning" }), h.api)).stage, "provisioning")
  assert.equal((await resolveCloudComputerProgress("token", status({ phase: "error", error: "safe error" }), h.api)).stage, "error")
  assert.deepEqual(h.calls, [])
})

test("a running phase still requires a running container and connector ID", async () => {
  const h = runtimeHarness()
  assert.equal((await resolveCloudComputerProgress("token", status({ containerState: "created" }), h.api)).stage, "provisioning")
  assert.equal((await resolveCloudComputerProgress("token", status({ connectorId: null }), h.api)).stage, "provisioning")
  assert.deepEqual(h.calls, [])
})

test("an offline cloud Connector keeps the recoverable connector stage", async () => {
  const h = runtimeHarness({ connectorOnline: false })
  const result = await resolveCloudComputerProgress("token", status(), h.api)
  assert.equal(result.stage, "connector")
  assert.deepEqual(h.calls.map((call) => call.action), ["connector"])
})

test("a running, active and available Yunwork Runtime completes provisioning", async () => {
  const h = runtimeHarness()
  const result = await resolveCloudComputerProgress("token", status(), h.api)
  assert.equal(result.stage, "ready")
  assert.equal(result.runtime.runtimeType, "yunwork")
  assert.deepEqual(h.calls.map((call) => call.action), ["connector", "discover"])
})

test("a discovered Yunwork Runtime is configured and activated without being recreated", async () => {
  const h = runtimeHarness({ runtimes: [runtime({ configured: false, active: false, status: "stopped" })] })
  const result = await resolveCloudComputerProgress("token", status(), h.api)
  assert.equal(result.stage, "ready")
  assert.deepEqual(h.calls.map((call) => call.action), ["connector", "discover", "configure", "activate"])
  assert.deepEqual(h.calls[2].config, {})
})

test("a missing Runtime is discovered by type and created once with an active empty configuration", async () => {
  const h = runtimeHarness({
    runtimes: [],
    runtimeTypes: [{ runtimeType: "yunwork", displayName: "云大师 Agent", present: true, available: true }],
  })
  const result = await resolveCloudComputerProgress("token", status(), h.api)
  assert.equal(result.stage, "ready")
  assert.deepEqual(h.calls.map((call) => call.action), ["connector", "discover", "types", "create"])
  assert.deepEqual(h.calls[3].payload, {
    runtimeType: "yunwork",
    name: "云大师 Agent",
    config: {},
    active: true,
  })
})

test("an unavailable Runtime type remains pending instead of creating an unusable Runtime", async () => {
  const h = runtimeHarness({
    runtimes: [],
    runtimeTypes: [{ runtimeType: "yunwork", displayName: "云大师 Agent", present: false, available: false }],
  })
  const result = await resolveCloudComputerProgress("token", status(), h.api)
  assert.equal(result.stage, "runtime")
  assert.deepEqual(h.calls.map((call) => call.action), ["connector", "discover", "types"])
})

test("starting or unavailable Runtimes never count as fully enabled", () => {
  assert.equal(isCloudRuntimeReady(runtime({ status: "starting" })), false)
  assert.equal(isCloudRuntimeReady(runtime({ available: false })), false)
  assert.equal(isCloudRuntimeReady(runtime({ present: false })), false)
  assert.equal(isCloudRuntimeReady(runtime({ active: false })), false)
  assert.equal(isCloudRuntimeReady(runtime({ runtimeType: "codex" })), false)
})

test("optimistic provisioning preserves server identity and clears stale errors", () => {
  const result = provisioningProgress(status({ phase: "error", error: "old error" }))
  assert.equal(result.stage, "provisioning")
  assert.equal(result.status.phase, "provisioning")
  assert.equal(result.status.connectorId, "conn_cloud")
  assert.equal(result.status.error, null)
})
