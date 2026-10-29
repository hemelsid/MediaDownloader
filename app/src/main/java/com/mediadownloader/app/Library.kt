package com.mediadownloader.app

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/** Finished downloads + the private vault. Saved to disk so it survives restarts. */
data class LibItem(
    val id: String,
    val title: String,
    val name: String,
    val mime: String,
    val uri: String?,       // public file (MediaStore)
    val path: String?,      // private vault file
    val thumb: String?,
    val source: String?,
    val size: Long,
    val durationSec: Long,
    val date: Long,
) {
    val vault get() = path != null
    val isAudio get() = mime.startsWith("audio")
    fun playUri(): Uri = if (path != null) Uri.fromFile(File(path)) else Uri.parse(uri)
}

object Library {
    private lateinit var ctx: Context
    private val _items = MutableStateFlow<List<LibItem>>(emptyList())
    val items: StateFlow<List<LibItem>> = _items
    private val file get() = File(ctx.filesDir, "library.json")
    private val vaultDir get() = File(ctx.filesDir, "vault").apply { mkdirs() }

    fun init(c: Context) {
        ctx = c.applicationContext
        _items.value = try {
            val arr = JSONArray(file.readText())
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                LibItem(
                    o.getString("id"), o.optString("title"), o.optString("name"), o.optString("mime"),
                    o.optString("uri").ifBlank { null }, o.optString("path").ifBlank { null },
                    o.optString("thumb").ifBlank { null }, o.optString("source").ifBlank { null },
                    o.optLong("size"), o.optLong("duration"), o.optLong("date"),
                )
            }
        } catch (_: Exception) { emptyList() }
    }

    @Synchronized
    private fun persist() {
        val arr = JSONArray()
        _items.value.forEach { i ->
            arr.put(JSONObject().apply {
                put("id", i.id); put("title", i.title); put("name", i.name); put("mime", i.mime)
                put("uri", i.uri ?: ""); put("path", i.path ?: ""); put("thumb", i.thumb ?: "")
                put("source", i.source ?: ""); put("size", i.size); put("duration", i.durationSec); put("date", i.date)
            })
        }
        val tmp = File(file.path + ".tmp")
        tmp.writeText(arr.toString())
        tmp.renameTo(file)
    }

    fun add(items: List<LibItem>) {
        _items.update { items + it }
        persist()
    }

    fun delete(item: LibItem) {
        item.uri?.let { Storage.delete(ctx, it) }
        item.path?.let { File(it).delete() }
        _items.update { l -> l.filterNot { it.id == item.id } }
        persist()
    }

    /** Moves a public file into app-private storage. Returns a message for the user. */
    fun moveToVault(item: LibItem): String {
        val uri = item.uri ?: return "Already private"
        val dest = File(vaultDir, "${item.id}_${item.name}")
        return try {
            ctx.contentResolver.openInputStream(Uri.parse(uri))!!.use { inp -> dest.outputStream().use { inp.copyTo(it) } }
            val removed = Storage.delete(ctx, uri)
            _items.update { l -> l.map { if (it.id == item.id) it.copy(uri = null, path = dest.absolutePath) else it } }
            persist()
            if (removed) "Moved to Private 🔒" else "Copied to Private, but the original couldn't be removed — delete it from your file manager"
        } catch (e: Throwable) {
            dest.delete()
            "Couldn't move to Private: ${e.message?.take(60)}"
        }
    }

    fun unhide(item: LibItem): String {
        val path = item.path ?: return "Already public"
        val saved = Storage.publish(ctx, File(path), item.name) ?: return "Couldn't move the file out"
        File(path).delete()
        _items.update { l -> l.map { if (it.id == item.id) it.copy(uri = saved.uri, path = null) else it } }
        persist()
        return "Moved back to Download/$SAVE_FOLDER"
    }

    // ---- PIN for the vault
    private val prefs get() = ctx.getSharedPreferences("vault", Context.MODE_PRIVATE)
    private fun hash(pin: String) =
        MessageDigest.getInstance("SHA-256").digest(("md-salt:" + pin).toByteArray()).joinToString("") { "%02x".format(it) }

    fun hasPin() = prefs.contains("pin")
    fun setPin(pin: String) = prefs.edit().putString("pin", hash(pin)).apply()
    fun checkPin(pin: String) = prefs.getString("pin", null) == hash(pin)
}
