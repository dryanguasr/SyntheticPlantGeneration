package org.uchuva.aruco

import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

data class Point2(val x: Double, val y: Double)
data class Box(val left: Double, val top: Double, val right: Double, val bottom: Double) {
    val center get() = Point2((left + right) / 2, (top + bottom) / 2)
}
data class OverlayRect(val left: Double, val top: Double, val right: Double, val bottom: Double)

fun placeAnnotationCard(box: Box, cardWidth: Double, cardHeight: Double, frameWidth: Int, frameHeight: Int, gap: Double): OverlayRect {
    val width = cardWidth.coerceIn(0.0, frameWidth.toDouble())
    val height = cardHeight.coerceIn(0.0, frameHeight.toDouble())
    val proposedRight = box.right + gap
    val proposedLeft = if (proposedRight + width <= frameWidth) proposedRight else box.left - gap - width
    val left = proposedLeft.coerceIn(0.0, frameWidth - width)
    val top = box.top.coerceIn(0.0, frameHeight - height)
    return OverlayRect(left, top, left + width, top + height)
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
enum class GridLineKind { GRID, X_AXIS, Y_AXIS }
data class PlanarGridLine(val start: Point2, val end: Point2, val kind: GridLineKind)

class PlanarMapping private constructor(
    private val imageToPlane: DoubleArray,
    private val planeToImage: DoubleArray,
    private val origin: Point2,
    private val scale: Double,
) {
    fun project(point: Point2): PlanarPosition? {
        val x = (point.x - origin.x) / scale
        val y = (point.y - origin.y) / scale
        val denominator = imageToPlane[6] * x + imageToPlane[7] * y + imageToPlane[8]
        // The marker center has positive denominator; do not cross its projective horizon.
        if (!denominator.isFinite() || denominator < 1e-8) return null
        val px = (imageToPlane[0] * x + imageToPlane[1] * y + imageToPlane[2]) / denominator
        val py = (imageToPlane[3] * x + imageToPlane[4] * y + imageToPlane[5]) / denominator
        return if (px.isFinite() && py.isFinite()) PlanarPosition(px, py) else null
    }

    fun unproject(point: PlanarPosition): Point2? {
        val denominator = planeToImage[6] * point.xCm + planeToImage[7] * point.yCm + planeToImage[8]
        if (!denominator.isFinite() || abs(denominator) < 1e-8) return null
        val normalizedX = (planeToImage[0] * point.xCm + planeToImage[1] * point.yCm + planeToImage[2]) / denominator
        val normalizedY = (planeToImage[3] * point.xCm + planeToImage[4] * point.yCm + planeToImage[5]) / denominator
        val x = normalizedX * scale + origin.x
        val y = normalizedY * scale + origin.y
        return if (x.isFinite() && y.isFinite() && abs(x) < 1e7 && abs(y) < 1e7) Point2(x, y) else null
    }

    fun grid(sideCm: Double, extentSides: Double = 2.0, stepSides: Double = 0.5): List<PlanarGridLine> {
        if (!sideCm.isFinite() || sideCm <= 0 || extentSides <= 0 || stepSides <= 0) return emptyList()
        val steps = Math.rint(extentSides / stepSides).toInt()
        val extent = extentSides * sideCm
        return (-steps..steps).flatMap { index ->
            val coordinate = index * stepSides * sideCm
            val verticalKind = if (index == 0) GridLineKind.Y_AXIS else GridLineKind.GRID
            val horizontalKind = if (index == 0) GridLineKind.X_AXIS else GridLineKind.GRID
            listOfNotNull(
                segment(PlanarPosition(coordinate, -extent), PlanarPosition(coordinate, extent), verticalKind),
                segment(PlanarPosition(-extent, coordinate), PlanarPosition(extent, coordinate), horizontalKind),
            )
        }
    }

    /** Clip infinite constant-coordinate lines to the image, rather than a marker-sized patch. */
    fun imageGrid(sideCm: Double, width: Int, height: Int): List<PlanarGridLine> {
        if (width <= 0 || height <= 0 || sideCm <= 0) return emptyList()
        val boundary = listOf(Point2(0.0, 0.0), Point2(width.toDouble(), 0.0),
            Point2(width.toDouble(), height.toDouble()), Point2(0.0, height.toDouble()))
        // Sampling also handles an image edge that crosses the projective horizon.
        val samples = boundary.indices.flatMap { edge ->
            val a = boundary[edge]; val b = boundary[(edge + 1) % 4]
            (0..32).mapNotNull { i -> project(Point2(a.x + (b.x-a.x)*i/32, a.y + (b.y-a.y)*i/32)) }
        }
        if (samples.isEmpty()) return emptyList()
        return (0..1).flatMap { axis ->
            val values = samples.map { if (axis == 0) it.xCm else it.yCm }
            val low = minOf(0.0, values.min()); val high = maxOf(0.0, values.max())
            var step = sideCm / 2
            while ((high-low)/step > 80) step *= 2
            val first = kotlin.math.floor(low/step).toInt()
            val last = kotlin.math.ceil(high/step).toInt()
            (first..last).mapNotNull { index ->
                val coordinate = index * step
                val row = axis * 3
                val a = imageToPlane[row] - coordinate * imageToPlane[6]
                val b = imageToPlane[row+1] - coordinate * imageToPlane[7]
                val c = imageToPlane[row+2] - coordinate * imageToPlane[8]
                fun value(p: Point2) = a*(p.x-origin.x)/scale + b*(p.y-origin.y)/scale + c
                val intersections = boundary.indices.mapNotNull { edge ->
                    val p = boundary[edge]; val q = boundary[(edge+1)%4]
                    val vp = value(p); val vq = value(q)
                    if (abs(vp-vq) < 1e-12) null else {
                        val t = vp/(vp-vq)
                        if (t < 0 || t > 1) null else Point2(p.x+(q.x-p.x)*t, p.y+(q.y-p.y)*t)
                    }
                }.distinct()
                if (intersections.size < 2) null else {
                    val p = intersections.first(); val q = intersections.last()
                    if (project(p) == null || project(q) == null) null else
                        PlanarGridLine(p, q, if (index != 0) GridLineKind.GRID else
                            if (axis == 0) GridLineKind.Y_AXIS else GridLineKind.X_AXIS)
                }
            }
        }
    }

    private fun segment(start: PlanarPosition, end: PlanarPosition, kind: GridLineKind): PlanarGridLine? {
        val a = unproject(start) ?: return null
        val b = unproject(end) ?: return null
        return PlanarGridLine(a, b, kind)
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
            val forward = DoubleArray(9) { if (it == 8) 1.0 else rows[it][8] }
            val inverse = invert3x3(forward) ?: return null
            return PlanarMapping(forward, inverse, origin, span)
        }

        private fun invert3x3(matrix: DoubleArray): DoubleArray? {
            val a = matrix[0]; val b = matrix[1]; val c = matrix[2]
            val d = matrix[3]; val e = matrix[4]; val f = matrix[5]
            val g = matrix[6]; val h = matrix[7]; val i = matrix[8]
            val determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
            if (!determinant.isFinite() || abs(determinant) < 1e-12) return null
            return doubleArrayOf(
                (e * i - f * h) / determinant,
                (c * h - b * i) / determinant,
                (b * f - c * e) / determinant,
                (f * g - d * i) / determinant,
                (a * i - c * g) / determinant,
                (c * d - a * f) / determinant,
                (d * h - e * g) / determinant,
                (b * g - a * h) / determinant,
                (a * e - b * d) / determinant,
            )
        }
    }
}
