import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { JSDOM } from 'jsdom'
import { registerSource } from './helpers/onboarding-source.mjs'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://app.example.test/', pretendToBeVisual: true })
for (const name of ['window', 'document', 'navigator', 'HTMLElement', 'HTMLInputElement', 'HTMLTextAreaElement', 'HTMLFormElement', 'HTMLButtonElement', 'HTMLAnchorElement', 'HTMLDivElement', 'HTMLSpanElement', 'Element', 'Node', 'NodeFilter', 'Event', 'MouseEvent', 'InputEvent', 'FocusEvent', 'CustomEvent', 'MutationObserver', 'getComputedStyle', 'requestAnimationFrame', 'cancelAnimationFrame', 'PointerEvent', 'KeyboardEvent', 'DragEvent', 'DocumentFragment', 'SVGElement']) {
  Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] })
}
window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })
window.HTMLElement.prototype.scrollIntoView = function () {}
window.HTMLElement.prototype.releasePointerCapture = function () {}
window.HTMLElement.prototype.hasPointerCapture = function () { return false }
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const { createElement: h, act } = await import('react')
const { createRoot } = await import('react-dom/client')
const { NextIntlClientProvider } = await import('next-intl')

const source = registerSource()
const hooks = registerHooks({
  load(url, context, next) {
    if (url.endsWith('/auth/auth-context.tsx')) {
      return { format: 'module', shortCircuit: true, source: 'export const useAuth = () => ({ session: { accessToken: "token" } })' }
    }
    if (url.endsWith('/features/releases/api.ts')) {
      return {
        format: 'module',
        shortCircuit: true,
        source: `export const releasesApi = {
          list: async () => globalThis.releaseFixture.list(),
          create: async (token, body) => {
            globalThis.releaseFixture.created.push(body)
            if (globalThis.releaseFixture.conflict) throw globalThis.releaseFixture.conflict
            return body
          },
          update: async (token, id, body) => { globalThis.releaseFixture.updated.push([id, body]); return body },
          remove: async (token, id) => { globalThis.releaseFixture.removed.push(id) },
          latest: async () => ({ items: [] }),
          check: async () => ({}),
        }`,
      }
    }
    return next(url, context)
  },
})
const { ApiError } = await import('../src/lib/api/errors.ts')
const { ReleaseFilesPage } = await import('../src/components/admin/release-files-page.tsx')
hooks.deregister()
source.deregister()

const messages = JSON.parse(readFileSync(new URL('../messages/zh-CN.json', import.meta.url), 'utf8'))

const ROWS = [
  {
    id: '11', platform: 'desktop-macos-arm64', version: '2.2.0',
    downloadUrl: 'https://dl.example.test/yundashi-2.2.0-arm64.dmg', fileName: 'yundashi-2.2.0-arm64.dmg',
    notes: 'First build', published: true, updatedAt: '2026-11-26T08:00:00+00:00', updatedBy: 'user1',
  },
  {
    id: '12', platform: 'android', version: '2.2.0',
    downloadUrl: 'https://dl.example.test/yundashi-2.2.0.apk', fileName: 'yundashi-2.2.0.apk',
    notes: '', published: false, updatedAt: '2026-11-26T09:00:00+00:00', updatedBy: 'user1',
  },
]

const ALL_PLATFORMS = [
  'desktop-macos-arm64', 'desktop-macos-x64', 'desktop-windows',
  'desktop-linux', 'android', 'ios',
]

async function render(t, rows = ROWS) {
  globalThis.releaseFixture = { list: async () => ({ items: rows, total: rows.length }), created: [], updated: [], removed: [], conflict: null }
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  await act(async () => {
    root.render(h(NextIntlClientProvider, { locale: 'zh-CN', messages, timeZone: 'Asia/Shanghai' }, h(ReleaseFilesPage)))
  })
  t.after(async () => {
    await act(async () => root.unmount())
    container.remove()
    document.body.innerHTML = ''
    delete globalThis.releaseFixture
  })
  return { container }
}

async function until(check) {
  for (let count = 0; count < 100; count++) {
    if (check()) return
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
  }
  assert.fail('Expected UI state did not arrive: ' + document.body.textContent)
}

