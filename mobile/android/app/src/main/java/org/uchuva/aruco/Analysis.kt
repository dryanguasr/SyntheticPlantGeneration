package org.uchuva.aruco

import org.json.JSONArray
import org.json.JSONObject

const val ESTIMATION_LABEL = "Estimación sobre el plano del ArUco"
data class Detection(val box: Box, val confidence: Float, val classId: Int = 0)
data class MarkerObservation(val id: Int, val corners: List<Point2>)
data class AnalysisSettings(val markerSideCm: Double = 10.0, val confidence: Float = 0.25f, val sizeConfirmed: Boolean = false)
enum class ReferenceState { VALID, SIZE_UNCONFIRMED, NO_SELECTION, MISSING, AMBIGUOUS, DEGENERATE }
data class ReferenceResolution(val selectedId: Int?, val state: ReferenceState, val mapping: PlanarMapping?)
data class MarkerReference(
    val observationIndex: Int,
    val marker: MarkerObservation,
    val state: ReferenceState,
    val mapping: PlanarMapping?,
    val selected: Boolean,
)
data class ReferenceSet(val selectedId: Int?, val references: List<MarkerReference>)

object ReferenceResolver {
    fun resolveAll(markers: List<MarkerObservation>, selectedId: Int?, settings: AnalysisSettings): ReferenceSet {
        val effectiveSelectedId = selectedId ?: markers.singleOrNull()?.id
        val idCounts = markers.groupingBy { it.id }.eachCount()
        val references = markers.mapIndexed { index, marker ->
            val mapping = PlanarMapping.fromMarker(marker.corners, settings.markerSideCm)
            val state = when {
                idCounts.getValue(marker.id) > 1 -> ReferenceState.AMBIGUOUS
                mapping == null -> ReferenceState.DEGENERATE
                !settings.sizeConfirmed -> ReferenceState.SIZE_UNCONFIRMED
                else -> ReferenceState.VALID
            }
            // Duplicate IDs cannot produce named coordinates, but each usable quadrilateral can still show its visual frame.
            MarkerReference(index, marker, state, mapping, marker.id == effectiveSelectedId)
        }.sortedWith(compareBy<MarkerReference> { it.marker.id }.thenBy { it.observationIndex })
        return ReferenceSet(effectiveSelectedId, references)
    }

    fun resolve(markers: List<MarkerObservation>, selectedId: Int?, settings: AnalysisSettings): ReferenceResolution {
        val all = resolveAll(markers, selectedId, settings)
        val id = all.selectedId
        if (id == null) return ReferenceResolution(null, ReferenceState.NO_SELECTION, null)
        val matches = all.references.filter { it.marker.id == id }
        if (matches.isEmpty()) return ReferenceResolution(id, ReferenceState.MISSING, null)
        if (matches.size != 1) return ReferenceResolution(id, ReferenceState.AMBIGUOUS, null)
        val match = matches.single()
        return ReferenceResolution(id, match.state, match.mapping.takeIf { match.state == ReferenceState.VALID })
    }
}

data class MarkerPosition(
    val observationIndex: Int,
    val markerId: Int,
    val state: ReferenceState,
    val position: PlanarPosition?,
)

fun locateDetection(detection: Detection, references: List<MarkerReference>, sideCm: Double): LocatedDetection =
    LocatedDetection(detection, references.map { ref ->
        val projected = ref.mapping.takeIf { ref.state == ReferenceState.VALID }
            ?.project(detection.box.center)
        MarkerPosition(ref.observationIndex, ref.marker.id, ref.state,
            projected)
    })
