package com.mediadownloader.app

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.MutableContextWrapper
import android.graphics.Bitmap
import android.net.Uri
import android.util.Base64
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import org.json.JSONTokener
import java.net.URLDecoder
import java.net.URLEncoder
import kotlin.coroutines.resume

enum class Tab { HOME, BROWSER, DOWNLOADS, FILES }

/** Request to open the quality sheet. */
data class SheetRequest(
    val url: String,
    val referer: String? = null,
    val titleHint: String? = null,
    val thumbHint: String? = null,
    /** Other media seen on the page, in case the guess was wrong (newest first). */
    val alternatives: List<String> = emptyList(),
    val nonce: Long = System.nanoTime(),
)

/** Small app-wide event bus between screens. */
object UiBus {
    val tab = MutableStateFlow(Tab.HOME)
    val sheet = MutableStateFlow<SheetRequest?>(null)
    val clipUrl = MutableStateFlow<String?>(null)
    val overlay = MutableStateFlow<String?>(null)   // "settings"

    fun openBrowser(url: String) {
        Browser.load(url)
        overlay.value = null
        tab.value = Tab.BROWSER
    }

    /** Text from the search box: link -> quality sheet / browser, words -> web search. */
    fun go(text: String) {
        val t = text.trim()
        if (t.isEmpty()) return
        val urls = Downloads.extractUrls(t)
        when {
            urls.isNotEmpty() -> {
                val u = urls.first()
                if (Browser.isVideoPage(u) || Browser.isMediaFile(u)) sheet.value = SheetRequest(u) else openBrowser(u)
            }
            Regex("""^[\w-]+(\.[\w-]+)+(/\S*)?$""").matches(t) -> openBrowser("https://$t")
            else -> openBrowser("https://www.google.com/search?tbm=vid&q=" + URLEncoder.encode(t, "UTF-8"))
        }
    }
}

/** A media request the page made, already cleaned and grouped. */
data class MediaHit(val key: String, val url: String, val time: Long, val audioOnly: Boolean)

/**
 * The in-app browser. One WebView lives for the whole app session, so switching tabs or apps
 * (e.g. to read an OTP) never reloads the page.
 *
 * Detection works like IDM: when ⬇ is tapped we ask the page which <video> is playing (or most
 * visible), then pick the matching source — the post's own link, Facebook's video id, the video's
 * direct file, or the most recent media request. Streaming pieces are merged into one entry.
 */
object Browser {
    var view: WebView? = null
        private set
    var userAgent: String? = null
        private set
    private var pendingUrl: String? = null

    val url = MutableStateFlow("")
    val title = MutableStateFlow("")
    val progress = MutableStateFlow(0)
    val canGoBack = MutableStateFlow(false)
    val canGoForward = MutableStateFlow(false)
    /** Media seen on the current page, one entry per real video/audio (not per piece). */
    val hits = MutableStateFlow<List<MediaHit>>(emptyList())

    private val mediaRegex = Regex(
        """\.(mp4|m4v|webm|mkv|mov|3gp|flv|m3u8|mpd|mp3|m4a|aac|ogg|oga|opus|wav)(\?.*)?$""", RegexOption.IGNORE_CASE
    )
    private val ignoreHosts = listOf("googlevideo.com", "doubleclick.net", "googlesyndication.com", "google-analytics.com")
    private val rangeParams = setOf("bytestart", "byteend", "range", "rn", "rbuf", "_nc_rid")

    private val videoPages = listOf(
        Regex("""youtube\.com/(watch|shorts/|live/|embed/)"""), Regex("""youtu\.be/."""),
        Regex("""tiktok\.com/.*/video/"""), Regex("""vt\.tiktok\.com/"""),
        Regex("""instagram\.com/(reel|reels|p|tv|stories)/"""),
        Regex("""facebook\.com/(.*/videos/\d|reel/\d|watch/?\?v=|story\.php\?story_fbid)"""), Regex("""fb\.watch/"""),
        Regex("""(x|twitter)\.com/[^/]+/status/"""), Regex("""vimeo\.com/\d+"""),
        Regex("""dailymotion\.com/video/"""), Regex("""dai\.ly/"""),
        Regex("""soundcloud\.com/[^/]+/[^/?]+"""), Regex("""reddit\.com/r/[^/]+/comments/"""),
        Regex("""/(view_video|video\d|videos?/[\w-]{4,})""", RegexOption.IGNORE_CASE),
    )