function fill(container, selector, value) {
  const input = container.querySelector(selector)
  assert.ok(input, `missing ${selector}`)
  const view = input instanceof window.HTMLTextAreaElement ? window.HTMLTextAreaElement : window.HTMLInputElement
  const setter = Object.getOwnPropertyDescriptor(view.prototype, 'value').set
  return act(async () => {
    setter.call(input, value)
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
}

function clickText(container, label) {
  const button = [...container.querySelectorAll('button')].find(item => item.textContent?.trim() === label)
  assert.ok(button, `missing button ${label}`)
  return act(async () => button.click())
}

test('release registry lists both platforms with their publication state', async t => {
  const { container } = await render(t)
  await until(() => container.textContent?.includes('2.2.0'))
  assert.match(container.textContent, /macOS（M 系列）/)
  assert.match(container.textContent, /Android/)
  assert.match(container.textContent, /已发布/)
  assert.match(container.textContent, /未发布/)
  assert.match(container.textContent, /yundashi-2\.2\.0-arm64\.dmg/)
  assert.equal(container.querySelectorAll('tbody tr').length, 2)
  // The public update-check endpoint is documented on the page.
  assert.match(container.textContent, /\/api\/v2\/releases\/check/)
})

test('adding a release sends the trimmed form to the admin endpoint', async t => {
  const { container } = await render(t)
  await until(() => container.textContent?.includes('2.2.0'))
  await clickText(container, '新增文件')
  const dialog = await (async () => {
    for (let count = 0; count < 100; count++) {
      const found = document.querySelector('[role="dialog"]')
      if (found) return found
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    }
    return null
  })()
  assert.ok(dialog, 'the release form did not open')
  await fill(dialog, '#release-version', ' 2.3.0 ')
  await fill(dialog, '#release-url', ' https://dl.example.test/yundashi-2.3.0.dmg ')
  await fill(dialog, '#release-file', ' yundashi-2.3.0.dmg ')
  await act(async () => {
    [...dialog.querySelectorAll('button')].find(item => item.textContent?.trim() === '保存').click()
  })
  await until(() => globalThis.releaseFixture.created.length === 1)
  const [created] = globalThis.releaseFixture.created
  // Apple Silicon is already registered, so the form defaults to the next free one.
  assert.equal(created.platform, 'desktop-macos-x64')
  assert.equal(created.version, '2.3.0')
  assert.equal(created.downloadUrl, 'https://dl.example.test/yundashi-2.3.0.dmg')
  assert.equal(created.fileName, 'yundashi-2.3.0.dmg')
  assert.equal(created.published, false)
})

test('the add button is disabled once every platform holds a release', async t => {
  const rows = ALL_PLATFORMS.map((platform, index) => ({
    id: String(20 + index), platform, version: '2.2.0',
    downloadUrl: `https://dl.example.test/yundashi-2.2.0-${platform}`, fileName: `yundashi-2.2.0-${platform}`,
    notes: '', published: true, updatedAt: '2026-11-26T08:00:00+00:00', updatedBy: 'user1',
  }))
  const { container } = await render(t, rows)
  await until(() => container.querySelectorAll('tbody tr').length === 6)
  const add = [...container.querySelectorAll('button')].find(item => item.textContent?.trim() === '新增文件')
  assert.ok(add, 'the add button stays visible')
  assert.equal(add.disabled, true, 'all six platforms are taken')
  assert.equal(add.getAttribute('title'), messages.admin.releases.allPlatformsTaken)
})

test('a platform taken by another administrator reports in Chinese and refreshes', async t => {
  const { container } = await render(t)
  await until(() => container.textContent?.includes('2.2.0'))
  await clickText(container, '新增文件')
  const dialog = await (async () => {
    for (let count = 0; count < 100; count++) {
      const found = document.querySelector('[role="dialog"]')
      if (found) return found
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    }
    return null
  })()
  assert.ok(dialog, 'the release form did not open')
  await fill(dialog, '#release-version', '2.3.0')
  await fill(dialog, '#release-url', 'https://dl.example.test/yundashi-2.3.0.dmg')
  await fill(dialog, '#release-file', 'yundashi-2.3.0.dmg')

  // The server answers in English; the page must not show that raw detail.
  globalThis.releaseFixture.conflict = new ApiError({
    status: 409,
    kind: 'http',
    detail: 'desktop-macos-x64 already has a release; edit that record instead',
  })
  globalThis.releaseFixture.list = async () => ({
    items: [
      ...ROWS,
      {
        id: '13', platform: 'desktop-macos-x64', version: '2.2.0',
        downloadUrl: 'https://dl.example.test/yundashi-2.2.0-x64.dmg', fileName: 'yundashi-2.2.0-x64.dmg',
        notes: '', published: true, updatedAt: '2026-11-26T10:00:00+00:00', updatedBy: 'user2',
      },
    ],
    total: ROWS.length + 1,
  })

  await act(async () => {
    [...dialog.querySelectorAll('button')].find(item => item.textContent?.trim() === '保存').click()
  })
  await until(() => dialog.textContent?.includes(messages.admin.releases.duplicateVersion.slice(0, 6)))
  assert.match(dialog.textContent, /该平台已有版本 2\.2\.0/)
  assert.equal(dialog.textContent.includes('already has a release'), false)
  // The list refreshed, so the occupying row is now visible behind the dialog.
  assert.match(container.textContent, /macOS（Intel）/)
})
