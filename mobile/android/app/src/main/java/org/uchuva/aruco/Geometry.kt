package org.uchuva.aruco

import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

data class Point2(val x: Double, val y: Double)
data class Box(val left: Double, val top: Double, val right: Double, val bottom: Double) {
    val center get() = Point2((left + right) / 2, (top + bottom) / 2)
}
data class PlanarPosition(val xCm: Double, val yCm: Double) {
    val distanceCm get() = hypot(xCm, yCm)
}

/** All geometry uses upright, cropped analysis-image pixels, never screen pixels. */
data class Letterbox(val width: Int, val height: Int, val size: Int = 640) {
    val scale = min(size.toDouble() / width, size.toDouble() / height)
    val resizedWidth = Math.rint(width * scale).toInt()
    val resizedHeight = Math.rint(height * scale).toInt()
    val left = (size - resizedWidth) / 2
    val top = (size - resizedHeight) / 2
    fun restore(box: Box) = Box(
        ((box.left - left) / scale).coerceIn(0.0, width.toDouble()),
        ((box.top - top) / scale).coerceIn(0.0, height.toDouble()),
        ((box.right - left) / scale).coerceIn(0.0, width.toDouble()),
        ((box.bottom - top) / scale).coerceIn(0.0, height.toDouble())
    )
}

data class FitTransform(val imageWidth: Int, val imageHeight: Int, val viewWidth: Int, val viewHeight: Int) {
    val scale = min(viewWidth.toDouble() / imageWidth, viewHeight.toDouble() / imageHeight)
    val offsetX = (viewWidth - imageWidth * scale) / 2
    val offsetY = (viewHeight - imageHeight * scale) / 2
    fun toImage(x: Double, y: Double) = Point2((x - offsetX) / scale, (y - offsetY) / scale)
    fun toView(p: Point2) = Point2(p.x * scale + offsetX, p.y * scale + offsetY)
}

fun containsPoint(corners: List<Point2>, point: Point2): Boolean {
    if (corners.size != 4) return false
    val crosses = corners.indices.map { i ->
        val a = corners[i]; val b = corners[(i + 1) % 4]
        (b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x)
    }
    return crosses.all { it >= 0 } || crosses.all { it <= 0 }
}

/** Four-point projective map. Thresholds are engineering heuristics, not accuracy guarantees. */
class PlanarMapping private constructor(private val h: DoubleArray, private val origin: Point2, private val scale: Double) {
    fun project(point: Point2): PlanarPosition? {
        val x = (point.x - origin.x) / scale
        val y = (point.y - origin.y) / scale
        val denominator = h[6] * x + h[7] * y + 1.0
        // The marker center has positive denominator; do not cross its projective horizon.
        if (!denominator.isFinite() || denominator < 1e-8) return null
        val px = (h[0] * x + h[1] * y + h[2]) / denominator
        val py = (h[3] * x + h[4] * y + h[5]) / denominator
        return if (px.isFinite() && py.isFinite()) PlanarPosition(px, py) else null
    }

    companion object {
        fun fromMarker(corners: List<Point2>, sideCm: Double): PlanarMapping? {
            if (corners.size != 4 || !sideCm.isFinite() || sideCm <= 0 || corners.any { !it.x.isFinite() || !it.y.isFinite() }) return null
            val edges = corners.indices.map { i ->
                val a = corners[i]; val b = corners[(i + 1) % 4]
                Point2(b.x - a.x, b.y - a.y)
            }
            if (edges.any { hypot(it.x, it.y) < 24.0 }) return null
            val cross = edges.indices.map { i ->
                val a = edges[i]; val b = edges[(i + 1) % 4]
                a.x * b.y - a.y * b.x
            }
            if (!(cross.all { it > 1.0 } || cross.all { it < -1.0 })) return null
            val area = abs(corners.indices.sumOf { i ->
                val a = corners[i]; val b = corners[(i + 1) % 4]; a.x * b.y - a.y * b.x
            }) / 2
            val span = max(corners.maxOf { it.x } - corners.minOf { it.x }, corners.maxOf { it.y } - corners.minOf { it.y })
            if (area < 576.0 || area / (span * span) < 0.04) return null
            val origin = Point2(corners.map { it.x }.average(), corners.map { it.y }.average())
            val half = sideCm / 2
            // OpenCV returns corners in decoded TL, TR, BR, BL order.
            val target = listOf(Point2(-half, half), Point2(half, half), Point2(half, -half), Point2(-half, -half))
            val rows = Array(8) { DoubleArray(9) }
            corners.forEachIndexed { i, p ->
                val x = (p.x - origin.x) / span; val y = (p.y - origin.y) / span
                val u = target[i].x; val v = target[i].y
                rows[i * 2] = doubleArrayOf(x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, u)
                rows[i * 2 + 1] = doubleArrayOf(0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, v)
            }
            for (col in 0..7) {
                val pivot = (col..7).maxBy { abs(rows[it][col]) }
                if (abs(rows[pivot][col]) < 1e-10) return null
                val swap = rows[col]; rows[col] = rows[pivot]; rows[pivot] = swap
                val divisor = rows[col][col]
                for (j in col..8) rows[col][j] /= divisor
                for (i in 0..7) if (i != col) {
                    val factor = rows[i][col]
                    for (j in col..8) rows[i][j] -= factor * rows[col][j]
                }
            }
            return PlanarMapping(DoubleArray(8) { rows[it][8] }, origin, span)
        }
    }
}
