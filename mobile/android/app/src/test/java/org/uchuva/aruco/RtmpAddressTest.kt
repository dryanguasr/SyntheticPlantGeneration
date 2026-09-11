package org.uchuva.aruco

import org.junit.Assert.*
import org.junit.Test

class RtmpAddressTest {
    @Test fun acceptsServerWithStreamPath() {
        assertTrue(validRtmpAddress("rtmp://192.168.1.20:1935/neo"))
        assertTrue(validRtmpAddress("rtmp://localhost/live/key"))
    }
    @Test fun rejectsMissingStreamAndWrongProtocol() {
        listOf("rtmp://host", "https://youtube.com/watch", "rtmp://", "not a url", "rtmp://host:99999/neo").forEach {
            assertFalse(it, validRtmpAddress(it))
        }
    }
}
