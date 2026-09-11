package org.uchuva.aruco

import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.net.Uri
import android.provider.MediaStore
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

data class SavedCapture(
    val captureId: String,
    val image: Uri,
    val json: Uri,
    val imageName: String,
    val jsonName: String,
    val legacyDirectory: File? = null,
) {
    val isLegacy get() = legacyDirectory != null
}

object CaptureStore {
    const val IMAGE_RELATIVE_PATH = "Pictures/UchuvaArUco"
    const val JSON_RELATIVE_PATH = "Download/UchuvaArUco"
    private const val PREFIX = "uchuva_"
    private val filenameTime = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss_SSS").withZone(ZoneOffset.UTC)

    fun save(context: Context, snapshot: FrameSnapshot): SavedCapture {
        return saveSnapshot(context, snapshot, false)
    }

    internal fun saveForRollbackTest(context: Context, snapshot: FrameSnapshot): SavedCapture {
        return saveSnapshot(context, snapshot, true)
    }

    private fun saveSnapshot(context: Context, snapshot: FrameSnapshot, failAfterImageWrite: Boolean): SavedCapture {
        val annotated = Bitmap.createBitmap(snapshot.bitmap.width, snapshot.bitmap.height, Bitmap.Config.ARGB_8888)
        val jpeg = try {
            FrameRenderer().draw(Canvas(annotated), snapshot)
            ByteArrayOutputStream().use { output ->
                check(annotated.compress(Bitmap.CompressFormat.JPEG, 95, output))
                output.toByteArray()
            }
        } finally { annotated.recycle() }
        val instant = runCatching { Instant.parse(snapshot.analysis.capturedAt) }.getOrElse { Instant.now() }
        val captureId = "${filenameTime.format(instant)}_f${snapshot.analysis.frameId}"
        return publish(context, captureId, jpeg, snapshot.analysis.toJson(BuildConfig.VERSION_NAME), failAfterImageWrite)
    }

    fun list(context: Context): List<SavedCapture> = (listPublic(context) + listLegacy(context))
        .sortedByDescending { it.captureId }

    fun listLegacy(context: Context): List<SavedCapture> {
        return File(context.filesDir, "captures").listFiles().orEmpty()
            .filter { !it.name.startsWith(".") && File(it, "capture.jpg").isFile && File(it, "analysis.json").isFile }
            .sortedByDescending { it.name }
            .map { directory ->
                SavedCapture(
                    directory.name,
                    FileProvider.getUriForFile(context, "${context.packageName}.files", File(directory, "capture.jpg")),
                    FileProvider.getUriForFile(context, "${context.packageName}.files", File(directory, "analysis.json")),
                    "capture.jpg",
                    "analysis.json",
                    directory,
                )
            }
    }

    fun exportLegacy(context: Context): List<SavedCapture> = listLegacy(context).mapIndexed { index, saved ->
        val directory = checkNotNull(saved.legacyDirectory)
        val jpeg = File(directory, "capture.jpg").readBytes()
        val json = JSONObject(File(directory, "analysis.json").readText())
        val id = "legacy_${directory.name}_${System.currentTimeMillis()}_$index"
        publish(context, id, jpeg, json)
    }

