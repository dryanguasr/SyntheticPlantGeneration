package org.uchuva.aruco

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import android.content.Context
import android.graphics.Bitmap
import org.json.JSONObject
import org.opencv.android.OpenCVLoader
import org.opencv.android.Utils
import org.opencv.core.Core
import org.opencv.core.Mat
import org.opencv.core.Scalar
import org.opencv.core.Size
import org.opencv.imgproc.Imgproc
import org.opencv.objdetect.ArucoDetector
import org.opencv.objdetect.DetectorParameters
import org.opencv.objdetect.Objdetect
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest

/** Single-thread owned engine. No networking, training, tracking or extra NMS. */
class VisionEngine(context: Context) : AutoCloseable {
    private val environment = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val inputName: String
    val modelHash: String
    val modelVersion: String
    private val aruco: ArucoDetector
    private val pixels = ByteArray(640 * 640 * 3)
    private val inputBuffer = ByteBuffer.allocateDirect(640 * 640 * 3 * 4).order(ByteOrder.nativeOrder()).asFloatBuffer()

    init {
        check(OpenCVLoader.initLocal()) { "No se pudo cargar OpenCV" }
        val manifest = JSONObject(context.assets.open("model_manifest.json").bufferedReader().use { it.readText() })
        modelVersion = manifest.getString("model_version")
        modelHash = manifest.getString("model_sha256")
        check(modelHash.matches(Regex("[0-9a-f]{64}"))) { "Hash de modelo inválido" }
        // Stream the asset to a private cache: avoid two full Java-heap copies of the model.
        val modelFile = File(context.codeCacheDir, "detector-$modelHash.onnx")
        if (!modelFile.isFile || digest(modelFile) != modelHash) {
            val partial = File(context.codeCacheDir, "detector-$modelHash.part")
            context.assets.open("detector.onnx").use { source -> partial.outputStream().use { source.copyTo(it, 65536) } }
            check(digest(partial) == modelHash) { "El modelo no coincide con su manifiesto" }
            check(partial.renameTo(modelFile)) { "No se pudo preparar el modelo local" }
        }
        check(manifest.getBoolean("end2end") && !manifest.getBoolean("additional_nms"))
        check(manifest.getJSONObject("classes").length() == 1 && manifest.getJSONObject("classes").getString("0") == "calyx")
        inputName = manifest.getString("input_name")
        session = OrtSession.SessionOptions().use { options ->
            options.setIntraOpNumThreads(minOf(4, Runtime.getRuntime().availableProcessors()))
            options.setInterOpNumThreads(1)
            environment.createSession(modelFile.absolutePath, options)
        }
        check((session.inputInfo[inputName]?.info as? TensorInfo)?.shape?.contentEquals(longArrayOf(1, 3, 640, 640)) == true)
        val parameters = DetectorParameters().apply { set_cornerRefinementMethod(Objdetect.CORNER_REFINE_SUBPIX) }
        aruco = ArucoDetector(Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50), parameters)
    }

    fun analyze(bitmap: Bitmap, confidence: Float): Pair<List<Detection>, List<MarkerObservation>> {
        val rgba = Mat(); val rgb = Mat(); val gray = Mat(); val resized = Mat(); val padded = Mat()
        val corners = ArrayList<Mat>(); val rejected = ArrayList<Mat>(); val ids = Mat()
        try {
            Utils.bitmapToMat(bitmap, rgba)
            Imgproc.cvtColor(rgba, gray, Imgproc.COLOR_RGBA2GRAY)
            aruco.detectMarkers(gray, corners, ids, rejected)
            val markers = corners.indices.map { i ->
                MarkerObservation(ids.get(i, 0)[0].toInt(), (0..3).map { j ->
                    val p = corners[i].get(0, j); Point2(p[0], p[1])
                })
            }
            Imgproc.cvtColor(rgba, rgb, Imgproc.COLOR_RGBA2RGB)
            val transform = Letterbox(bitmap.width, bitmap.height)
            Imgproc.resize(rgb, resized, Size(transform.resizedWidth.toDouble(), transform.resizedHeight.toDouble()), 0.0, 0.0, Imgproc.INTER_LINEAR)
            Core.copyMakeBorder(resized, padded, transform.top, 640 - transform.resizedHeight - transform.top,
                transform.left, 640 - transform.resizedWidth - transform.left, Core.BORDER_CONSTANT, Scalar(114.0, 114.0, 114.0))
            padded.get(0, 0, pixels)
            val planeSize = 640 * 640
            for (i in 0 until planeSize) for (channel in 0..2) {
                inputBuffer.put(channel * planeSize + i, (pixels[i * 3 + channel].toInt() and 255) / 255.0f)
            }
            inputBuffer.rewind()
            val detections = OnnxTensor.createTensor(environment, inputBuffer, longArrayOf(1, 3, 640, 640)).use { tensor ->
                session.run(mapOf(inputName to tensor)).use { output ->
                    val result = output[0] as OnnxTensor
                    val shape = result.info.shape
                    check(shape.size == 3 && shape[0] == 1L && shape[2] == 6L) { "Formato de salida del modelo incompatible" }
                    val buffer = result.floatBuffer
                    buildList {
                        repeat(shape[1].toInt()) {
                            val x1 = buffer.get(); val y1 = buffer.get(); val x2 = buffer.get(); val y2 = buffer.get()
                            val score = buffer.get(); val classId = buffer.get()
                            if (score.isFinite() && score >= confidence && classId == 0.0f &&
                                listOf(x1, y1, x2, y2).all { it.isFinite() }) {
                                val box = transform.restore(Box(x1.toDouble(), y1.toDouble(), x2.toDouble(), y2.toDouble()))
                                if (box.right > box.left && box.bottom > box.top) add(Detection(box, score))
                            }
                        }
                    }
                }
            }
            return detections to markers
        } finally {
            listOf(rgba, rgb, gray, resized, padded, ids).forEach { it.release() }
            corners.forEach { it.release() }; rejected.forEach { it.release() }
        }
    }

    override fun close() { session.close() }

    private fun digest(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { stream ->
            val buffer = ByteArray(65536)
            while (true) {
                val count = stream.read(buffer)
                if (count == -1) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
