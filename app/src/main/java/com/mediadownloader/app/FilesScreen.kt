package com.mediadownloader.app

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Backspace
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
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
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Vault stays unlocked only while you stay on this screen. */
private object VaultSession { var unlocked = false }

@Composable
fun FilesScreen() {
    val all by Library.items.collectAsState()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var unlocked by remember { mutableStateOf(VaultSession.unlocked) }

    Column(Modifier.fillMaxSize()) {
        Text("Files", fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(start = 20.dp, top = 14.dp, bottom = 8.dp))
        TabRow(
            selectedTabIndex = tab, containerColor = Bg, contentColor = Orange,
            indicator = { pos -> TabRowDefaults.SecondaryIndicator(Modifier.tabIndicatorOffset(pos[tab]), color = Orange, height = 3.dp) },
            divider = { HorizontalDivider(color = Card2) },
        ) {
            listOf("Video", "Audio", "🔒 Private").forEachIndexed { i, t ->
                Tab(selected = tab == i, onClick = {
                    tab = i
                    if (i != 2) { VaultSession.unlocked = false; unlocked = false }
                }, text = { Text(t, color = if (tab == i) Orange else Muted, fontSize = 15.sp) })
            }
        }
        when (tab) {
            0 -> FileList(all.filter { !it.vault && !it.isAudio }, "No videos yet")
            1 -> FileList(all.filter { !it.vault && it.isAudio }, "No audio yet")
            else -> if (unlocked) FileList(all.filter { it.vault }, "Nothing here yet.\nIn the Video or Audio list, tap ⋮ ▸ \"Move to Private\".")
                    else PinPad(onUnlock = { VaultSession.unlocked = true; unlocked = true })
        }
    }
}

@Composable
private fun FileList(list: List<LibItem>, empty: String) {
    if (list.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(40.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.height(50.dp))
            Icon(Icons.Default.VideoLibrary, null, tint = Card2, modifier = Modifier.size(84.dp))
            Spacer(Modifier.height(12.dp))
            Text(empty, color = Muted, fontSize = 15.sp)
        }
        return
    }
    LazyColumn(contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)) {
        items(list, key = { it.id }) { FileRow(it) }
    }
}

private val dateFmt = SimpleDateFormat("d MMM, h:mm a", Locale.getDefault())

@Composable
private fun FileRow(item: LibItem) {
    val ctx = LocalContext.current
    var menu by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 5.dp).clip(RoundedCornerShape(14.dp)).background(Card1)
            .clickable { play(ctx, item.playUri(), item.title) }.padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val model: Any? = item.thumb ?: if (item.isAudio) null else item.path?.let { File(it) } ?: item.uri?.let { Uri.parse(it) }
        Thumb(model, item.isAudio, item.durationSec, Modifier.width(128.dp).height(72.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(item.title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            Text("${humanSize(item.size)} • ${dateFmt.format(Date(item.date))}", color = Muted, fontSize = 12.sp)
        }
        Box {
            IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, null, tint = Muted) }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }, containerColor = Card2) {
                DropdownMenuItem(text = { Text("Play") }, onClick = { menu = false; play(ctx, item.playUri(), item.title) })
                if (!item.vault) {
                    item.uri?.let { u ->
                        DropdownMenuItem(text = { Text("Share") }, onClick = { menu = false; shareFile(ctx, Uri.parse(u), item.mime, item.name) })
                        DropdownMenuItem(text = { Text("Open with…") }, onClick = { menu = false; openExternal(ctx, Uri.parse(u), item.mime) })
                    }
                    DropdownMenuItem(text = { Text("🔒 Move to Private") }, onClick = {
                        menu = false
                        if (!Library.hasPin()) toast(ctx, "Set a PIN in the Private tab first")
                        else toast(ctx, Library.moveToVault(item))
                    })
                } else {
                    DropdownMenuItem(text = { Text("Move out of Private") }, onClick = { menu = false; toast(ctx, Library.unhide(item)) })
                }
                item.source?.let { src ->
                    DropdownMenuItem(text = { Text("Open source page") }, onClick = { menu = false; UiBus.openBrowser(src) })
                }
                DropdownMenuItem(text = { Text("Delete", color = Color(0xFFFF8A80)) }, onClick = { menu = false; confirmDelete = true })
            }
        }
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            containerColor = Card1,
            title = { Text("Delete this file?") },
            text = { Text("\"${item.title}\" will be removed from your phone.") },
            confirmButton = { TextButton(onClick = { confirmDelete = false; Library.delete(item) }) { Text("Delete", color = Orange) } },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun PinPad(onUnlock: () -> Unit) {
    val ctx = LocalContext.current
    val creating = !Library.hasPin()
    var pin by remember { mutableStateOf("") }
    var first by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf(false) }

    fun submit(p: String) {
        when {
            !creating -> if (Library.checkPin(p)) onUnlock() else { error = true; pin = "" }
            first == null -> { first = p; pin = "" }
            first == p -> { Library.setPin(p); toast(ctx, "PIN set 🔒"); onUnlock() }
            else -> { error = true; first = null; pin = "" }
        }
    }

    Column(Modifier.fillMaxSize().padding(top = 28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(Icons.Default.Lock, null, tint = Gold, modifier = Modifier.size(40.dp))
        Spacer(Modifier.height(10.dp))
        Text(
            when {
                creating && first == null -> "Create a 4-digit PIN"
                creating -> "Confirm your PIN"
                else -> "Enter your PIN"
            },
            fontSize = 18.sp, fontWeight = FontWeight.SemiBold,
        )
        if (error) Text(if (creating) "PINs didn't match, try again" else "Wrong PIN", color = Color(0xFFFF8A80), fontSize = 13.sp)
        Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
            repeat(4) { i ->
                Box(Modifier.size(14.dp).clip(CircleShape).background(if (i < pin.length) Orange else Color(0xFF3A3A40)))
            }
        }
        Spacer(Modifier.height(26.dp))
        val keys = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫")
        keys.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                row.forEach { k ->
                    Box(
                        Modifier.size(76.dp).clip(RoundedCornerShape(20.dp))
                            .background(if (k.isEmpty()) Color.Transparent else Card1)
                            .clickable(enabled = k.isNotEmpty()) {
                                error = false
                                if (k == "⌫") pin = pin.dropLast(1)
                                else if (pin.length < 4) {
                                    pin += k
                                    if (pin.length == 4) submit(pin)
                                }
                            },
                        contentAlignment = Alignment.Center,
                    ) {
                        if (k == "⌫") Icon(Icons.AutoMirrored.Filled.Backspace, "Delete", tint = Color.White)
                        else Text(k, fontSize = 28.sp, fontWeight = FontWeight.Medium)
                    }
                }
            }
        }
    }
}
