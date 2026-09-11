package org.uchuva.aruco

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
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
        paint.textSize = 13f * unit
        canvas.save()
        canvas.clipRect(0f, 0f, frame.bitmap.width.toFloat(), frame.bitmap.height.toFloat())
        result.references.forEach { reference -> drawReferenceGrid(canvas, reference, result.settings.markerSideCm, unit, result.width, result.height) }
        result.references.forEach { reference ->
            paint.textSize = 13f * unit
            val marker = reference.marker
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = (if (reference.selected) 4f else 2.5f) * unit
            paint.color = if (reference.selected) cyan else markerColor(marker.id)
            val path = Path().apply {
                moveTo(marker.corners[0].x.toFloat(), marker.corners[0].y.toFloat())
                marker.corners.drop(1).forEach { lineTo(it.x.toFloat(), it.y.toFloat()) }
                close()
            }
            canvas.drawPath(path, paint)
            val state = when (reference.state) {
                ReferenceState.VALID -> ""
                ReferenceState.SIZE_UNCONFIRMED -> " · escala sin confirmar"
                ReferenceState.AMBIGUOUS -> " · ID duplicado"
                ReferenceState.DEGENERATE -> " · geometría no válida"
                else -> " · no disponible"
            }
            label(canvas, "ArUco ${marker.id}" + (if (reference.selected) " · seleccionado" else "") + state,
                marker.corners[0].x.toFloat(), marker.corners[0].y.toFloat(), frame.bitmap.width, frame.bitmap.height)
        }
        result.detections.forEachIndexed { index, located ->
            paint.textSize = 13f * unit
            val box = located.detection.box
            paint.style = Paint.Style.STROKE; paint.color = green; paint.strokeWidth = 2.5f * unit
            canvas.drawRect(box.left.toFloat(), box.top.toFloat(), box.right.toFloat(), box.bottom.toFloat(), paint)
            canvas.drawCircle(box.center.x.toFloat(), box.center.y.toFloat(), 3 * unit, paint)
            val name = String.format(Locale.US, "Capacho %d · %.0f%%", index + 1, located.detection.confidence * 100)
            label(canvas, name, box.left.toFloat(), box.top.toFloat(), frame.bitmap.width, frame.bitmap.height)
            detectionCard(canvas, located, result.selectedMarkerId, box, frame.bitmap.width, frame.bitmap.height, unit)
        }
        canvas.restore()
        paint.textSize = 12f * unit
        label(canvas, ESTIMATION_LABEL, 6 * unit, result.height - 22 * unit, result.width, result.height)
        label(canvas, "Sin profundidad ni corrección de lente · cuadro ${result.frameId}", 6 * unit, result.height - 6 * unit, result.width, result.height)
    }

    private fun drawReferenceGrid(canvas: Canvas, reference: MarkerReference, sideCm: Double, unit: Float, width: Int, height: Int) {
        val mapping = reference.mapping ?: return
        mapping.imageGrid(sideCm, width, height).forEach { line ->
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = when (line.kind) {
                GridLineKind.GRID -> (if (reference.selected) 1.3f else 0.9f) * unit
                else -> (if (reference.selected) 3.2f else 2.2f) * unit
            }
            paint.color = when (line.kind) {
                GridLineKind.GRID -> withAlpha(markerColor(reference.marker.id), if (reference.selected) 125 else 75)
                GridLineKind.X_AXIS -> Color.argb(220, 244, 82, 82)
                GridLineKind.Y_AXIS -> Color.argb(220, 85, 220, 110)
            }
            canvas.drawLine(line.start.x.toFloat(), line.start.y.toFloat(), line.end.x.toFloat(), line.end.y.toFloat(), paint)
        }
        val origin = mapping.unproject(PlanarPosition(0.0, 0.0)) ?: return
        mapping.unproject(PlanarPosition(sideCm, 0.0))?.let {
            drawArrow(canvas, origin, it, Color.rgb(244, 82, 82), unit)
            axisLabel(canvas, "X+", it, unit)
        }
        mapping.unproject(PlanarPosition(0.0, sideCm))?.let {
            drawArrow(canvas, origin, it, Color.rgb(85, 220, 110), unit)
            axisLabel(canvas, "Y+", it, unit)
        }
        paint.style = Paint.Style.FILL
        paint.color = if (reference.selected) cyan else markerColor(reference.marker.id)
        canvas.drawCircle(origin.x.toFloat(), origin.y.toFloat(), 4f * unit, paint)
    }

    private fun drawArrow(canvas: Canvas, start: Point2, end: Point2, color: Int, unit: Float) {
        val dx = end.x - start.x; val dy = end.y - start.y
        val length = kotlin.math.hypot(dx, dy)
        if (length < 1.0) return
        val ux = dx / length; val uy = dy / length
        val arrow = minOf(12.0 * unit, length * 0.25)
        paint.style = Paint.Style.STROKE; paint.color = color; paint.strokeWidth = 3f * unit
        canvas.drawLine(start.x.toFloat(), start.y.toFloat(), end.x.toFloat(), end.y.toFloat(), paint)
        canvas.drawLine(end.x.toFloat(), end.y.toFloat(), (end.x - arrow * ux + arrow * 0.55 * uy).toFloat(),
            (end.y - arrow * uy - arrow * 0.55 * ux).toFloat(), paint)
        canvas.drawLine(end.x.toFloat(), end.y.toFloat(), (end.x - arrow * ux - arrow * 0.55 * uy).toFloat(),
            (end.y - arrow * uy + arrow * 0.55 * ux).toFloat(), paint)
    }

    private fun axisLabel(canvas: Canvas, text: String, point: Point2, unit: Float) {
        paint.style = Paint.Style.FILL; paint.color = Color.WHITE; paint.textSize = 11f * unit
        canvas.drawText(text, point.x.toFloat() + 3f * unit, point.y.toFloat() - 3f * unit, paint)
    }

    private fun detectionCard(canvas: Canvas, located: LocatedDetection, selectedId: Int?, box: Box, width: Int, height: Int, unit: Float) {
        if (located.positions.isEmpty()) return
        val duplicateCounts = located.positions.groupingBy { it.markerId }.eachCount()
        val lines = located.positions.map { relative ->
            val suffix = if (duplicateCounts.getValue(relative.markerId) > 1) " #${relative.observationIndex + 1}" else ""
            val position = relative.position
            val units = "cm"
            if (position == null) "ArUco ${relative.markerId}$suffix · " +
                (if (relative.state == ReferenceState.SIZE_UNCONFIRMED) "indica el lado en Ajustes" else "no disponible")
            else String.format(Locale.US, "ArUco %d%s · X %+.2f · Y %+.2f · d %.2f %s",
                relative.markerId, suffix, position.xCm, position.yCm, position.distanceCm, units)
        }
        val padding = 4f * unit
        val lineHeightFactor = 1.28f
        val preferredTextSize = 11.5f * unit
        val availableHeight = maxOf(1f, height - 2 * padding)
        paint.textSize = minOf(preferredTextSize, availableHeight / (lines.size * lineHeightFactor)).coerceAtLeast(1f)
        val measuredWidth = lines.maxOf { paint.measureText(it) } + 2 * padding
        if (measuredWidth > width) paint.textSize *= width / measuredWidth
        val lineHeight = paint.textSize * lineHeightFactor
        val cardWidth = minOf(width.toFloat(), lines.maxOf { paint.measureText(it) } + 2 * padding)
        val cardHeight = lines.size * lineHeight + 2 * padding
        val gap = 6f * unit
        val placement = placeAnnotationCard(box, cardWidth.toDouble(), cardHeight.toDouble(), width, height, gap.toDouble())
        val cardLeft = placement.left.toFloat(); val cardTop = placement.top.toFloat()
        paint.style = Paint.Style.FILL; paint.color = Color.argb(220, 8, 18, 12)
        canvas.drawRoundRect(RectF(cardLeft, cardTop, placement.right.toFloat(), placement.bottom.toFloat()), 4f * unit, 4f * unit, paint)
        lines.forEachIndexed { index, line ->
            val selected = located.positions[index].markerId == selectedId
            paint.color = if (selected) cyan else Color.WHITE
            canvas.drawText(line, cardLeft + padding, cardTop + padding + paint.textSize + index * lineHeight, paint)
        }
    }

    private fun markerColor(id: Int): Int = Color.HSVToColor(floatArrayOf(((id * 67) % 360).toFloat(), 0.55f, 1f))
    private fun withAlpha(color: Int, alpha: Int) = Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color))

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
