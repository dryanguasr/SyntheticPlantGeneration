package org.uchuva.aruco

import android.content.Context
import android.graphics.Bitmap
import android.graphics.SurfaceTexture
import android.os.SystemClock
import android.view.Surface
import android.view.TextureView
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.rtmp.RtmpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import java.net.URI

/** Main-thread decoder owner. Each texture update supplies one immutable analysis frame.
 * DJI Fly is the publisher; this is a reader of an RTMP server, not a DJI controller.
 */
@androidx.annotation.OptIn(UnstableApi::class)
class RtmpFrames(context: Context, private val texture: TextureView,
    private val canAccept: () -> Boolean,
    private val onFrame: (Bitmap, Long) -> Unit,
    private val onStatus: (String) -> Unit,
) : TextureView.SurfaceTextureListener, AutoCloseable {
    private val player = ExoPlayer.Builder(context).build()
    private var surface: Surface? = null
    private var width = 0
    private var height = 0
    private var lastFrameMs = 0L
    private var closed = false

    init {
        texture.surfaceTextureListener = this
        if (texture.isAvailable) attach(checkNotNull(texture.surfaceTexture))
        player.volume = 0f
        player.addListener(object : Player.Listener {
            override fun onVideoSizeChanged(size: VideoSize) {
                val scale = minOf(1.0, 1280.0 / maxOf(size.width, size.height).coerceAtLeast(1))
                width = (size.width * size.pixelWidthHeightRatio * scale).toInt().coerceAtLeast(1)
                height = (size.height * scale).toInt().coerceAtLeast(1)
            }
            override fun onPlayerError(error: PlaybackException) {
                // Do not show the exception's URL: it can contain a stream key.
                onStatus("RTMP desconectado (${error.errorCodeName}). Revisa el emisor y pulsa Fuente para reconectar.")
            }
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_BUFFERING) onStatus("Esperando video RTMP…")
                if (state == Player.STATE_ENDED) onStatus("La transmisión RTMP terminó. Pulsa Fuente para reconectar.")
            }
        })
    }

    fun connect(address: String) {
        require(validRtmpAddress(address)) { "Usa rtmp://servidor:1935/ruta" }
        val source = ProgressiveMediaSource.Factory(RtmpDataSource.Factory())
            .createMediaSource(MediaItem.fromUri(address))
        player.setMediaSource(source)
        player.prepare()
        player.play()
    }

    private fun attach(value: SurfaceTexture) {
        surface?.release()
        surface = Surface(value)
        player.setVideoSurface(surface)
    }
    override fun onSurfaceTextureAvailable(value: SurfaceTexture, width: Int, height: Int) = attach(value)
    override fun onSurfaceTextureSizeChanged(value: SurfaceTexture, width: Int, height: Int) = Unit
    override fun onSurfaceTextureDestroyed(value: SurfaceTexture): Boolean {
        player.clearVideoSurface(); surface?.release(); surface = null
        return true
    }
    override fun onSurfaceTextureUpdated(value: SurfaceTexture) {
        val now = SystemClock.elapsedRealtime()
        if (closed || width <= 0 || height <= 0 || now - lastFrameMs < 200 || !canAccept()) return
        val bitmap = texture.getBitmap(width, height) ?: return
        lastFrameMs = now
        onFrame(bitmap, value.timestamp)
    }
    override fun close() {
        closed = true
        texture.surfaceTextureListener = null
        player.release(); surface?.release(); surface = null
    }
}

fun validRtmpAddress(address: String): Boolean = try {
    val uri = URI(address)
    uri.scheme == "rtmp" && !uri.host.isNullOrBlank() && !uri.path.isNullOrBlank() &&
        uri.path != "/" && uri.fragment == null && (uri.port == -1 || uri.port in 1..65535)
} catch (_: Exception) { false }