    fun isVideoPage(u: String) = videoPages.any { it.containsMatchIn(u) }
    fun isMediaFile(u: String) = mediaRegex.containsMatchIn(u.substringBefore('#').substringBefore('?'))
    private fun isFacebook(u: String) = Cookies.hostOf(u)?.let { it.contains("facebook.") || it.contains("fbcdn.") || it == "fb.watch" } == true

    fun load(u: String) {
        url.value = u
        val v = view
        if (v == null) pendingUrl = u else v.loadUrl(u)
    }

    @SuppressLint("SetJavaScriptEnabled")
    fun obtain(ctx: Context): WebView {
        view?.let { existing ->
            (existing.parent as? ViewGroup)?.removeView(existing)
            (existing.context as? MutableContextWrapper)?.setBaseContext(ctx)
            return existing
        }
        val w = WebView(MutableContextWrapper(ctx))
        w.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            @Suppress("DEPRECATION")
            databaseEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = true
            displayZoomControls = false
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            // Look like normal Chrome (Google blocks logins from "wv" WebViews)
            userAgentString = WebSettings.getDefaultUserAgent(ctx)
                .replace("; wv", "")
                .replace(Regex("""Version/\d+(\.\d+)*\s"""), "")
        }
        userAgent = w.settings.userAgentString
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(w, true)

