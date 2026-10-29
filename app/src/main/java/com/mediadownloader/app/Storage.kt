package com.mediadownloader.app

import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

const val SAVE_FOLDER = "MediaDownloader"

data class SavedFile(val uri: String, val mime: String, val name: String, val size: Long)

object Storage {
    fun mimeOf(name: String): String =
        MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substringAfterLast('.', "").lowercase())
            ?: when (name.substringAfterLast('.', "").lowercase()) {
                "mkv" -> "video/x-matroska"; "opus" -> "audio/ogg"; "m4a" -> "audio/mp4"
                else -> "application/octet-stream"
            }

    /** Copies a file into the public Download/MediaDownloader folder (shows up in Gallery / Music). */
    fun publish(ctx: Context, file: File, displayName: String = file.name): SavedFile? = try {
        val mime = mimeOf(displayName)
        val uri: Uri? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = ctx.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, displayName)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + SAVE_FOLDER)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)?.also { uri ->
                resolver.openOutputStream(uri)!!.use { out -> file.inputStream().use { it.copyTo(out) } }
                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
            }
        } else {
            @Suppress("DEPRECATION")
            val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), SAVE_FOLDER)
            dir.mkdirs()
            val base = displayName.substringBeforeLast('.')
            val ext = displayName.substringAfterLast('.', "")
            var dest = File(dir, displayName)
            var n = 1
            while (dest.exists()) dest = File(dir, "$base (${n++}).$ext")
            file.copyTo(dest)
            var scanned: Uri? = null
            val latch = CountDownLatch(1)
            MediaScannerConnection.scanFile(ctx, arrayOf(dest.absolutePath), arrayOf(mime)) { _, u ->
                scanned = u; latch.countDown()
            }
            latch.await(5, TimeUnit.SECONDS)
            scanned ?: Uri.fromFile(dest)
        }
        uri?.let { SavedFile(it.toString(), mime, displayName, file.length()) }
    } catch (e: Throwable) {
        null
    }

    fun delete(ctx: Context, uri: String): Boolean = try {
        val u = Uri.parse(uri)
        if (u.scheme == "file") File(u.path!!).delete() else ctx.contentResolver.delete(u, null, null) > 0
    } catch (e: Throwable) {
        false
    }

    fun sanitize(name: String): String =
        name.replace(Regex("""[\\/:*?"<>|\n\r\t]"""), " ").replace(Regex("""\s+"""), " ").trim().take(150)
}
