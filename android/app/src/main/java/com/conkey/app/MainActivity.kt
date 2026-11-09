package com.conkey.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.text.format.Formatter
import android.util.Log
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONArray
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : Activity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var vibrator: Vibrator

    private lateinit var rootLayout: View
    private lateinit var topBar: View
    private lateinit var pillDevice: View
    private lateinit var dotStatus: View
    private lateinit var tvDeviceName: TextView
    private lateinit var btnToggleScreen: Button
    private lateinit var webViewKeyboard: WebView

    private var isScreenActive = false

    // Real-time voice typing (Phonon-2 runs on the laptop; audio streams over Wi-Fi)
    private var voiceStreamer: VoiceStreamer? = null
    private var voiceStarting = false
    private var voiceActive = false
    private var voiceCancelRequested = false
    private var pendingVoiceStart = false
    private var pendingVoiceAutoType = false

    // Bluetooth HID Engine (Primary - Serverless, Zero Software on Laptop)
    private var bluetoothAdapter: BluetoothAdapter? = null
    private var hidManager: BluetoothHidManager? = null
    private var isHidRegistered = false

    // Wi-Fi WebSocket Engine (Secondary Fallback)
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var webSocket: WebSocket? = null
    private var isWifiConnected = false
    private val isConnecting = AtomicBoolean(false)

    // Configuration & State
    private var currentHost = "10.60.12.147"
    private var currentPort = 8765
    private var currentPin = "2026"
    private var deviceName = "Laptop"

    // Background Executors
    private val networkExecutor = Executors.newFixedThreadPool(6)
    private val autoReconnectScheduler: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
    private var udpSocket: DatagramSocket? = null
    private val isScanning = AtomicBoolean(false)
    private val mainHandler = Handler(Looper.getMainLooper())

    companion object {
        private const val TAG = "ConKey"
        private const val REQUEST_BT_PERMS = 101
        private const val REQUEST_DISCOVERABLE = 102
        private const val REQUEST_MIC_PERMS = 103
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Support display cutouts (notch / hole-punch camera)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            window.attributes.layoutInDisplayCutoutMode =
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        }

        // Set status bar & navigation bar theme colors
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            window.statusBarColor = Color.parseColor("#121418")
            window.navigationBarColor = Color.parseColor("#121418")
        }

        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("conkey_prefs", Context.MODE_PRIVATE)
        vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator

        currentHost = prefs.getString("server_ip", "10.60.12.147") ?: "10.60.12.147"
        currentPort = prefs.getInt("server_port", 8765)
        currentPin = prefs.getString("server_pin", "2026") ?: "2026"

        val btManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        bluetoothAdapter = btManager?.adapter ?: BluetoothAdapter.getDefaultAdapter()

        initViews()
        applyWindowInsets()
        setupWebView()

        checkBluetoothPermissionsAndInit()

        // Background Wi-Fi UDP discovery & auto-connection
        startUdpDiscoveryListener()
        startAutoConnectionPipeline()
        startAutoReconnectScheduler()
    }

    private fun initViews() {
        rootLayout = findViewById(R.id.rootLayout)
        topBar = findViewById(R.id.topBar)
        pillDevice = findViewById(R.id.pillDevice)
        dotStatus = findViewById(R.id.dotStatus)
        tvDeviceName = findViewById(R.id.tvDeviceName)
        btnToggleScreen = findViewById(R.id.btnToggleScreen)
        webViewKeyboard = findViewById(R.id.webViewKeyboard)

        pillDevice.setOnClickListener {
            vibrate(15)
            showConnectionMenu()
        }

        btnToggleScreen.setOnClickListener {
            vibrate(12)
            toggleScreenStream()
        }
        updateScreenButtonUi()
    }

    private fun toggleScreenStream() {
        isScreenActive = !isScreenActive
        updateScreenButtonUi()
        val js = "if(window.setScreenStreamActive) window.setScreenStreamActive($isScreenActive);"
        webViewKeyboard.evaluateJavascript(js, null)
    }

    private fun updateScreenButtonUi() {
        if (isScreenActive) {
            btnToggleScreen.text = "Screen ON"
            btnToggleScreen.setTextColor(Color.parseColor("#38BDF8"))
        } else {
            btnToggleScreen.text = "Screen OFF"
            btnToggleScreen.setTextColor(Color.parseColor("#94A3B8"))
        }
    }

    /**
     * Prevents top app bar from hiding under the camera notch / cutout
     * and bottom keyboard rows from colliding with navigation gesture bar.
     */
    private fun applyWindowInsets() {
        val baseTopBarHeightPx = (48 * resources.displayMetrics.density).toInt()
        val horizPaddingPx = (12 * resources.displayMetrics.density).toInt()

        ViewCompat.setOnApplyWindowInsetsListener(rootLayout) { _, windowInsets ->
            val insets = windowInsets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )

            // Top padding so ConKey title, status pill, and settings are 100% visible below notch
            topBar.setPadding(horizPaddingPx + insets.left, insets.top, horizPaddingPx + insets.right, 0)
            val lp = topBar.layoutParams
            lp.height = baseTopBarHeightPx + insets.top
            topBar.layoutParams = lp

            // Bottom padding to lift keyboard above gesture bar / navigation pill
            rootLayout.setPadding(0, 0, 0, insets.bottom)

            WindowInsetsCompat.CONSUMED
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val settings: WebSettings = webViewKeyboard.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true
        settings.allowFileAccess = true
        settings.allowContentAccess = true

        webViewKeyboard.setBackgroundColor(Color.parseColor("#0C0E12"))
        webViewKeyboard.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                Log.d(TAG, "WebView: ${consoleMessage?.message()} (${consoleMessage?.lineNumber()})")
                return true
            }
        }
        webViewKeyboard.webViewClient = WebViewClient()
        webViewKeyboard.addJavascriptInterface(KeyboardBridge(), "ConKeyBridge")
        webViewKeyboard.loadUrl("file:///android_asset/keyboard/index.html")
    }

    // =========================================================================
    // BLUETOOTH HID ENGINE (PRIMARY ZERO-SOFTWARE MODE)
    // =========================================================================

    private fun checkBluetoothPermissionsAndInit() {
        val permissionsNeeded = mutableListOf<String>()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.BLUETOOTH_SCAN)
            }
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.BLUETOOTH_ADVERTISE)
            }
        } else {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.ACCESS_FINE_LOCATION)
            }
        }

        if (permissionsNeeded.isNotEmpty()) {
            requestPermissions(permissionsNeeded.toTypedArray(), REQUEST_BT_PERMS)
        } else {
            initBluetoothHidManager()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_BT_PERMS) {
            val allGranted = grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }
            if (allGranted) {
                initBluetoothHidManager()
            } else {
                Toast.makeText(this, "Bluetooth permissions are required for the wireless keyboard.", Toast.LENGTH_LONG).show()
                updateStatusUi()
            }
        } else if (requestCode == REQUEST_MIC_PERMS) {
            val granted = grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED
            val shouldStart = pendingVoiceStart
            pendingVoiceStart = false
            if (granted && shouldStart) {
                beginVoiceSession(pendingVoiceAutoType)
            } else if (!granted) {
                dispatchVoiceEvent(
                    JSONObject()
                        .put("type", "voice_error")
                        .put("message", "Microphone permission is required for voice typing.")
                )
            }
        }
    }

    private fun initBluetoothHidManager() {
        if (hidManager != null) return

        hidManager = BluetoothHidManager(this, object : BluetoothHidManager.HidStateListener {
            override fun onAppRegistered(registered: Boolean) {
                isHidRegistered = registered
                runOnUiThread {
                    updateStatusUi()
                }
            }

            override fun onDeviceConnected(device: BluetoothDevice) {
                val devName = try { device.name ?: device.address } catch (e: SecurityException) { device.address }
                deviceName = devName
                runOnUiThread {
                    updateStatusUi()
                    Toast.makeText(this@MainActivity, "Connected to $devName as Bluetooth Keyboard & Mouse!", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onDeviceDisconnected(device: BluetoothDevice) {
                runOnUiThread {
                    updateStatusUi()
                }
            }

            override fun onDeviceConnecting(device: BluetoothDevice) {
                val devName = try { device.name ?: device.address } catch (e: SecurityException) { device.address }
                runOnUiThread {
                    tvDeviceName.text = "Connecting to $devName (HID)..."
                    dotStatus.setBackgroundColor(Color.parseColor("#F59E0B")) // Amber
                }
            }

            override fun onError(message: String) {
                Log.e(TAG, "HID Manager Error: $message")
                runOnUiThread {
                    updateStatusUi()
                }
            }
        })

        hidManager?.start()
    }

    private fun updateStatusUi() {
        val hidConnected = hidManager?.isConnected() == true
        when {
            hidConnected -> {
                val dev = hidManager?.getConnectedDevice()
                val devName = try { dev?.name ?: dev?.address ?: "Laptop" } catch (e: SecurityException) { "Laptop" }
                tvDeviceName.text = "$devName (BT HID)"
                dotStatus.setBackgroundColor(Color.parseColor("#10B981")) // Green
            }
            isWifiConnected -> {
                tvDeviceName.text = "$deviceName (Wi-Fi)"
                dotStatus.setBackgroundColor(Color.parseColor("#10B981")) // Green
            }
            isHidRegistered -> {
                tvDeviceName.text = "Bluetooth HID Ready"
                dotStatus.setBackgroundColor(Color.parseColor("#38BDF8")) // Sky Blue
            }
            else -> {
                tvDeviceName.text = "Tap to Connect / Pair Laptop"
                dotStatus.setBackgroundColor(Color.parseColor("#EF4444")) // Red
            }
        }

        val safeHost = currentHost.replace("'", "\\'")
        val safeName = deviceName.replace("'", "\\'")
        val js = "if(window.onConnectionStatusChanged) window.onConnectionStatusChanged($hidConnected, $isWifiConnected, '$safeHost', '$safeName');"
        webViewKeyboard.evaluateJavascript(js, null)
    }

    @SuppressLint("MissingPermission")
    private fun requestDiscoverability() {
        if (bluetoothAdapter == null || !bluetoothAdapter!!.isEnabled) {
            startActivity(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            return
        }
        val discoverableIntent = Intent(BluetoothAdapter.ACTION_REQUEST_DISCOVERABLE).apply {
            putExtra(BluetoothAdapter.EXTRA_DISCOVERABLE_DURATION, 300)
        }
        startActivityForResult(discoverableIntent, REQUEST_DISCOVERABLE)
        Toast.makeText(this, "Phone is now discoverable! On your laptop: Settings > Bluetooth > Add device.", Toast.LENGTH_LONG).show()
    }

    @SuppressLint("MissingPermission")
    private fun showBluetoothDevicePicker() {
        if (bluetoothAdapter == null || !bluetoothAdapter!!.isEnabled) {
            Toast.makeText(this, "Please enable Bluetooth first", Toast.LENGTH_SHORT).show()
            startActivity(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            return
        }

        val bonded = bluetoothAdapter?.bondedDevices?.toList() ?: emptyList()
        val items = mutableListOf<String>()

        items.add("Make Phone Discoverable (Pair New Laptop)")
        for (d in bonded) {
            items.add("Connect: ${d.name ?: d.address}")
        }
        items.add("Open Phone Bluetooth Settings")

        AlertDialog.Builder(this)
            .setTitle("Bluetooth HID Keyboard & Mouse")
            .setItems(items.toTypedArray()) { _, which ->
                when {
                    which == 0 -> requestDiscoverability()
                    which <= bonded.size -> {
                        val selectedDevice = bonded[which - 1]
                        hidManager?.connectDevice(selectedDevice)
                        Toast.makeText(this, "Connecting to ${selectedDevice.name}...", Toast.LENGTH_SHORT).show()
                    }
                    else -> startActivity(Intent(Settings.ACTION_BLUETOOTH_SETTINGS))
                }
            }
            .setNegativeButton("Close", null)
            .show()
    }

    // =========================================================================
    // WI-FI WEBSOCKET CONNECTION ENGINE (SECONDARY FALLBACK)
    // =========================================================================

    private fun startAutoConnectionPipeline() {
        networkExecutor.execute {
            val success = probeAndConnect(currentHost, currentPort)
            if (!success) {
                scanLocalSubnet(silent = true)
            }
        }
    }

    private fun startAutoReconnectScheduler() {
        autoReconnectScheduler.scheduleWithFixedDelay({
            if (!isWifiConnected && !isConnecting.get() && hidManager?.isConnected() != true && !isScanning.get()) {
                probeAndConnect(currentHost, currentPort)
            }
        }, 5, 5, TimeUnit.SECONDS)
    }

    private fun probeAndConnect(host: String, port: Int): Boolean {
        if (isWifiConnected || isConnecting.get() || hidManager?.isConnected() == true) return true
        try {
            val fastClient = OkHttpClient.Builder().connectTimeout(600, TimeUnit.MILLISECONDS).build()
            val req = Request.Builder().url("http://$host:$port/api/device").build()
            val resp = fastClient.newCall(req).execute()
            if (resp.isSuccessful) {
                val body = resp.body?.string() ?: ""
                val json = JSONObject(body)
                if (json.optString("service") == "conkey") {
                    val name = json.optString("name", host)
                    val pin = json.optString("pin", currentPin)
                    deviceName = name
                    currentPin = pin
                    currentHost = host
                    currentPort = port

                    prefs.edit()
                        .putString("server_ip", host)
                        .putInt("server_port", port)
                        .putString("server_pin", pin)
                        .apply()

                    connectToWifiServer(host, port)
                    return true
                }
            }
        } catch (e: Exception) {
            // Host unreachable
        }
        return false
    }

    private fun startUdpDiscoveryListener() {
        networkExecutor.execute {
            try {
                udpSocket = DatagramSocket(8766).apply {
                    broadcast = true
                    reuseAddress = true
                }
                val buffer = ByteArray(2048)
                val packet = DatagramPacket(buffer, buffer.size)

                while (!isFinishing) {
                    udpSocket?.receive(packet)
                    val raw = String(packet.data, 0, packet.length, Charsets.UTF_8)
                    try {
                        val json = JSONObject(raw)
                        if (json.optString("service") == "conkey") {
                            val ip = json.optString("ip", packet.address?.hostAddress ?: currentHost)
                            val port = json.optInt("port", 8765)
                            val name = json.optString("name", ip)
                            val pin = json.optString("pin", currentPin)

                            if (!isWifiConnected && !isConnecting.get() && hidManager?.isConnected() != true) {
                                deviceName = name
                                currentPin = pin
                                currentHost = ip
                                currentPort = port
                                prefs.edit().putString("server_ip", ip).apply()
                                connectToWifiServer(ip, port)
                            }
                        }
                    } catch (e: Exception) {
                        // ignore malformed beacon
                    }
                }
            } catch (e: Exception) {
                Log.d(TAG, "UDP Discovery stopped: ${e.message}")
            }
        }
    }

    private fun connectToWifiServer(host: String, port: Int = 8765) {
        if (isWifiConnected && currentHost == host && currentPort == port && webSocket != null) return
        if (isConnecting.getAndSet(true)) return

        disconnectWifi()

        val wsUrl = "ws://$host:$port/ws"
        val request = Request.Builder().url(wsUrl).build()

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                Log.i(TAG, "WebSocket opened to $wsUrl")
            }

            override fun onMessage(ws: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    when (json.optString("type")) {
                        "auth_required" -> {
                            val authPayload = JSONObject().apply {
                                put("type", "auth")
                                put("payload", JSONObject().put("pin", currentPin))
                            }
                            ws.send(authPayload.toString())
                        }
                        "auth_result" -> {
                            val success = json.optBoolean("success", false)
                            isConnecting.set(false)
                            if (success) {
                                isWifiConnected = true
                                val name = json.optString("device_name", host)
                                deviceName = name
                                prefs.edit().putString("server_ip", host).apply()

                                runOnUiThread {
                                    updateStatusUi()
                                }
                            }
                        }
                        "voice_loading",
                        "voice_ready",
                        "voice_partial",
                        "voice_final",
                        "voice_done",
                        "voice_error" -> {
                            handleVoiceServerMessage(json.optString("type"), json)
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Error parsing WS message: $text", e)
                }
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                isConnecting.set(false)
                isWifiConnected = false
                handleVoiceTransportLost()
                runOnUiThread {
                    updateStatusUi()
                }
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                isConnecting.set(false)
                isWifiConnected = false
                handleVoiceTransportLost()
                runOnUiThread {
                    updateStatusUi()
                }
            }
        })
    }

    private fun disconnectWifi() {
        isConnecting.set(false)
        isWifiConnected = false
        try {
            webSocket?.close(1000, "Transport switch")
        } catch (e: Exception) {
            // ignore
        }
        webSocket = null
    }

    private fun scanLocalSubnet(silent: Boolean = false) {
        if (isScanning.getAndSet(true)) return

        if (!silent) {
            runOnUiThread {
                tvDeviceName.text = "Scanning Wi-Fi..."
                dotStatus.setBackgroundColor(Color.parseColor("#3B82F6"))
                Toast.makeText(this, "Scanning Wi-Fi for laptop...", Toast.LENGTH_SHORT).show()
            }
        }

        networkExecutor.execute {
            try {
                val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
                val ipInt = wifiManager?.connectionInfo?.ipAddress ?: 0
                val myIp = if (ipInt != 0) {
                    @Suppress("DEPRECATION")
                    Formatter.formatIpAddress(ipInt)
                } else {
                    "10.60.12.1"
                }

                val subnetPrefix = myIp.substringBeforeLast(".") + "."
                val fastClient = OkHttpClient.Builder().connectTimeout(350, TimeUnit.MILLISECONDS).build()
                var found = false

                if (probeAndConnect(currentHost, currentPort)) {
                    found = true
                }

                if (!found) {
                    val scanPool = Executors.newFixedThreadPool(16)
                    for (i in 1..254) {
                        if (found) break
                        val targetIp = "$subnetPrefix$i"
                        scanPool.execute {
                            if (found) return@execute
                            try {
                                val req = Request.Builder().url("http://$targetIp:8765/api/device").build()
                                val resp = fastClient.newCall(req).execute()
                                if (resp.isSuccessful) {
                                    val body = resp.body?.string() ?: ""
                                    if (body.contains("conkey") && !found) {
                                        found = true
                                        connectToWifiServer(targetIp, 8765)
                                    }
                                }
                            } catch (e: Exception) {
                                // non-responsive host
                            }
                        }
                    }
                    scanPool.shutdown()
                    scanPool.awaitTermination(3, TimeUnit.SECONDS)
                }

                if (!found && !silent) {
                    runOnUiThread {
                        updateStatusUi()
                        Toast.makeText(this@MainActivity, "Laptop not found on Wi-Fi.", Toast.LENGTH_SHORT).show()
                    }
                }
            } finally {
                isScanning.set(false)
            }
        }
    }

    // =========================================================================
    // DUAL-MODE UNIFIED DISPATCHER
    // =========================================================================

    private fun sendKey(key: String) {
        when {
            hidManager?.isConnected() == true -> {
                hidManager?.sendKeyPress(key)
            }
            isWifiConnected && webSocket != null -> {
                sendWifiCommand("key_press", JSONObject().put("key", key))
            }
            else -> {
                promptConnectionRequired()
            }
        }
    }

    private fun sendCombo(modifiers: List<String>, key: String) {
        when {
            hidManager?.isConnected() == true -> {
                hidManager?.sendKeyCombo(modifiers, key)
            }
            isWifiConnected && webSocket != null -> {
                val payload = JSONObject().apply {
                    put("modifiers", JSONArray(modifiers))
                    put("key", key)
                }
                sendWifiCommand("key_combo", payload)
            }
            else -> {
                promptConnectionRequired()
            }
        }
    }

    private fun sendText(text: String) {
        when {
            hidManager?.isConnected() == true -> {
                hidManager?.sendText(text)
            }
            isWifiConnected && webSocket != null -> {
                sendWifiCommand("type_text", JSONObject().put("text", text))
            }
            else -> {
                promptConnectionRequired()
            }
        }
    }

    private fun sendMouseMove(dx: Float, dy: Float) {
        when {
            hidManager?.isConnected() == true -> {
                hidManager?.sendMouseMove(dx, dy)
            }
            isWifiConnected && webSocket != null -> {
                val payload = JSONObject().apply {
                    put("dx", dx.toInt())
                    put("dy", dy.toInt())
                }
                sendWifiCommand("mouse_move", payload)
            }
        }
    }

    private fun sendMouseClick(button: String) {
        when {
            hidManager?.isConnected() == true -> {
                hidManager?.sendMouseClick(button)
            }
            isWifiConnected && webSocket != null -> {
                sendWifiCommand("mouse_click", JSONObject().put("button", button))
            }
            else -> {
                promptConnectionRequired()
            }
        }
    }

    private fun sendMouseScroll(dy: Float) {
        when {
            hidManager?.isConnected() == true -> {
                hidManager?.sendMouseScroll(dy)
            }
            isWifiConnected && webSocket != null -> {
                sendWifiCommand("mouse_scroll", JSONObject().put("dy", dy.toInt()))
            }
        }
    }

    private fun sendWifiCommand(type: String, payload: JSONObject) {
        networkExecutor.execute {
            try {
                val json = JSONObject().apply {
                    put("type", type)
                    put("payload", payload)
                }
                webSocket?.send(json.toString())
            } catch (e: Exception) {
                Log.w(TAG, "Wi-Fi send failed: ${e.message}")
            }
        }
    }

    // =========================================================================
    // REAL-TIME VOICE TYPING (Phonon-2 streaming on the laptop)
    // =========================================================================

    private fun requestStartVoice(autoType: Boolean): String {
        if (!isWifiConnected || webSocket == null) return "no_wifi"
        if (voiceActive || voiceStarting) return "already"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
            checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED
        ) {
            pendingVoiceStart = true
            pendingVoiceAutoType = autoType
            mainHandler.post {
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_MIC_PERMS)
            }
            return "permission"
        }
        return beginVoiceSession(autoType)
    }

    private fun beginVoiceSession(autoType: Boolean): String {
        if (!isWifiConnected || webSocket == null) return "no_wifi"
        if (voiceActive || voiceStarting) return "already"
        voiceStarting = true
        voiceCancelRequested = false
        pendingVoiceAutoType = autoType
        val payload = JSONObject().apply {
            put("sample_rate", VoiceStreamer.SAMPLE_RATE)
            put("format", "pcm_s16le")
            put("auto_type", autoType)
        }
        sendWifiCommand("voice_start", payload)
        return "ok"
    }

    private fun startVoiceCapture() {
        voiceStarting = false
        if (voiceActive) return
        if (!isWifiConnected || webSocket == null) {
            dispatchVoiceEvent(
                JSONObject().put("type", "voice_error")
                    .put("message", "Lost the Wi-Fi connection to the laptop.")
            )
            return
        }

        val streamer = VoiceStreamer(
            onChunk = { data ->
                try {
                    webSocket?.send(data.toByteString())
                } catch (e: Exception) {
                    Log.w(TAG, "Voice chunk send failed: ${e.message}")
                }
            },
            onError = { message ->
                mainHandler.post {
                    voiceActive = false
                    voiceStarting = false
                    voiceStreamer?.stop()
                    voiceStreamer = null
                    dispatchVoiceEvent(
                        JSONObject().put("type", "voice_error").put("message", message)
                    )
                }
            },
        )
        voiceStreamer = streamer
        voiceActive = true
        streamer.start()
    }

    private fun stopVoiceCapture() {
        voiceActive = false
        voiceStarting = false
        voiceStreamer?.stop()
        voiceStreamer = null
    }

    private fun requestStopVoice() {
        if (voiceStarting && !voiceActive) {
            // Still loading the model: ask the host to abort, and ignore the
            // ready event if it was already on its way.
            voiceStarting = false
            voiceCancelRequested = true
            sendWifiCommand("voice_cancel", JSONObject())
            dispatchVoiceEvent(
                JSONObject().put("type", "voice_error")
                    .put("message", "Voice typing cancelled.")
            )
            return
        }
        if (!voiceActive) return
        stopVoiceCapture()
        // Binary chunks are queued in order; the text stop frame follows them.
        sendWifiCommand("voice_stop", JSONObject())
    }

    private fun handleVoiceServerMessage(type: String, json: JSONObject) {
        if (type == "voice_ready") {
            if (voiceCancelRequested) {
                voiceCancelRequested = false
                voiceStarting = false
                sendWifiCommand("voice_cancel", JSONObject())
                dispatchVoiceEvent(
                    JSONObject().put("type", "voice_error")
                        .put("message", "Voice typing cancelled.")
                )
                return
            }
            startVoiceCapture()
        } else if (type == "voice_done" || type == "voice_error") {
            voiceCancelRequested = false
            stopVoiceCapture()
        }
        dispatchVoiceEvent(json)
    }

    private fun handleVoiceTransportLost() {
        val wasLive = voiceActive || voiceStarting
        voiceCancelRequested = false
        stopVoiceCapture()
        if (wasLive) {
            dispatchVoiceEvent(
                JSONObject().put("type", "voice_error")
                    .put("message", "Disconnected from the laptop. Voice typing stopped.")
            )
        }
    }

    private fun dispatchVoiceEvent(event: JSONObject) {
        val payload = event.toString()
        mainHandler.post {
            webViewKeyboard.evaluateJavascript(
                "window.onVoiceEvent && window.onVoiceEvent($payload);",
                null
            )
        }
    }

    private fun promptConnectionRequired() {
        runOnUiThread {
            Toast.makeText(this, "Please pair or connect to your laptop first.", Toast.LENGTH_SHORT).show()
            showConnectionMenu()
        }
    }

    private fun vibrate(ms: Long) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(ms)
        }
    }

    // =========================================================================
    // CONNECTION SELECTION & SETTINGS MENU
    // =========================================================================

    private fun showConnectionMenu() {
        val statusText = when {
            hidManager?.isConnected() == true -> "Connected (Bluetooth HID - Serverless)"
            isWifiConnected -> "Connected (Wi-Fi WebSocket)"
            else -> "Not Connected"
        }

        val options = arrayOf(
            "Bluetooth HID: Pair & Connect (Zero Software)",
            "Make Phone Discoverable (5 Min)",
            "Connect via Wi-Fi ($currentHost)",
            "Auto-Scan Local Wi-Fi",
            "Enter Laptop IP Manually",
            "Zero-Software Pairing Instructions"
        )

        AlertDialog.Builder(this)
            .setTitle("ConKey - $statusText")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> showBluetoothDevicePicker()
                    1 -> requestDiscoverability()
                    2 -> connectToWifiServer(currentHost, currentPort)
                    3 -> scanLocalSubnet(silent = false)
                    4 -> showManualIpDialog()
                    5 -> showPairingGuideDialog()
                }
            }
            .setNegativeButton("Close", null)
            .show()
    }

    private fun showPairingGuideDialog() {
        AlertDialog.Builder(this)
            .setTitle("How to Pair with Laptop (Serverless)")
            .setMessage(
                "ConKey operates as a genuine Bluetooth HID Hardware Keyboard and Mouse.\n\n" +
                "NO software or client is required on your laptop!\n\n" +
                "Steps to Pair:\n" +
                "1. On this phone, tap 'Make Phone Discoverable'.\n" +
                "2. On your Laptop, open Windows Settings > Bluetooth & devices > Add device > Bluetooth.\n" +
                "3. Select 'ConKey Keyboard' (or your phone name) from the list.\n" +
                "4. Windows automatically installs the built-in Bluetooth keyboard driver.\n\n" +
                "Once paired, all keys, shortcuts, and touchpad actions work instantly!"
            )
            .setPositiveButton("Make Discoverable Now") { _, _ -> requestDiscoverability() }
            .setNegativeButton("Got it", null)
            .show()
    }

    private fun showManualIpDialog() {
        val input = EditText(this)
        input.setText(currentHost)
        input.setSelection(currentHost.length)

        AlertDialog.Builder(this)
            .setTitle("Enter Laptop IP Address")
            .setView(input)
            .setPositiveButton("Connect") { _, _ ->
                val ip = input.text.toString().trim()
                if (ip.isNotEmpty()) {
                    currentHost = ip
                    prefs.edit().putString("server_ip", ip).apply()
                    connectToWifiServer(ip, currentPort)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // =========================================================================
    // JAVASCRIPT BRIDGE FOR VIRTUAL KEYBOARD & TOUCHPAD
    // =========================================================================

    inner class KeyboardBridge {
        @JavascriptInterface
        fun getHostIp(): String = currentHost

        @JavascriptInterface
        fun getHostPort(): Int = currentPort

        @JavascriptInterface
        fun isWifiConnected(): Boolean = isWifiConnected

        @JavascriptInterface
        fun isHidConnected(): Boolean = hidManager?.isConnected() == true

        @JavascriptInterface
        fun isVoiceAvailable(): Boolean = isWifiConnected && webSocket != null

        @JavascriptInterface
        fun startVoice(autoType: Boolean): String = requestStartVoice(autoType)

        @JavascriptInterface
        fun stopVoice() {
            mainHandler.post { requestStopVoice() }
        }

        @JavascriptInterface
        fun isScreenActive(): Boolean = isScreenActive

        @JavascriptInterface
        fun reportScreenActive(active: Boolean) {
            runOnUiThread {
                isScreenActive = active
                updateScreenButtonUi()
            }
        }

        @JavascriptInterface
        fun openConnectionMenu() {
            runOnUiThread {
                showConnectionMenu()
            }
        }

        @JavascriptInterface
        fun sendMouseTouch(normX: Float, normY: Float, click: Boolean) {
            val payload = JSONObject().apply {
                put("x", (normX * 1920).toInt())
                put("y", (normY * 1200).toInt())
                put("click", click)
            }
            if (isWifiConnected && webSocket != null) {
                sendWifiCommand("mouse_touch", payload)
            }
        }

        @JavascriptInterface
        fun sendMouseMoveAbs(normX: Float, normY: Float) {
            val payload = JSONObject().apply {
                put("x", (normX * 1920).toInt())
                put("y", (normY * 1200).toInt())
            }
            if (isWifiConnected && webSocket != null) {
                sendWifiCommand("mouse_move_abs", payload)
            }
        }

        @JavascriptInterface
        fun sendKey(key: String) {
            vibrate(10)
            this@MainActivity.sendKey(key)
        }

        @JavascriptInterface
        fun sendCombo(modsJson: String, key: String) {
            vibrate(16)
            val modsArray = JSONArray(modsJson)
            val modsList = mutableListOf<String>()
            for (i in 0 until modsArray.length()) {
                modsList.add(modsArray.getString(i))
            }
            this@MainActivity.sendCombo(modsList, key)
        }

        @JavascriptInterface
        fun sendText(text: String) {
            vibrate(10)
            this@MainActivity.sendText(text)
        }

        @JavascriptInterface
        fun sendMouseMove(dx: Float, dy: Float) {
            this@MainActivity.sendMouseMove(dx, dy)
        }

        @JavascriptInterface
        fun sendMouseClick(button: String) {
            vibrate(14)
            this@MainActivity.sendMouseClick(button)
        }

        @JavascriptInterface
        fun sendMouseScroll(dy: Float) {
            this@MainActivity.sendMouseScroll(dy)
        }

        @JavascriptInterface
        fun vibrate(ms: Long) {
            this@MainActivity.vibrate(ms)
        }
    }

    override fun onPause() {
        super.onPause()
        // Never leave the phone microphone hot when ConKey is not in front.
        if (voiceActive) {
            requestStopVoice()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopVoiceCapture()
        hidManager?.stop()
        disconnectWifi()
        try {
            udpSocket?.close()
        } catch (e: Exception) {
            // ignore
        }
        autoReconnectScheduler.shutdown()
        networkExecutor.shutdown()
    }
}
