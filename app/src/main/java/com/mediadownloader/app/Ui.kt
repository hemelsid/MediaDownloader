package com.mediadownloader.app

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage

val Orange = Color(0xFFFF6A13)
val OrangeSoft = Color(0xFFFF8A3D)
val Gold = Color(0xFFFFB627)
val Bg = Color(0xFF111111)
val Card1 = Color(0xFF1C1C1E)
val Card2 = Color(0xFF26262A)
val Muted = Color(0xFFA0A0A8)
val Good = Color(0xFF3DDC84)

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Orange, onPrimary = Color.White,
            primaryContainer = Color(0xFF3A1E0C), onPrimaryContainer = OrangeSoft,
            secondary = Gold, onSecondary = Color.Black,
            secondaryContainer = Color(0xFF3A1E0C), onSecondaryContainer = OrangeSoft,
            background = Bg, onBackground = Color(0xFFF2F2F2),
            surface = Bg, onSurface = Color(0xFFF2F2F2),
            surfaceVariant = Card2, onSurfaceVariant = Muted,
            surfaceContainer = Card1, surfaceContainerHigh = Card2, surfaceContainerHighest = Color(0xFF303035),
            surfaceContainerLow = Card1, surfaceContainerLowest = Bg,
            outline = Color(0xFF4A4A50), outlineVariant = Color(0xFF2E2E33),
            error = Color(0xFFFF6B6B),
        ),
    ) {
        // Default text/icon colour for every screen, including ones not inside a Scaffold/Surface
        CompositionLocalProvider(LocalContentColor provides Color(0xFFF2F2F2), content = content)
    }
}

/** Thumbnail with play/duration overlay — remote image, local video frame, or a music icon. */
@Composable
fun Thumb(model: Any?, audio: Boolean, durationSec: Long, modifier: Modifier) {
    Box(modifier.clip(RoundedCornerShape(10.dp)).background(Card2)) {
        if (model != null) {
            AsyncImage(model = model, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        }
        if (model == null && audio) {
            Icon(Icons.Default.MusicNote, null, tint = Orange, modifier = Modifier.align(Alignment.Center).size(28.dp))
        }
        if (durationSec > 0 || !audio) {
            Box(
                Modifier.align(Alignment.BottomStart).padding(5.dp)
                    .background(Color.Black.copy(alpha = 0.7f), RoundedCornerShape(5.dp))
                    .padding(horizontal = 4.dp, vertical = 1.dp)
            ) {
                androidx.compose.foundation.layout.Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.PlayArrow, null, tint = Color.White, modifier = Modifier.size(11.dp))
                    if (durationSec > 0) Text(formatDuration(durationSec), color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

fun formatDuration(s: Long): String {
    val h = s / 3600; val m = (s % 3600) / 60; val sec = s % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%d:%02d".format(m, sec)
}

fun humanSize(b: Long): String = when {
    b <= 0 -> "—"
    b >= 1L shl 30 -> "%.2f GB".format(b / (1L shl 30).toDouble())
    b >= 1L shl 20 -> "%.2f MB".format(b / (1L shl 20).toDouble())
    else -> "%.0f KB".format(b / 1024.0)
}

fun compactNumber(n: Long): String = when {
    n >= 1_000_000_000 -> "%.1fB".format(n / 1e9)
    n >= 1_000_000 -> "%.1fM".format(n / 1e6)
    n >= 1_000 -> "%.1fK".format(n / 1e3)
    else -> n.toString()
}

fun toast(ctx: Context, msg: String) = Toast.makeText(ctx, msg, Toast.LENGTH_LONG).show()

/** Play inside the app's own player. */
fun play(ctx: Context, uri: Uri, title: String) {
    ctx.startActivity(Intent(ctx, PlayerActivity::class.java).setData(uri).putExtra("title", title))
}

fun openExternal(ctx: Context, uri: Uri, mime: String) {
    val i = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    try { ctx.startActivity(i) } catch (e: ActivityNotFoundException) { toast(ctx, "No app found to open this") }
}

fun shareFile(ctx: Context, uri: Uri, mime: String, name: String) {
    val i = Intent(Intent.ACTION_SEND).setType(mime)
        .putExtra(Intent.EXTRA_STREAM, uri)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(i, name))
}
