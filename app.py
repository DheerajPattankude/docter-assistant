from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_PATH = os.getenv("DB_PATH", "driver_platform.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

app = FastAPI(title="Driver Requirement API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Pydantic models
class UserRequestIn(BaseModel):
    name: str
    contact: str
    start_location: str
    end_location: str
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None

class RideOut(BaseModel):
    ride_id: int
    status: str
    driver_id: Optional[int]
    user_name: str
    start_location: str
    end_location: str
    created_at: str

class DriverIn(BaseModel):
    name: str
    contact: str
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None

class DriverOut(BaseModel):
    id: int
    name: str
    contact: str
    location_lat: Optional[float]
    location_lon: Optional[float]
    license_url: Optional[str]
    status: str
    updated_at: str

# ---- helpers
SCHEMA_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT NOT NULL,
    start_location TEXT NOT NULL,
    end_location TEXT NOT NULL,
    start_lat REAL,
    start_lon REAL,
    end_lat REAL,
    end_lon REAL,
    request_status TEXT DEFAULT 'requested',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
SCHEMA_DRIVERS = """
CREATE TABLE IF NOT EXISTS drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT NOT NULL,
    location_lat REAL,
    location_lon REAL,
    license_url TEXT,
    status TEXT DEFAULT 'pending',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
SCHEMA_RIDES = """
CREATE TABLE IF NOT EXISTS rides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    driver_id INTEGER,
    status TEXT DEFAULT 'requested',
    start_time TEXT,
    end_time TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(driver_id) REFERENCES drivers(id)
);
"""

def init_db():
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_USERS))
        conn.execute(text(SCHEMA_DRIVERS))
        conn.execute(text(SCHEMA_RIDES))

init_db()

# ---- endpoints
@app.post("/user/request")
def user_request(req: UserRequestIn):
    with engine.begin() as conn:
        conn.execute(text(
            """
            INSERT INTO users (name, contact, start_location, end_location, start_lat, start_lon, end_lat, end_lon, request_status)
            VALUES (:name, :contact, :sl, :el, :sla, :slo, :ela, :elo, 'requested')
            """
        ), {
            "name": req.name, "contact": req.contact,
            "sl": req.start_location, "el": req.end_location,
            "sla": req.start_lat, "slo": req.start_lon,
            "ela": req.end_lat, "elo": req.end_lon,
        })
        row = conn.execute(text("SELECT last_insert_rowid() as id")).mappings().first()
        user_id = row["id"]
        conn.execute(text("INSERT INTO rides (user_id, status, start_time) VALUES (:uid, 'requested', :t)"),
                     {"uid": user_id, "t": datetime.utcnow().isoformat()})
        return {"ok": True, "user_id": user_id}

@app.post("/driver/register")
async def driver_register(
    name: str = Form(...), contact: str = Form(...),
    location_lat: Optional[float] = Form(None), location_lon: Optional[float] = Form(None),
    license_file: Optional[UploadFile] = File(None)
):
    lic_path = None
    if license_file is not None:
        ext = os.path.splitext(license_file.filename)[1]
        fname = f"license_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{contact}{ext}"
        lic_path = os.path.join(UPLOAD_DIR, fname)
        with open(lic_path, "wb") as f:
            f.write(await license_file.read())
    with engine.begin() as conn:
        conn.execute(text(
            """
            INSERT INTO drivers (name, contact, location_lat, location_lon, license_url, status, updated_at)
            VALUES (:n,:c,:la,:lo,:lic,'pending',:u)
            """
        ), {"n": name, "c": contact, "la": location_lat, "lo": location_lon, "lic": lic_path, "u": datetime.utcnow().isoformat()})
    return {"ok": True}

@app.get("/driver/available")
def driver_available():
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT * FROM drivers WHERE status IN ('approved','available')")).mappings().all()
        return rows

@app.post("/ride/accept")
def ride_accept(ride_id: int, driver_contact: str):
    with engine.begin() as conn:
        d = conn.execute(text("SELECT id, status FROM drivers WHERE contact=:c"), {"c": driver_contact}).mappings().first()
        if not d:
            raise HTTPException(status_code=404, detail="Driver not found")
        conn.execute(text("UPDATE rides SET status='accepted', driver_id=:did WHERE id=:rid"), {"did": d['id'], "rid": ride_id})
        conn.execute(text("UPDATE drivers SET status='busy', updated_at=:u WHERE id=:did"), {"u": datetime.utcnow().isoformat(), "did": d['id']})
        return {"ok": True}

@app.post("/ride/end")
def ride_end(ride_id: int, driver_contact: str):
    with engine.begin() as conn:
        d = conn.execute(text("SELECT id FROM drivers WHERE contact=:c"), {"c": driver_contact}).mappings().first()
        if not d:
            raise HTTPException(status_code=404, detail="Driver not found")
        conn.execute(text("UPDATE rides SET status='completed', end_time=:t WHERE id=:rid"), {"t": datetime.utcnow().isoformat(), "rid": ride_id})
        conn.execute(text("UPDATE drivers SET status='available', updated_at=:u WHERE id=:did"), {"u": datetime.utcnow().isoformat(), "did": d['id']})
        return {"ok": True}

@app.get("/rides/latest", response_model=List[RideOut])
def rides_latest():
    q = text("""
        SELECT r.id as ride_id, r.status, r.driver_id, u.name as user_name, u.start_location, u.end_location, u.created_at
        FROM rides r JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC LIMIT 50
    """)
    with engine.begin() as conn:
        rows = conn.execute(q).mappings().all()
        return rows

@app.post("/admin/driver/status")
def admin_driver_status(driver_id: int, status: str):
    if status not in ["approved", "available", "busy", "inactive", "pending"]:
        raise HTTPException(400, "Invalid status")
    with engine.begin() as conn:
        conn.execute(text("UPDATE drivers SET status=:s, updated_at=:u WHERE id=:i"), {"s": status, "u": datetime.utcnow().isoformat(), "i": driver_id})
        return {"ok": True}


# =============================
# ANDROID — Jetpack Compose app (folder: android-app/)
# =============================
# File: android-app/settings.gradle.kts
rootProject.name = "DriverRequirementApp"
include(":app")

# File: android-app/build.gradle.kts
plugins {
    id("com.android.application") version "8.5.0" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
}

# File: android-app/app/build.gradle.kts
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.example.driverrequirement"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.driverrequirement"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }
    buildTypes { release { isMinifyEnabled = false } }
    buildFeatures { compose = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3:1.2.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
    implementation("io.coil-kt:coil-compose:2.6.0")

    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-moshi:2.11.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("com.squareup.moshi:moshi-kotlin:1.15.1")
}

# File: android-app/app/src/main/AndroidManifest.xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <application
        android:label="DriverRequirement"
        android:icon="@mipmap/ic_launcher"
        android:usesCleartextTraffic="true">
        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>

# File: android-app/app/src/main/java/com/example/driverrequirement/Api.kt
package com.example.driverrequirement

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.*

// IMPORTANT: For Android emulator talking to your PC localhost, use 10.0.2.2
const val BASE_URL = "http://10.0.2.2:8000/"

data class UserRequestIn(
    val name: String,
    val contact: String,
    val start_location: String,
    val end_location: String,
    val start_lat: Double? = null,
    val start_lon: Double? = null,
    val end_lat: Double? = null,
    val end_lon: Double? = null
)

data class RideOut(
    val ride_id: Int,
    val status: String,
    val driver_id: Int?,
    val user_name: String,
    val start_location: String,
    val end_location: String,
    val created_at: String
)

data class SimpleOk(val ok: Boolean)

data class DriverOut(
    val id: Int,
    val name: String,
    val contact: String,
    val location_lat: Double?,
    val location_lon: Double?,
    val license_url: String?,
    val status: String,
    val updated_at: String
)

interface ApiService {
    @POST("user/request")
    suspend fun userRequest(@Body body: UserRequestIn): SimpleOk

    @FormUrlEncoded
    @POST("ride/accept")
    suspend fun rideAccept(@Field("ride_id") rideId: Int, @Field("driver_contact") driverContact: String): SimpleOk

    @FormUrlEncoded
    @POST("ride/end")
    suspend fun rideEnd(@Field("ride_id") rideId: Int, @Field("driver_contact") driverContact: String): SimpleOk

    @GET("rides/latest")
    suspend fun ridesLatest(): List<RideOut>

    @GET("driver/available")
    suspend fun driversAvailable(): List<DriverOut>

    @FormUrlEncoded
    @POST("admin/driver/status")
    suspend fun adminSetDriverStatus(@Field("driver_id") driverId: Int, @Field("status") status: String): SimpleOk
}

object ApiClient {
    private val logger = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BODY }
    private val client = OkHttpClient.Builder().addInterceptor(logger).build()

    val api: ApiService = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(client)
        .addConverterFactory(MoshiConverterFactory.create())
        .build()
        .create(ApiService::class.java)
}

# File: android-app/app/src/main/java/com/example/driverrequirement/MainActivity.kt
package com.example.driverrequirement

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { App() }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun App() {
    val tabs = listOf("User", "Driver", "Admin")
    var selected by remember { mutableStateOf(0) }
    MaterialTheme(colorScheme = darkColorScheme(
        primary = androidx.compose.ui.graphics.Color(0xFF10B981),
        secondary = androidx.compose.ui.graphics.Color(0xFF6366F1),
        tertiary = androidx.compose.ui.graphics.Color(0xFFF59E0B)
    )) {
        Scaffold(topBar = {
            TopAppBar(title = { Text("Driver Requirement Platform") })
        }) { padding ->
            Column(Modifier.padding(padding)) {
                TabRow(selectedTabIndex = selected) {
                    tabs.forEachIndexed { i, t ->
                        Tab(selected = selected == i, onClick = { selected = i }, text = { Text(t) })
                    }
                }
                when (selected) {
                    0 -> UserScreen()
                    1 -> DriverScreen()
                    2 -> AdminScreen()
                }
            }
        }
    }
}

@Composable
fun UserScreen() {
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var contact by remember { mutableStateOf("") }
    var startLoc by remember { mutableStateOf("") }
    var endLoc by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }

    Column(Modifier.padding(16.dp)) {
        OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Name") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = contact, onValueChange = { contact = it }, label = { Text("Contact") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = startLoc, onValueChange = { startLoc = it }, label = { Text("Start Location") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = endLoc, onValueChange = { endLoc = it }, label = { Text("End Location") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(12.dp))
        Button(onClick = {
            scope.launch {
                runCatching {
                    ApiClient.api.userRequest(UserRequestIn(name, contact, startLoc, endLoc))
                }.onSuccess { message = "Request sent!" }.onFailure { message = it.message ?: "Error" }
            }
        }, modifier = Modifier.fillMaxWidth()) { Text("Send Ride Request") }
        Spacer(Modifier.height(12.dp))
        Text(message)
        Spacer(Modifier.height(16.dp))
        Text("Latest Rides", style = MaterialTheme.typography.titleMedium)
        LatestRidesList()
    }
}

@Composable
fun LatestRidesList() {
    val scope = rememberCoroutineScope()
    var rides by remember { mutableStateOf(listOf<RideOut>()) }
    LaunchedEffect(Unit) {
        scope.launch {
            runCatching { ApiClient.api.ridesLatest() }.onSuccess { rides = it }
        }
    }
    Column { rides.forEach { Text("#${it.ride_id} • ${it.status} • ${it.start_location} → ${it.end_location}") } }
}

@Composable
fun DriverScreen() {
    val scope = rememberCoroutineScope()
    var driverContact by remember { mutableStateOf("") }
    var rideId by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf("") }

    Column(Modifier.padding(16.dp)) {
        Text("Driver Actions", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = driverContact, onValueChange = { driverContact = it }, label = { Text("Contact (login)") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = rideId, onValueChange = { rideId = it }, label = { Text("Ride ID") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                scope.launch {
                    runCatching { ApiClient.api.rideAccept(rideId.toIntOrNull() ?: -1, driverContact) }
                        .onSuccess { msg = "Accepted" }.onFailure { msg = it.message ?: "Error" }
                }
            }, modifier = Modifier.weight(1f)) { Text("Accept Ride") }
            Button(onClick = {
                scope.launch {
                    runCatching { ApiClient.api.rideEnd(rideId.toIntOrNull() ?: -1, driverContact) }
                        .onSuccess { msg = "Completed" }.onFailure { msg = it.message ?: "Error" }
                }
            }, modifier = Modifier.weight(1f)) { Text("End Ride") }
        }
        Spacer(Modifier.height(12.dp))
        Text(msg)
        Spacer(Modifier.height(16.dp))
        Text("Available Drivers", style = MaterialTheme.typography.titleMedium)
        AvailableDriversList()
    }
}

@Composable
fun AvailableDriversList() {
    val scope = rememberCoroutineScope()
    var drivers by remember { mutableStateOf(listOf<DriverOut>()) }
    LaunchedEffect(Unit) {
        scope.launch { runCatching { ApiClient.api.driversAvailable() }.onSuccess { drivers = it } }
    }
    Column { drivers.forEach { Text("#${it.id} • ${it.name} • ${it.status}") } }
}

@Composable
fun AdminScreen() {
    val scope = rememberCoroutineScope()
    var driverId by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("approved") }
    var note by remember { mutableStateOf("") }

    Column(Modifier.padding(16.dp)) {
        Text("Admin — Update Driver Status", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = driverId, onValueChange = { driverId = it }, label = { Text("Driver ID") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        StatusDropdown(status) { status = it }
        Spacer(Modifier.height(12.dp))
        Button(onClick = {
            scope.launch {
                runCatching { ApiClient.api.adminSetDriverStatus(driverId.toIntOrNull() ?: -1, status) }
                    .onSuccess { note = "Updated" }.onFailure { note = it.message ?: "Error" }
            }
        }, modifier = Modifier.fillMaxWidth()) { Text("Save Status") }
        Spacer(Modifier.height(12.dp))
        Text(note)
    }
}

@Composable
fun StatusDropdown(current: String, onChange: (String) -> Unit) {
    val options = listOf("approved", "available", "busy", "inactive", "pending")
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = !expanded }) {
        OutlinedTextField(
            value = current,
            onValueChange = {},
            readOnly = true,
            label = { Text("Status") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.menuAnchor().fillMaxWidth()
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach {
                DropdownMenuItem(text = { Text(it) }, onClick = { onChange(it); expanded = false })
            }
        }
    }
}
