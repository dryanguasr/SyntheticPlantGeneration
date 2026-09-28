package org.uchuva.aruco

import org.junit.Assert.assertEquals
import org.junit.Test

class DictionarySettingsTest {
    @Test fun historicalDefaultAndPilotSelection() {
        assertEquals("DICT_4X4_50", AnalysisSettings().dictionary)
        assertEquals("DICT_4X4_100", AnalysisSettings(dictionary = "DICT_4X4_100").dictionary)
    }
    @Test(expected = IllegalArgumentException::class)
    fun invalidDictionaryIsRejected() { AnalysisSettings(dictionary = "unknown") }
}
