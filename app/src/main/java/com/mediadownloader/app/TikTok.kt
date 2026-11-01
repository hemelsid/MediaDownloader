package com.mediadownloader.app

import android.annotation.SuppressLint
import android.content.Context
import android.net.Uri
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.coroutines.resume

/**
 * TikTok now only answers real browsers, so the phone's yt-dlp (which can't imitate one) fails.
 * Instead we open the TikTok page in a hidden WebView — a real browser — and read the video
 * details TikTok puts in the page (all qualities, without watermark). The video file itself is
 * then downloaded with that page's cookies.
 */
object TikTok {
    const val REFERER = "https://www.tiktok.com/"
    const val DESKTOP_UA =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

    private val pathRe = Regex("""^/(@[^/]*/(video|photo)/\d+|t/\w+|embed/(v2/)?\d+|share/video/\d+)""")

    fun isTikTok(url: String): Boolean {
        val h = Cookies.hostOf(url) ?: return false
        return h == "tiktok.com" || h.endsWith(".tiktok.com")
    }

    /** One video (or photo post) link, including short links like vt.tiktok.com/xxxx */
    fun isPostLink(url: String): Boolean {
        val h = Cookies.hostOf(url) ?: return false
        if (h == "vt.tiktok.com" || h == "vm.tiktok.com") return true
        if (!isTikTok(url)) return false
        val p = try { Uri.parse(url).path ?: "" } catch (_: Exception) { "" }
        return pathRe.containsMatchIn(p)
    }

    /** m.tiktok.com/…, tiktok.com/… and /photo/ links -> the www form the engine knows. */
    fun normalize(url: String): String {
        val u = try { Uri.parse(url.trim()) } catch (_: Exception) { return url }
        val h = u.host?.lowercase() ?: return url
        val path = u.path ?: return url
        if (h !in setOf("tiktok.com", "m.tiktok.com", "web.tiktok.com", "www.tiktok.com")) return url
        if (!pathRe.containsMatchIn(path)) return url
        return "https://www.tiktok.com" + path.replace("/photo/", "/video/")
    }

    private val READ_JS = """
        (function(){try{
          var e=document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
          if(!e) return JSON.stringify({wait:true,url:location.href});
          var d=(JSON.parse(e.textContent)||{}).__DEFAULT_SCOPE__||{};
          var vd=d['webapp.video-detail'];
          if(!vd) return JSON.stringify({wait:true,url:location.href});
          var it=(vd.itemInfo||{}).itemStruct;
          if(!it||!it.id) return JSON.stringify({status:vd.statusCode||-1,msg:vd.statusMsg||'',url:location.href});
          var ip=null;
          if(it.imagePost&&it.imagePost.images) ip=it.imagePost.images.map(function(i){return ((i.imageURL||{}).urlList||[])[0]||'';});
          var a=it.author||{};
          return JSON.stringify({ok:true,url:location.href,id:it.id,desc:it.desc||'',author:a.uniqueId||'',nick:a.nickname||'',
            video:it.video||{},music:it.music||{},stats:it.stats||{},images:ip});
        }catch(x){return JSON.stringify({wait:true,err:String(x)});}})()
    """.trimIndent()

    @SuppressLint("SetJavaScriptEnabled")
    suspend fun loadInfo(ctx: Context, link: String): MediaInfo {
        val url = normalize(link)
        val data = withContext(Dispatchers.Main) {
            val w = WebView(ctx.applicationContext)
            try {
                w.settings.javaScriptEnabled = true
                w.settings.domStorageEnabled = true
                w.settings.mediaPlaybackRequiresUserGesture = true
                w.settings.blockNetworkImage = true
                w.settings.userAgentString = DESKTOP_UA
                CookieManager.getInstance().setAcceptCookie(true)
                CookieManager.getInstance().setAcceptThirdPartyCookies(w, true)
                w.webViewClient = WebViewClient()
                w.loadUrl(url)
                var result: JSONObject? = null
                var last: JSONObject? = null
                withTimeoutOrNull(30_000) {
                    while (result == null) {
                        delay(700)
                        val o = eval(w, READ_JS) ?: continue
                        last = o
                        if (o.optBoolean("ok") || o.has("status")) result = o
                    }
                }
                CookieManager.getInstance().flush()
                result ?: last
            } finally {
                w.stopLoading()
                w.destroy()
            }
        }
        if (data == null || !data.optBoolean("ok")) throw failure(data)
        return toInfo(data)
    }

    private suspend fun eval(w: WebView, js: String): JSONObject? = suspendCancellableCoroutine { cont ->
        w.evaluateJavascript(js) { raw ->
            val o = try { (JSONTokener(raw).nextValue() as? String)?.let { JSONObject(it) } } catch (_: Exception) { null }
            if (cont.isActive) cont.resume(o)
        }
    }

    private fun failure(d: JSONObject?): InfoException {
        val site = Cookies.SITES.firstOrNull { it.key == "tiktok" }
        val status = d?.optInt("status", 0) ?: 0
        val at = d?.optString("url").orEmpty()
        val msg = when {
            status == 10204 || status == 10202 -> "This TikTok video was deleted or the link is wrong."
            status == 10216 || status == 10222 -> "This TikTok video is private or for friends only. Log in to TikTok in the Browser, then try again."
            status == 10101 || status == 10223 -> "TikTok doesn't show this video in your country."
            at.contains("/login") -> "TikTok asks to log in for this video. Log in to TikTok in the Browser, then try again."
            d == null || d.optBoolean("wait") -> "TikTok didn't answer. Check the connection and try again — or open the video in the Browser, play it, then tap ⬇."
            else -> "TikTok couldn't show this video (code $status)."
        }
        return InfoException(msg, "TikTok reader: ${d ?: "no answer"}", if (at.contains("/login")) site else null, false)
    }

