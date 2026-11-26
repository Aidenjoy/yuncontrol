/** macOS ships two builds, so Apple Silicon and Intel are separate platforms. */
export const RELEASE_PLATFORMS = [
  "desktop-macos-arm64",
  "desktop-macos-x64",
  "desktop-windows",
  "android",
  "ios",
] as const

export type ReleasePlatform = (typeof RELEASE_PLATFORMS)[number]

/** One administrator-managed installer record, drafts included. */
export type ReleaseRecord = {
  id: string
  platform: string
  version: string
  downloadUrl: string
  fileName: string
  notes: string
  published: boolean
  updatedAt: string
  updatedBy: string
}

export type ReleaseList = {
  items: ReleaseRecord[]
  total: number
}

export type ReleaseWrite = {
  platform: ReleasePlatform
  version: string
  downloadUrl: string
  fileName: string
  notes: string
  published: boolean
}

/** Published record exposed by the public update check. */
export type PublicRelease = {
  type: string
  platform: string
  version: string
  downloadUrl: string
  fileName: string
  notes: string
  publishedAt: string | null
}

export type ReleaseCheck = {
  platform: string
  currentVersion: string
  latestVersion: string | null
  updateAvailable: boolean
  downloadUrl: string | null
  fileName: string
  notes: string
  publishedAt: string | null
}
