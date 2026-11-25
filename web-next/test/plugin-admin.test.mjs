import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { JSDOM } from 'jsdom'
import { registerSource } from './helpers/onboarding-source.mjs'
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'https://fixture.example/',
  pretendToBeVisual: true,
})
for (const name of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLTextAreaElement',
  'HTMLFormElement',
  'HTMLButtonElement',
  'Element',
  'Node',
  'NodeFilter',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'CustomEvent',
  'MutationObserver',
  'getComputedStyle',
  'requestAnimationFrame',
  'cancelAnimationFrame',
  'DocumentFragment',
])
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value: dom.window[name],
  })
window.matchMedia = () => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
})
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
HTMLElement.prototype.scrollIntoView = () => {}
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const { createElement: h, act } = await import('react')
const { createRoot } = await import('react-dom/client')
const { NextIntlClientProvider } = await import('next-intl')
const hooks = registerSource()
const authHook = registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('/components/auth/auth-context.tsx'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export const useAuth=()=>({session:{accessToken:"test"}})',
      }
    return nextLoad(url, context)
  },
})
const { PluginEditor } =
  await import('../src/components/admin/plugin-editor.tsx')
const { PluginsPage } = await import('../src/components/admin/plugins-page.tsx')
const { parseItems, patchItem, validateItem } =
  await import('../src/features/plugin-catalog/editor.ts')
const { apiClient } = await import('../src/lib/api/index.ts')
const { PluginSyncCard } =
  await import('../src/components/admin/plugin-sync-card.tsx')
authHook.deregister()
hooks.deregister()
const messages = JSON.parse(
  readFileSync(new URL('../messages/zh-CN.json', import.meta.url), 'utf8'),
)
const item = {
  id: 'test-plugin',
  name: 'test-plugin',
  displayName: '测试插件',
  summary: '测试简介',
  package: { registry: 'npm', name: 'test-plugin' },
  categories: ['tools'],
}
async function render(t, element) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  await act(async () =>
    root.render(
      h(
        NextIntlClientProvider,
        { locale: 'zh-CN', messages, timeZone: 'Asia/Shanghai' },
        element,
      ),
    ),
  )
  t.after(async () => {
    await act(async () => root.unmount())
    container.remove()
  })
  return container
}
const button = (name) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === name,
  )
