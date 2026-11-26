import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { setTimeout as delay } from "node:timers/promises"
import { JSDOM } from "jsdom"
import { registerSource } from "./helpers/onboarding-source.mjs"

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "https://app.example.test/", pretendToBeVisual: true })
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "HTMLButtonElement", "Element", "Node", "NodeFilter", "Event", "CustomEvent", "MutationObserver", "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame"]) {
  Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] })
}
// Matches the reduced-motion path, which keeps the slide transition synchronous.
window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} })
// jsdom has no scrollTo; the flow calls it on the viewport after each slide change.
dom.window.Element.prototype.scrollTo = () => undefined
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const { createElement: h, act } = await import("react")
const { createRoot } = await import("react-dom/client")
const { NextIntlClientProvider } = await import("next-intl")
const hooks = registerSource()
const { OnboardingGuideOverlay } = await import("../src/components/onboarding/onboarding-guide-overlay.tsx")
hooks.deregister()

function messages(locale) {
  return JSON.parse(readFileSync(new URL(`../messages/${locale}.json`, import.meta.url), "utf8"))
}

async function render(t) {
  const onClose = t.mock.fn()
  const container = document.createElement("div")
  document.body.append(container)
  const root = createRoot(container)
  await act(async () => root.render(
    h(NextIntlClientProvider, { locale: "zh-CN", messages: messages("zh-CN"), timeZone: "Asia/Shanghai" },
      h(OnboardingGuideOverlay, { open: true, onClose })),
  ))
  t.after(async () => { await act(async () => root.unmount()); container.remove() })
  return { onClose }
}

async function until(check) {
  for (let count = 0; count < 60; count++) {
    if (check()) return
    await act(async () => { await delay(15) })
  }
  assert.fail("Expected UI state did not arrive: " + document.body.textContent)
}

function button(label) {
  return [...document.body.querySelectorAll("button")].find((item) => item.textContent?.includes(label))
}

async function click(node) {
  assert.ok(node, "expected button to exist")
  await act(async () => { node.dispatchEvent(new window.MouseEvent("click", { bubbles: true })) })
}

test("the guide walks all four slides and can be closed from the last one", async (t) => {
  const { onClose } = await render(t)

  await until(() => button("下一页"))
  assert.match(document.body.textContent, /你的 Agent/)

  await click(button("下一页"))
  await until(() => button("下一步"))
  // Device slide uses the illustrative fixture, never a real connector.
  assert.match(document.body.textContent, /示例设备/)
  assert.ok(document.body.querySelector('ul[aria-label="示例 Agent"]'))

  await click(button("下一步"))
  await until(() => button("连接手机"))
  assert.equal(document.body.querySelector('[data-slide="phone"]') !== null, true)

  // The phone step advances instead of opening the live pairing dialog.
  await click(button("连接手机"))
  await until(() => button("立刻体验"))
  assert.equal(document.body.querySelector('[data-slide="complete"]') !== null, true)

  await click(button("立刻体验"))
  assert.equal(onClose.mock.callCount(), 1)
})

test("reopening the guide starts over at the welcome slide", async (t) => {
  const onClose = t.mock.fn()
  const container = document.createElement("div")
  document.body.append(container)
  const root = createRoot(container)
  const view = (open) => h(NextIntlClientProvider, { locale: "zh-CN", messages: messages("zh-CN"), timeZone: "Asia/Shanghai" },
    h(OnboardingGuideOverlay, { open, onClose }))
  t.after(async () => { await act(async () => root.unmount()); container.remove() })

  await act(async () => root.render(view(true)))
  await until(() => button("下一页"))
  await click(button("下一页"))
  await until(() => button("下一步"))
  assert.equal(document.body.querySelector('[data-slide="welcome"]'), null)

  // Closing and opening again replays from the first slide, not the last one seen.
  await act(async () => root.render(view(false)))
  await act(async () => root.render(view(true)))
  await until(() => button("下一页"))
  assert.equal(document.body.querySelector('[data-slide="welcome"]') !== null, true)
})

test("the guide renders nothing while closed", async (t) => {
  const container = document.createElement("div")
  document.body.append(container)
  const root = createRoot(container)
  await act(async () => root.render(
    h(NextIntlClientProvider, { locale: "zh-CN", messages: messages("zh-CN"), timeZone: "Asia/Shanghai" },
      h(OnboardingGuideOverlay, { open: false, onClose: () => undefined })),
  ))
  t.after(async () => { await act(async () => root.unmount()); container.remove() })
  assert.equal(document.body.querySelector('[data-slide="welcome"]'), null)
})
