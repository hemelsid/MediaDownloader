package com.mediadownloader.app

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun SettingsScreen(onBack: () -> Unit) {
    val ctx = LocalContext.current
    val engine by Downloads.engine.collectAsState()
    var refresh by remember { mutableIntStateOf(0) }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val text = try {
            ctx.contentResolver.openInputStream(uri)?.use { it.readBytes().decodeToString() }.orEmpty()
        } catch (e: Exception) { "" }
        val sites = Cookies.importNetscape(ctx, text)
        if (sites.isEmpty()) toast(ctx, "No usable cookies found (needs a Netscape cookies.txt)")
        else { toast(ctx, "Imported: ${sites.joinToString()} ✔"); Downloads.retryLoginFailures(ctx) }
        refresh++
    }

    Column(Modifier.fillMaxSize().background(Bg).statusBarsPadding().navigationBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
            Text("Settings", fontSize = 22.sp, fontWeight = FontWeight.Bold)
        }
        LazyColumn(contentPadding = PaddingValues(16.dp)) {
            item {
                val wifi by Prefs.wifiOnly.collectAsState()
                val par by Prefs.parallel.collectAsState()
                val subs by Prefs.subtitles.collectAsState()
                val bg by Prefs.backgroundAudio.collectAsState()
                Section("Downloads") {
                    Toggle("Wi-Fi only", "Wait for Wi-Fi instead of using mobile data", wifi) { Prefs.setWifiOnly(it) }
                    Toggle("Save subtitles", "Put subtitles (English, Bangla) inside videos when the site has them", subs) { Prefs.setSubtitles(it) }
                    Text("Downloads at the same time", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
                    Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(1, 2, 3, 5).forEach { n ->
                            FilterChip(
                                selected = par == n, onClick = { Prefs.setParallel(n) }, label = { Text("$n") },
                                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Orange, selectedLabelColor = androidx.compose.ui.graphics.Color.White),
                            )
                        }
                    }
                }
                Spacer(Modifier.height(16.dp))
                Section("Player") {
                    Toggle("Keep music playing in the background", "Audio files keep playing when you leave the player or lock the screen", bg) {
                        Prefs.setBackgroundAudio(it)
                    }
                    Text("Videos go into a small floating window (picture-in-picture) when you press Home while they play.",
                        color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
                }
                Spacer(Modifier.height(16.dp))
            }
            item {
                Section("Login (only if needed)") {
                    Text(
                        "If you are logged in to a site in the built-in Browser, downloads use that login automatically. " +
                            "Most sites work without logging in; if YouTube blocks you, log in once.",
                        color = Muted, fontSize = 13.sp,
                    )
                }
            }
            items(Cookies.SITES, key = { it.key }) { site ->
                val logged = remember(refresh) { Cookies.isLoggedIn(ctx, site) }
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(site.name, fontWeight = FontWeight.SemiBold)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (logged) Icon(Icons.Default.CheckCircle, null, Modifier.size(14.dp), tint = Good)
                            Text(if (logged) " Logged in" else "Not logged in", color = Muted, fontSize = 12.sp)
                        }
                    }
                    if (logged) OutlinedButton(onClick = { Cookies.logout(ctx, site); refresh++ }) { Text("Log out") }
                    else Button(onClick = { UiBus.openBrowser(site.loginUrl) }, colors = ButtonDefaults.buttonColors(containerColor = Orange)) { Text("Log in") }
                }
                HorizontalDivider(color = Card2)
            }
            item {
                Spacer(Modifier.height(16.dp))
                Section("Import cookies.txt (from a PC)") {
                    Text(
                        "If you are logged in on a PC, export cookies with the \"Get cookies.txt LOCALLY\" Chrome extension, send the file to your phone, then import it here.",
                        color = Muted, fontSize = 13.sp,
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = { importer.launch(arrayOf("text/*", "application/octet-stream")) }) { Text("Import cookies.txt") }
                }
                Spacer(Modifier.height(16.dp))
                Section("Download engine") {
                    Text(engine, color = Muted, fontSize = 13.sp)
                    Text("Updates itself daily. If a site stops working, tap update here.", color = Muted, fontSize = 13.sp)
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = { Downloads.updateEngine() }) { Text("Update yt-dlp") }
                }
                Spacer(Modifier.height(16.dp))
                Section("What can't be downloaded") {
                    Text(
                        "Services like Netflix, Prime Video, Disney+/Hotstar, Hoichoi, Chorki and Spotify lock their content with DRM, " +
                            "so no downloader can save it. Use the download option in their own apps.",
                        color = Muted, fontSize = 13.sp,
                    )
                }
                Spacer(Modifier.height(16.dp))
                Text("Save folder: Download/$SAVE_FOLDER", color = Muted, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun Toggle(title: String, hint: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold)
            Text(hint, color = Muted, fontSize = 12.sp)
        }
        Switch(checked = checked, onCheckedChange = onChange, colors = SwitchDefaults.colors(checkedTrackColor = Orange))
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Card1).padding(16.dp)) {
        Text(title, fontWeight = FontWeight.Bold, fontSize = 16.sp)
        Spacer(Modifier.height(6.dp))
        content()
    }
}
