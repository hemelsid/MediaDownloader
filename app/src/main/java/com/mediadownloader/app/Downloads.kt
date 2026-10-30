package com.mediadownloader.app

import android.content.Context
import android.content.Intent
import android.widget.Toast
import androidx.core.content.ContextCompat
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import com.yausername.youtubedl_android.YoutubeDLResponse
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.runInterruptible
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

enum class AudioKind { MP3_320, MP3_128, M4A }

/** One row in the quality sheet. */
data class QualityOption(
    val label: String,
    val size: Long,
    val height: Int? = null,        // max video height; null = best available
    val audio: AudioKind? = null,   // non-null = audio only
) {
    val isAudio get() = audio != null

    fun apply(req: YoutubeDLRequest) {
        when (audio) {
            AudioKind.MP3_320, AudioKind.MP3_128 -> {
                req.addOption("-f", "ba/b")
                req.addOption("-x")
                req.addOption("--audio-format", "mp3")
                req.addOption("--audio-quality", if (audio == AudioKind.MP3_320) "320K" else "128K")
            }
            AudioKind.M4A -> {
                req.addOption("-f", "ba[ext=m4a]/ba/b")
                req.addOption("-x")
                req.addOption("--audio-format", "m4a")
            }
            null -> {
                req.addOption("-f", "bv*+ba/b")
                // Prefer H.264 + AAC so the file plays in every phone gallery
                req.addOption("-S", if (height != null) "res:$height,vcodec:h264,acodec:m4a" else "res,vcodec:h264,acodec:m4a")
                req.addOption("--merge-output-format", "mp4")
            }
        }
    }

    companion object {
        val BEST_VIDEO = QualityOption("Best quality", 0)
    }
}

data class MediaInfo(
    val url: String,
    val referer: String?,
    val title: String,
    val thumbnail: String?,
    val uploader: String?,
    val site: String?,
    val durationSec: Long,
    val views: Long,
    val isPlaylist: Boolean,
    val count: Int,
    val video: List<QualityOption>,
    val audio: List<QualityOption>,
)

class InfoException(val friendly: String, val detail: String, val site: Cookies.Site?, val drm: Boolean) : Exception(friendly)

enum class Status { QUEUED, STARTING, DOWNLOADING, PROCESSING, DONE, FAILED, CANCELLED }

data class DownloadItem(
    val id: String,
    val url: String,
    val option: QualityOption,
    val playlist: Boolean,
    val referer: String? = null,
    val customName: String? = null,
    val title: String = url,
    val thumbnail: String? = null,
    val durationSec: Long = 0,
    val status: Status = Status.QUEUED,
    val progress: Float = 0f,
    val etaSec: Long = -1,
    val speed: String = "",
    val total: String = "",
    val error: String? = null,
    val errorDetail: String? = null,
    val needsLogin: Cookies.Site? = null,
    val files: List<SavedFile> = emptyList(),
) {
    val isActive get() = status in setOf(Status.QUEUED, Status.STARTING, Status.DOWNLOADING, Status.PROCESSING)
}

object Downloads {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val ready = CompletableDeferred<Boolean>()
    private val semaphore = Semaphore(3)
    private val jobs = ConcurrentHashMap<String, Job>()
    private val counter = AtomicInteger()
    private lateinit var appCtx: Context

    private val _items = MutableStateFlow<List<DownloadItem>>(emptyList())
    val items: StateFlow<List<DownloadItem>> = _items

    private val _engine = MutableStateFlow("Preparing engine…")
    val engine: StateFlow<String> = _engine

