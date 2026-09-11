package org.uchuva.aruco

import org.junit.Assert.*
import org.junit.Test

class GeometryTest {
    @Test fun gridReachesImageEdgesFarBeyondMarker() {
        val map = PlanarMapping.fromMarker(listOf(Point2(100.0,100.0), Point2(200.0,100.0),
            Point2(200.0,200.0), Point2(100.0,200.0)), 10.0)!!
        val grid = map.imageGrid(10.0, 720, 1280)
        assertTrue(grid.any { it.start.y == 1280.0 || it.end.y == 1280.0 })
        assertTrue(grid.any { it.start.x == 720.0 || it.end.x == 720.0 })
        assertTrue(grid.all { listOf(it.start,it.end).all { p -> p.x in 0.0..720.0 && p.y in 0.0..1280.0 } })
    }

    @Test fun coordinatesRequireExplicitSizeConfirmationForBothMarkers() {
        val markers = listOf(MarkerObservation(0, square), MarkerObservation(1, square.map { Point2(it.x+400,it.y) }))
        val refs = ReferenceResolver.resolveAll(markers, null, AnalysisSettings()).references
        val located = locateDetection(Detection(Box(190.0,790.0,210.0,810.0),0.8f), refs, 10.0)
        assertEquals(2, located.positions.size)
        assertTrue(located.positions.all { it.position == null })
        val confirmed = ReferenceResolver.resolveAll(markers, null, settings).references
        val measured = locateDetection(located.detection, confirmed, 10.0)
        assertEquals(-30.0, measured.positions[0].position!!.yCm, 1e-7)
        assertEquals(-20.0, measured.positions[1].position!!.xCm, 1e-7)
    }
    private val square = listOf(Point2(100.0, 100.0), Point2(300.0, 100.0), Point2(300.0, 300.0), Point2(100.0, 300.0))
    private val settings = AnalysisSettings(10.0, 0.25f, true)
    private fun checkPosition(p: PlanarPosition?, x: Double, y: Double) {
        assertNotNull(p); assertEquals(x, p!!.xCm, 1e-7); assertEquals(y, p.yCm, 1e-7)
    }

    @Test fun originAxesAndPhysicalSize() {
        val map = PlanarMapping.fromMarker(square, 10.0)!!
        checkPosition(map.project(Point2(200.0, 200.0)), 0.0, 0.0)
        checkPosition(map.project(Point2(300.0, 100.0)), 5.0, 5.0)
        checkPosition(map.project(Point2(400.0, 400.0)), 10.0, -10.0)
        checkPosition(PlanarMapping.fromMarker(square, 20.0)!!.project(Point2(300.0, 100.0)), 10.0, 10.0)
    }

    @Test fun perspectiveKeepsMetricCoordinates() {
        fun image(x: Double, y: Double): Point2 {
            val d = 0.012 * x + 0.008 * y + 1
            return Point2((25 * x + 3 * y + 350) / d, (2 * x - 22 * y + 300) / d)
        }
        val corners = listOf(image(-5.0, 5.0), image(5.0, 5.0), image(5.0, -5.0), image(-5.0, -5.0))
        val map = PlanarMapping.fromMarker(corners, 10.0)!!
        for ((x, y) in listOf(0.0 to 0.0, 3.2 to -1.7, -12.0 to 8.0)) {
            checkPosition(map.project(image(x, y)), x, y)
            val restored = map.unproject(PlanarPosition(x, y))!!
            assertEquals(image(x, y).x, restored.x, 1e-7)
            assertEquals(image(x, y).y, restored.y, 1e-7)
        }
    }

    @Test fun projectedGridUsesHalfSideSpacingAndTwoSideExtent() {
        val map = PlanarMapping.fromMarker(square, 10.0)!!
        val grid = map.grid(10.0)
        assertEquals(18, grid.size)
        assertEquals(8, grid.count { it.kind == GridLineKind.GRID } / 2)
        assertEquals(1, grid.count { it.kind == GridLineKind.X_AXIS })
        assertEquals(1, grid.count { it.kind == GridLineKind.Y_AXIS })
        val xAxis = grid.single { it.kind == GridLineKind.X_AXIS }
        checkPosition(map.project(xAxis.start), -20.0, 0.0)
        checkPosition(map.project(xAxis.end), 20.0, 0.0)
    }

