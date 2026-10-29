package com.mediadownloader.app

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun DownloadsScreen() {
    val items by Downloads.items.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 14.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Download", fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
            if (items.any { !it.isActive }) {
                IconButton(onClick = { Downloads.clearFinished() }) { Icon(Icons.Default.DeleteSweep, "Clear finished", tint = Muted) }
            }
        }
        if (items.isEmpty()) {
            Column(Modifier.fillMaxSize().padding(40.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Spacer(Modifier.height(60.dp))
                Icon(Icons.Default.Download, null, tint = Card2, modifier = Modifier.size(90.dp))
                Spacer(Modifier.height(12.dp))
                Text("No downloads yet", color = Muted, fontSize = 16.sp)
                Text("Finished files appear in the Files tab", color = Muted, fontSize = 13.sp)
            }
        } else {
            LazyColumn(contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                items(items.asReversed(), key = { it.id }) { DownloadRow(it) }
            }
        }
    }
}

@Composable
private fun DownloadRow(item: DownloadItem) {
    val ctx = LocalContext.current
    var menu by remember { mutableStateOf(false) }
    var showDetail by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().padding(vertical = 5.dp).clip(RoundedCornerShape(14.dp)).background(Card1)
            .clickable {
                when (item.status) {
                    Status.DONE -> item.files.firstOrNull()?.let { play(ctx, Uri.parse(it.uri), item.title) }
                    Status.FAILED -> showDetail = !showDetail
                    else -> {}
                }
            }
            .padding(10.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Thumb(item.thumbnail, item.option.isAudio, item.durationSec, Modifier.width(128.dp).height(72.dp))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(item.title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(6.dp))
                Row {
                    Text(leftText(item), color = statusColor(item), fontSize = 13.sp, maxLines = 1)
                    Spacer(Modifier.weight(1f))
                    Text(rightText(item), color = Muted, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(start = 8.dp).widthIn(max = 130.dp))
                }
                Spacer(Modifier.height(6.dp))
                when {
                    item.status == Status.DOWNLOADING && item.progress > 0f ->
                        LinearProgressIndicator(progress = { item.progress / 100f }, color = Orange, trackColor = Card2,
                            modifier = Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)))
                    item.isActive ->
                        LinearProgressIndicator(color = Orange, trackColor = Card2,
                            modifier = Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)))
                }
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, null, tint = Muted) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }, containerColor = Card2) {
                    if (item.isActive) DropdownMenuItem(text = { Text("Cancel") }, onClick = { menu = false; Downloads.cancel(item.id) })
                    if (item.status == Status.FAILED || item.status == Status.CANCELLED) {
                        DropdownMenuItem(text = { Text("Retry") }, onClick = { menu = false; Downloads.retry(ctx, item.id) })
                    }
                    item.needsLogin?.let { site ->
                        DropdownMenuItem(text = { Text("Log in to ${site.name}") }, onClick = { menu = false; UiBus.openBrowser(site.loginUrl) })
                    }
                    if (item.status == Status.DONE) item.files.firstOrNull()?.let { f ->
                        DropdownMenuItem(text = { Text("Play") }, onClick = { menu = false; play(ctx, Uri.parse(f.uri), item.title) })
                        DropdownMenuItem(text = { Text("Share") }, onClick = { menu = false; shareFile(ctx, Uri.parse(f.uri), f.mime, f.name) })
                    }
                    DropdownMenuItem(text = { Text("Remove from list") }, onClick = { menu = false; Downloads.remove(item.id) })
                }
            }
        }
        if (item.status == Status.FAILED) {
            Spacer(Modifier.height(8.dp))
            Text(item.error ?: "Failed", color = Color(0xFFFF8A80), fontSize = 13.sp)
            if (showDetail && item.errorDetail != null) {
                Text(item.errorDetail, color = Muted, fontSize = 11.sp,
                    modifier = Modifier.padding(top = 6.dp).fillMaxWidth().background(Card2, RoundedCornerShape(8.dp)).padding(8.dp))
            } else if (item.errorDetail != null) {
                Text("Tap to see details", color = Orange, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
            }
        }
    }
}

private fun leftText(i: DownloadItem) = when (i.status) {
    Status.QUEUED -> "Queued"
    Status.STARTING -> "Starting…"
    Status.DOWNLOADING -> "%.0f%%".format(i.progress) + if (i.total.isNotBlank()) "  of ${i.total}" else ""
    Status.PROCESSING -> "Converting…"
    Status.DONE -> "Complete ✔"
    Status.FAILED -> "Failed"
    Status.CANCELLED -> "Cancelled"
}

private fun rightText(i: DownloadItem) = when (i.status) {
    Status.DOWNLOADING -> listOfNotNull(i.speed.ifBlank { null }, i.etaSec.takeIf { it > 0 }?.let { formatDuration(it) }).joinToString(" • ")
    Status.DONE -> i.files.sumOf { it.size }.let { humanSize(it) }
    Status.FAILED, Status.CANCELLED -> ""
    else -> i.option.label.substringBefore(" - ").let { if (i.option.isAudio) i.option.label else it }
}

private fun statusColor(i: DownloadItem) = when (i.status) {
    Status.DONE -> Good
    Status.FAILED -> Color(0xFFFF8A80)
    Status.DOWNLOADING -> Color.White
    else -> Muted
}
