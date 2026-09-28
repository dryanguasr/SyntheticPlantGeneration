package org.uchuva.aruco

import android.Manifest
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Matrix
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.net.Uri
import android.text.InputType
import android.util.Size
import android.view.Surface
import android.view.View
import android.view.TextureView
import android.widget.FrameLayout
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import java.time.Instant
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private lateinit var analysisView: AnalysisView
    private lateinit var status: TextView
    private lateinit var referenceStatus: TextView
    private lateinit var captureButton: Button
    private lateinit var permissionButton: Button
    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val fileExecutor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private var engine: VisionEngine? = null // Created/closed on analysisExecutor.
    private var engineReady = false
    private var provider: ProcessCameraProvider? = null
    @Volatile private var generation = 0
    @Volatile private var revision = 0
    @Volatile private var selectedId: Int? = null
    @Volatile private var settings = AnalysisSettings()
    private var frameId = 0L
    private var lastFrameAt = 0L
    private var saving = false
    private var sizePromptShown = false
    private lateinit var streamTexture: TextureView
    private var rtmp: RtmpFrames? = null
    private var streamAddress: String? = null
    @Volatile private var streamBusy = false
    private val permission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startCamera() else unavailable("Permite el acceso a la cámara para analizar la escena.")
        permissionButton.visibility = if (granted) View.GONE else View.VISIBLE
    }
    private val freshnessCheck = object : Runnable {
        override fun run() {
            if (analysisView.snapshot != null && SystemClock.elapsedRealtime() - lastFrameAt > 1500) {
                unavailable("Esperando un fotograma actualizado…")
            }
            handler.postDelayed(this, 500)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        streamAddress = savedInstanceState?.getString("stream_address")
        selectedId = savedInstanceState?.takeIf { it.containsKey("selected_id") }?.getInt("selected_id")
        val preferences = getSharedPreferences("analysis", MODE_PRIVATE)
        settings = AnalysisSettings(preferences.getFloat("side", 10f).toDouble(), preferences.getFloat("confidence", 0.25f), preferences.getBoolean("confirmed", false),
            preferences.getString("dictionary", "DICT_4X4_50") ?: "DICT_4X4_50")
        createLayout()
        analysisView.onMarkerTapped = { id ->
            selectedId = id; revision++
            analysisView.snapshot = null; captureButton.isEnabled = false
            referenceStatus.text = "Referencia ArUco $id · esperando nuevo cuadro"
        }
        status.text = "Preparando detector…"
        analysisExecutor.execute {
            try {
                engine = VisionEngine(applicationContext)
                runOnUiThread { if (!isDestroyed) { engineReady = true; startSource() } }
            } catch (error: Exception) {
                runOnUiThread { if (!isDestroyed) unavailable(error.message ?: "No se pudo cargar el modelo") }
            }
        }
        if (streamAddress == null && !hasCameraPermission()) permission.launch(Manifest.permission.CAMERA)
    }

    override fun onStart() {
        super.onStart()
        handler.post(freshnessCheck)
        permissionButton.visibility = if (hasCameraPermission()) View.GONE else View.VISIBLE
        if (!hasCameraPermission()) unavailable("Permite el acceso a la cámara para analizar la escena.")
        // LifecycleRegistry reaches STARTED after onStart returns. Bind on the next UI turn.
        handler.post { if (engineReady) startSource() }
    }

    override fun onStop() {
        generation++
        rtmp?.close(); rtmp = null
        provider?.unbindAll()
        handler.removeCallbacks(freshnessCheck)
        analysisView.snapshot = null
        captureButton.isEnabled = false
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        selectedId?.let { outState.putInt("selected_id", it) }
        streamAddress?.let { outState.putString("stream_address", it) }
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        analysisExecutor.execute { engine?.close(); engine = null }
        analysisExecutor.shutdown()
        fileExecutor.shutdown()
        super.onDestroy()
    }

    private fun hasCameraPermission() = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun startSource() {
        if (streamAddress == null) startCamera() else startStream()
    }

    private fun chooseSource() {
        AlertDialog.Builder(this).setTitle("Fuente de video")
            .setItems(arrayOf("Cámara del celular", "RTMP del dron / reconectar")) { _, index ->
                if (index == 0) {
                    streamAddress = null; rtmp?.close(); rtmp = null
                    generation++; unavailable("Abriendo cámara…")
                    if (hasCameraPermission()) startCamera() else permission.launch(Manifest.permission.CAMERA)
                } else {
                    val input = EditText(this).apply {
                        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                        hint = "rtmp://192.168.1.10:1935/neo"
                        setText(streamAddress ?: "")
                    }
                    val dialog = AlertDialog.Builder(this).setTitle("Recibir RTMP")
                        .setMessage("Publica desde DJI Fly al servidor del PC e introduce aquí la misma dirección. Mantén DJI Fly abierto en el teléfono emisor; usa otro Android como receptor.")
                        .setView(input).setNegativeButton("Cancelar", null).setPositiveButton("Conectar", null).create()
                    dialog.setOnShowListener {
                        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                            val address = input.text.toString().trim()
                            if (!validRtmpAddress(address)) { input.error = "Usa rtmp://servidor:1935/ruta"; return@setOnClickListener }
                            streamAddress = address; dialog.dismiss(); startStream()
                        }
                    }
                    dialog.show()
                }
            }.show()
    }

    private fun startStream() {
        if (!engineReady || !lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return
        val address = streamAddress ?: return
        generation++; val streamGeneration = generation
        provider?.unbindAll(); rtmp?.close()
        unavailable("Conectando al servidor RTMP…")
        permissionButton.visibility = View.GONE
        rtmp = RtmpFrames(this, streamTexture, { !streamBusy }, { bitmap, timestamp ->
            val receivedAt = Instant.now().toString()
            val receivedMonotonic = SystemClock.elapsedRealtime()
            val frameRevision = revision; val frameSettings = settings; val frameSelected = selectedId
            streamBusy = true
            analysisExecutor.execute {
                try {
                    if (streamGeneration != generation) { bitmap.recycle(); return@execute }
                    val start = SystemClock.elapsedRealtimeNanos()
                    val detector = checkNotNull(engine)
                    val (detections, markers) = detector.analyze(bitmap, frameSettings.confidence, frameSettings.dictionary)
                    val refs = ReferenceResolver.resolveAll(markers, frameSelected, frameSettings)
                    val selected = ReferenceResolver.resolve(markers, frameSelected, frameSettings)
                    val result = FrameAnalysis(++frameId, receivedAt, timestamp, bitmap.width, bitmap.height, 0,
                        detector.modelHash, frameSettings, markers, refs.references, selected.selectedId, selected.state,
                        detections.map { locateDetection(it, refs.references, frameSettings.markerSideCm) },
                        (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0, detector.modelVersion,
                        sourceKind = "rtmp", receivedAt = receivedAt)
                    runOnUiThread {
                        if (!isDestroyed && streamGeneration == generation && frameRevision == revision &&
                            SystemClock.elapsedRealtime() - receivedMonotonic <= 1500) {
                            if (selectedId == null) selectedId = selected.selectedId
                            showFrame(FrameSnapshot(bitmap, result))
                            lastFrameAt = receivedMonotonic
                        } else bitmap.recycle()
                    }
                } catch (_: Exception) {
                    bitmap.recycle()
                    runOnUiThread { if (!isDestroyed && streamGeneration == generation) unavailable("No se pudo analizar el fotograma RTMP") }
                } finally { streamBusy = false }
            }
        }, { message -> if (streamGeneration == generation) unavailable(message) }).also { it.connect(address) }
    }

    private fun startCamera() {
        if (streamAddress != null) return
        if (!engineReady || !hasCameraPermission() || !lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return
        generation++
        val cameraGeneration = generation
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            if (isDestroyed || cameraGeneration != generation || !lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return@addListener
            try {
                val cameraProvider = future.get()
                provider = cameraProvider
                cameraProvider.unbindAll()
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .setTargetRotation(analysisView.display?.rotation ?: Surface.ROTATION_0)
                    .setResolutionSelector(ResolutionSelector.Builder().setResolutionStrategy(
                        ResolutionStrategy(Size(1280, 720), ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER)).build())
                    .build()
                analysis.setAnalyzer(analysisExecutor) { image ->
                    val start = SystemClock.elapsedRealtimeNanos()
                    val frameRevision = revision
                    val frameSettings = settings
                    val frameSelectedId = selectedId
                    try {
                        if (cameraGeneration == generation) {
                            val capturedAt = Instant.now().toString()
                            val timestampNs = image.imageInfo.timestamp
                            val rotation = image.imageInfo.rotationDegrees
                            val original = image.toBitmap()
                            val crop = image.cropRect
                            val matrix = Matrix().apply { postRotate(rotation.toFloat()) }
                            val upright = Bitmap.createBitmap(original, crop.left, crop.top, crop.width(), crop.height(), matrix, false)
                            if (upright !== original) original.recycle()
                            val (detections, markers) = checkNotNull(engine).analyze(upright, frameSettings.confidence, frameSettings.dictionary)
                            val referenceSet = ReferenceResolver.resolveAll(markers, frameSelectedId, frameSettings)
                            val reference = ReferenceResolver.resolve(markers, frameSelectedId, frameSettings)
                            val result = FrameAnalysis(++frameId, capturedAt, timestampNs, upright.width, upright.height, rotation,
                                checkNotNull(engine).modelHash, frameSettings, markers, referenceSet.references, reference.selectedId, reference.state,
                                detections.map { locateDetection(it, referenceSet.references, frameSettings.markerSideCm) },
                                (SystemClock.elapsedRealtimeNanos() - start) / 1_000_000.0,
                                modelVersion = checkNotNull(engine).modelVersion)
                            runOnUiThread {
                                if (!isDestroyed && cameraGeneration == generation && frameRevision == revision) {
                                    if (selectedId == null) selectedId = reference.selectedId
                                    showFrame(FrameSnapshot(upright, result))
                                }
                            }
                        }
                    } catch (error: Exception) {
                        runOnUiThread {
                            if (!isDestroyed && cameraGeneration == generation && frameRevision == revision) unavailable(error.message ?: "Error de análisis")
                        }
                    } finally { image.close() }
                }
                cameraProvider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, analysis)
                status.text = "Analizando cámara…"
                permissionButton.visibility = View.GONE
            } catch (error: Exception) {
                unavailable(error.message ?: "No se pudo abrir la cámara trasera")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun showFrame(snapshot: FrameSnapshot) {
        if (!settings.sizeConfirmed && !sizePromptShown && snapshot.analysis.markers.isNotEmpty()) {
            sizePromptShown = true
            editSettings()
        }
        lastFrameAt = SystemClock.elapsedRealtime()
        analysisView.snapshot = snapshot
        val result = snapshot.analysis
        val count = result.detections.size
        status.text = (if (count == 0) "Sin detecciones" else "Capachos detectados: $count") +
            String.format(Locale.US, " · %.0f ms", result.analysisMs) + if (result.sourceKind == "rtmp") " · RTMP" else " · Cámara"
        val valid = result.references.count { it.state == ReferenceState.VALID }
        val ambiguous = result.references.count { it.state == ReferenceState.AMBIGUOUS }
        referenceStatus.text = when {
            result.markers.isEmpty() -> if (result.selectedMarkerId == null) "Sin marcador de referencia" else
                "Sin marcador · ArUco seleccionado ${result.selectedMarkerId} ausente"
            !result.settings.sizeConfirmed -> "ArUcos detectados: ${result.markers.size} · confirma el lado para mostrar centímetros"
            valid > 0 -> buildString {
                append("ArUcos detectados: ${result.markers.size} · referencias métricas: $valid · X derecha / Y arriba")
                if (result.referenceState == ReferenceState.MISSING) append(" · seleccionado ${result.selectedMarkerId} ausente")
                if (ambiguous > 0) append(" · $ambiguous con ID duplicado")
            }
            ambiguous > 0 -> "IDs duplicados · coordenadas no disponibles"
            else -> "Acerca o endereza los marcadores · coordenadas no disponibles"
        }
        captureButton.isEnabled = !saving
    }

    private fun unavailable(reason: String) {
        analysisView.snapshot = null
        captureButton.isEnabled = false
        status.text = "Análisis no disponible"
        referenceStatus.text = reason
    }

    private fun createLayout() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.rgb(16, 27, 21)) }
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom); insets
        }
        fun text(value: String, size: Float, color: Int = Color.WHITE) = TextView(this).apply {
            this.text = value; textSize = size; setTextColor(color); setPadding(dp(16), dp(5), dp(16), dp(5))
        }
        root.addView(text("UCHUVA  /  ArUco", 22f, Color.rgb(181, 236, 115)))
        status = text("Preparando detector…", 16f); root.addView(status)
        referenceStatus = text("", 13f); root.addView(referenceStatus)
        analysisView = AnalysisView(this)
        val frame = FrameLayout(this)
        streamTexture = TextureView(this)
        frame.addView(streamTexture, FrameLayout.LayoutParams(-1, -1))
        frame.addView(analysisView, FrameLayout.LayoutParams(-1, -1))
        root.addView(frame, LinearLayout.LayoutParams(-1, 0, 1f))
        root.addView(Button(this).apply { this.text = "Fuente: cámara / RTMP"; setOnClickListener { chooseSource() } })
        root.addView(text(ESTIMATION_LABEL, 13f, Color.rgb(181, 236, 115)))
        root.addView(text("Las distintas profundidades cambian las medidas. Sin corrección de lente.", 11f))
        permissionButton = Button(this).apply {
            this.text = "Permitir cámara"; visibility = if (hasCameraPermission()) View.GONE else View.VISIBLE
            setOnClickListener {
                if (shouldShowRequestPermissionRationale(Manifest.permission.CAMERA)) permission.launch(Manifest.permission.CAMERA)
                else startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
            }
        }
        root.addView(permissionButton)
        val buttons = LinearLayout(this)
        captureButton = Button(this).apply { this.text = "Capturar"; isEnabled = false; setOnClickListener { capture() } }
        buttons.addView(captureButton, LinearLayout.LayoutParams(0, -2, 1f))
        buttons.addView(Button(this).apply { this.text = "Ajustes"; setOnClickListener { editSettings() } }, LinearLayout.LayoutParams(0, -2, 1f))
        buttons.addView(Button(this).apply { this.text = "Guardadas"; setOnClickListener { showCaptures() } }, LinearLayout.LayoutParams(0, -2, 1f))
        root.addView(buttons)
        setContentView(root)
    }

    private fun editSettings() {
        val fields = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(8), dp(20), 0) }
        fun field(label: String, value: String): EditText {
            fields.addView(TextView(this).apply { text = label })
            return EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(value); fields.addView(this) }
        }
        val side = field("¿Cuánto mide el lado negro del ArUco, en cm?", if (settings.sizeConfirmed) settings.markerSideCm.toString() else "")
        val confidence = field("Confianza mínima (0.05–0.95)", settings.confidence.toString())
        val dictionary = android.widget.CheckBox(this).apply {
            text = "DICT_4X4_100 (piloto); desmarcado: DICT_4X4_50"
            isChecked = settings.dictionary == "DICT_4X4_100"
            fields.addView(this)
        }
        fields.addView(TextView(this).apply { text = "Mide el cuadrado negro, sin el margen blanco. La escala configurada se aplica a todos los marcadores visibles." })
        val dialog = AlertDialog.Builder(this).setTitle("Medida del ArUco").setView(fields)
            .setNegativeButton("Cancelar", null).setPositiveButton("Confirmar medida", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val cm = side.text.toString().replace(',', '.').toDoubleOrNull()
                val threshold = confidence.text.toString().replace(',', '.').toFloatOrNull()
                if (cm == null || !cm.isFinite() || cm !in 0.1..1000.0) { side.error = "Introduce un lado válido (0.1–1000 cm)"; return@setOnClickListener }
                if (threshold == null || !threshold.isFinite() || threshold !in 0.05f..0.95f) { confidence.error = "Usa un valor entre 0.05 y 0.95"; return@setOnClickListener }
                settings = AnalysisSettings(cm, threshold, true, if (dictionary.isChecked) "DICT_4X4_100" else "DICT_4X4_50"); revision++
                selectedId = null
                getSharedPreferences("analysis", MODE_PRIVATE).edit().putFloat("side", cm.toFloat()).putFloat("confidence", threshold).putBoolean("confirmed", true)
                    .putString("dictionary", settings.dictionary).apply()
                analysisView.snapshot = null; captureButton.isEnabled = false
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun capture() {
        val snapshot = analysisView.snapshot ?: return
        if (SystemClock.elapsedRealtime() - lastFrameAt > 1500 || saving) return
        saving = true; captureButton.isEnabled = false
        fileExecutor.execute {
            try {
                val saved = CaptureStore.save(applicationContext, snapshot)
                runOnUiThread { if (!isDestroyed) {
                    saving = false; captureButton.isEnabled = analysisView.snapshot != null
                    AlertDialog.Builder(this).setTitle("Captura guardada")
                        .setMessage("${saved.imageName}\nGalería · UchuvaArUco\n\n${saved.jsonName}\nDescargas · UchuvaArUco")
                        .setNegativeButton("Cerrar", null)
                        .setNeutralButton("Abrir imagen") { _, _ -> openSaved(saved.image, "image/jpeg") }
                        .setPositiveButton("Compartir") { _, _ -> CaptureStore.share(this, saved) }.show()
                } }
            } catch (error: Exception) {
                runOnUiThread { if (!isDestroyed) {
                    saving = false; captureButton.isEnabled = analysisView.snapshot != null
                    Toast.makeText(this, "No se pudo guardar: ${error.message}", Toast.LENGTH_LONG).show()
                } }
            }
        }
    }

    private fun showCaptures() {
        val captures = CaptureStore.list(this)
        if (captures.isEmpty()) { Toast.makeText(this, "Todavía no hay capturas", Toast.LENGTH_SHORT).show(); return }
        val builder = AlertDialog.Builder(this).setTitle("Capturas guardadas")
            .setItems(captures.map { it.captureId + if (it.isLegacy) " · privada anterior" else " · Galería + Descargas" }.toTypedArray()) { _, index ->
                showCaptureActions(captures[index])
            }.setNegativeButton("Cerrar", null)
        if (captures.any { it.isLegacy }) builder.setPositiveButton("Exportar anteriores") { _, _ -> exportLegacyCaptures() }
        builder.show()
    }

    private fun showCaptureActions(saved: SavedCapture) {
        AlertDialog.Builder(this).setTitle(saved.captureId)
            .setItems(arrayOf("Abrir imagen", "Abrir JSON", "Compartir imagen + JSON")) { _, action ->
                when (action) {
                    0 -> openSaved(saved.image, "image/jpeg")
                    1 -> openSaved(saved.json, "application/json")
                    else -> CaptureStore.share(this, saved)
                }
            }.setNegativeButton("Cerrar", null).show()
    }

    private fun openSaved(uri: Uri, mimeType: String) {
        runCatching { CaptureStore.open(this, uri, mimeType) }
            .onFailure { Toast.makeText(this, "No hay una aplicación disponible para abrir este archivo", Toast.LENGTH_LONG).show() }
    }

    private fun exportLegacyCaptures() {
        fileExecutor.execute {
            runCatching { CaptureStore.exportLegacy(applicationContext) }
                .onSuccess { exported -> runOnUiThread {
                    Toast.makeText(this, "Capturas anteriores exportadas: ${exported.size}", Toast.LENGTH_LONG).show()
                } }.onFailure { error -> runOnUiThread {
                    Toast.makeText(this, "No se pudieron exportar: ${error.message}", Toast.LENGTH_LONG).show()
                } }
        }
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
