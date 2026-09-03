package org.uchuva.aruco

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.core.content.FileProvider
import java.io.File
import java.security.MessageDigest

data class SavedCapture(val directory: File, val image: File, val json: File)

object CaptureStore {
    fun save(context: Context, snapshot: FrameSnapshot): SavedCapture {
        val root = File(context.filesDir, "captures").apply { mkdirs() }
        val id = "${System.currentTimeMillis()}_${snapshot.analysis.frameId}"
        val partial = File(root, ".$id.partial").apply { check(mkdir()) }
        val completed = File(root, id)
        try {
            val image = File(partial, "capture.jpg")
            val annotated = Bitmap.createBitmap(snapshot.bitmap.width, snapshot.bitmap.height, Bitmap.Config.ARGB_8888)
            try {
                FrameRenderer().draw(Canvas(annotated), snapshot)
                image.outputStream().use { check(annotated.compress(Bitmap.CompressFormat.JPEG, 95, it)) }
            } finally { annotated.recycle() }
            val json = snapshot.analysis.toJson(BuildConfig.VERSION_NAME)
            json.put("image_file", "capture.jpg")
            json.put("image_sha256", MessageDigest.getInstance("SHA-256").digest(image.readBytes()).joinToString("") { "%02x".format(it) })
            File(partial, "analysis.json").writeText(json.toString(2))
            check(partial.renameTo(completed)) { "No se pudo finalizar la captura" }
            return SavedCapture(completed, File(completed, "capture.jpg"), File(completed, "analysis.json"))
        } catch (error: Exception) {
            partial.listFiles()?.forEach { it.delete() }; partial.delete()
            throw error
        }
    }

    fun list(context: Context): List<SavedCapture> = File(context.filesDir, "captures").listFiles().orEmpty()
        .filter { !it.name.startsWith(".") && File(it, "capture.jpg").isFile && File(it, "analysis.json").isFile }
        .sortedByDescending { it.name }
        .map { SavedCapture(it, File(it, "capture.jpg"), File(it, "analysis.json")) }

    fun share(context: Context, saved: SavedCapture) {
        val uris = arrayListOf(saved.image, saved.json).mapTo(ArrayList()) {
            FileProvider.getUriForFile(context, "${context.packageName}.files", it)
        }
        val intent = Intent(Intent.ACTION_SEND_MULTIPLE).apply {
            type = "*/*"
            putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            clipData = android.content.ClipData.newUri(context.contentResolver, "Captura de uchuva", uris[0]).apply {
                addItem(android.content.ClipData.Item(uris[1]))
            }
        }
        context.startActivity(Intent.createChooser(intent, "Compartir imagen y datos"))
    }
}