    private fun toInfo(d: JSONObject): MediaInfo {
        val v = d.optJSONObject("video") ?: JSONObject()
        val author = d.optString("author")
        val id = d.optString("id")
        val desc = d.optString("desc").lines().firstOrNull { it.isNotBlank() }?.trim().orEmpty()
        val duration = v.optLong("duration", 0)
        val pageUrl = "https://www.tiktok.com/@$author/video/$id"

        // Every quality TikTok offers (no watermark). Prefer H.264 so the file plays in every gallery.
        class Var(val short: Int, val size: Long, val url: String, val h264: Boolean, val bitrate: Long)
        val vars = mutableListOf<Var>()
        val br = v.optJSONArray("bitrateInfo") ?: JSONArray()
        for (i in 0 until br.length()) {
            val b = br.optJSONObject(i) ?: continue
            val pa = b.optJSONObject("PlayAddr") ?: continue
            val u = pa.optJSONArray("UrlList")?.let { l -> (0 until l.length()).map { l.optString(it) } }
                ?.firstOrNull { it.startsWith("http") } ?: continue
            val wd = pa.optInt("Width", 0); val ht = pa.optInt("Height", 0)
            val codec = b.optString("CodecType")
            vars += Var(minOf(wd, ht).takeIf { it > 0 } ?: maxOf(wd, ht), pa.optLong("DataSize", 0), u,
                codec.contains("264") || codec.isBlank(), b.optLong("Bitrate", 0))
        }
        val play = v.optString("playAddr").takeIf { it.startsWith("http") }
        if (vars.isEmpty() && play != null) {
            vars += Var(minOf(v.optInt("width"), v.optInt("height")), v.optLong("size", 0), play, true, 0)
        }

        val video = mutableListOf<QualityOption>()
        vars.groupBy { it.short }.toSortedMap(compareByDescending { it }).forEach { (short, list) ->
            val best = list.filter { it.h264 }.maxByOrNull { it.bitrate } ?: list.maxByOrNull { it.bitrate } ?: return@forEach
            val label = if (short > 0) "${qualityLabel(short)} - ${short}p" else "Original quality"
            video += QualityOption(label, best.size, height = short.takeIf { it > 0 }, direct = best.url)
        }

        val images = d.optJSONArray("images")?.let { a -> (0 until a.length()).map { a.optString(it) }.filter { it.startsWith("http") } }
            .orEmpty()
        if (images.isNotEmpty()) {
            video.add(0, QualityOption("All photos (${images.size})", 0, images = images))
        }

        // Sound: taken from the smallest video (same sound track), or the post's music for photo posts.
        val musicUrl = d.optJSONObject("music")?.optString("playUrl")?.takeIf { it.startsWith("http") }
        val audioSrc = vars.filter { it.h264 }.minByOrNull { it.size.takeIf { s -> s > 0 } ?: Long.MAX_VALUE }?.url
            ?: vars.firstOrNull()?.url ?: musicUrl
        val audio = if (audioSrc == null) emptyList() else listOf(
            QualityOption("MP3 - 320 kbps", duration * 40_000, audio = AudioKind.MP3_320, direct = audioSrc),
            QualityOption("MP3 - 128 kbps", duration * 16_000, audio = AudioKind.MP3_128, direct = audioSrc),
            QualityOption("M4A - original", duration * 16_000, audio = AudioKind.M4A, direct = audioSrc),
        )
        if (video.isEmpty() && audio.isEmpty()) {
            throw InfoException("No downloadable video in this TikTok post.", "TikTok reader: no play address", null, false)
        }
        val stats = d.optJSONObject("stats")
        return MediaInfo(
            url = pageUrl,
            referer = REFERER,
            title = desc.ifBlank { "TikTok video by @$author" }.take(150),
            thumbnail = v.optString("originCover").ifBlank { v.optString("cover") }.ifBlank { null },
            uploader = "@$author".takeIf { author.isNotBlank() },
            site = "TikTok",
            durationSec = duration,
            views = stats?.optLong("playCount", 0) ?: 0,
            isPlaylist = false,
            count = 0,
            video = video,
            audio = audio,
        )
    }

    private fun qualityLabel(h: Int) = when {
        h >= 2160 -> "4K Ultra HD"; h >= 1440 -> "QHD Video"; h >= 1080 -> "FHD Video"
        h >= 720 -> "HD Video"; h >= 480 -> "SD Video"; else -> "Low"
    }

    /** Plain HTTP download with TikTok's cookies (used for photos, which yt-dlp can't fetch). */
    fun fetch(url: String, dest: File, onProgress: (Float, String) -> Unit) {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.connectTimeout = 20_000; c.readTimeout = 30_000
            c.setRequestProperty("User-Agent", DESKTOP_UA)
            c.setRequestProperty("Referer", REFERER)
            CookieManager.getInstance().getCookie(REFERER)?.let { c.setRequestProperty("Cookie", it) }
            if (c.responseCode !in 200..299) throw IllegalStateException("HTTP Error ${c.responseCode}")
            val total = c.contentLengthLong
            var done = 0L
            c.inputStream.use { inp ->
                dest.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        if (Thread.interrupted()) throw InterruptedException()
                        val n = inp.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        done += n
                        if (total > 0) onProgress(done * 100f / total, "")
                    }
                }
            }
        } finally {
            c.disconnect()
        }
    }

    fun imageExt(url: String): String {
        val p = url.substringBefore('?').lowercase()
        return when {
            p.endsWith(".webp") -> "webp"; p.endsWith(".png") -> "png"; p.endsWith(".heic") -> "heic"; else -> "jpg"
        }
    }
}
