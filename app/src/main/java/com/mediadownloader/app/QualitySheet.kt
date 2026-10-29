package com.mediadownloader.app

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Public
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
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

private sealed interface LoadState {
    data object Loading : LoadState
    data class Ready(val info: MediaInfo) : LoadState
    data class Failed(val e: InfoException) : LoadState
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QualitySheet(req: SheetRequest, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    // Which url we are looking at (the user can switch between media found on the page)
    var target by remember(req.nonce) { mutableStateOf(req.url to req.referer) }
    var state by remember(req.nonce) { mutableStateOf<LoadState>(LoadState.Loading) }
    var attempt by remember(req.nonce) { mutableIntStateOf(0) }

    val page = remember(req.nonce) { req.referer ?: Browser.url.value.ifBlank { null } }
    val pick: (String) -> Unit = { u -> target = u to (if (u == page) null else page) }

    LaunchedEffect(target, attempt) {
        state = LoadState.Loading
        state = try {
            var info = Downloads.loadInfo(target.first, target.second)
            // Direct files have no real title — use what the page showed instead of a random file name
            val hint = req.titleHint?.takeIf { it.isNotBlank() }
            if (hint != null && (info.site == null || looksLikeFileName(info.title, target.first))) info = info.copy(title = hint)
            if (info.thumbnail == null && req.thumbHint != null) info = info.copy(thumbnail = req.thumbHint)
            LoadState.Ready(info)
        } catch (e: InfoException) {
            LoadState.Failed(e)
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = Card1,
        dragHandle = null,
    ) {
        Column(Modifier.navigationBarsPadding().padding(bottom = 12.dp)) {
            Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Select Download Quality", fontSize = 19.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                IconButton(onClick = onDismiss) { Icon(Icons.Default.Close, "Close", tint = Color.White) }
            }
            when (val s = state) {
                LoadState.Loading -> Column(
                    Modifier.fillMaxWidth().padding(vertical = 48.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    CircularProgressIndicator(color = Orange)
                    Spacer(Modifier.height(14.dp))
                    Text("Finding video…", color = Muted)
                    Text(Cookies.hostOf(target.first) ?: "", color = Muted, fontSize = 12.sp)
                }
                is LoadState.Failed -> FailedView(
                    s.e, req, target.first,
                    onPick = pick,
                    onRetry = { attempt++ },
                    onDismiss = onDismiss,
                )
                is LoadState.Ready -> ReadyView(s.info, req, target.first, onPick = pick) { opt, name, playlist ->
                    Downloads.enqueue(ctx, s.info.url, opt, playlist = playlist, info = s.info, customName = name)
                    toast(ctx, "Download started ⬇")
                    onDismiss()
                }
            }
        }
    }
}

@Composable
private fun Header(info: MediaInfo) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Thumb(info.thumbnail, audio = false, durationSec = info.durationSec, modifier = Modifier.width(132.dp).height(76.dp))
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(info.title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
            val meta = listOfNotNull(
                info.uploader, info.site,
                info.views.takeIf { it > 0 }?.let { "${compactNumber(it)} views" },
                if (info.isPlaylist) "${info.count} videos" else null,
            ).joinToString(" • ")
            if (meta.isNotEmpty()) Text(meta, color = Muted, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun ReadyView(
    info: MediaInfo, req: SheetRequest, current: String,
    onPick: (String) -> Unit,
    onDownload: (QualityOption, String?, Boolean) -> Unit,
) {
    var tab by remember(info) { mutableIntStateOf(if (info.video.isEmpty()) 1 else 0) }
    var selected by remember(info) { mutableStateOf(info.video.firstOrNull { (it.height ?: 0) <= 1080 } ?: info.video.firstOrNull() ?: info.audio.first()) }
    var name by remember(info) { mutableStateOf<String?>(null) }
    var renaming by remember { mutableStateOf(false) }
    val listUrl = Regex("""[?&]list=""").containsMatchIn(info.url) && !info.isPlaylist
    var wholePlaylist by remember(info) { mutableStateOf(info.isPlaylist) }

    Header(info)
    if (req.alternatives.isNotEmpty()) CandidateRow(req, current, onPick)
    HorizontalDivider(color = Card2)
    TabRow(
        selectedTabIndex = tab, containerColor = Card1, contentColor = Orange,
        indicator = { pos -> TabRowDefaults.SecondaryIndicator(Modifier.tabIndicatorOffset(pos[tab]), color = Orange, height = 3.dp) },
        divider = { HorizontalDivider(color = Card2) },
    ) {
        Tab(selected = tab == 0, onClick = { tab = 0; info.video.firstOrNull()?.let { selected = it } },
            text = { Text("Video", fontSize = 16.sp, color = if (tab == 0) Orange else Muted) })
        Tab(selected = tab == 1, onClick = { tab = 1; selected = info.audio.first() },
            text = { Text("Audio", fontSize = 16.sp, color = if (tab == 1) Orange else Muted) })
    }
    val options = if (tab == 0) info.video else info.audio
    LazyColumn(Modifier.heightIn(max = 330.dp)) {
        if (options.isEmpty()) item {
            Text("No video in this link — check the Audio tab.", color = Muted, modifier = Modifier.padding(20.dp))
        }
        items(options) { opt ->
            Row(
                Modifier.fillMaxWidth().clickable { selected = opt }.padding(horizontal = 20.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(38.dp).clip(RoundedCornerShape(8.dp)).background(Card2), contentAlignment = Alignment.Center) {
                    Icon(if (opt.isAudio) Icons.Default.MusicNote else Icons.Default.PlayCircle, null, tint = Color(0xFFBDBDC2))
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(opt.label, fontSize = 16.sp, fontWeight = FontWeight.Medium)
                    if (!info.isPlaylist) Text(if (opt.size > 0) "~ " + humanSize(opt.size) else "Size unknown", color = Muted, fontSize = 13.sp)
                }
                RadioButton(selected = selected == opt, onClick = { selected = opt },
                    colors = RadioButtonDefaults.colors(selectedColor = Orange, unselectedColor = Muted))
            }
            HorizontalDivider(color = Card2, modifier = Modifier.padding(horizontal = 20.dp))
        }
    }
    if (listUrl || info.isPlaylist) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (info.isPlaylist) "Whole playlist (${info.count})" else "Download the whole playlist", modifier = Modifier.weight(1f))
            Switch(checked = wholePlaylist, onCheckedChange = { wholePlaylist = it },
                colors = SwitchDefaults.colors(checkedTrackColor = Orange))
        }
    }
    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedButton(
            onClick = { renaming = true },
            enabled = !wholePlaylist,
            modifier = Modifier.weight(1f).height(54.dp),
            shape = RoundedCornerShape(28.dp),
            colors = ButtonDefaults.outlinedButtonColors(containerColor = Card2, contentColor = Color.White),
        ) { Text("Rename", fontSize = 16.sp) }
        Button(
            onClick = { onDownload(selected, name, wholePlaylist) },
            modifier = Modifier.weight(2f).height(54.dp),
            shape = RoundedCornerShape(28.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Orange),
        ) { Text("Download", fontSize = 17.sp, fontWeight = FontWeight.SemiBold) }
    }
    name?.let { Text("Name: $it", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 24.dp)) }

    if (renaming) {
        var text by remember { mutableStateOf(name ?: info.title) }
        AlertDialog(
            onDismissRequest = { renaming = false },
            containerColor = Card1,
            title = { Text("File name") },
            text = { OutlinedTextField(text, { text = it }, singleLine = false, maxLines = 3) },
            confirmButton = { TextButton(onClick = { name = text.trim().ifBlank { null }; renaming = false }) { Text("OK", color = Orange) } },
            dismissButton = { TextButton(onClick = { renaming = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun CandidateRow(req: SheetRequest, current: String, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    val list = (listOf(req.url) + req.alternatives).distinct()
    Column(Modifier.padding(horizontal = 20.dp, vertical = 2.dp)) {
        Text(
            if (open) "Hide other videos ▴" else "Not this video? ▾",
            color = Orange, fontSize = 13.sp,
            modifier = Modifier.clickable { open = !open }.padding(vertical = 4.dp),
        )
        AnimatedVisibility(open) {
            Column {
                list.forEachIndexed { i, u ->
                    val label = if (i == 0) "Detected video (recommended)" else "Other video $i — ${Cookies.hostOf(u) ?: ""}"
                    Text(
                        (if (u == current) "● " else "○ ") + label,
                        color = if (u == current) Orange else Color(0xFFD0D0D5), fontSize = 13.sp,
                        modifier = Modifier.fillMaxWidth().clickable { onPick(u) }.padding(vertical = 6.dp),
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

private fun looksLikeFileName(title: String, url: String): Boolean {
    val base = url.substringBefore('?').substringAfterLast('/').substringBeforeLast('.')
    return title == base || title.startsWith(base.take(12)) || (!title.contains(' ') && title.length > 14)
}

@Composable
private fun FailedView(
    e: InfoException, req: SheetRequest, current: String,
    onPick: (String) -> Unit, onRetry: () -> Unit, onDismiss: () -> Unit,
) {
    var details by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp)) {
        Row(verticalAlignment = Alignment.Top) {
            Icon(if (e.drm) Icons.Default.Lock else Icons.Default.ErrorOutline, null,
                tint = if (e.drm) Gold else MaterialErrorRed, modifier = Modifier.size(26.dp))
            Spacer(Modifier.width(10.dp))
            Text(e.friendly, fontSize = 15.sp)
        }
        if (!e.drm) {
            Text(
                if (details) "Hide details ▴" else "Details ▾", color = Orange, fontSize = 13.sp,
                modifier = Modifier.padding(top = 8.dp).clickable { details = !details },
            )
            AnimatedVisibility(details) {
                Text(
                    e.detail, color = Muted, fontSize = 12.sp,
                    modifier = Modifier.padding(top = 6.dp).fillMaxWidth().background(Card2, RoundedCornerShape(8.dp)).padding(10.dp),
                )
            }
        }
        if (req.alternatives.isNotEmpty()) CandidateRow(req, current, onPick)
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            e.site?.let { site ->
                OutlinedButton(onClick = { onDismiss(); UiBus.openBrowser(site.loginUrl) }, shape = RoundedCornerShape(24.dp)) {
                    Text("Log in to ${site.name}")
                }
            }
            if (!e.drm && !current.startsWith(Browser.url.value.ifBlank { "∅" }) && !Browser.isMediaFile(current)) {
                OutlinedButton(onClick = { onDismiss(); UiBus.openBrowser(current) }, shape = RoundedCornerShape(24.dp)) {
                    Icon(Icons.Default.Public, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Open in Browser")
                }
            }
            if (!e.drm) {
                Button(onClick = onRetry, shape = RoundedCornerShape(24.dp), colors = ButtonDefaults.buttonColors(containerColor = Orange)) {
                    Text("Retry")
                }
            }
        }
    }
}

private val MaterialErrorRed = Color(0xFFFF6B6B)
