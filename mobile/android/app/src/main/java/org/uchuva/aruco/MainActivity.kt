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
import android.widget.Button
import android.widget.CheckBox
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
        selectedId = savedInstanceState?.takeIf { it.containsKey("selected_id") }?.getInt("selected_id")
        val preferences = getSharedPreferences("analysis", MODE_PRIVATE)
        settings = AnalysisSettings(preferences.getFloat("side", 10f).toDouble(), preferences.getFloat("confidence", 0.25f), preferences.getBoolean("confirmed", false))
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
                runOnUiThread { if (!isDestroyed) { engineReady = true; startCamera() } }
            } catch (error: Exception) {
                runOnUiThread { if (!isDestroyed) unavailable(error.message ?: "No se pudo cargar el modelo") }
            }
        }
        if (!hasCameraPermission()) permission.launch(Manifest.permission.CAMERA)
    }

    override fun onStart() {
        super.onStart()
        handler.post(freshnessCheck)
        permissionButton.visibility = if (hasCameraPermission()) View.GONE else View.VISIBLE
        if (!hasCameraPermission()) unavailable("Permite el acceso a la cámara para analizar la escena.")
        // LifecycleRegistry reaches STARTED after onStart returns. Bind on the next UI turn.
        handler.post { if (engineReady) startCamera() }
    }

    override fun onStop() {
        generation++
        provider?.unbindAll()
        handler.removeCallbacks(freshnessCheck)
        analysisView.snapshot = null
        captureButton.isEnabled = false
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        selectedId?.let { outState.putInt("selected_id", it) }
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        analysisExecutor.execute { engine?.close(); engine = null }
        analysisExecutor.shutdown()
        fileExecutor.shutdown()
        super.onDestroy()
    }

    private fun hasCameraPermission() = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun startCamera() {
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
                            val (detections, markers) = checkNotNull(engine).analyze(upright, frameSettings.confidence)
                            val reference = ReferenceResolver.resolve(markers, frameSelectedId, frameSettings)
                            val result = FrameAnalysis(++frameId, capturedAt, timestampNs, upright.width, upright.height, rotation,
                                checkNotNull(engine).modelHash, frameSettings, markers, reference.selectedId, reference.state,
                                detections.map { LocatedDetection(it, reference.mapping?.project(it.box.center)) },
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
        lastFrameAt = SystemClock.elapsedRealtime()
        analysisView.snapshot = snapshot
        val result = snapshot.analysis
        val count = result.detections.size
        status.text = (if (count == 0) "Sin detecciones" else "Capachos detectados: $count") +
            String.format(Locale.US, " · %.0f ms", result.analysisMs)
        referenceStatus.text = when (result.referenceState) {
            ReferenceState.VALID -> "ArUco ${result.selectedMarkerId} · X derecha / Y arriba del marcador"
            ReferenceState.SIZE_UNCONFIRMED -> "Confirma el lado impreso en Ajustes para mostrar centímetros"
            ReferenceState.NO_SELECTION -> if (result.markers.isEmpty()) "Sin marcador de referencia" else "Toca un ArUco para elegir la referencia"
            ReferenceState.MISSING -> "Sin marcador de referencia · esperando ArUco ${result.selectedMarkerId}"
            ReferenceState.AMBIGUOUS -> "ID ${result.selectedMarkerId} duplicado · coordenadas no disponibles"
            ReferenceState.DEGENERATE -> "Acerca o endereza el marcador · coordenadas no disponibles"
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
        root.addView(analysisView, LinearLayout.LayoutParams(-1, 0, 1f))
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
        val side = field("Lado negro exterior del ArUco (cm)", settings.markerSideCm.toString())
        val confidence = field("Confianza mínima (0.05–0.95)", settings.confidence.toString())
        val confirmed = CheckBox(this).apply { text = "Medí y confirmé el lado impreso"; isChecked = settings.sizeConfirmed }
        fields.addView(confirmed)
        fields.addView(TextView(this).apply { text = "DICT_4X4_50 · mide el cuadrado negro, sin el margen blanco. Usa el mismo tamaño para los marcadores de esta sesión." })
        val dialog = AlertDialog.Builder(this).setTitle("Referencia y detección").setView(fields)
            .setNegativeButton("Cancelar", null).setPositiveButton("Guardar", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val cm = side.text.toString().replace(',', '.').toDoubleOrNull()
                val threshold = confidence.text.toString().replace(',', '.').toFloatOrNull()
                if (cm == null || !cm.isFinite() || cm !in 0.1..1000.0) { side.error = "Introduce un lado válido (0.1–1000 cm)"; return@setOnClickListener }
                if (threshold == null || !threshold.isFinite() || threshold !in 0.05f..0.95f) { confidence.error = "Usa un valor entre 0.05 y 0.95"; return@setOnClickListener }
                settings = AnalysisSettings(cm, threshold, confirmed.isChecked); revision++
                getSharedPreferences("analysis", MODE_PRIVATE).edit().putFloat("side", cm.toFloat()).putFloat("confidence", threshold).putBoolean("confirmed", confirmed.isChecked).apply()
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
                    AlertDialog.Builder(this).setTitle("Captura guardada").setMessage("Imagen y JSON del cuadro ${snapshot.analysis.frameId}.")
                        .setNegativeButton("Cerrar", null).setPositiveButton("Compartir") { _, _ -> CaptureStore.share(this, saved) }.show()
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
        AlertDialog.Builder(this).setTitle("Compartir captura guardada")
            .setItems(captures.map { it.directory.name }.toTypedArray()) { _, index -> CaptureStore.share(this, captures[index]) }
            .setNegativeButton("Cerrar", null).show()
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