    fun share(context: Context, saved: SavedCapture) {
        val uris = arrayListOf(saved.image, saved.json)
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

    fun open(context: Context, uri: Uri, mimeType: String) {
        context.startActivity(Intent.createChooser(Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, mimeType)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }, "Abrir archivo"))
    }

    fun delete(context: Context, saved: SavedCapture) {
        if (saved.isLegacy) {
            saved.legacyDirectory?.listFiles()?.forEach { it.delete() }
            saved.legacyDirectory?.delete()
        } else {
            context.contentResolver.delete(saved.image, null, null)
            context.contentResolver.delete(saved.json, null, null)
        }
    }

    private fun publish(
        context: Context,
        captureId: String,
        jpeg: ByteArray,
        json: JSONObject,
        failAfterImageWrite: Boolean = false,
    ): SavedCapture {
        val safeId = captureId.replace(Regex("[^A-Za-z0-9_-]"), "_")
        val imageName = "$PREFIX$safeId.jpg"
        val jsonName = "$PREFIX$safeId.json"
        val resolver = context.contentResolver
        var imageUri: Uri? = null
        var jsonUri: Uri? = null
        try {
            imageUri = resolver.insert(MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY), ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, imageName)
                put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
                put(MediaStore.MediaColumns.RELATIVE_PATH, "$IMAGE_RELATIVE_PATH/")
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }) ?: error("Android no permitió crear la imagen en Galería")
            resolver.openOutputStream(imageUri, "w")?.use { it.write(jpeg) } ?: error("No se pudo escribir la imagen")
            if (failAfterImageWrite) error("Fallo de prueba después de escribir la imagen")

            jsonUri = resolver.insert(MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY), ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, jsonName)
                put(MediaStore.MediaColumns.MIME_TYPE, "application/json")
                put(MediaStore.MediaColumns.RELATIVE_PATH, "$JSON_RELATIVE_PATH/")
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }) ?: error("Android no permitió crear el JSON en Descargas")

            val hash = MessageDigest.getInstance("SHA-256").digest(jpeg).joinToString("") { "%02x".format(it) }
            json.put("capture_id", safeId)
            json.put("image_file", imageName)
            json.put("json_file", jsonName)
            json.put("image_sha256", hash)
            json.put("storage", JSONObject()
                .put("image_collection", "gallery")
                .put("image_relative_path", IMAGE_RELATIVE_PATH)
                .put("json_collection", "downloads")
                .put("json_relative_path", JSON_RELATIVE_PATH))
            resolver.openOutputStream(jsonUri, "w")?.use { it.write(json.toString(2).toByteArray(Charsets.UTF_8)) }
                ?: error("No se pudo escribir el JSON")

            val published = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
            check(resolver.update(jsonUri, published, null, null) == 1) { "No se pudo publicar el JSON" }
            check(resolver.update(imageUri, published, null, null) == 1) { "No se pudo publicar la imagen" }
            return SavedCapture(safeId, imageUri, jsonUri, imageName, jsonName)
        } catch (error: Exception) {
            jsonUri?.let { resolver.delete(it, null, null) }
            imageUri?.let { resolver.delete(it, null, null) }
            throw error
        }
    }

    private fun listPublic(context: Context): List<SavedCapture> {
        val images = queryCollection(context, MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY), IMAGE_RELATIVE_PATH, ".jpg")
        val jsonFiles = queryCollection(context, MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY), JSON_RELATIVE_PATH, ".json")
        return images.keys.intersect(jsonFiles.keys).map { stem ->
            val image = checkNotNull(images[stem]); val json = checkNotNull(jsonFiles[stem])
            SavedCapture(stem.removePrefix(PREFIX), image.first, json.first, image.second, json.second)
        }
    }

    private fun queryCollection(context: Context, collection: Uri, relativePath: String, extension: String): Map<String, Pair<Uri, String>> {
        val result = linkedMapOf<String, Pair<Uri, String>>()
        val projection = arrayOf(MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DISPLAY_NAME)
        context.contentResolver.query(collection, projection, "${MediaStore.MediaColumns.RELATIVE_PATH} = ?",
            arrayOf("$relativePath/"), "${MediaStore.MediaColumns.DATE_ADDED} DESC")?.use { cursor ->
            val idColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns._ID)
            val nameColumn = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)
            while (cursor.moveToNext()) {
                val name = cursor.getString(nameColumn)
                if (name.startsWith(PREFIX) && name.endsWith(extension, ignoreCase = true)) {
                    val stem = name.dropLast(extension.length)
                    result.putIfAbsent(stem, ContentUris.withAppendedId(collection, cursor.getLong(idColumn)) to name)
                }
            }
        }
        return result
    }
}
