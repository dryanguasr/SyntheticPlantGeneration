package org.uchuva.aruco

import android.Manifest
import android.view.View
import android.view.ViewGroup
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CameraLifecycleTest {
    private fun analysisView(view: View): AnalysisView? {
        if (view is AnalysisView) return view
        if (view is ViewGroup) for (i in 0 until view.childCount) analysisView(view.getChildAt(i))?.let { return it }
        return null
    }

    private fun awaitFrame(scenario: ActivityScenario<MainActivity>): FrameSnapshot {
        val deadline = System.nanoTime() + 60_000_000_000L
        while (System.nanoTime() < deadline) {
            var frame: FrameSnapshot? = null
            scenario.onActivity { frame = analysisView(it.window.decorView)?.snapshot }
            frame?.let { return it }
            Thread.sleep(100)
        }
        throw AssertionError("Camera did not deliver an analyzed frame in 60 seconds")
    }

    @Test fun cameraResumesAndRecreatesWithoutOldFrames() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.grantRuntimePermission(instrumentation.targetContext.packageName, Manifest.permission.CAMERA)
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            val first = awaitFrame(scenario)
            assertTrue(first.bitmap.width > 0 && first.bitmap.height > 0)
            assertEquals(first.bitmap.width, first.analysis.width)
            scenario.moveToState(Lifecycle.State.CREATED)
            scenario.onActivity { assertNull(analysisView(it.window.decorView)?.snapshot) }
            scenario.moveToState(Lifecycle.State.RESUMED)
            val resumed = awaitFrame(scenario)
            assertTrue(resumed.analysis.cameraTimestampNs > first.analysis.cameraTimestampNs)
            scenario.recreate()
            val recreated = awaitFrame(scenario)
            assertTrue(recreated.analysis.cameraTimestampNs > resumed.analysis.cameraTimestampNs)
        }
    }
}
