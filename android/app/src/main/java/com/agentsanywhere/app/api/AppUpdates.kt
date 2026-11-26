package com.agentsanywhere.app.api

import org.json.JSONArray
import org.json.JSONObject

data class AndroidAppRelease(
    val versionName: String,
    val downloadUrl: String,
)

class AppUpdatesApi(private val client: ApiClient = ApiClient()) {
    fun check(serverUrl: String, currentVersionName: String): AndroidAppRelease? {
        val payload = client.getJson(
            serverUrl = serverUrl,
            path = "/api/v2/releases/latest?type=android",
        )
        val release = payload.latestAndroidRelease() ?: return null
        val comparison = compareUpdateVersions(release.versionName, currentVersionName)
            ?: throw ApiException("Server release response has no valid version.")
        if (comparison <= 0) return null
        if (release.downloadUrl.isBlank()) throw ApiException("Server release response has no download URL.")
        return release
    }

    /**
     * Accepts a single release object, `{items: [...]}` or `{result: {...}}` so the
     * endpoint can change shape without breaking the client.
     */
    private fun JSONObject.latestAndroidRelease(): AndroidAppRelease? {
        val candidates = buildList {
            optJSONArray("items")?.let { addAll(it.toReleaseObjects()) }
            optJSONObject("result")?.let { result ->
                val items = result.optJSONArray("items")
                if (items != null) addAll(items.toReleaseObjects()) else add(result)
            }
            if (has("version")) add(this@latestAndroidRelease)
        }
        return candidates
            .mapNotNull { it.toAndroidRelease() }
            .maxWithOrNull { a, b -> compareUpdateVersions(a.versionName, b.versionName) ?: 0 }
    }

    private fun JSONArray.toReleaseObjects(): List<JSONObject> {
        return (0 until length()).mapNotNull { optJSONObject(it) }
    }

    private fun JSONObject.toAndroidRelease(): AndroidAppRelease? {
        val platform = firstText("platform", "type")
        if (platform.isNotEmpty() && !platform.equals(ANDROID_PLATFORM, ignoreCase = true)) return null
        val versionName = text("version")
        if (versionName.isEmpty() || compareUpdateVersions(versionName, versionName) == null) return null
        return AndroidAppRelease(
            versionName = versionName,
            downloadUrl = text("downloadUrl"),
        )
    }

    /** Reads a string field, treating `null` and JSON null as empty. */
    private fun JSONObject.text(key: String): String {
        return if (isNull(key)) "" else optString(key).trim()
    }

    private fun JSONObject.firstText(vararg keys: String): String {
        return keys.firstNotNullOfOrNull { key -> text(key).takeIf(String::isNotEmpty) }.orEmpty()
    }

    private companion object {
        const val ANDROID_PLATFORM = "android"
    }
}