async function click(node) {
  assert.ok(node, 'button exists')
  await act(async () => {
    node.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true, button: 0 }),
    )
    node.click()
  })
}
async function input(id, value) {
  const node = document.getElementById(id)
  assert.ok(node, id)
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      node instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype,
      'value',
    ).set.call(node, value)
    node.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function submit() {
  await act(async () =>
    document
      .getElementById('plugin-editor-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })),
  )
}

test('real schema validation and lossless patches preserve unsupported extension fields', () => {
  assert.deepEqual(validateItem(item), [])
  const { package: ignored, ...noInstall } = item
  assert.ok(validateItem(noInstall).some((e) => e.keyword === 'anyOf'))
  assert.ok(
    validateItem({ ...item, package: { registry: 'git', name: 'UPPER NAME' } })
      .length,
  )
  assert.ok(validateItem({ ...item, categories: ['UPPER SPACE'] }).length)
  assert.ok(
    validateItem({
      ...item,
      repository: { url: 'https://github.com/owner' },
    }).some((e) => e.keyword === 'repository'),
  )
  const extended = {
    ...item,
    future: { custom: true },
    publisher: { name: '作者', future: 'retained' },
  }
  const patched = patchItem(extended, ['publisher', 'name'], '新作者')
  assert.deepEqual(patched.future, { custom: true })
  assert.equal(patched.publisher.future, 'retained')
  assert.equal(extended.publisher.name, '作者')
  assert.ok(
    validateItem(patched).some((e) => e.keyword === 'additionalProperties'),
  )
  assert.deepEqual(parseItems(JSON.stringify({ items: [extended] }), true), [
    extended,
  ])
  assert.throws(() => parseItems('{', false))
  assert.throws(() => parseItems('[]', true))
})
test('new form validates required fields and submits metadata without publication', async (t) => {
  const save = t.mock.fn(async () => {})
  await render(
    t,
    h(PluginEditor, {
      entry: 'new',
      categories: ['tools'],
      onClose() {},
      onSave: save,
    }),
  )
  assert.equal(
    document.querySelector('[role="tab"][data-state="active"]').textContent,
    '表单录入',
  )
  await submit()
  assert.equal(save.mock.callCount(), 0)
  assert.ok(document.querySelector('[aria-invalid="true"]'))
  for (const [key, value] of Object.entries({
    id: 'new-plugin',
    displayName: '新插件',
    name: 'new-plugin',
    summary: '可视化录入',
    'package-name': 'new-plugin',
  }))
    await input(`plugin-field-${key}`, value)
  await submit()
  assert.equal(save.mock.callCount(), 1)
  const sent = save.mock.calls[0].arguments[0][0]
  assert.equal(sent.id, 'new-plugin')
  assert.equal(sent.summary, '可视化录入')
  assert.equal('status' in sent, false)
})
test('edit fills values, freezes ID and retains published status', async (t) => {
  const save = t.mock.fn(async () => {})
  await render(
    t,
    h(PluginEditor, {
      entry: { id: '42', status: 'published', item },
      categories: ['tools'],
      onClose() {},
      onSave: save,
    }),
  )
  assert.equal(document.getElementById('plugin-field-id').disabled, true)
  assert.equal(
    document.getElementById('plugin-field-displayName').value,
    '测试插件',
  )
  assert.match(document.body.textContent, /当前已上架/)
  await input('plugin-field-summary', '更新后的简介')
  await submit()
  assert.equal(save.mock.calls[0].arguments[0][0].summary, '更新后的简介')
  assert.equal('status' in save.mock.calls[0].arguments[0][0], false)
})
test('JSON switching preserves extensions and invalid text; immutable ID cannot be bypassed', async (t) => {
  const save = t.mock.fn(async () => {})
  await render(
    t,
    h(PluginEditor, {
      entry: { id: '42', status: 'draft', item },
      categories: [],
      onClose() {},
      onSave: save,
    }),
  )
  await click(button('JSON 导入'))
  await input('plugin-json', '{broken')
  await click(button('表单录入'))
  assert.equal(document.getElementById('plugin-json').value, '{broken')
  await input(
    'plugin-json',
    JSON.stringify({ ...item, future: { retain: true } }),
  )
  await click(button('解析并回填表单'))
  await input('plugin-field-summary', '改了简介')
  await click(button('JSON 导入'))
  assert.deepEqual(
    JSON.parse(document.getElementById('plugin-json').value).future,
    { retain: true },
  )
  await submit()
  assert.equal(save.mock.callCount(), 0)
  assert.match(document.body.textContent, /当前后端不支持/)
  await input('plugin-json', JSON.stringify({ ...item, id: 'other-id' }))
  await submit()
  assert.equal(save.mock.callCount(), 0)
  assert.match(document.body.textContent, /插件 ID 创建后不可修改/)
})
test('batch JSON fills per-plugin forms and submits all records', async (t) => {
  const save = t.mock.fn(async () => {})
  await render(
    t,
    h(PluginEditor, {
      entry: 'import',
      categories: [],
      onClose() {},
      onSave: save,
    }),
  )
  await input(
    'plugin-json',
    JSON.stringify({ items: [item, { ...item, id: 'second' }] }),
  )
  await click(button('解析并回填表单'))
  assert.equal(document.getElementById('plugin-field-id').value, item.id)
  await submit()
  assert.equal(save.mock.calls[0].arguments[0].length, 2)
})
test('list uses server pagination and stats, confirms bulk actions and reuses publication switch', async (t) => {
  const calls = []
  t.mock.method(apiClient, 'get', async (path) => {
    calls.push(path)
    if (path === '/admin/plugins/summary')
      return {
        total: 34752,
        published: 12,
        draft: 34740,
        sourceCount: 2,
        categories: ['tools'],
        sources: { dshfind: 'https://api.dshfind.com/v1/catalog' },
      }
    if (path === '/admin/plugins/sync')
      return {
        jobId: null,
        status: 'idle',
        source: null,
        total: 0,
        processed: 0,
        created: 0,
        updated: 0,
        unchanged: 0,
        skipped: 0,
        failed: 0,
        errors: [],
      }
    return { items: [{ id: '42', status: 'draft', item }], total: 34752 }
  })
  const patch = t.mock.method(apiClient, 'patch', async () => ({}))
  const post = t.mock.method(apiClient, 'post', async () => ({ updated: 1 }))
  await render(t, h(PluginsPage))
  assert.ok(
    calls.some(
      (path) => path.includes('limit=20') && path.includes('offset=0'),
    ),
  )
  assert.match(document.body.textContent, /34,752/)
  await click(button('已上架'))
  assert.ok(calls.some((path) => path.includes('status=published')))
  await click(document.querySelector('[role="switch"]'))
  assert.equal(patch.mock.callCount(), 1)
  assert.equal(patch.mock.calls[0].arguments[1].status, 'published')
  await click(document.querySelector('[aria-label="选择插件：测试插件"]'))
  await click(button('批量上架'))
  assert.equal(post.mock.callCount(), 0)
  await click(button('确认'))
  assert.equal(post.mock.callCount(), 1)
  assert.equal(post.mock.calls[0].arguments[0], '/admin/plugins/bulk')
  assert.deepEqual(post.mock.calls[0].arguments[1], {
    ids: ['42'],
    status: 'published',
  })
})

test('page size and source filters use query parameters and deletion requires confirmation', async (t) => {
  const calls = []
  t.mock.method(apiClient, 'get', async (path) => {
    calls.push(path)
    if (path === '/admin/plugins/summary')
      return {
        total: 1,
        published: 0,
        draft: 1,
        sourceCount: 1,
        categories: ['tools'],
        sources: { dshfind: 'https://api.dshfind.com/v1/catalog' },
      }
    if (path === '/admin/plugins/sync')
      return { jobId: null, status: 'idle', errors: [] }
    return { items: [{ id: '42', status: 'draft', item }], total: 1 }
  })
  const remove = t.mock.method(apiClient, 'delete', async () => ({}))
  await render(t, h(PluginsPage))
  async function choose(label, text) {
    const trigger = document.querySelector(
      `[role="combobox"][aria-label="${label}"]`,
    )
    await act(async () =>
      trigger.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }),
      ),
    )
    const option = [...document.querySelectorAll('[role="option"]')].find(
      (n) => n.textContent.trim() === text,
    )
    await click(option)
  }
  await choose('每页条数', '50 条/页')
  assert.ok(calls.some((path) => path.includes('limit=50')))
  await choose('来源', 'dshfind')
  assert.ok(calls.some((path) => path.includes('source=dshfind')))
  const trigger = document.querySelector('[aria-label="操作：测试插件"]')
  await act(async () =>
    trigger.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }),
    ),
  )
  await click(
    [...document.querySelectorAll('[role="menuitem"]')].find(
      (n) => n.textContent === '删除插件',
    ),
  )
  assert.equal(remove.mock.callCount(), 0)
  assert.match(
    document.querySelector('[role="dialog"]').textContent,
    /确认删除/,
  )
  await click(button('取消'))
  assert.equal(remove.mock.callCount(), 0)
})