    private val destRegex = Regex("""Destination:\s*(.+)$""")
    private val mergeRegex = Regex("""Merging formats into "(.+)"""")
    private val speedRegex = Regex("""at\s+(\S+/s)""")
    private val totalRegex = Regex("""of\s+~?\s*([\d.]+\s*[KMGT]i?B)""")

    /** Alternate YouTube clients tried automatically when the default ones are bot-blocked. */
    private val ALT_CLIENTS = listOf(
        "youtube:player_client=tv_simply,web_safari,mweb",
        "youtube:player_client=android_vr,web_embedded,tv",
    )

    /** Streaming services that lock video with DRM — no downloader can save these. */
    private val DRM_HOSTS = listOf(
        "netflix.com", "primevideo.com", "disneyplus.com", "hotstar.com", "hulu.com", "max.com", "hbomax.com",
        "tv.apple.com", "peacocktv.com", "paramountplus.com", "zee5.com", "sonyliv.com", "chorki.com",
        "hoichoi.tv", "bongobd.com", "binge.buzz", "spotify.com", "music.apple.com",
    )

    fun isDrmSite(url: String): Boolean {
        val h = Cookies.hostOf(url) ?: return false
        return DRM_HOSTS.any { h == it || h.endsWith(".$it") } || (h.contains("amazon.") && url.contains("/gp/video"))
    }

    fun init(ctx: Context) {
        appCtx = ctx.applicationContext
        scope.launch {
            try {
                YoutubeDL.getInstance().init(appCtx)
                FFmpeg.getInstance().init(appCtx)
                ready.complete(true)
                _engine.value = engineLabel()
                autoUpdate()
            } catch (e: Throwable) {
                _engine.value = "Engine failed to load: ${e.message}"
                ready.complete(false)
            }
        }
    }

    private fun engineLabel(): String {
        val v = (YoutubeDL.getInstance().versionName(appCtx) ?: "").removePrefix("yt-dlp").trim()
        return "yt-dlp $v"
    }

    private suspend fun autoUpdate() {
        val prefs = appCtx.getSharedPreferences("app", Context.MODE_PRIVATE)
        if (System.currentTimeMillis() - prefs.getLong("last_update", 0) < 24 * 3600 * 1000L) return
        runUpdate(silent = true)
        prefs.edit().putLong("last_update", System.currentTimeMillis()).apply()
    }

    fun updateEngine() {
        scope.launch { runUpdate(silent = false) }
    }

    private suspend fun runUpdate(silent: Boolean) {
        if (!ready.await()) return
        val before = _engine.value
        _engine.value = "Updating yt-dlp…"
        val msg = try {
            val st = YoutubeDL.getInstance().updateYoutubeDL(appCtx, YoutubeDL.UpdateChannel.STABLE)
            if (st == YoutubeDL.UpdateStatus.ALREADY_UP_TO_DATE) "yt-dlp already latest ✔" else "yt-dlp updated ✔"
        } catch (e: Throwable) {
            "Update failed: ${e.message?.take(80)}"
        }
        _engine.value = try { engineLabel() } catch (e: Throwable) { before }
        if (!silent) toast(msg)
    }

    private fun isYoutube(url: String) = Cookies.siteFor(url)?.key == "youtube"

    private fun addCommon(req: YoutubeDLRequest, runDir: File, url: String, referer: String?, extractorArgs: String?) {
        extractorArgs?.let { req.addOption("--extractor-args", it) }
        req.addOption("--cache-dir", File(appCtx.cacheDir, "ytdlp-cache").absolutePath)
        req.addOption("--no-warnings")
        req.addOption("--retries", 10)
        req.addOption("--socket-timeout", 20)
        if (referer != null && referer != url) {
            req.addOption("--referer", referer)
            Browser.userAgent?.let { req.addOption("--user-agent", it) }
        }
        Cookies.fileForRun(appCtx, runDir, listOfNotNull(url, referer))?.let { req.addOption("--cookies", it.absolutePath) }
    }

    /** Runs yt-dlp, retrying YouTube with other clients when it is bot-blocked. */
    private fun execWithFallback(
        url: String,
        build: (extractorArgs: String?) -> YoutubeDLRequest,
        pid: String,
        callback: ((Float, Long, String) -> Unit)?,
    ): YoutubeDLResponse {
        val yt = isYoutube(url)
        val attempts = buildList<String?> {
            // Token captured while the video played in the built-in browser (best chance)
            if (yt) YtTokens.forUrl(url)?.let { add("youtube:player_client=mweb;po_token=mweb.gvs+$it") }
            add(null)
            if (yt) addAll(ALT_CLIENTS)
        }
        var last: Throwable? = null
        for ((i, args) in attempts.withIndex()) {
            try {
                return YoutubeDL.getInstance().execute(build(args), pid, false, callback)
            } catch (e: YoutubeDL.CanceledException) {
                throw e
            } catch (e: InterruptedException) {
                throw e
            } catch (e: Throwable) {
                last = e
                val d = errorDetail(e)
                val worthRetry = isLoginError(d) || (yt && (d.contains("403") || d.contains("format is not available", true) ||
                    d.contains("PO Token", true) || d.contains("Only images", true)))
                if (i == attempts.lastIndex || !worthRetry) throw e
            }
        }
        throw last ?: IllegalStateException()
    }

    // ================================================================= info / quality list

    suspend fun loadInfo(url: String, referer: String?): MediaInfo {
        if (isDrmSite(url)) {
            throw InfoException(
                "This service locks its videos with DRM (like Netflix and Prime Video), so no downloader can save them. " +
                    "Use the download option in their own app instead.", "DRM protected service", null, true
            )
        }
        if (!ready.await()) throw InfoException(_engine.value, _engine.value, null, false)
        val pid = "info-${counter.incrementAndGet()}"
        val dir = File(appCtx.cacheDir, pid).apply { mkdirs() }
        try {
            val resp = withContext(Dispatchers.IO) {
                runInterruptible {
                    execWithFallback(url, { args ->
                        YoutubeDLRequest(url).apply {
                            addOption("-J")
                            addOption("--flat-playlist")
                            addOption("--no-playlist")
                            addCommon(this, dir, url, referer, args)
                        }
                    }, pid, null)
                }
            }
            val json = JSONObject(resp.out.lines().last { it.trimStart().startsWith("{") })
            return parseInfo(url, referer, json)
        } catch (e: Throwable) {
            if (e is InfoException || e is YoutubeDL.CanceledException || e is InterruptedException ||
                e is kotlinx.coroutines.CancellationException) throw e
            val detail = errorDetail(e)
            val site = if (isLoginError(detail)) Cookies.siteFor(url) ?: Cookies.siteFor(referer ?: "") else null
            throw InfoException(friendlyError(detail, site), detail, site, detail.contains("DRM", true))
        } finally {
            try { YoutubeDL.getInstance().destroyProcessById(pid) } catch (_: Throwable) {}
            dir.deleteRecursively()
        }
    }

    private fun parseInfo(url: String, referer: String?, j: JSONObject): MediaInfo {
        val isPlaylist = j.optString("_type") == "playlist"
        val entries = j.optJSONArray("entries")
        var thumb = j.optString("thumbnail").ifBlank { null }
        if (thumb == null) {
            val thumbs = j.optJSONArray("thumbnails") ?: entries?.optJSONObject(0)?.optJSONArray("thumbnails")
            if (thumbs != null && thumbs.length() > 0) thumb = thumbs.optJSONObject(thumbs.length() - 1)?.optString("url")
        }
        val duration = j.optDouble("duration", 0.0)
        val fs = formats(j)
        val audios = fs.filter { it.audio && !it.video && it.size > 0 }
        val bestAudio = audios.filter { it.m4a }.maxByOrNull { it.size } ?: audios.maxByOrNull { it.size }

        val video = mutableListOf<QualityOption>()
        if (!isPlaylist) {
            val vids = fs.filter { it.video }
            val heights = vids.map { it.height }.filter { it >= 100 }.distinct().sortedDescending().take(8)
            heights.forEach { h ->
                val atH = vids.filter { it.height == h && it.size > 0 }
                val v = atH.filter { it.h264 }.maxByOrNull { it.size } ?: atH.maxByOrNull { it.size }
                val size = if (v == null) 0 else v.size + (if (v.audio) 0 else bestAudio?.size ?: 0)
                video += QualityOption("${qualityName(h)} - ${h}p", size, height = h)
            }
            if (video.isEmpty() && (vids.isNotEmpty() || fs.isEmpty())) {
                val size = vids.maxOfOrNull { it.size } ?: j.optLong("filesize", j.optLong("filesize_approx", 0))
                video += QualityOption("Original quality", size)
            }
        } else {
            listOf(1080, 720, 480, 360).forEach { h -> video += QualityOption("${qualityName(h)} - ${h}p", 0, height = h) }
        }
        val audio = listOf(
            QualityOption("MP3 - 320 kbps", (duration * 40_000).toLong(), audio = AudioKind.MP3_320),
            QualityOption("MP3 - 128 kbps", (duration * 16_000).toLong(), audio = AudioKind.MP3_128),
            QualityOption("M4A - original", bestAudio?.size ?: 0, audio = AudioKind.M4A),
        )
        return MediaInfo(
            url = url,
            referer = referer,
            title = j.optString("title").ifBlank { j.optString("webpage_url", url) },
            thumbnail = thumb?.ifBlank { null },
            uploader = (j.optString("uploader").ifBlank { j.optString("channel") }).ifBlank { null },
            site = j.optString("extractor_key").ifBlank { null }?.takeIf { it != "Generic" },
            durationSec = duration.toLong(),
            views = j.optLong("view_count", 0),
            isPlaylist = isPlaylist,
            count = j.optInt("playlist_count", entries?.length() ?: 0),
            video = video,
            audio = audio,
        )
    }

    private fun qualityName(h: Int) = when {
        h >= 2160 -> "4K Ultra HD"; h >= 1440 -> "QHD Video"; h >= 1080 -> "FHD Video"
        h >= 720 -> "HD Video"; h >= 480 -> "SD Video"; else -> "Low"
    }

    private class F(val height: Int, val video: Boolean, val audio: Boolean, val size: Long, val h264: Boolean, val m4a: Boolean)

    private fun formats(j: JSONObject): List<F> {
        val arr = j.optJSONArray("formats") ?: return emptyList()
        val out = ArrayList<F>()
        for (i in 0 until arr.length()) {
            val f = arr.optJSONObject(i) ?: continue
            val vc = f.optString("vcodec", "")
            val ac = f.optString("acodec", "")
            val ext = f.optString("ext")
            val size = f.optLong("filesize", 0).takeIf { it > 0 } ?: f.optLong("filesize_approx", 0)
            val h = f.optInt("height", 0)
            // Some sites don't report codecs: guess from height / extension
            val isVideo = if (vc.isNotBlank()) vc != "none" else (h > 0 || ext in setOf("mp4", "webm", "mkv", "mov", "flv"))
            val isAudio = if (ac.isNotBlank()) ac != "none" else (vc.isBlank() || ext in setOf("m4a", "mp3", "opus", "ogg"))
            out += F(h, isVideo, isAudio, size, vc.startsWith("avc1") || vc.startsWith("h264"), ext == "m4a")
        }
        return out
    }

    // ================================================================= downloads

    fun enqueue(
        ctx: Context, url: String, option: QualityOption, playlist: Boolean = false, info: MediaInfo? = null,
        customName: String? = null, referer: String? = info?.referer,
    ) {
        val name = customName?.let { Storage.sanitize(it) }?.ifBlank { null }
        val item = DownloadItem(
            id = UUID.randomUUID().toString(), url = url, option = option, playlist = playlist,
            referer = referer, customName = name,
            title = name ?: info?.title ?: url,
            thumbnail = info?.thumbnail, durationSec = info?.durationSec ?: 0,
        )
        _items.update { it + item }
        start(item.id)
        ContextCompat.startForegroundService(ctx, Intent(ctx, DownloadService::class.java))
    }

    fun extractUrls(text: String): List<String> =
        Regex("""https?://\S+""").findAll(text).map { it.value.trimEnd('.', ',', ')', '"', '\'') }.distinct().toList()

    fun cancel(id: String) {
        update(id) { copy(status = Status.CANCELLED, speed = "", etaSec = -1) }
        try { YoutubeDL.getInstance().destroyProcessById(id) } catch (_: Throwable) {}
        jobs.remove(id)?.cancel()
    }

    fun retry(ctx: Context, id: String) {
        update(id) {
            copy(status = Status.QUEUED, progress = 0f, error = null, errorDetail = null, needsLogin = null, speed = "", etaSec = -1)
        }
        start(id)
        ContextCompat.startForegroundService(ctx, Intent(ctx, DownloadService::class.java))
    }

    fun retryLoginFailures(ctx: Context) {
        _items.value.filter { it.status == Status.FAILED && it.needsLogin != null }.forEach { retry(ctx, it.id) }
    }

    fun remove(id: String) {
        if (get(id)?.isActive == true) cancel(id)
        _items.update { list -> list.filterNot { it.id == id } }
    }

    fun clearFinished() {
        _items.update { list -> list.filter { it.isActive || it.status == Status.FAILED } }
    }

    private fun get(id: String) = _items.value.firstOrNull { it.id == id }

    private fun update(id: String, f: DownloadItem.() -> DownloadItem) {
        _items.update { list -> list.map { if (it.id == id) it.f() else it } }
    }

    private fun start(id: String) {
        jobs[id] = scope.launch {
            semaphore.withPermit { run(id) }
            jobs.remove(id)
        }
    }

    private suspend fun run(id: String) {
        val item = get(id) ?: return
        if (item.status == Status.CANCELLED) return
        update(id) { copy(status = Status.STARTING) }
        if (!ready.await()) {
            update(id) { copy(status = Status.FAILED, error = _engine.value) }
            return
        }
        val tmp = File(appCtx.cacheDir, "dl/$id").apply { deleteRecursively(); mkdirs() }
        val out = File(tmp, "out").apply { mkdirs() }
        try {
            val template = when {
                item.customName != null && !item.playlist -> "${item.customName}.%(ext)s"
                item.playlist -> "%(playlist_index)03d - %(title).140B.%(ext)s"
                else -> "%(title).150B.%(ext)s"
            }
            execWithFallback(item.url, { args ->
                out.listFiles()?.forEach { it.deleteRecursively() }
                YoutubeDLRequest(item.url).apply {
                    item.option.apply(this)
                    addOption("-o", out.absolutePath + "/" + template)
                    addOption(if (item.playlist) "--yes-playlist" else "--no-playlist")
                    addOption("--windows-filenames")
                    addOption("--no-mtime")
                    addOption("--concurrent-fragments", 8)
                    addOption("--http-chunk-size", "10M")
                    addOption("--fragment-retries", 10)
                    addCommon(this, tmp, item.url, item.referer, args)
                }
            }, id) { progress, eta, line -> onOutput(id, progress, eta, line) }

            if (get(id)?.status == Status.CANCELLED) return
            update(id) { copy(status = Status.PROCESSING, progress = 100f, speed = "", etaSec = -1) }
            val produced = out.walkTopDown()
                .filter { it.isFile && it.length() > 0 }
                .filterNot { f -> listOf(".part", ".ytdl", ".temp", ".tmp").any { f.name.endsWith(it) } }
                .filterNot { it.name.contains(".part-Frag") }
                .sortedBy { it.name }
                .toList()
            if (produced.isEmpty()) throw IllegalStateException("No file was produced")
            val saved = produced.mapNotNull { Storage.publish(appCtx, it) }
            if (saved.isEmpty()) throw IllegalStateException("Could not save to the phone (storage full?)")

            val cur = get(id) ?: item
            val single = saved.size == 1
            Library.add(saved.map { s ->
                LibItem(
                    id = UUID.randomUUID().toString(),
                    title = if (single && cur.customName == null && cur.title != cur.url) cur.title else s.name.substringBeforeLast('.'),
                    name = s.name, mime = s.mime, uri = s.uri, path = null,
                    thumb = if (single) cur.thumbnail else null, source = cur.url, size = s.size,
                    durationSec = if (single) cur.durationSec else 0, date = System.currentTimeMillis(),
                )
            })
            val title = if (single) cur.title.takeIf { it != cur.url } ?: saved[0].name else "${saved.size} files"
            update(id) { copy(status = Status.DONE, files = saved, title = title) }
            Notifications.done(appCtx, id, title, saved.first())
        } catch (e: YoutubeDL.CanceledException) {
            update(id) { copy(status = Status.CANCELLED) }
        } catch (e: Throwable) {
            if (get(id)?.status != Status.CANCELLED) {
                val detail = errorDetail(e)
                val site = if (isLoginError(detail)) Cookies.siteFor(item.url) ?: Cookies.siteFor(item.referer ?: "") else null
                update(id) {
                    copy(status = Status.FAILED, error = friendlyError(detail, site), errorDetail = detail,
                        needsLogin = site, speed = "", etaSec = -1)
                }
            }
        } finally {
            tmp.deleteRecursively()
        }
    }

    private fun onOutput(id: String, progress: Float, eta: Long, line: String) {
        if (get(id)?.status == Status.CANCELLED) return
        val dest = destRegex.find(line)?.groupValues?.get(1) ?: mergeRegex.find(line)?.groupValues?.get(1)
        val processing = line.startsWith("[Merger]") || line.startsWith("[ExtractAudio]") ||
            line.startsWith("[Fixup") || line.startsWith("[Metadata]") || line.startsWith("[VideoConvertor]")
        update(id) {
            var next = this
            if (dest != null && title == url) {
                next = next.copy(title = File(dest.trim()).nameWithoutExtension.replace(Regex("""\.f\d+$"""), ""))
            }
            next = when {
                processing -> next.copy(status = Status.PROCESSING, speed = "", etaSec = -1)
                progress >= 0f && line.startsWith("[download]") -> next.copy(
                    status = Status.DOWNLOADING,
                    progress = progress.coerceIn(0f, 100f),
                    etaSec = eta,
                    speed = speedRegex.find(line)?.groupValues?.get(1) ?: next.speed,
                    total = totalRegex.find(line)?.groupValues?.get(1) ?: next.total,
                )
                else -> next
            }
            next
        }
    }

    private fun errorDetail(e: Throwable): String {
        val text = e.message ?: e.toString()
        val errs = text.lines().filter { it.contains("ERROR:") }.map { it.substringAfter("ERROR:").trim() }
        return (errs.ifEmpty { text.lines().filter { it.isNotBlank() }.takeLast(3) }).joinToString("\n").take(600)
    }

    private fun isLoginError(d: String) = listOf(
        "Sign in to confirm", "LOGIN_REQUIRED", "login required", "--cookies", "log in", "logged-in",
        "rate-limit reached", "requested content is not available", "age-restricted", "confirm your age",
    ).any { d.contains(it, ignoreCase = true) }

    private fun friendlyError(d: String, site: Cookies.Site?): String = when {
        d.contains("DRM", true) -> "This video is DRM-protected and can't be downloaded."
        site?.key == "youtube" ->
            "YouTube blocked this request. Open the video in the Browser, let it play for a few seconds, then tap ⬇ again. " +
                "If it still fails, switch between Wi-Fi and mobile data" + if (Cookies.isLoggedIn(appCtx, site!!)) "." else ", or log in to YouTube in the Browser."
        site != null && Cookies.isLoggedIn(appCtx, site) ->
            "${site.name} is still blocking. Switch between Wi-Fi and mobile data, then try again."
        site != null -> "${site.name} is blocking this network. Switch between Wi-Fi and mobile data and retry, " +
            "or log in to ${site.name} once in the Browser."
        d.contains("Unsupported URL", true) ->
            "No downloadable video on this page. Open it in the Browser, play the video, then tap ⬇."
        d.contains("Private video", true) -> "This video is private and can't be downloaded"
        d.contains("Unable to resolve host", true) || d.contains("Network is unreachable", true) ||
            d.contains("timed out", true) -> "Internet connection problem"
        d.contains("Postprocessing", true) || d.contains("Invalid data found", true) ->
            "The downloaded data was incomplete. Play the video in the Browser, then tap ⬇ again."
        d.contains("HTTP Error 403", true) -> "The site refused access (403). Play the video in the Browser, then tap ⬇ again."
        else -> d.lines().first().take(200)
    }

    private suspend fun toast(msg: String) = withContext(Dispatchers.Main) {
        Toast.makeText(appCtx, msg, Toast.LENGTH_SHORT).show()
    }
}