        w.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val u = request?.url ?: return false
                if (u.scheme == "http" || u.scheme == "https") return false
                try {
                    val i = if (u.scheme == "intent") Intent.parseUri(u.toString(), Intent.URI_INTENT_SCHEME)
                    else Intent(Intent.ACTION_VIEW, u)
                    view?.context?.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                } catch (_: Exception) {}
                return true
            }

            override fun onPageStarted(view: WebView?, u: String?, favicon: Bitmap?) {
                if (u != null) setPage(u)
            }

            override fun onPageFinished(view: WebView?, u: String?) {
                if (u != null) url.value = u
                updateNav()
                CookieManager.getInstance().flush()
            }

            override fun doUpdateVisitedHistory(view: WebView?, u: String?, isReload: Boolean) {
                if (u != null && u != url.value) setPage(u)
                updateNav()
            }

            override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): WebResourceResponse? {
                request?.url?.toString()?.let { sniff(it) }
                return null
            }
        }
        w.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) { progress.value = newProgress }
            override fun onReceivedTitle(view: WebView?, t: String?) { title.value = t.orEmpty() }
        }
        w.setDownloadListener { dlUrl, _, contentDisposition, _, _ ->
            val name = Regex("""filename\*?=(?:UTF-8'')?"?([^";]+)""").find(contentDisposition ?: "")?.groupValues?.get(1)
            UiBus.sheet.value = SheetRequest(dlUrl, referer = url.value.ifBlank { null }, titleHint = name?.substringBeforeLast('.'))
        }
        view = w
        (pendingUrl ?: url.value.ifBlank { null })?.let { w.loadUrl(it) }
        pendingUrl = null
        return w
    }

    private fun setPage(u: String) {
        val old = url.value
        url.value = u
        // A brand-new page (not just a scroll/SPA change on the same site) forgets old media
        if (Cookies.hostOf(old) != Cookies.hostOf(u)) hits.value = emptyList()
    }

    private fun updateNav() {
        canGoBack.value = view?.canGoBack() == true
        canGoForward.value = view?.canGoForward() == true
    }

    // ------------------------------------------------------------------ sniffing

    /** Removes byte-range parameters so a streaming piece becomes the whole file. */
    fun wholeFile(u: String): String {
        val uri = Uri.parse(u)
        val names = uri.queryParameterNames
        if (names.none { it.lowercase() in rangeParams }) return u
        val b = uri.buildUpon().clearQuery()
        names.filter { it.lowercase() !in rangeParams }.forEach { n ->
            uri.getQueryParameters(n).forEach { v -> b.appendQueryParameter(n, v) }
        }
        return b.build().toString()
    }

    /** Facebook CDN links carry a base64 JSON in "efg" (video id, audio/video track…). */
    private fun efgJson(u: String): String {
        val efg = try { Uri.parse(u).getQueryParameter("efg") } catch (_: Exception) { null } ?: return ""
        val raw = try { URLDecoder.decode(efg, "UTF-8") } catch (_: Exception) { efg }
        for (flags in listOf(Base64.DEFAULT, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)) {
            try { String(Base64.decode(raw, flags)).let { if (it.contains("{")) return it } } catch (_: Exception) {}
        }
        return ""
    }

    fun facebookVideoId(u: String): String? =
        efgJson(u).let { j ->
            Regex(""""video_id"\s*:\s*"?(\d{6,})""").find(j)?.groupValues?.get(1)
                ?: Regex(""""xpv_asset_id"\s*:\s*"?(\d{6,})""").find(j)?.groupValues?.get(1)
        }

    private fun isAudioOnly(u: String): Boolean {
        val l = u.lowercase()
        if (Regex("""\.(mp3|m4a|aac|ogg|oga|opus|wav)(\?|$)""").containsMatchIn(l)) return true
        if (efgJson(u).contains("audio", true)) return true
        return l.contains("audio_only") || l.contains("/audio/") || l.contains("mime=audio")
    }

    private fun sniff(u: String) {
        if (!u.startsWith("http")) return
        val host = Cookies.hostOf(u) ?: return
        if (host.endsWith("googlevideo.com")) { YtTokens.capture(u, url.value); return }
        if (ignoreHosts.any { host.endsWith(it) }) return
        if (!isMediaFile(u)) return
        // HLS/DASH segment files are useless alone; their playlist is what we want
        if (Regex("""\.(ts|m4s)(\?|$)""", RegexOption.IGNORE_CASE).containsMatchIn(u)) return
        if (u.contains(Regex("""(seg|chunk|frag)[-_]?\d+""", RegexOption.IGNORE_CASE))) return
        val clean = wholeFile(u)
        val key = facebookVideoId(clean)?.let { "fb:$it" + if (isAudioOnly(clean)) ":a" else ":v" }
            ?: clean.substringBefore('?')
        val hit = MediaHit(key, clean, System.currentTimeMillis(), isAudioOnly(clean))
        hits.update { list -> (list.filterNot { it.key == key } + hit).takeLast(30) }
    }

    // ------------------------------------------------------------------ detection

    private data class Active(
        val src: String, val poster: String, val link: String, val text: String, val playing: Boolean,
    )

    private val ACTIVE_JS = """
        (function(){
          function area(v){var r=v.getBoundingClientRect();
            var w=Math.max(0,Math.min(r.right,innerWidth)-Math.max(r.left,0));
            var h=Math.max(0,Math.min(r.bottom,innerHeight)-Math.max(r.top,0));return w*h;}
          var best=null,score=-1;
          [].slice.call(document.querySelectorAll('video')).forEach(function(v){
            var s=area(v); if(!v.paused&&!v.ended) s+=1e9; else if(v.currentTime>0) s+=1e6;
            if(s>score){score=s;best=v;}});
          if(!best) return JSON.stringify({found:false});
          var src=best.currentSrc||best.src||'';
          if(!src){var so=best.querySelector('source[src]'); if(so) src=so.src;}
          var strong=/\/(reel|reels)\/|\/videos\/|\/watch\/?\?v=|[?&]v=|\/status\/|\/video\/|\/p\/|\/tv\//;
          var weak=/story\.php|story_fbid|\/permalink|\/posts\//;
          var link='',weakLink='',text='',el=best;
          for(var i=0;i<25&&el;i++){
            el=el.parentElement; if(!el) break;
            var as=el.querySelectorAll('a[href]');
            for(var j=0;j<as.length&&!link;j++){var h=as[j].href||'';
              if(h.indexOf('/hashtag/')>=0||h.indexOf('/photo')>=0||h.indexOf('/groups/')>=0&&!strong.test(h)) continue;
              if(strong.test(h)) link=h; else if(!weakLink&&weak.test(h)) weakLink=h;}
            if(!text){var t=el.querySelector('[dir="auto"],[data-ad-preview="message"],h1,h2,h3');
              if(t&&t.innerText&&t.innerText.trim().length>8) text=t.innerText.trim();}
            if(link&&text) break;
          }
          return JSON.stringify({found:true,src:src,poster:best.poster||'',link:link||weakLink,
            text:text.slice(0,140),playing:!best.paused});
        })()
    """.trimIndent()

    private suspend fun activeVideo(): Active? {
        val w = view ?: return null
        val raw = withTimeoutOrNull(2500) {
            suspendCancellableCoroutine<String?> { cont ->
                w.post { w.evaluateJavascript(ACTIVE_JS) { r -> if (cont.isActive) cont.resume(r) } }
            }
        } ?: return null
        return try {
            val str = JSONTokener(raw).nextValue() as? String ?: return null
            val o = JSONObject(str)
            if (!o.optBoolean("found")) null
            else Active(o.optString("src"), o.optString("poster"), o.optString("link"), o.optString("text"), o.optBoolean("playing"))
        } catch (_: Exception) { null }
    }

    private fun cleanText(t: String): String? =
        t.lines().firstOrNull { it.isNotBlank() }?.trim()?.removeSuffix("… See more")?.removeSuffix("See more")?.trim()
            ?.take(100)?.ifBlank { null }

    /** Works out which single video the user is watching right now. */
    suspend fun detect(): SheetRequest? {
        val page = url.value.ifBlank { return null }
        if (Downloads.isDrmSite(page)) return SheetRequest(page)
        val active = activeVideo()
        val all = hits.value
        val videos = all.filterNot { it.audioOnly }.sortedByDescending { it.time }
        val pageTitle = title.value.takeIf { it.isNotBlank() && !it.equals("Facebook", true) && !it.startsWith("http") }
        val titleHint = active?.text?.let { cleanText(it) } ?: pageTitle
        val thumb = active?.poster?.ifBlank { null }
        val alts = (listOfNotNull(active?.link?.ifBlank { null }, page) + videos.map { it.url }).distinct()

        fun req(u: String, ref: String?) = SheetRequest(
            u, referer = ref, titleHint = titleHint, thumbHint = thumb, alternatives = alts.filter { it != u }.take(6),
        )

        if (isFacebook(page)) {
            // Facebook: the video id hidden in the stream link -> official watch link (real title + sound)
            val fromActive = active?.src?.takeIf { it.startsWith("http") }?.let { facebookVideoId(it) }
            val id = fromActive ?: videos.firstNotNullOfOrNull { h ->
                if (h.key.startsWith("fb:")) h.key.removePrefix("fb:").substringBefore(':') else null
            }
            val link = active?.link?.takeIf { isVideoPage(it) }
            if (link != null) return req(link, null)
            if (id != null) return req("https://www.facebook.com/watch/?v=$id", null)
            if (isVideoPage(page)) return req(page, null)
        } else if (isVideoPage(page)) {
            // The page itself is one video (YouTube watch, a reel, a tweet…)
            return req(page, null)
        }
        // 3. The post/permalink that wraps the playing video
        active?.link?.takeIf { isVideoPage(it) || (Cookies.hostOf(it) == Cookies.hostOf(page) && active?.playing == true) }?.let {
            return req(it, null)
        }
        // 4. The <video> element's own file
        active?.src?.takeIf { it.startsWith("http") }?.let { return req(wholeFile(it), page) }
        // 5. The newest media the page loaded (what is playing now)
        videos.firstOrNull()?.let { return req(it.url, page) }
        all.maxByOrNull { it.time }?.let { return req(it.url, page) }
        // 6. Let yt-dlp try the page
        return req(page, null)
    }

    fun detach() {
        (view?.context as? MutableContextWrapper)?.let { it.setBaseContext(it.applicationContext) }
    }
}

/**
 * YouTube only serves video to clients that prove they are a real player ("PO token").
 * When a video plays in the built-in browser, its stream requests carry that token (pot=…),
 * bound to that one video. We keep it and give it to yt-dlp for the same video.
 */
object YtTokens {
    private val tokens = java.util.concurrent.ConcurrentHashMap<String, String>()

    fun videoId(u: String): String? =
        Regex("""(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})""").find(u)?.groupValues?.get(1)

    fun capture(streamUrl: String, pageUrl: String) {
        if (!streamUrl.contains("videoplayback")) return
        val pot = try { Uri.parse(streamUrl).getQueryParameter("pot") } catch (_: Exception) { null } ?: return
        val id = videoId(pageUrl) ?: return
        tokens[id] = pot
    }

    fun forUrl(u: String): String? = videoId(u)?.let { tokens[it] }
}
