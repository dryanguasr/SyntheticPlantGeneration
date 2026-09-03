import java.security.MessageDigest

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.uchuva.aruco"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.uchuva.aruco"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    androidResources { noCompress += "onnx" }
    packaging { resources.excludes += setOf("META-INF/DEPENDENCIES", "META-INF/LICENSE.md", "META-INF/NOTICE.md") }
}

dependencies {
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.camera:camera-core:1.4.2")
    implementation("androidx.camera:camera-camera2:1.4.2")
    implementation("androidx.camera:camera-lifecycle:1.4.2")
    implementation("org.opencv:opencv:4.11.0")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.22.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}

val verifyModel by tasks.registering {
    val model = layout.projectDirectory.file("src/main/assets/detector.onnx")
    val manifest = layout.projectDirectory.file("src/main/assets/model_manifest.json")
    inputs.files(model, manifest)
    doLast {
        check(model.asFile.isFile && manifest.asFile.isFile) {
            "Prepare el modelo: python scripts/export_mobile_detector.py (desde la raíz del repositorio)."
        }
        val metadata = groovy.json.JsonSlurper().parse(manifest.asFile) as Map<*, *>
        val hash = MessageDigest.getInstance("SHA-256").digest(model.asFile.readBytes())
            .joinToString("") { "%02x".format(it) }
        check(hash == metadata["model_sha256"]) { "El modelo y el manifiesto tienen hashes distintos." }
    }
}
tasks.named("preBuild") { dependsOn(verifyModel) }