test('loading, empty data and failures have explicit states and English has matching translation keys', async (t) => {
  let release
  const deferred = new Promise((resolve) => {
    release = resolve
  })
  let fail = false
  t.mock.method(apiClient, 'get', async (path) => {
    if (path === '/admin/plugins/summary')
      return {
        total: 0,
        published: 0,
        draft: 0,
        sourceCount: 0,
        categories: [],
        sources: {},
      }
    if (path === '/admin/plugins/sync')
      return { jobId: null, status: 'idle', errors: [] }
    if (fail) throw new Error('fixture unavailable')
    return deferred
  })
  await render(t, h(PluginsPage))
  assert.match(document.body.textContent, /加载中/)
  await act(async () => release({ items: [], total: 0 }))
  assert.match(document.body.textContent, /没有符合条件/)
  fail = true
  await click(button('已上架'))
  assert.match(document.body.textContent, /fixture unavailable/)
  assert.ok(button('重试'))
  const en = JSON.parse(
    readFileSync(new URL('../messages/en.json', import.meta.url), 'utf8'),
  ).pluginAdmin
  function keys(object, prefix = '') {
    return Object.entries(object)
      .flatMap(([key, value]) =>
        typeof value === 'object'
          ? keys(value, prefix + key + '.')
          : [prefix + key],
      )
      .sort()
  }
  assert.deepEqual(keys(en), keys(messages.pluginAdmin))
})

test('compact sync never starts on mount, collapses completed details and retains URL validation', async (t) => {
  const complete = t.mock.fn(async () => {})
  t.mock.method(apiClient, 'get', async () => ({
    jobId: 'done',
    status: 'completed',
    source: 'custom',
    total: 10,
    processed: 10,
    created: 7,
    updated: 2,
    unchanged: 1,
    skipped: 0,
    failed: 0,
    errors: [],
  }))
  const post = t.mock.method(apiClient, 'post', async () => ({}))
  await render(t, h(PluginSyncCard, { token: 'test', onComplete: complete }))
  assert.equal(post.mock.callCount(), 0)
  assert.equal(complete.mock.callCount(), 1)
  assert.doesNotMatch(document.body.textContent, /新增 7/)
  await click(button('同步详情'))
  assert.match(document.body.textContent, /新增 7/)
  await click(button('同步目录'))
  assert.equal(
    document.getElementById('plugin-catalog-url').value,
    'https://deepseek1024.com/api/v2/plugins',
  )
  await input('plugin-catalog-url', 'http://127.0.0.1:8000/plugins')
  await act(async () =>
    document
      .querySelector('[role="dialog"] form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })),
  )
  assert.equal(post.mock.callCount(), 0)
  assert.match(
    document.querySelector('[role="dialog"]').textContent,
    /公网 HTTPS/,
  )
})

test('generated form schema stays identical to the server source of truth', () => {
  assert.equal(
    readFileSync(
      new URL(
        '../src/features/plugin-catalog/catalog.schema.json',
        import.meta.url,
      ),
      'utf8',
    ),
    readFileSync(
      new URL(
        '../../server/agent_server/core/plugin_schemas/catalog-provider-page.schema.json',
        import.meta.url,
      ),
      'utf8',
    ),
  )
})
