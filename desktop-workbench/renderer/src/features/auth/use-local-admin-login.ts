"use client"

import { useSyncExternalStore } from "react"

const subscribe = (onChange: () => void) => {
  window.addEventListener("hashchange", onChange)
  return () => window.removeEventListener("hashchange", onChange)
}

/** Keep local administrator authentication on its dedicated address, outside the public login UI. */
export function useLocalAdminLogin() {
  return useSyncExternalStore(
    subscribe,
    () =>
      window.location.hash.replace(/^#\/?/, "").split("?")[0] === "admin-login",
    () => false,
  )
}
