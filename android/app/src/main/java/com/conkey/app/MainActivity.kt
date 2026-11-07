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
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.view.View
import android.view.inputmethod.EditorInfo
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStream
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : Activity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var vibrator: Vibrator

    private lateinit var pillDevice: View
    private lateinit var dotStatus: View
    private lateinit var tvDeviceName: TextView
    private lateinit var etTextInput: EditText
    private lateinit var webViewKeyboard: WebView

    private var bluetoothAdapter: BluetoothAdapter? = null
    private var bluetoothSocket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null
    private var isConnected = false
    private val executor = Executors.newSingleThreadExecutor()

    companion object {
        private val SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
        private const val REQUEST_BT_PERMS = 101
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("conkey_prefs", Context.MODE_PRIVATE)
        vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator

        val btManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        bluetoothAdapter = btManager?.adapter ?: BluetoothAdapter.getDefaultAdapter()

        initViews()
        setupWebView()
        checkPermissionsAndAutoConnect()
    }

    private fun initViews() {
        pillDevice = findViewById(R.id.pillDevice)
        dotStatus = findViewById(R.id.dotStatus)
        tvDeviceName = findViewById(R.id.tvDeviceName)
        etTextInput = findViewById(R.id.etTextInput)
        webViewKeyboard = findViewById(R.id.webViewKeyboard)

        pillDevice.setOnClickListener {
            vibrate(20)
            showPairedDevicesDialog()
        }

        findViewById<Button>(R.id.btnBluetoothSettings).setOnClickListener {
            vibrate(20)
            startActivity(Intent(Settings.ACTION_BLUETOOTH_SETTINGS))
        }

        findViewById<Button>(R.id.btnSendText).setOnClickListener {
            val text = etTextInput.text.toString()
            if (text.isNotEmpty()) {
                vibrate(20)
                sendText(text)
                etTextInput.setText("")
            }
        }

        etTextInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND || actionId == EditorInfo.IME_ACTION_DONE) {
                val text = etTextInput.text.toString()
                if (text.isNotEmpty()) {
                    vibrate(20)
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
            vibrate(18)
            sendMouseClick("left")
        }

        findViewById<Button>(R.id.btnRightClick).setOnClickListener {
            vibrate(18)
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

        webViewKeyboard.setBackgroundColor(Color.parseColor("#0F1115"))
        webViewKeyboard.addJavascriptInterface(KeyboardBridge(), "ConKeyBridge")
        webViewKeyboard.loadUrl("file:///android_asset/keyboard/index.html")
    }

    private fun checkPermissionsAndAutoConnect() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val hasConnect = checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
            val hasScan = checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
            if (!hasConnect || !hasScan) {
                requestPermissions(
                    arrayOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN),
                    REQUEST_BT_PERMS
                )
                return
            }
        }
        autoConnectPairedDevice()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_BT_PERMS && grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            autoConnectPairedDevice()
        }
    }

    @SuppressLint("MissingPermission")
    private fun autoConnectPairedDevice() {
        if (bluetoothAdapter == null || !bluetoothAdapter!!.isEnabled) {
            tvDeviceName.text = "Bluetooth Disabled"
            dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
            return
        }

        val bonded = bluetoothAdapter?.bondedDevices?.toList() ?: emptyList()
        if (bonded.isEmpty()) {
            tvDeviceName.text = "No Paired Devices (Tap to Pair)"
            dotStatus.setBackgroundColor(Color.parseColor("#F59E0B"))
            return
        }

        // Check if last connected device is still bonded
        val lastMac = prefs.getString("last_bt_mac", "")
        val target = bonded.find { it.address == lastMac }
            ?: bonded.find { it.name.contains("Laptop", ignoreCase = true) || it.name.contains("ave", ignoreCase = true) }
            ?: if (bonded.size == 1) bonded.first() else null

        if (target != null) {
            connectToBluetoothDevice(target)
        } else {
            tvDeviceName.text = "${bonded.size} Devices (Tap to Choose)"
            dotStatus.setBackgroundColor(Color.parseColor("#3B82F6"))
        }
    }

    @SuppressLint("MissingPermission")
    private fun showPairedDevicesDialog() {
        if (bluetoothAdapter == null || !bluetoothAdapter!!.isEnabled) {
            Toast.makeText(this, "Please turn on Bluetooth first", Toast.LENGTH_SHORT).show()
            startActivity(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
            return
        }

        val bonded = bluetoothAdapter?.bondedDevices?.toList() ?: emptyList()
        val items = mutableListOf<String>()
        for (d in bonded) {
            items.add("${d.name}\n${d.address}")
        }
        items.add("⚙ Pair New Device via Settings...")

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
        disconnectSocket()

        val devName = device.name ?: device.address
        tvDeviceName.text = "Connecting to $devName..."
        dotStatus.setBackgroundColor(Color.parseColor("#F59E0B"))

        executor.execute {
            var socket: BluetoothSocket? = null
            var success = false

            // Try 1: Direct RFCOMM Channel 4
            try {
                val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
                socket = method.invoke(device, 4) as? BluetoothSocket
                socket?.connect()
                success = true
            } catch (e1: Exception) {
                // Try 2: Insecure RFCOMM Channel 4
                try {
                    val method = device.javaClass.getMethod("createInsecureRfcommSocket", Int::class.javaPrimitiveType)
                    socket = method.invoke(device, 4) as? BluetoothSocket
                    socket?.connect()
                    success = true
                } catch (e2: Exception) {
                    // Try 3: Standard SPP UUID
                    try {
                        socket = device.createInsecureRfcommSocketToServiceRecord(SPP_UUID)
                        socket.connect()
                        success = true
                    } catch (e3: Exception) {
                        try {
                            socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
                            socket.connect()
                            success = true
                        } catch (e4: Exception) {
                            success = false
                        }
                    }
                }
            }

            if (success && socket != null) {
                bluetoothSocket = socket
                outputStream = socket.outputStream
                isConnected = true

                prefs.edit()
                    .putString("last_bt_mac", device.address)
                    .putString("last_bt_name", devName)
                    .apply()

                runOnUiThread {
                    tvDeviceName.text = "$devName (Bluetooth)"
                    dotStatus.setBackgroundColor(Color.parseColor("#10B981"))
                    Toast.makeText(this@MainActivity, "Connected to $devName", Toast.LENGTH_SHORT).show()
                }
            } else {
                runOnUiThread {
                    tvDeviceName.text = "Disconnected"
                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                    Toast.makeText(this@MainActivity, "Connection failed. Make sure ConKey is running on laptop.", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun disconnectSocket() {
        isConnected = false
        try {
            outputStream?.close()
            bluetoothSocket?.close()
        } catch (e: Exception) {
            // ignore
        }
        outputStream = null
        bluetoothSocket = null
    }

    private fun sendBluetoothCommand(type: String, payload: JSONObject) {
        if (!isConnected || outputStream == null) {
            runOnUiThread {
                Toast.makeText(this, "Bluetooth not connected. Tap header to connect.", Toast.LENGTH_SHORT).show()
            }
            return
        }

        executor.execute {
            try {
                val json = JSONObject().apply {
                    put("type", type)
                    put("payload", payload)
                }
                val packet = (json.toString() + "\n").toByteArray(Charsets.UTF_8)
                outputStream?.write(packet)
                outputStream?.flush()
            } catch (e: Exception) {
                runOnUiThread {
                    tvDeviceName.text = "Disconnected"
                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                    disconnectSocket()
                }
            }
        }
    }

    private fun sendKey(key: String) {
        val payload = JSONObject().put("key", key)
        sendBluetoothCommand("key_press", payload)
    }

    private fun sendText(text: String) {
        val payload = JSONObject().put("text", text)
        sendBluetoothCommand("type_text", payload)
    }

    private fun sendMouseClick(button: String) {
        val payload = JSONObject().put("button", button)
        sendBluetoothCommand("mouse_click", payload)
    }

    private fun vibrate(ms: Long) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(ms)
        }
    }

    inner class KeyboardBridge {
        @JavascriptInterface
        fun sendKey(key: String) {
            vibrate(18)
            val payload = JSONObject().put("key", key)
            sendBluetoothCommand("key_press", payload)
        }

        @JavascriptInterface
        fun sendCombo(modsJson: String, key: String) {
            vibrate(22)
            val modsArray = JSONArray(modsJson)
            val payload = JSONObject().apply {
                put("modifiers", modsArray)
                put("key", key)
            }
            sendBluetoothCommand("key_combo", payload)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        disconnectSocket()
    }
}
