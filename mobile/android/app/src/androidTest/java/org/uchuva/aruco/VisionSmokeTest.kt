package org.uchuva.aruco

import android.graphics.Bitmap
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
    @Test fun realNativeLibrariesDecodeMarkerAndSaveMatchingFrame() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertTrue(OpenCVLoader.initLocal())
        val marker = Mat(); val scene = Mat(640, 640, CvType.CV_8UC1, Scalar(255.0))
        try {
            Objdetect.generateImageMarker(Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50), 0, 240, marker)
            val region = scene.submat(Rect(200, 200, 240, 240))
            try { marker.copyTo(region) } finally { region.release() }
            val bitmap = Bitmap.createBitmap(640, 640, Bitmap.Config.ARGB_8888)
            Utils.matToBitmap(scene, bitmap)
            VisionEngine(context).use { engine ->
                val (_, markers) = engine.analyze(bitmap, 0.95f)
                assertEquals(listOf(0), markers.map { it.id })
                val settings = AnalysisSettings(10.0, 0.95f, true)
                val ref = ReferenceResolver.resolve(markers, null, settings)
                assertEquals(ReferenceState.VALID, ref.state)
                val result = FrameAnalysis(42, "2026-09-02T12:00:00Z", 123L, 640, 640, 0,
                    engine.modelHash, settings, markers, ref.selectedId, ref.state, emptyList(), 10.0)
                val saved = CaptureStore.save(context, FrameSnapshot(bitmap, result))
                try {
                    val json = org.json.JSONObject(saved.json.readText())
                    assertEquals(42L, json.getLong("frame_id"))
                    assertEquals(640, json.getJSONObject("image").getInt("width"))
                    assertTrue(saved.image.length() > 0)
                    val hash = java.security.MessageDigest.getInstance("SHA-256").digest(saved.image.readBytes()).joinToString("") { "%02x".format(it) }
                    assertEquals(hash, json.getString("image_sha256"))
                } finally { saved.image.delete(); saved.json.delete(); saved.directory.delete() }
            }
            bitmap.recycle()
        } finally { marker.release(); scene.release() }
    }
}