    @Test fun decodedCornerOrderSurvivesRotation() {
        val rotated = square.map { Point2(400 - it.y, it.x) }
        val map = PlanarMapping.fromMarker(rotated, 10.0)!!
        checkPosition(map.project(rotated[0]), -5.0, 5.0)
        checkPosition(map.project(rotated[2]), 5.0, -5.0)
    }

    @Test fun degenerateSmallAndNonfiniteMarkersAreRejected() {
        assertNull(PlanarMapping.fromMarker(List(4) { Point2(5.0, 5.0) }, 10.0))
        assertNull(PlanarMapping.fromMarker(listOf(square[0], square[2], square[1], square[3]), 10.0))
        assertNull(PlanarMapping.fromMarker(square.map { Point2(it.x / 100, it.y / 100) }, 10.0))
        assertNull(PlanarMapping.fromMarker(square, Double.NaN))
        assertNull(PlanarMapping.fromMarker(square, -1.0))
    }

    @Test fun letterboxRestoresPortraitAndLandscapeWithoutStretching() {
        for ((w, h) in listOf(1280 to 720, 720 to 1280, 1001 to 777)) {
            val t = Letterbox(w, h)
            val original = Box(20.0, 45.0, w - 30.0, h - 50.0)
            val encoded = Box(original.left * t.scale + t.left, original.top * t.scale + t.top,
                original.right * t.scale + t.left, original.bottom * t.scale + t.top)
            val restored = t.restore(encoded)
            assertEquals(original.left, restored.left, 1e-7)
            assertEquals(original.top, restored.top, 1e-7)
            assertEquals(original.right, restored.right, 1e-7)
            assertEquals(original.bottom, restored.bottom, 1e-7)
        }
    }

    @Test fun previewTouchMappingIncludesLetterboxMargins() {
        val fit = FitTransform(1280, 720, 400, 800)
        val center = fit.toView(Point2(640.0, 360.0))
        assertEquals(200.0, center.x, 1e-9); assertEquals(400.0, center.y, 1e-9)
        assertEquals(Point2(640.0, 360.0), fit.toImage(center.x, center.y))
        assertTrue(containsPoint(square, Point2(200.0, 200.0)))
        assertFalse(containsPoint(square, Point2(50.0, 200.0)))
    }

    @Test fun annotationCardsStayInsideFrameAndPreferAvailableSide() {
        val right = placeAnnotationCard(Box(20.0, 30.0, 80.0, 90.0), 100.0, 70.0, 300, 200, 8.0)
        assertEquals(88.0, right.left, 1e-9)
        val left = placeAnnotationCard(Box(230.0, 170.0, 290.0, 190.0), 120.0, 80.0, 300, 200, 8.0)
        assertEquals(102.0, left.left, 1e-9)
        assertEquals(120.0, left.top, 1e-9)
        assertTrue(left.right <= 300.0 && left.bottom <= 200.0)
    }

    @Test fun selectionDoesNotJumpWhenSelectedMarkerDisappears() {
        val first = ReferenceResolver.resolve(listOf(MarkerObservation(7, square)), null, settings)
        assertEquals(7, first.selectedId); assertEquals(ReferenceState.VALID, first.state)
        val missing = ReferenceResolver.resolve(listOf(MarkerObservation(8, square)), first.selectedId, settings)
        assertEquals(7, missing.selectedId); assertEquals(ReferenceState.MISSING, missing.state); assertNull(missing.mapping)
        val returned = ReferenceResolver.resolve(listOf(MarkerObservation(7, square)), first.selectedId, settings)
        assertEquals(ReferenceState.VALID, returned.state)
    }

    @Test fun duplicateIdsInvalidateEvenIfBothQuadsAreUsable() {
        val result = ReferenceResolver.resolve(listOf(MarkerObservation(3, square), MarkerObservation(3, square)), 3, settings)
        assertEquals(ReferenceState.AMBIGUOUS, result.state); assertNull(result.mapping)
    }

