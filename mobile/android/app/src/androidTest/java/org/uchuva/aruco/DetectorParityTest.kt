package org.uchuva.aruco

import android.graphics.BitmapFactory
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.max
import kotlin.math.min

@RunWith(AndroidJUnit4::class)
class DetectorParityTest {
    @Test fun androidPreprocessingMatchesRealValidationReference() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val fixture = JSONObject(instrumentation.context.assets.open("mobile_validation_fixture.json").bufferedReader().use { it.readText() })
        val image = instrumentation.context.assets.open("mobile_validation_fixture.png").use { BitmapFactory.decodeStream(it) }
        try {
            VisionEngine(instrumentation.targetContext).use { engine ->
                assertEquals(fixture.getString("model_sha256"), engine.modelHash)
                val actual = engine.analyze(image, 0.25f).first.toMutableList()
                val expected = fixture.getJSONArray("detections")
                assertTrue("Fixture must contain real capachos", expected.length() > 0)
                assertEquals(expected.length(), actual.size)
                for (i in 0 until expected.length()) {
                    val reference = expected.getJSONObject(i)
                    val b = reference.getJSONArray("box")
                    val box = Box(b.getDouble(0), b.getDouble(1), b.getDouble(2), b.getDouble(3))
                    val match = actual.maxBy { iou(it.box, box) }
                    assertTrue("Android box differs from reference", iou(match.box, box) >= 0.99)
                    assertEquals(reference.getDouble("confidence"), match.confidence.toDouble(), 0.001)
                    assertEquals(reference.getInt("class_id"), match.classId)
                    actual.remove(match)
                }
            }
        } finally { image.recycle() }
    }

    private fun iou(a: Box, b: Box): Double {
        val overlap = max(0.0, min(a.right, b.right) - max(a.left, b.left)) * max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))
        return overlap / ((a.right - a.left) * (a.bottom - a.top) + (b.right - b.left) * (b.bottom - b.top) - overlap)
    }
}
