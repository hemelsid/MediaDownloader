package com.mediadownloader.app

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
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
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView

@Composable
fun BrowserScreen() {
    val ctx = LocalContext.current
    val focus = LocalFocusManager.current
    val url by Browser.url.collectAsState()
    val progress by Browser.progress.collectAsState()
    val canBack by Browser.canGoBack.collectAsState()
    val canFwd by Browser.canGoForward.collectAsState()
    val hits by Browser.hits.collectAsState()
    val scope = rememberCoroutineScope()
    var editing by remember { mutableStateOf(false) }
    var field by remember { mutableStateOf("") }
    var menu by remember { mutableStateOf(false) }

    BackHandler {
        if (canBack) Browser.view?.goBack() else UiBus.tab.value = Tab.HOME
    }

    val videoPage = url.isNotBlank() && Browser.isVideoPage(url)
    val detected = videoPage || hits.isNotEmpty()

    Column(Modifier.fillMaxSize()) {
        // ---- address bar
        Row(Modifier.fillMaxWidth().background(Bg).padding(horizontal = 6.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { UiBus.tab.value = Tab.HOME }) { Icon(Icons.Default.Home, "Home", tint = Color.White) }
            Row(
                Modifier.weight(1f).height(44.dp).clip(RoundedCornerShape(14.dp)).background(Card2).padding(start = 14.dp, end = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.weight(1f)) {
                    val shown = if (editing) field else Cookies.hostOf(url) ?: url
                    if (shown.isEmpty()) Text("Search or type URL", color = Muted, fontSize = 15.sp)
                    BasicTextField(
                        value = shown,
                        onValueChange = { field = it },
                        singleLine = true,
                        textStyle = TextStyle(color = Color.White, fontSize = 15.sp),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go),
                        keyboardActions = KeyboardActions(onGo = {
                            val t = field.trim()
                            focus.clearFocus()
                            if (t.isNotEmpty()) {
                                if (Downloads.extractUrls(t).isNotEmpty() || Regex("""^[\w-]+(\.[\w-]+)+(/\S*)?$""").matches(t)) {
                                    Browser.load(if (t.startsWith("http")) t else "https://$t")
                                } else UiBus.go(t)
                            }
                        }),
                        modifier = Modifier.fillMaxWidth().onFocusChanged {
                            if (it.isFocused && !editing) field = url
                            editing = it.isFocused
                        },
                    )
                }
                if (editing) {
                    IconButton(onClick = { field = "" }) { Icon(Icons.Default.Close, "Clear", tint = Muted) }
                } else {
                    IconButton(onClick = { if (progress in 1..99) Browser.view?.stopLoading() else Browser.view?.reload() }) {
                        Icon(if (progress in 1..99) Icons.Default.Close else Icons.Default.Refresh, "Reload", tint = Muted)
                    }
                }
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, "Menu", tint = Color.White) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }, containerColor = Card1) {
                    DropdownMenuItem(
                        text = { Text("Back") }, enabled = canBack,
                        leadingIcon = { Icon(Icons.AutoMirrored.Filled.ArrowBack, null) },
                        onClick = { menu = false; Browser.view?.goBack() })
                    DropdownMenuItem(
                        text = { Text("Forward") }, enabled = canFwd,
                        leadingIcon = { Icon(Icons.AutoMirrored.Filled.ArrowForward, null) },
                        onClick = { menu = false; Browser.view?.goForward() })
                    DropdownMenuItem(text = { Text("Add to Home") }, onClick = {
                        menu = false
                        val name = Browser.title.value.ifBlank { Cookies.hostOf(url) ?: "Site" }.take(20)
                        Shortcuts.save(ctx, Shortcuts.custom(ctx) + Shortcut(name, url, true))
                        toast(ctx, "Added to Home")
                    })
                    DropdownMenuItem(text = { Text("Open in Chrome") }, onClick = {
                        menu = false
                        try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } catch (_: Exception) {}
                    })
                }
            }
        }
        if (progress in 1..99) {
            LinearProgressIndicator(progress = { progress / 100f }, color = Orange, trackColor = Card2, modifier = Modifier.fillMaxWidth().height(2.dp))
        }

        // ---- page + floating download button
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (url.isBlank()) {
                Column(Modifier.fillMaxSize().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Spacer(Modifier.height(60.dp))
                    Text("Type a link or search above, or open a site from Home.", color = Muted, fontSize = 15.sp)
                }
            } else {
                AndroidView(factory = { c -> Browser.obtain(c) }, modifier = Modifier.fillMaxSize())
            }
            DownloadFab(
                detected = detected,
                modifier = Modifier.align(Alignment.BottomEnd).padding(18.dp),
            ) {
                scope.launch {
                    val req = Browser.detect()
                    if (req == null) toast(ctx, "Open a site first") else UiBus.sheet.value = req
                }
            }
        }
    }
}

@Composable
private fun DownloadFab(detected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val pulse = rememberInfiniteTransition(label = "pulse")
    val scale by pulse.animateFloat(
        initialValue = 1f, targetValue = if (detected) 1.12f else 1f,
        animationSpec = infiniteRepeatable(tween(650), RepeatMode.Reverse), label = "scale",
    )
    Box(modifier) {
        Box(
            Modifier.scale(scale).size(62.dp)
                .shadow(14.dp, CircleShape, spotColor = Orange, ambientColor = Orange)
                .clip(CircleShape)
                .background(if (detected) Orange else Color(0xFF6A3A1E))
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center,
        ) { Icon(Icons.Default.Download, "Download", tint = Color.White, modifier = Modifier.size(30.dp)) }
    }
    Spacer(Modifier.width(0.dp))
}