    @Test fun allUniqueMarkersProduceIndependentPositions() {
        val shifted = square.map { Point2(it.x + 400, it.y) }
        val all = ReferenceResolver.resolveAll(listOf(MarkerObservation(7, square), MarkerObservation(8, shifted)), null, settings)
        assertNull(all.selectedId)
        assertEquals(listOf(7, 8), all.references.map { it.marker.id })
        assertTrue(all.references.all { it.state == ReferenceState.VALID })
        checkPosition(all.references[0].mapping!!.project(Point2(200.0, 200.0)), 0.0, 0.0)
        checkPosition(all.references[1].mapping!!.project(Point2(200.0, 200.0)), -20.0, 0.0)
    }

    @Test fun duplicateIdDoesNotInvalidateAnotherUniqueMarker() {
        val shifted = square.map { Point2(it.x + 400, it.y) }
        val markers = listOf(MarkerObservation(3, square), MarkerObservation(3, shifted), MarkerObservation(4, square))
        val all = ReferenceResolver.resolveAll(markers, 4, settings)
        assertEquals(2, all.references.count { it.state == ReferenceState.AMBIGUOUS })
        assertTrue(all.references.filter { it.state == ReferenceState.AMBIGUOUS }.all { it.mapping != null })
        assertEquals(1, all.references.count { it.state == ReferenceState.VALID })
        assertNotNull(all.references.single { it.marker.id == 4 }.mapping)
    }

    @Test fun multipleMarkersRequireExplicitInitialSelection() {
        val markers = listOf(MarkerObservation(1, square), MarkerObservation(2, square))
        assertEquals(ReferenceState.NO_SELECTION, ReferenceResolver.resolve(markers, null, settings).state)
        assertEquals(ReferenceState.VALID, ReferenceResolver.resolve(markers, 2, settings).state)
    }

    @Test fun centimetersRequireConfirmedPrintedSize() {
        val result = ReferenceResolver.resolve(listOf(MarkerObservation(0, square)), null, AnalysisSettings())
        assertEquals(ReferenceState.SIZE_UNCONFIRMED, result.state); assertNull(result.mapping)
        val visualReference = ReferenceResolver.resolveAll(listOf(MarkerObservation(0, square)), null, AnalysisSettings()).references.single()
        assertEquals(ReferenceState.SIZE_UNCONFIRMED, visualReference.state)
        assertNotNull(visualReference.mapping)
    }

    @Test fun missingReferenceExportsNullNotOldCoordinates() {
        val result = FrameAnalysis(12, "2026-09-02T12:00:00Z", 1234, 640, 480, 90, "abc", settings,
            emptyList(), emptyList(), 7, ReferenceState.MISSING,
            listOf(LocatedDetection(Detection(Box(1.0, 2.0, 3.0, 4.0), 0.5f), emptyList())), 10.0)
        val json = result.toJson("0.1.0")
        assertTrue(json.getJSONArray("detections").getJSONObject(0).isNull("position_cm"))
        assertEquals(12L, json.getLong("frame_id"))
        assertFalse(json.getJSONObject("estimation").getBoolean("object_depth_measured"))
        assertFalse(json.getJSONObject("estimation").getBoolean("lens_distortion_corrected"))
        assertEquals("missing", json.getJSONObject("reference").getString("state"))
    }

    @Test fun jsonExportsEveryMarkerAndKeepsSelectedCompatibilityPosition() {
        val markers = listOf(MarkerObservation(1, square), MarkerObservation(2, square.map { Point2(it.x + 400, it.y) }))
        val resolved = ReferenceResolver.resolveAll(markers, 2, settings)
        val detection = Detection(Box(190.0, 190.0, 210.0, 210.0), 0.8f)
        val positions = resolved.references.map { ref ->
            MarkerPosition(ref.observationIndex, ref.marker.id, ref.state, ref.mapping?.project(detection.box.center))
        }
        val result = FrameAnalysis(15, "2026-09-03T12:00:00Z", 555, 800, 600, 0, "abc", settings,
            markers, resolved.references, 2, ReferenceState.VALID, listOf(LocatedDetection(detection, positions)), 12.0)
        val json = result.toJson("0.2.0")
        assertEquals("1.4", json.getString("schema_version"))
        assertEquals(2, json.getJSONArray("references").length())
        val exported = json.getJSONArray("detections").getJSONObject(0)
        assertEquals(2, exported.getJSONArray("positions_by_marker").length())
        assertEquals(-20.0, exported.getJSONObject("position_cm").getDouble("x"), 1e-7)
    }
}
