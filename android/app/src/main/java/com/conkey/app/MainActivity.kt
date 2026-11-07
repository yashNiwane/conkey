package com.conkey.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.text.format.Formatter
import android.util.Log
import android.view.View
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
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStream
import java.net.InetAddress
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : Activity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var vibrator: Vibrator

    private lateinit var pillDevice: View
    private lateinit var dotStatus: View
    private lateinit var tvDeviceName: TextView
    private lateinit var etTextInput: EditText
    private lateinit var webViewKeyboard: WebView

    // Network / Wi-Fi WebSocket
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS) // Keep alive for WebSocket
        .build()
    private var webSocket: WebSocket? = null
    private var isWifiConnected = false

    // Bluetooth
    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bluetoothSocket: BluetoothSocket? = null
    private var btOutputStream: OutputStream? = null
    private var isBtConnected = false

    // State & Async
    private var currentHost = "10.60.12.147"
    private var currentPort = 8765
    private var currentPin = "2026"
    private var deviceName = "YashN's Laptop (ave)"
    private val networkExecutor = Executors.newFixedThreadPool(4)
    private val isScanning = AtomicBoolean(false)

    companion object {
        private const val TAG = "ConKey"
        private val SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
        private const val REQUEST_BT_PERMS = 101
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("conkey_prefs", Context.MODE_PRIVATE)
        vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator

        currentHost = prefs.getString("server_ip", "10.60.12.147") ?: "10.60.12.147"
        currentPort = prefs.getInt("server_port", 8765)
        currentPin = prefs.getString("server_pin", "2026") ?: "2026"

        val btManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        bluetoothAdapter = btManager?.adapter ?: BluetoothAdapter.getDefaultAdapter()

        initViews()
        setupWebView()
        connectToWifiServer(currentHost, currentPort)
    }

    private fun initViews() {
        pillDevice = findViewById(R.id.pillDevice)
        dotStatus = findViewById(R.id.dotStatus)
        tvDeviceName = findViewById(R.id.tvDeviceName)
        etTextInput = findViewById(R.id.etTextInput)
        webViewKeyboard = findViewById(R.id.webViewKeyboard)

        pillDevice.setOnClickListener {
            vibrate(15)
            showConnectionMenu()
        }

        findViewById<Button>(R.id.btnBluetoothSettings).setOnClickListener {
            vibrate(15)
            showConnectionMenu()
        }

        findViewById<Button>(R.id.btnSendText).setOnClickListener {
            val text = etTextInput.text.toString()
            if (text.isNotEmpty()) {
                vibrate(15)
                sendText(text)
                etTextInput.setText("")
            }
        }

        etTextInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND || actionId == EditorInfo.IME_ACTION_DONE) {
                val text = etTextInput.text.toString()
                if (text.isNotEmpty()) {
                    vibrate(15)
                    sendText(text)
                    etTextInput.setText("")
                }
                sendKey("ENTER")
                true
            } else {
                false
            }
        }

        findViewById<Button>(R.id.btnLeftClick).setOnClickListener {
            vibrate(15)
            sendMouseClick("left")
        }

        findViewById<Button>(R.id.btnRightClick).setOnClickListener {
            vibrate(15)
            sendMouseClick("right")
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

        webViewKeyboard.setBackgroundColor(Color.parseColor("#0F1115"))
        webViewKeyboard.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                Log.d(TAG, "WebView Console: ${consoleMessage?.message()} (${consoleMessage?.lineNumber()})")
                return true
            }
        }
        webViewKeyboard.webViewClient = WebViewClient()
        webViewKeyboard.addJavascriptInterface(KeyboardBridge(), "ConKeyBridge")
        webViewKeyboard.loadUrl("file:///android_asset/keyboard/index.html")
    }

    // =========================================================================
    // WI-FI WEBSOCKET CONNECTION ENGINE (PRIMARY & INSTANT)
    // =========================================================================

    private fun connectToWifiServer(host: String, port: Int = 8765) {
        disconnectWifi()
        disconnectBluetooth()

        runOnUiThread {
            tvDeviceName.text = "Connecting to $host..."
            dotStatus.setBackgroundColor(Color.parseColor("#F59E0B")) // Amber
        }

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
                            if (success) {
                                isWifiConnected = true
                                val name = json.optString("device_name", host)
                                deviceName = name
                                prefs.edit().putString("server_ip", host).apply()

                                runOnUiThread {
                                    tvDeviceName.text = "$deviceName (Wi-Fi)"
                                    dotStatus.setBackgroundColor(Color.parseColor("#10B981")) // Green
                                    Toast.makeText(this@MainActivity, "Connected to $deviceName", Toast.LENGTH_SHORT).show()
                                }
                            } else {
                                runOnUiThread {
                                    tvDeviceName.text = "PIN Required"
                                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Error parsing WS message: $text", e)
                }
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "WebSocket failed: ${t.message}")
                isWifiConnected = false
                runOnUiThread {
                    tvDeviceName.text = "Disconnected (Tap to Connect)"
                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                }
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                isWifiConnected = false
                runOnUiThread {
                    tvDeviceName.text = "Disconnected (Tap to Connect)"
                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                }
            }
        })
    }

    private fun disconnectWifi() {
        isWifiConnected = false
        try {
            webSocket?.close(1000, "Switching transport")
        } catch (e: Exception) {
            // ignore
        }
        webSocket = null
    }

    // =========================================================================
    // SUBNET AUTO-DISCOVERY SCANNER
    // =========================================================================

    private fun scanLocalSubnet() {
        if (isScanning.getAndSet(true)) return

        runOnUiThread {
            tvDeviceName.text = "Scanning Wi-Fi network..."
            dotStatus.setBackgroundColor(Color.parseColor("#3B82F6")) // Blue
            Toast.makeText(this, "Scanning local Wi-Fi for ConKey laptop...", Toast.LENGTH_SHORT).show()
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

                // Probe current host first
                try {
                    val req = Request.Builder().url("http://$currentHost:8765/api/device").build()
                    val resp = fastClient.newCall(req).execute()
                    if (resp.isSuccessful) {
                        val body = resp.body?.string() ?: ""
                        if (body.contains("conkey")) {
                            found = true
                            connectToWifiServer(currentHost, 8765)
                        }
                    }
                } catch (e: Exception) {
                    // try subnet
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
                                // Ignore non-responsive host
                            }
                        }
                    }
                    scanPool.shutdown()
                    scanPool.awaitTermination(3, TimeUnit.SECONDS)
                }

                if (!found) {
                    runOnUiThread {
                        tvDeviceName.text = "Laptop not found (Check IP)"
                        dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                        Toast.makeText(this@MainActivity, "Could not find ConKey laptop on Wi-Fi. Tap to enter IP.", Toast.LENGTH_LONG).show()
                    }
                }
            } finally {
                isScanning.set(false)
            }
        }
    }

    // =========================================================================
    // BLUETOOTH CONNECTION ENGINE (SECONDARY FALLBACK)
    // =========================================================================

    private fun checkBluetoothPermissionsAndOpen() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val hasConnect = checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
            val hasScan = checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
            if (!hasConnect || !hasScan) {
                requestPermissions(arrayOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN), REQUEST_BT_PERMS)
                return
            }
        }
        showPairedBluetoothDevicesDialog()
    }

    @SuppressLint("MissingPermission")
    private fun showPairedBluetoothDevicesDialog() {
        if (bluetoothAdapter == null || !bluetoothAdapter!!.isEnabled) {
            Toast.makeText(this, "Please enable Bluetooth first", Toast.LENGTH_SHORT).show()
            startActivity(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            return
        }

        val bonded = bluetoothAdapter?.bondedDevices?.toList() ?: emptyList()
        val items = mutableListOf<String>()
        for (d in bonded) {
            items.add("${d.name}\n${d.address}")
        }
        items.add("⚙ Open Bluetooth Settings...")

        AlertDialog.Builder(this)
            .setTitle("Select Bluetooth Device")
            .setItems(items.toTypedArray()) { _, which ->
                if (which == bonded.size) {
                    startActivity(Intent(Settings.ACTION_BLUETOOTH_SETTINGS))
                } else {
                    connectToBluetoothDevice(bonded[which])
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    @SuppressLint("MissingPermission")
    private fun connectToBluetoothDevice(device: BluetoothDevice) {
        disconnectWifi()
        disconnectBluetooth()

        val devName = device.name ?: device.address
        runOnUiThread {
            tvDeviceName.text = "Connecting to $devName (BT)..."
            dotStatus.setBackgroundColor(Color.parseColor("#F59E0B"))
        }

        networkExecutor.execute {
            var socket: BluetoothSocket? = null
            var success = false

            try {
                socket = device.createInsecureRfcommSocketToServiceRecord(SPP_UUID)
                socket.connect()
                success = true
            } catch (e1: Exception) {
                try {
                    val method = device.javaClass.getMethod("createInsecureRfcommSocket", Int::class.javaPrimitiveType)
                    socket = method.invoke(device, 4) as? BluetoothSocket
                    socket?.connect()
                    success = true
                } catch (e2: Exception) {
                    success = false
                }
            }

            if (success && socket != null) {
                bluetoothSocket = socket
                btOutputStream = socket.outputStream
                isBtConnected = true

                runOnUiThread {
                    tvDeviceName.text = "$devName (Bluetooth)"
                    dotStatus.setBackgroundColor(Color.parseColor("#10B981"))
                    Toast.makeText(this@MainActivity, "Connected via Bluetooth to $devName", Toast.LENGTH_SHORT).show()
                }
            } else {
                runOnUiThread {
                    tvDeviceName.text = "Bluetooth Failed"
                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle("Bluetooth Notice")
                        .setMessage("Windows OS rejected Bluetooth SPP socket connection (lacks SDP record in Windows driver).\n\nWi-Fi connection is instant, low-latency, and recommended.")
                        .setPositiveButton("Connect via Wi-Fi") { _, _ -> connectToWifiServer(currentHost, currentPort) }
                        .setNegativeButton("Close", null)
                        .show()
                }
            }
        }
    }

    private fun disconnectBluetooth() {
        isBtConnected = false
        networkExecutor.execute {
            try {
                btOutputStream?.close()
                bluetoothSocket?.close()
            } catch (e: Exception) {
                // ignore
            }
            btOutputStream = null
            bluetoothSocket = null
        }
    }

    // =========================================================================
    // COMMAND DISPATCHER (TRANSPARENTLY SENDS TO WI-FI OR BLUETOOTH)
    // =========================================================================

    private fun sendCommand(type: String, payload: JSONObject) {
        if (!isWifiConnected && !isBtConnected) {
            runOnUiThread {
                Toast.makeText(this, "Not connected. Tap header to connect.", Toast.LENGTH_SHORT).show()
            }
            return
        }

        networkExecutor.execute {
            try {
                val json = JSONObject().apply {
                    put("type", type)
                    put("payload", payload)
                }

                if (isWifiConnected && webSocket != null) {
                    webSocket?.send(json.toString())
                } else if (isBtConnected && btOutputStream != null) {
                    val packet = (json.toString() + "\n").toByteArray(Charsets.UTF_8)
                    btOutputStream?.write(packet)
                    btOutputStream?.flush()
                }
            } catch (e: Exception) {
                Log.w(TAG, "Send command failed: ${e.message}")
            }
        }
    }

    private fun sendKey(key: String) {
        sendCommand("key_press", JSONObject().put("key", key))
    }

    private fun sendText(text: String) {
        sendCommand("type_text", JSONObject().put("text", text))
    }

    private fun sendMouseClick(button: String) {
        sendCommand("mouse_click", JSONObject().put("button", button))
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
    // CONNECTION SELECTION MENU
    // =========================================================================

    private fun showConnectionMenu() {
        val options = arrayOf(
            "⚡ Connect to Laptop Wi-Fi ($currentHost)",
            "🔍 Auto-Scan Local Wi-Fi Network",
            "📶 Connect via Bluetooth",
            "✏ Enter Laptop IP Manually"
        )

        AlertDialog.Builder(this)
            .setTitle("Connect to ConKey Laptop")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> connectToWifiServer(currentHost, currentPort)
                    1 -> scanLocalSubnet()
                    2 -> checkBluetoothPermissionsAndOpen()
                    3 -> showManualIpDialog()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showManualIpDialog() {
        val input = EditText(this)
        input.setText(currentHost)
        input.setSelection(currentHost.length)

        AlertDialog.Builder(this)
            .setTitle("Enter Laptop IP Address")
            .setMessage("Your laptop's current IP is $currentHost:")
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
    // JAVASCRIPT BRIDGE FOR VIRTUAL KEYBOARD
    // =========================================================================

    inner class KeyboardBridge {
        @JavascriptInterface
        fun sendKey(key: String) {
            vibrate(12)
            sendCommand("key_press", JSONObject().put("key", key))
        }

        @JavascriptInterface
        fun sendCombo(modsJson: String, key: String) {
            vibrate(18)
            val modsArray = JSONArray(modsJson)
            val payload = JSONObject().apply {
                put("modifiers", modsArray)
                put("key", key)
            }
            sendCommand("key_combo", payload)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        disconnectWifi()
        disconnectBluetooth()
        networkExecutor.shutdown()
    }
}
