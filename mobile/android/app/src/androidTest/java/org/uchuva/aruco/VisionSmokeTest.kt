package org.uchuva.aruco

import android.graphics.Bitmap
import android.provider.MediaStore
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.opencv.android.OpenCVLoader
import org.opencv.android.Utils
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Rect
import org.opencv.core.Scalar
import org.opencv.objdetect.Objdetect

@RunWith(AndroidJUnit4::class)
class VisionSmokeTest {
    @Test fun realNativeLibrariesDecodeMarkersAndPublishMatchingMediaStorePair() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertTrue(OpenCVLoader.initLocal())
        val marker0 = Mat(); val marker1 = Mat(); val scene = Mat(640, 640, CvType.CV_8UC1, Scalar(255.0))
        try {
            val dictionary = Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50)
            Objdetect.generateImageMarker(dictionary, 0, 180, marker0)
            Objdetect.generateImageMarker(dictionary, 1, 180, marker1)
            val region0 = scene.submat(Rect(50, 230, 180, 180))
            val region1 = scene.submat(Rect(410, 230, 180, 180))
            try { marker0.copyTo(region0); marker1.copyTo(region1) } finally { region0.release(); region1.release() }
            val bitmap = Bitmap.createBitmap(640, 640, Bitmap.Config.ARGB_8888)
            Utils.matToBitmap(scene, bitmap)
            VisionEngine(context).use { engine ->
                val (_, markers) = engine.analyze(bitmap, 0.95f)
                assertEquals(listOf(0, 1), markers.map { it.id }.sorted())
                val settings = AnalysisSettings(10.0, 0.95f, true)
                val all = ReferenceResolver.resolveAll(markers, 0, settings)
                val ref = ReferenceResolver.resolve(markers, 0, settings)
                assertEquals(ReferenceState.VALID, ref.state)
                val detection = Detection(Box(300.0, 300.0, 340.0, 340.0), 0.9f)
                val located = LocatedDetection(detection, all.references.map { reference ->
                    MarkerPosition(reference.observationIndex, reference.marker.id, reference.state,
                        reference.mapping.takeIf { reference.state == ReferenceState.VALID }?.project(detection.box.center))
                })
                val result = FrameAnalysis(42, "2026-09-02T12:00:00Z", 123L, 640, 640, 0,
                    engine.modelHash, settings, markers, all.references, ref.selectedId, ref.state, listOf(located), 10.0)
                val snapshot = FrameSnapshot(bitmap, result)
                val expectedId = "20260902_120000_000_f42"
                CaptureStore.list(context).filter { it.captureId == expectedId }.forEach { CaptureStore.delete(context, it) }
                assertThrows(IllegalStateException::class.java) { CaptureStore.saveForRollbackTest(context, snapshot) }
                assertFalse(CaptureStore.list(context).any { it.captureId == expectedId })
                val saved = CaptureStore.save(context, snapshot)
                try {
                    val imageBytes = context.contentResolver.openInputStream(saved.image)!!.use { it.readBytes() }
                    val json = context.contentResolver.openInputStream(saved.json)!!.bufferedReader().use { org.json.JSONObject(it.readText()) }
                    assertEquals(42L, json.getLong("frame_id"))
                    assertEquals(640, json.getJSONObject("image").getInt("width"))
                    assertEquals("1.4", json.getString("schema_version"))
                    assertEquals(2, json.getJSONArray("references").length())
                    assertEquals(2, json.getJSONArray("detections").getJSONObject(0).getJSONArray("positions_by_marker").length())
                    assertEquals(saved.captureId, json.getString("capture_id"))
                    assertEquals(CaptureStore.IMAGE_RELATIVE_PATH, json.getJSONObject("storage").getString("image_relative_path"))
                    assertEquals(CaptureStore.JSON_RELATIVE_PATH, json.getJSONObject("storage").getString("json_relative_path"))
                    assertTrue(imageBytes.isNotEmpty())
                    val hash = java.security.MessageDigest.getInstance("SHA-256").digest(imageBytes).joinToString("") { "%02x".format(it) }
                    assertEquals(hash, json.getString("image_sha256"))
                    assertTrue(CaptureStore.list(context).any { it.captureId == saved.captureId && !it.isLegacy })
                    assertPublished(context, saved.image)
                    assertPublished(context, saved.json)
                } finally { CaptureStore.delete(context, saved) }
            }
            bitmap.recycle()
        } finally { marker0.release(); marker1.release(); scene.release() }
    }

    private fun assertPublished(context: android.content.Context, uri: android.net.Uri) {
        context.contentResolver.query(uri, arrayOf(MediaStore.MediaColumns.IS_PENDING), null, null, null)!!.use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals(0, cursor.getInt(0))
        }
    }
}
