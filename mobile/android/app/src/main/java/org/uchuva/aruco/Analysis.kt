package org.uchuva.aruco

import org.json.JSONArray
import org.json.JSONObject

const val ESTIMATION_LABEL = "Estimación sobre el plano del ArUco"
data class Detection(val box: Box, val confidence: Float, val classId: Int = 0)
data class MarkerObservation(val id: Int, val corners: List<Point2>)
data class AnalysisSettings(val markerSideCm: Double = 10.0, val confidence: Float = 0.25f, val sizeConfirmed: Boolean = false)
enum class ReferenceState { VALID, SIZE_UNCONFIRMED, NO_SELECTION, MISSING, AMBIGUOUS, DEGENERATE }
data class ReferenceResolution(val selectedId: Int?, val state: ReferenceState, val mapping: PlanarMapping?)

object ReferenceResolver {
    fun resolve(markers: List<MarkerObservation>, selectedId: Int?, settings: AnalysisSettings): ReferenceResolution {
        val id = selectedId ?: markers.singleOrNull()?.id
        if (id == null) return ReferenceResolution(null, ReferenceState.NO_SELECTION, null)
        val matches = markers.filter { it.id == id }
        if (matches.isEmpty()) return ReferenceResolution(id, ReferenceState.MISSING, null)
        if (matches.size != 1) return ReferenceResolution(id, ReferenceState.AMBIGUOUS, null)
        if (!settings.sizeConfirmed) return ReferenceResolution(id, ReferenceState.SIZE_UNCONFIRMED, null)
        val mapping = PlanarMapping.fromMarker(matches.single().corners, settings.markerSideCm)
        return ReferenceResolution(id, if (mapping == null) ReferenceState.DEGENERATE else ReferenceState.VALID, mapping)
    }
}

data class LocatedDetection(val detection: Detection, val position: PlanarPosition?)
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
    val selectedMarkerId: Int?,
    val referenceState: ReferenceState,
    val detections: List<LocatedDetection>,
    val analysisMs: Double,
    val modelVersion: String = "natural_hybrid_alpha_045",
) {
    fun toJson(appVersion: String): JSONObject = JSONObject().apply {
        put("schema_version", "1.0")
        put("app_version", appVersion)
        put("model_sha256", modelHash)
        put("model_version", modelVersion)
        put("frame_id", frameId)
        put("captured_at", capturedAt)
        put("camera_timestamp_ns", cameraTimestampNs)
        put("image", JSONObject().put("width", width).put("height", height).put("rotation_applied_degrees", rotationDegrees).put("coordinates", "upright_analysis_pixels"))
        put("confidence_threshold", settings.confidence)
        put("analysis_ms", analysisMs)
        put("reference", JSONObject().apply {
            put("dictionary", "DICT_4X4_50")
            put("selected_id", selectedMarkerId ?: JSONObject.NULL)
            put("side_cm", settings.markerSideCm)
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
        put("detections", JSONArray().apply { detections.forEach { located ->
            val detection = located.detection
            put(JSONObject().apply {
                put("class_id", detection.classId); put("class_name", "calyx")
                put("confidence", detection.confidence)
                put("box_xyxy_px", JSONArray(listOf(detection.box.left, detection.box.top, detection.box.right, detection.box.bottom)))
                put("center_px", JSONArray(listOf(detection.box.center.x, detection.box.center.y)))
                put("position_cm", located.position?.let { JSONObject().put("x", it.xCm).put("y", it.yCm).put("distance", it.distanceCm) } ?: JSONObject.NULL)
                put("position_status", if (located.position != null) "estimated" else "unavailable")
            })
        } })
    }
}
