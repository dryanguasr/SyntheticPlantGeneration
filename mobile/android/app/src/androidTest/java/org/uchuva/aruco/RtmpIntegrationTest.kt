package org.uchuva.aruco

import android.Manifest
import android.view.View
import android.view.ViewGroup
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Optional local integration: pass -e rtmp_url rtmp://10.0.2.2:1935/neo. */
@RunWith(AndroidJUnit4::class)
class RtmpIntegrationTest {
    private fun find(view: View): AnalysisView? {
        if (view is AnalysisView) return view
        if (view is ViewGroup) for (i in 0 until view.childCount) find(view.getChildAt(i))?.let { return it }
        return null
    }
    private fun awaitFrame(scenario: ActivityScenario<MainActivity>): FrameSnapshot {
        val deadline = System.nanoTime() + 45_000_000_000L
        while (System.nanoTime() < deadline) {
            var result: FrameSnapshot? = null
            scenario.onActivity { result = find(it.window.decorView)?.snapshot }
            result?.takeIf { it.analysis.sourceKind == "rtmp" }?.let { return it }
            Thread.sleep(100)
        }
        throw AssertionError("No analyzed RTMP frame within 45 seconds")
    }
    @Test fun streamDecodesAnalyzesSavesAndResumes() {
        val address = InstrumentationRegistry.getArguments().getString("rtmp_url")
        assumeTrue("RTMP server fixture not supplied", address != null)
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        instrumentation.uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.CAMERA)
        val prefs = context.getSharedPreferences("analysis", 0)
        val wasConfirmed = prefs.getBoolean("confirmed", false)
        prefs.edit().putBoolean("confirmed", true).commit()
        try {
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                scenario.onActivity { activity ->
                    MainActivity::class.java.getDeclaredField("streamAddress").apply { isAccessible = true }.set(activity, address)
                    MainActivity::class.java.getDeclaredMethod("startSource").apply { isAccessible = true }.invoke(activity)
                }
                val first = awaitFrame(scenario)
                assertEquals(640, first.bitmap.width)
                assertEquals(480, first.bitmap.height)
                assertTrue("Markers survive decoding and texture readback", first.analysis.markers.size >= 2)
                val saved = CaptureStore.save(context, first)
                try {
                    val json = context.contentResolver.openInputStream(saved.json)!!.bufferedReader().use { org.json.JSONObject(it.readText()) }
                    assertEquals("rtmp", json.getJSONObject("source").getString("kind"))
                    assertTrue(json.isNull("camera_timestamp_ns"))
                    assertEquals(first.analysis.frameId, json.getLong("frame_id"))
                    val bytes = context.contentResolver.openInputStream(saved.image)!!.use { it.readBytes() }
                    val digest = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
                    assertEquals(digest, json.getString("image_sha256"))
                } finally {
                    context.contentResolver.delete(saved.image, null, null)
                    context.contentResolver.delete(saved.json, null, null)
                }
                scenario.moveToState(Lifecycle.State.CREATED)
                scenario.onActivity { assertNull(find(it.window.decorView)?.snapshot) }
                scenario.moveToState(Lifecycle.State.RESUMED)
                awaitFrame(scenario)
                scenario.recreate()
                assertEquals("rtmp", awaitFrame(scenario).analysis.sourceKind)
            }
        } finally { prefs.edit().putBoolean("confirmed", wasConfirmed).commit() }
    }
}
