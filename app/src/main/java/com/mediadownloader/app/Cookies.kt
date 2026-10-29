package com.mediadownloader.app

import android.content.Context
import android.webkit.CookieManager
import java.io.File

/**
 * Cookies come from two places:
 *  1. The in-app browser — if the user is logged in there, downloads automatically use that login.
 *  2. An imported cookies.txt (exported from a PC browser).
 * Both are written into one private cookies.txt for every yt-dlp run.
 */
object Cookies {
    data class Site(
        val key: String,
        val name: String,
        val loginUrl: String,
        val cookieUrl: String,
        val loginCookie: String,
        val hosts: List<String>,
    )

    val SITES = listOf(
        Site("youtube", "YouTube",
            "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fm.youtube.com%2F",
            "https://www.youtube.com", "SAPISID", listOf("youtube.com", "youtu.be")),
        Site("facebook", "Facebook", "https://m.facebook.com/login/",
            "https://www.facebook.com", "c_user", listOf("facebook.com", "fb.watch", "fb.com")),
        Site("instagram", "Instagram", "https://www.instagram.com/accounts/login/",
            "https://www.instagram.com", "sessionid", listOf("instagram.com")),
        Site("tiktok", "TikTok", "https://www.tiktok.com/login",
            "https://www.tiktok.com", "sessionid", listOf("tiktok.com")),
        Site("x", "X / Twitter", "https://x.com/i/flow/login",
            "https://x.com", "auth_token", listOf("x.com", "twitter.com")),
    )

    fun hostOf(url: String): String? =
        try { java.net.URI(url.trim()).host?.lowercase()?.removePrefix("www.") } catch (_: Exception) { null }

    fun siteFor(url: String): Site? {
        val host = hostOf(url) ?: return null
        return SITES.firstOrNull { s -> s.hosts.any { host == it || host.endsWith(".$it") } }
    }

    /** "m.youtube.com" -> "youtube.com", "www.bbc.co.uk" -> "bbc.co.uk" */
    fun baseDomain(host: String): String {
        val p = host.split('.').filter { it.isNotEmpty() }
        if (p.size <= 2) return host
        val twoLevel = p[p.size - 1].length == 2 && p[p.size - 2].length <= 3
        return p.takeLast(if (twoLevel) 3 else 2).joinToString(".")
    }

    private fun importFile(ctx: Context, s: Site) = File(ctx.filesDir, "cookies/${s.key}.txt")

    private fun browserCookies(url: String): Map<String, String> {
        val raw = try { CookieManager.getInstance().getCookie(url) } catch (_: Throwable) { null } ?: return emptyMap()
        val out = linkedMapOf<String, String>()
        raw.split(";").forEach { part ->
            val p = part.trim()
            val eq = p.indexOf('=')
            if (eq > 0) out[p.substring(0, eq)] = p.substring(eq + 1)
        }
        return out
    }

    fun isLoggedIn(ctx: Context, s: Site) =
        importFile(ctx, s).let { it.exists() && it.length() > 0 } ||
            browserCookies(s.cookieUrl).containsKey(s.loginCookie)

    fun logout(ctx: Context, s: Site) {
        importFile(ctx, s).delete()
        val cm = CookieManager.getInstance()
        val domain = "." + baseDomain(hostOf(s.cookieUrl) ?: return)
        browserCookies(s.cookieUrl).keys.forEach { name ->
            val dead = "$name=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/"
            cm.setCookie(s.cookieUrl, dead)
            cm.setCookie(s.cookieUrl, "$dead; Domain=$domain")
        }
        cm.flush()
    }

    /** Import a Netscape cookies.txt. Returns names of the sites found in it. */
    fun importNetscape(ctx: Context, text: String): List<String> {
        val bySite = linkedMapOf<Site, MutableList<String>>()
        text.lineSequence().forEach { raw ->
            var line = raw.trim()
            if (line.startsWith("#HttpOnly_")) line = line.removePrefix("#HttpOnly_")
            if (line.isEmpty() || line.startsWith("#")) return@forEach
            val cols = line.split("\t")
            if (cols.size < 7) return@forEach
            val domain = cols[0].trimStart('.').lowercase()
            val site = SITES.firstOrNull { s -> s.hosts.any { domain == it || domain.endsWith(".$it") } }
                ?: SITES.first().takeIf { domain == "google.com" || domain.endsWith(".google.com") }
                ?: return@forEach
            bySite.getOrPut(site) { mutableListOf() } += cols.take(7).joinToString("\t")
        }
        bySite.forEach { (site, lines) ->
            importFile(ctx, site).apply { parentFile?.mkdirs() }.writeText(lines.joinToString("\n") + "\n")
        }
        return bySite.keys.map { it.name }
    }

    /**
     * Private cookies.txt for one yt-dlp run (yt-dlp rewrites the file on exit, so runs must not share one).
     * [urls] = the media url and the page it came from.
     */
    fun fileForRun(ctx: Context, dir: File, urls: List<String>): File? {
        val lines = mutableListOf<String>()
        SITES.forEach { s ->
            val f = importFile(ctx, s)
            if (f.exists()) lines += f.readLines().filter { it.isNotBlank() && !it.startsWith("#") }
        }
        val expiry = System.currentTimeMillis() / 1000 + 30L * 24 * 3600
        val domains = linkedSetOf<String>()
        urls.forEach { u ->
            hostOf(u)?.let { domains += baseDomain(it) }
            siteFor(u)?.let { s -> hostOf(s.cookieUrl)?.let { domains += baseDomain(it) } }
        }
        domains.forEach { d ->
            val cookies = browserCookies("https://$d") + browserCookies("https://www.$d") + browserCookies("https://m.$d")
            cookies.forEach { (k, v) -> lines += listOf(".$d", "TRUE", "/", "TRUE", expiry, k, v).joinToString("\t") }
        }
        if (lines.isEmpty()) return null
        val out = File(dir, "cookies.txt")
        out.writeText("# Netscape HTTP Cookie File\n" + lines.joinToString("\n") + "\n")
        return out
    }
}
