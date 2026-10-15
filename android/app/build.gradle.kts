import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing reads android/key.properties (gitignored). See
// android/key.properties.example. Without that file the release build is
// signed with the debug keys, which is fine for `flutter run --release` but
// cannot be uploaded to a store.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    keystorePropertiesFile.inputStream().use { keystoreProperties.load(it) }
}

fun keystoreProperty(name: String): String =
    requireNotNull(keystoreProperties.getProperty(name)) {
        "android/key.properties is missing '$name'"
    }

android {
    // PLACEHOLDER: change together with applicationId and the folder of
    // MainActivity.kt. See "Application ID" in README.md.
    namespace = "com.terrarun.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // PLACEHOLDER: replace with an ID you own, then see README.md.
        applicationId = "com.terrarun.app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        // Plain http:// is blocked unless asked for. A build for a backend on
        // the local network sets it: ORG_GRADLE_PROJECT_allowCleartext=true
        manifestPlaceholders["usesCleartextTraffic"] =
            (project.findProperty("allowCleartext") ?: "false").toString()
    }

    signingConfigs {
        if (keystorePropertiesFile.exists()) {
            create("release") {
                keyAlias = keystoreProperty("keyAlias")
                keyPassword = keystoreProperty("keyPassword")
                storeFile = file(keystoreProperty("storeFile"))
                storePassword = keystoreProperty("storePassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (keystorePropertiesFile.exists()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

flutter {
    source = "../.."
}
