package com.mediadownloader.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

object Notifications {
    const val CH_PROGRESS = "progress"
    const val CH_DONE = "done"
    const val PROGRESS_ID = 1

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CH_PROGRESS, "Download progress", NotificationManager.IMPORTANCE_LOW)
        )
        nm.createNotificationChannel(
            NotificationChannel(CH_DONE, "Download complete", NotificationManager.IMPORTANCE_DEFAULT)
        )
    }

    fun canNotify(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun openAppIntent(ctx: Context) = PendingIntent.getActivity(
        ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )

    fun progress(ctx: Context, active: List<DownloadItem>): android.app.Notification {
        val first = active.firstOrNull()
        val title = when {
            active.size > 1 -> "${active.size} downloads running"
            first != null -> first.title
            else -> "Downloading"
        }
        val b = NotificationCompat.Builder(ctx, CH_PROGRESS)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(title)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setContentIntent(openAppIntent(ctx))
        if (first != null && first.status == Status.DOWNLOADING) {
            b.setProgress(100, first.progress.toInt(), false)
            b.setContentText("${first.progress.toInt()}%  ${first.speed}")
        } else {
            b.setProgress(0, 0, true)
            b.setContentText(if (first?.status == Status.PROCESSING) "Converting…" else "Starting…")
        }
        return b.build()
    }

    @SuppressLint("MissingPermission")
    fun done(ctx: Context, id: String, title: String, file: SavedFile) {
        if (!canNotify(ctx)) return
        val view = Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse(file.uri), file.mime)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        val pi = PendingIntent.getActivity(
            ctx, id.hashCode(), view, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val n = NotificationCompat.Builder(ctx, CH_DONE)
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle("Download complete")
            .setContentText(title)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        NotificationManagerCompat.from(ctx).notify(id.hashCode(), n)
    }
}
