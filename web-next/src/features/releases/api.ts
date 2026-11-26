import { apiClient } from "@/lib/api"
import type {
  PublicRelease,
  ReleaseCheck,
  ReleaseList,
  ReleasePlatform,
  ReleaseRecord,
  ReleaseWrite,
} from "./types"

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value)
  }
  const text = search.toString()
  return text ? `?${text}` : ""
}

export const releasesApi = {
  list(token: string, params: { platform?: ReleasePlatform } = {}) {
    return apiClient.get<ReleaseList>(`/admin/releases${query(params)}`, {
      token,
      cache: "no-store",
    })
  },
  create(token: string, body: ReleaseWrite) {
    return apiClient.post<ReleaseRecord>("/admin/releases", body, { token })
  },
  update(token: string, id: string, body: ReleaseWrite) {
    return apiClient.put<ReleaseRecord>(`/admin/releases/${id}`, body, { token })
  },
  remove(token: string, id: string) {
    return apiClient.delete<void>(`/admin/releases/${id}`, { token })
  },
  /** Public: newest published build per platform, for clients that poll directly. */
  latest(signal?: AbortSignal) {
    return apiClient.get<{ items: PublicRelease[] }>("/releases/latest", {
      auth: false,
      cache: "no-store",
      signal,
    })
  },
  check(platform: ReleasePlatform, currentVersion: string, signal?: AbortSignal) {
    return apiClient.get<ReleaseCheck>(
      `/releases/check${query({ platform, currentVersion })}`,
      { auth: false, cache: "no-store", signal },
    )
  },
}