data class LocatedDetection(val detection: Detection, val positions: List<MarkerPosition>) {
    fun positionFor(markerId: Int?): PlanarPosition? = markerId?.let { id -> positions.singleOrNull { it.markerId == id }?.position }
}
data class FrameAnalysis(
    val frameId: Long,
    val capturedAt: String,
    val cameraTimestampNs: Long,
    val width: Int,
    val height: Int,
    val rotationDegrees: Int,
    val modelHash: String,
    val settings: AnalysisSettings,
    val markers: List<MarkerObservation>,
    val references: List<MarkerReference>,
    val selectedMarkerId: Int?,
    val referenceState: ReferenceState,
    val detections: List<LocatedDetection>,
    val analysisMs: Double,
    val modelVersion: String = "natural_hybrid_alpha_045",
    val sourceKind: String = "camera",
    val receivedAt: String = capturedAt,
) {
    fun toJson(appVersion: String): JSONObject = JSONObject().apply {
        put("schema_version", "1.4")
        put("app_version", appVersion)
        put("model_sha256", modelHash)
        put("model_version", modelVersion)
        put("frame_id", frameId)
        put("captured_at", capturedAt)
        put("camera_timestamp_ns", if (sourceKind == "camera") cameraTimestampNs else JSONObject.NULL)
        put("source", JSONObject().put("kind", sourceKind)
            .put("received_at", receivedAt).put("drone_capture_time_known", false)
            .put("decoder_timestamp_ns", if (sourceKind == "rtmp") cameraTimestampNs else JSONObject.NULL)
            .put("timestamp_basis", if (sourceKind == "rtmp") "decoder_surface_timestamp" else "camera_timestamp"))
        put("image", JSONObject().put("width", width).put("height", height).put("rotation_applied_degrees", rotationDegrees).put("coordinates", "upright_analysis_pixels"))
        put("confidence_threshold", settings.confidence)
        put("analysis_ms", analysisMs)
        put("reference", JSONObject().apply {
            put("dictionary", "DICT_4X4_50")
            put("selected_id", selectedMarkerId ?: JSONObject.NULL)
            put("side_cm", if (settings.sizeConfirmed) settings.markerSideCm else JSONObject.NULL)
            put("size_confirmed", settings.sizeConfirmed)
            put("state", referenceState.name.lowercase())
            put("origin", "marker_center")
            put("axes", "x_marker_right_y_marker_up")
        })
        put("estimation", JSONObject().put("method", "marker_plane_homography").put("status", "estimated")
            .put("label", ESTIMATION_LABEL).put("lens_distortion_corrected", false)
            .put("object_depth_measured", false).put("point", "bounding_box_center")
            .put("geometric_threshold_provenance", "engineering_heuristic"))
        put("markers", JSONArray().apply { markers.forEach { marker ->
            put(JSONObject().put("id", marker.id).put("corners_px", JSONArray().apply {
                marker.corners.forEach { put(JSONArray(listOf(it.x, it.y))) }
            }))
        } })
        put("references", JSONArray().apply { references.forEach { reference ->
            put(JSONObject().apply {
                put("observation_index", reference.observationIndex)
                put("marker_id", reference.marker.id)
                put("selected", reference.selected)
                put("state", reference.state.name.lowercase())
                put("side_cm", if (settings.sizeConfirmed) settings.markerSideCm else JSONObject.NULL)
                put("origin", "marker_center")
                put("axes", "x_marker_right_y_marker_up")
                put("corners_px", JSONArray().apply {
                    reference.marker.corners.forEach { put(JSONArray(listOf(it.x, it.y))) }
                })
            })
        } })
        put("detections", JSONArray().apply { detections.forEach { located ->
            val detection = located.detection
            val selectedPosition = located.positionFor(selectedMarkerId)
            put(JSONObject().apply {
                put("class_id", detection.classId); put("class_name", "calyx")
                put("confidence", detection.confidence)
                put("box_xyxy_px", JSONArray(listOf(detection.box.left, detection.box.top, detection.box.right, detection.box.bottom)))
                put("center_px", JSONArray(listOf(detection.box.center.x, detection.box.center.y)))
                put("position_cm", selectedPosition?.toJson() ?: JSONObject.NULL)
                put("position_status", if (selectedPosition != null) "estimated" else "unavailable")
                put("positions_by_marker", JSONArray().apply { located.positions.forEach { relative ->
                    put(JSONObject().apply {
                        put("observation_index", relative.observationIndex)
                        put("marker_id", relative.markerId)
                        put("state", relative.state.name.lowercase())
                        put("reference_state", relative.state.name.lowercase())
                        put("position_status", if (relative.position != null) "estimated" else "unavailable")
                        put("position_cm", relative.position?.toJson() ?: JSONObject.NULL)
                    })
                } })
            })
        } })
    }
}

private fun PlanarPosition.toJson() = JSONObject().put("x", xCm).put("y", yCm).put("distance", distanceCm)
