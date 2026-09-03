package org.uchuva.aruco

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.view.MotionEvent
import android.view.View
import java.util.Locale

data class FrameSnapshot(val bitmap: Bitmap, val analysis: FrameAnalysis)

/** Displays the analyzed frame itself; overlays and saved data never refer to a newer preview. */
class AnalysisView(context: Context) : View(context) {
    var snapshot: FrameSnapshot? = null
        set(value) { field = value; invalidate() }
    var onMarkerTapped: ((Int) -> Unit)? = null
    private val renderer = FrameRenderer()

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.rgb(8, 14, 11))
        val frame = snapshot ?: return
        val fit = FitTransform(frame.bitmap.width, frame.bitmap.height, width, height)
        canvas.save()
        canvas.translate(fit.offsetX.toFloat(), fit.offsetY.toFloat())
        canvas.scale(fit.scale.toFloat(), fit.scale.toFloat())
        renderer.draw(canvas, frame)
        canvas.restore()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action != MotionEvent.ACTION_UP) return true
        performClick()
        val frame = snapshot ?: return true
        val p = FitTransform(frame.bitmap.width, frame.bitmap.height, width, height).toImage(event.x.toDouble(), event.y.toDouble())
        val markers = frame.analysis.markers.filter { containsPoint(it.corners, p) }
        if (markers.size == 1) onMarkerTapped?.invoke(markers.single().id)
        return true
    }

    override fun performClick(): Boolean { super.performClick(); return true }
}

class FrameRenderer {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val green = Color.rgb(181, 236, 115)
    private val cyan = Color.rgb(99, 218, 236)

    fun draw(canvas: Canvas, frame: FrameSnapshot) {
        val result = frame.analysis
        canvas.drawBitmap(frame.bitmap, 0f, 0f, null)
        val unit = maxOf(1f, frame.bitmap.width / 640f)
        paint.strokeWidth = 2.5f * unit
        paint.textSize = 13f * unit
        result.markers.forEach { marker ->
            paint.style = Paint.Style.STROKE
            paint.color = if (marker.id == result.selectedMarkerId) cyan else Color.WHITE
            val path = Path().apply {
                moveTo(marker.corners[0].x.toFloat(), marker.corners[0].y.toFloat())
                marker.corners.drop(1).forEach { lineTo(it.x.toFloat(), it.y.toFloat()) }
                close()
            }
            canvas.drawPath(path, paint)
            label(canvas, "ArUco ${marker.id}" + if (marker.id == result.selectedMarkerId) " · referencia" else "", marker.corners[0].x.toFloat(), marker.corners[0].y.toFloat(), frame.bitmap.width, frame.bitmap.height)
        }
        result.detections.forEachIndexed { index, located ->
            val box = located.detection.box
            paint.style = Paint.Style.STROKE; paint.color = green
            canvas.drawRect(box.left.toFloat(), box.top.toFloat(), box.right.toFloat(), box.bottom.toFloat(), paint)
            canvas.drawCircle(box.center.x.toFloat(), box.center.y.toFloat(), 3 * unit, paint)
            val name = String.format(Locale.US, "Capacho %d · %.0f%%", index + 1, located.detection.confidence * 100)
            label(canvas, name, box.left.toFloat(), box.top.toFloat(), frame.bitmap.width, frame.bitmap.height)
            located.position?.let { p ->
                val text = String.format(Locale.US, "X %.1f  Y %.1f  d %.1f cm", p.xCm, p.yCm, p.distanceCm)
                label(canvas, text, box.left.toFloat(), box.bottom.toFloat() + 16 * unit, frame.bitmap.width, frame.bitmap.height)
            }
        }
        paint.textSize = 12f * unit
        label(canvas, ESTIMATION_LABEL, 6 * unit, result.height - 22 * unit, result.width, result.height)
        label(canvas, "Sin profundidad ni corrección de lente · cuadro ${result.frameId}", 6 * unit, result.height - 6 * unit, result.width, result.height)
    }

    private fun label(canvas: Canvas, text: String, x: Float, baseline: Float, width: Int, height: Int) {
        val padding = paint.textSize * 0.25f
        val textWidth = paint.measureText(text)
        val left = x.coerceIn(padding, maxOf(padding, width - textWidth - padding))
        val y = baseline.coerceIn(paint.textSize + padding, height - padding)
        paint.style = Paint.Style.FILL
        paint.color = Color.argb(210, 8, 18, 12)
        canvas.drawRect(left - padding, y - paint.textSize, left + textWidth + padding, y + padding, paint)
        paint.color = Color.WHITE
        canvas.drawText(text, left, y, paint)
    }
}
