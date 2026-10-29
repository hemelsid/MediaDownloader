package com.mediadownloader.app

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.decode.VideoFrameDecoder

class App : Application(), ImageLoaderFactory {
    override fun onCreate() {
        super.onCreate()
        Notifications.createChannels(this)
        Library.init(this)
        Downloads.init(this)
    }

    // Lets Coil show a frame from local video files as thumbnail
    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .components { add(VideoFrameDecoder.Factory()) }
        .crossfade(true)
        .build()
}
