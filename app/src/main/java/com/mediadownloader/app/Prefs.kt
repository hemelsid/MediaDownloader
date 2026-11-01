package com.mediadownloader.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import kotlinx.coroutines.flow.MutableStateFlow

/** User choices from Settings (stored on the phone). */
object Prefs {
    private lateinit var appCtx: Context
    private val sp get() = appCtx.getSharedPreferences("app", Context.MODE_PRIVATE)

    /** Download only on Wi-Fi (or another unmetered network); otherwise wait. */
    val wifiOnly = MutableStateFlow(false)
    /** How many downloads run at the same time. */
    val parallel = MutableStateFlow(3)
    /** Save subtitles (or auto-captions) inside the video when the site has them. */
    val subtitles = MutableStateFlow(false)
    /** Keep audio files playing when you leave the player. */
    val backgroundAudio = MutableStateFlow(true)

    fun init(ctx: Context) {
        appCtx = ctx.applicationContext
        wifiOnly.value = sp.getBoolean("wifi_only", false)
        parallel.value = sp.getInt("parallel", 3).coerceIn(1, 5)
        subtitles.value = sp.getBoolean("subtitles", false)
        backgroundAudio.value = sp.getBoolean("bg_audio", true)
    }

    fun setWifiOnly(v: Boolean) { wifiOnly.value = v; sp.edit().putBoolean("wifi_only", v).apply() }
    fun setParallel(v: Int) { parallel.value = v.coerceIn(1, 5); sp.edit().putInt("parallel", parallel.value).apply() }
    fun setSubtitles(v: Boolean) { subtitles.value = v; sp.edit().putBoolean("subtitles", v).apply() }
    fun setBackgroundAudio(v: Boolean) { backgroundAudio.value = v; sp.edit().putBoolean("bg_audio", v).apply() }

    /** True when the phone is on Wi-Fi / Ethernet / any network that isn't charged per MB. */
    fun onUnmeteredNetwork(): Boolean {
        val cm = appCtx.getSystemService(ConnectivityManager::class.java) ?: return true
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }
}
