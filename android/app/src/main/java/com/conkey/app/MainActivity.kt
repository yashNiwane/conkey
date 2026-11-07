package com.conkey.app

import android.app.Activity
import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
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
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var tvStatus: TextView
    private lateinit var cardConnection: View
    private lateinit var etHostIp: EditText
    private lateinit var etPort: EditText
    private lateinit var etPin: EditText
    private lateinit var etTextInput: EditText
    private lateinit var vibrator: Vibrator

    private val httpClient = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var webSocket: WebSocket? = null
    private var isConnected = false
    private val discoveryClient = DiscoveryClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("conkey_prefs", Context.MODE_PRIVATE)
        vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator

        tvStatus = findViewById(R.id.tvStatus)
        cardConnection = findViewById(R.id.cardConnection)
        etHostIp = findViewById(R.id.etHostIp)
        etPort = findViewById(R.id.etPort)
        etPin = findViewById(R.id.etPin)
        etTextInput = findViewById(R.id.etTextInput)

        // Restore saved settings
        etHostIp.setText(prefs.getString("host_ip", ""))
        etPort.setText(prefs.getString("host_port", "8765"))
        etPin.setText(prefs.getString("pin", ""))

        findViewById<Button>(R.id.btnToggleSettings).setOnClickListener {
            vibrate(15)
            cardConnection.visibility = if (cardConnection.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }

        findViewById<Button>(R.id.btnAutoDetect).setOnClickListener {
            vibrate(20)
            tvStatus.text = "Scanning..."
            discoveryClient.discover(object : DiscoveryClient.Callback {
                override fun onDiscovered(ip: String, port: Int, hostname: String) {
                    etHostIp.setText(ip)
                    etPort.setText(port.toString())
                    Toast.makeText(this@MainActivity, "Found: $hostname ($ip)", Toast.LENGTH_SHORT).show()
                    tvStatus.text = "Discovered"
                }

                override fun onFailed(error: String) {
                    Toast.makeText(this@MainActivity, "Auto-detect: $error", Toast.LENGTH_SHORT).show()
                    tvStatus.text = "Disconnected"
                }
            })
        }

        findViewById<Button>(R.id.btnConnect).setOnClickListener {
            vibrate(20)
            connect()
        }

        // Text & Typing
        val btnSendText = findViewById<Button>(R.id.btnSendText)
        btnSendText.setOnClickListener {
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

        // Frequently Broken Shortcuts
        bindCombo(R.id.btnCtrlC, listOf("CTRL"), "C")
        bindCombo(R.id.btnCtrlV, listOf("CTRL"), "V")
        bindCombo(R.id.btnCtrlZ, listOf("CTRL"), "Z")
        bindCombo(R.id.btnCtrlX, listOf("CTRL"), "X")
        bindCombo(R.id.btnCtrlA, listOf("CTRL"), "A")
        bindCombo(R.id.btnCtrlS, listOf("CTRL"), "S")
        bindCombo(R.id.btnCtrlF, listOf("CTRL"), "F")
        bindCombo(R.id.btnAltTab, listOf("ALT"), "TAB")

        // Broken Keys Rescue Bar (A, S, !, etc.)
        bindTextButton(R.id.btnKeyCapA, "A")
        bindTextButton(R.id.btnKeyLowA, "a")
        bindTextButton(R.id.btnKeyCapS, "S")
        bindTextButton(R.id.btnKeyLowS, "s")
        bindTextButton(R.id.btnKeyExcl, "!")
        bindTextButton(R.id.btnKeyAt, "@")
        bindTextButton(R.id.btnKeyHash, "#")
        bindTextButton(R.id.btnKeyQuest, "?")

        // Editing & Navigation
        bindKeyButton(R.id.btnBack, "BACKSPACE")
        bindKeyButton(R.id.btnEnter, "ENTER")
        bindKeyButton(R.id.btnTab, "TAB")
        bindKeyButton(R.id.btnEsc, "ESCAPE")
        bindKeyButton(R.id.btnSpace, "SPACE")
        bindKeyButton(R.id.btnDel, "DELETE")
        bindKeyButton(R.id.btnWin, "WIN")
        bindCombo(R.id.btnTaskMgr, listOf("CTRL", "SHIFT"), "ESCAPE")

        bindKeyButton(R.id.btnUp, "UP")
        bindKeyButton(R.id.btnDown, "DOWN")
        bindKeyButton(R.id.btnLeft, "LEFT")
        bindKeyButton(R.id.btnRight, "RIGHT")

        // Trackpad
        setupTrackpad()
    }

    private fun bindCombo(resId: Int, modifiers: List<String>, key: String) {
        findViewById<Button>(resId).setOnClickListener {
            vibrate(25)
            sendCombo(modifiers, key)
        }
    }

    private fun bindTextButton(resId: Int, text: String) {
        findViewById<Button>(resId).setOnClickListener {
            vibrate(20)
            sendText(text)
        }
    }

    private fun bindKeyButton(resId: Int, key: String) {
        findViewById<Button>(resId).setOnClickListener {
            vibrate(20)
            sendKey(key)
        }
    }

    private fun setupTrackpad() {
        val viewTrackpad = findViewById<View>(R.id.viewTrackpad)
        var lastX = 0f
        var lastY = 0f
        var touchStartTime = 0L

        viewTrackpad.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    lastX = event.x
                    lastY = event.y
                    touchStartTime = System.currentTimeMillis()
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    if (event.pointerCount == 1) {
                        val dx = (event.x - lastX).toInt()
                        val dy = (event.y - lastY).toInt()
                        if (dx != 0 || dy != 0) {
                            sendMouseMove(dx * 2, dy * 2)
                            lastX = event.x
                            lastY = event.y
                        }
                    } else if (event.pointerCount == 2) {
                        val dy = ((event.y - lastY) / 10f).toInt()
                        if (dy != 0) {
                            sendMouseScroll(dy)
                            lastY = event.y
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    val duration = System.currentTimeMillis() - touchStartTime
                    if (duration < 200 && event.pointerCount == 1) {
                        vibrate(15)
                        sendMouseClick("left")
                    }
                    true
                }
                else -> false
            }
        }

        findViewById<Button>(R.id.btnLeftClick).setOnClickListener {
            vibrate(20)
            sendMouseClick("left")
        }
        findViewById<Button>(R.id.btnRightClick).setOnClickListener {
            vibrate(20)
            sendMouseClick("right")
        }
    }

    private fun connect() {
        val ip = etHostIp.text.toString().trim()
        val port = etPort.text.toString().trim()
        val pin = etPin.text.toString().trim()

        if (ip.isEmpty()) {
            Toast.makeText(this, "Please enter Laptop IP", Toast.LENGTH_SHORT).show()
            return
        }

        // Save preferences
        prefs.edit()
            .putString("host_ip", ip)
            .putString("host_port", port)
            .putString("pin", pin)
            .apply()

        webSocket?.close(1000, "Reconnecting")

        val wsUrl = "ws://$ip:$port/ws"
        val request = Request.Builder().url(wsUrl).build()

        tvStatus.text = "Connecting..."
        tvStatus.setTextColor(getColor(R.color.accent_warn))

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                runOnUiThread {
                    tvStatus.text = "Authorizing..."
                }
                // Send Auth
                val authPayload = JSONObject().apply {
                    put("pin", pin)
                }
                val authMsg = JSONObject().apply {
                    put("type", "auth")
                    put("payload", authPayload)
                }
                webSocket.send(authMsg.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    when (json.optString("type")) {
                        "auth_result" -> {
                            val success = json.optBoolean("success", false)
                            runOnUiThread {
                                if (success) {
                                    isConnected = true
                                    tvStatus.text = "Connected"
                                    tvStatus.setTextColor(getColor(R.color.status_green))
                                    cardConnection.visibility = View.GONE
                                    Toast.makeText(this@MainActivity, "Connected to Laptop", Toast.LENGTH_SHORT).show()
                                } else {
                                    isConnected = false
                                    tvStatus.text = "Auth Failed"
                                    tvStatus.setTextColor(getColor(R.color.status_red))
                                    Toast.makeText(this@MainActivity, json.optString("message", "Invalid PIN"), Toast.LENGTH_LONG).show()
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                runOnUiThread {
                    isConnected = false
                    tvStatus.text = "Disconnected"
                    tvStatus.setTextColor(getColor(R.color.status_red))
                    Toast.makeText(this@MainActivity, "Connection Error: ${t.localizedMessage}", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                runOnUiThread {
                    isConnected = false
                    tvStatus.text = "Disconnected"
                    tvStatus.setTextColor(getColor(R.color.status_red))
                }
            }
        })
    }

    private fun send(type: String, payload: JSONObject) {
        if (webSocket == null) return
        val msg = JSONObject().apply {
            put("type", type)
            put("payload", payload)
        }
        webSocket?.send(msg.toString())
    }

    private fun sendText(text: String) {
        val payload = JSONObject().apply {
            put("text", text)
        }
        send("type_text", payload)
    }

    private fun sendKey(key: String) {
        val payload = JSONObject().apply {
            put("key", key)
        }
        send("key_press", payload)
    }

    private fun sendCombo(modifiers: List<String>, key: String) {
        val modsArray = JSONArray()
        for (m in modifiers) modsArray.put(m)
        val payload = JSONObject().apply {
            put("modifiers", modsArray)
            put("key", key)
        }
        send("key_combo", payload)
    }

    private fun sendMouseMove(dx: Int, dy: Int) {
        val payload = JSONObject().apply {
            put("dx", dx)
            put("dy", dy)
        }
        send("mouse_move", payload)
    }

    private fun sendMouseClick(button: String) {
        val payload = JSONObject().apply {
            put("button", button)
        }
        send("mouse_click", payload)
    }

    private fun sendMouseScroll(dy: Int) {
        val payload = JSONObject().apply {
            put("dy", dy)
        }
        send("mouse_scroll", payload)
    }

    private fun vibrate(ms: Long) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(ms)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        webSocket?.close(1000, "Activity destroyed")
    }
}
