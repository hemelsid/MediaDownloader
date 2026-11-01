package com.mediadownloader.app

import android.app.PictureInPictureParams
import android.content.ComponentName
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Rational
import androidx.activity.ComponentActivity
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import androidx.media3.ui.PlayerView
import com.google.common.util.concurrent.ListenableFuture

/**
 * Built-in video/audio player (also plays private vault files).
 * Videos: picture-in-picture when you press Home while playing.
 * Audio: plays through PlaybackService, so it keeps going in the background (Settings).
 */
class PlayerActivity : ComponentActivity() {
    private var player: ExoPlayer? = null
    private var controllerFuture: ListenableFuture<MediaController>? = null
    private lateinit var view: PlayerView
    private var videoRatio: Rational? = null
    private var newFile = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val uri = intent.data ?: run { finish(); return }
        val title = intent.getStringExtra("title").orEmpty()

        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }

        view = PlayerView(this).apply {
            setBackgroundColor(Color.BLACK)
            keepScreenOn = true
        }
        setContentView(view)

        val item = MediaItem.Builder().setUri(uri)
            .setMediaMetadata(MediaMetadata.Builder().setTitle(title).build())
            .build()
        val pos = savedInstanceState?.getLong("pos") ?: 0L

        if (isAudio(uri) && Prefs.backgroundAudio.value) {
            val token = SessionToken(this, ComponentName(this, PlaybackService::class.java))
            val fut = MediaController.Builder(this, token).buildAsync()
            controllerFuture = fut
            fut.addListener({
                val c = try { fut.get() } catch (_: Exception) { return@addListener playLocally(item, pos) }
                view.player = c
                if (savedInstanceState == null || c.currentMediaItem?.localConfiguration?.uri != uri) {
                    c.setMediaItem(item)
                    if (pos > 0) c.seekTo(pos)
                    c.prepare()
                }
                c.playWhenReady = true
            }, ContextCompat.getMainExecutor(this))
        } else {
            playLocally(item, pos)
        }
    }

    private fun playLocally(item: MediaItem, pos: Long) {
        val p = ExoPlayer.Builder(this).build()
        player = p
        view.player = p
        p.setMediaItem(item)
        p.addListener(object : Player.Listener {
            override fun onVideoSizeChanged(videoSize: VideoSize) {
                if (videoSize.width > 0 && videoSize.height > 0) {
                    videoRatio = Rational(videoSize.width, videoSize.height)
                    if (!isInPictureInPictureMode) {
                        requestedOrientation = if (videoSize.width > videoSize.height)
                            ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                        else ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
                    }
                    updatePip()
                }
            }
            override fun onIsPlayingChanged(isPlaying: Boolean) = updatePip()
        })
        if (pos > 0) p.seekTo(pos)
        p.prepare()
        p.playWhenReady = true
    }

    private fun isAudio(uri: Uri): Boolean {
        val type = try { contentResolver.getType(uri) } catch (_: Exception) { null }
        if (type != null) return type.startsWith("audio/")
        val name = uri.lastPathSegment.orEmpty().lowercase()
        return listOf(".mp3", ".m4a", ".aac", ".opus", ".ogg", ".oga", ".wav", ".flac").any { name.endsWith(it) }
    }

    // ------------------------------------------------------------------ picture-in-picture (videos)

    private fun pipParams(): PictureInPictureParams {
        val b = PictureInPictureParams.Builder()
        videoRatio?.let { r ->
            // Android only accepts ratios between 1:2.39 and 2.39:1
            val v = r.toFloat().coerceIn(1 / 2.39f, 2.39f)
            b.setAspectRatio(if (v == r.toFloat()) r else Rational((v * 1000).toInt(), 1000))
        }
        if (Build.VERSION.SDK_INT >= 31) b.setAutoEnterEnabled(player?.isPlaying == true)
        return b.build()
    }

    private fun updatePip() {
        if (player == null) return
        try { setPictureInPictureParams(pipParams()) } catch (_: Exception) {}
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        val p = player ?: return
        if (Build.VERSION.SDK_INT < 31 && p.isPlaying && p.videoSize.width > 0) {
            try { enterPictureInPictureMode(pipParams()) } catch (_: Exception) {}
        }
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        view.useController = !isInPictureInPictureMode
    }

    // ------------------------------------------------------------------ lifecycle

    /** Another file was opened while the player (or its PiP window) is showing. */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        newFile = true
        recreate()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (!newFile) (player ?: view.player)?.let { outState.putLong("pos", it.currentPosition) }
    }

    override fun onStop() {
        super.onStop()
        player?.pause()          // videos stop when the window (or the PiP window) is closed; background audio keeps playing
    }

    override fun onDestroy() {
        player?.release()
        player = null
        controllerFuture?.let { MediaController.releaseFuture(it) }
        controllerFuture = null
        super.onDestroy()
    }
}
