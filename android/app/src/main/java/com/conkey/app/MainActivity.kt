package com.conkey.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Color
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

class MainActivity : Activity(), DiscoveryClient.Listener {

    private lateinit var prefs: SharedPreferences
    private lateinit var vibrator: Vibrator

    // UI Top bar
    private lateinit var pillDevice: View
    private lateinit var dotStatus: View
    private lateinit var tvDeviceName: TextView
    private lateinit var cardManualSetup: View
    private lateinit var etHostIp: EditText
    private lateinit var etPort: EditText
    private lateinit var etTextInput: EditText

    // Decks
    private lateinit var deckFullPC: View
    private lateinit var deckShortcuts: View
    private lateinit var deckFKeys: View
    private lateinit var deckTouchpad: View

    // Tab buttons
    private lateinit var tabBtnFullPC: Button
    private lateinit var tabBtnShortcuts: Button
    private lateinit var tabBtnFKeys: Button
    private lateinit var tabBtnTouchpad: Button

    // Modifier buttons
    private lateinit var btnCtrl: Button
    private lateinit var btnAlt: Button
    private lateinit var btnShift: Button
    private lateinit var btnWin: Button

    // Sticky Modifier States
    private var isCtrlActive = false
    private var isAltActive = false
    private var isShiftActive = false
    private var isWinActive = false

    // Network & Socket
    private val httpClient = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var webSocket: WebSocket? = null
    private var isConnected = false
    private var currentConnectedIp = ""
    private var currentPin = "2026"

    private lateinit var discoveryClient: DiscoveryClient
    private val discoveredDevices = mutableListOf<DiscoveredDevice>()
    private var autoConnectAttempted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("conkey_prefs", Context.MODE_PRIVATE)
        vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        discoveryClient = DiscoveryClient(this)
        discoveryClient.setListener(this)

        initViews()
        setupTabs()
        setupFullPCKeyboard()
        setupShortcuts()
        setupFKeysAndNumpad()
        setupTouchpad()
        setupDirectTyping()
    }

    override fun onStart() {
        super.onStart()
        discoveryClient.start()
    }

    override fun onStop() {
        super.onStop()
        discoveryClient.stop()
    }

    private fun initViews() {
        pillDevice = findViewById(R.id.pillDevice)
        dotStatus = findViewById(R.id.dotStatus)
        tvDeviceName = findViewById(R.id.tvDeviceName)
        cardManualSetup = findViewById(R.id.cardManualSetup)
        etHostIp = findViewById(R.id.etHostIp)
        etPort = findViewById(R.id.etPort)
        etTextInput = findViewById(R.id.etTextInput)

        deckFullPC = findViewById(R.id.deckFullPC)
        deckShortcuts = findViewById(R.id.deckShortcuts)
        deckFKeys = findViewById(R.id.deckFKeys)
        deckTouchpad = findViewById(R.id.deckTouchpad)

        tabBtnFullPC = findViewById(R.id.tabBtnFullPC)
        tabBtnShortcuts = findViewById(R.id.tabBtnShortcuts)
        tabBtnFKeys = findViewById(R.id.tabBtnFKeys)
        tabBtnTouchpad = findViewById(R.id.tabBtnTouchpad)

        etHostIp.setText(prefs.getString("last_host_ip", ""))
        etPort.setText(prefs.getString("last_port", "8765"))
        currentPin = prefs.getString("last_pin", "2026") ?: "2026"

        findViewById<Button>(R.id.btnToggleManual).setOnClickListener {
            vibrate(15)
            cardManualSetup.visibility = if (cardManualSetup.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }

        findViewById<Button>(R.id.btnManualConnect).setOnClickListener {
            vibrate(20)
            val ip = etHostIp.text.toString().trim()
            val port = etPort.text.toString().trim().toIntOrNull() ?: 8765
            if (ip.isNotEmpty()) {
                connectToDevice(ip, port, currentPin, "Laptop ($ip)")
            }
        }

        pillDevice.setOnClickListener {
            vibrate(20)
            showDevicePicker()
        }
    }

    // --- Discovery & Auto-Connect Callbacks ---

    override fun onDeviceFound(device: DiscoveredDevice) {
        // Auto-connect seamlessly if not connected
        if (!isConnected && (!autoConnectAttempted || device.id == prefs.getString("last_device_id", ""))) {
            autoConnectAttempted = true
            connectToDevice(device.ip, device.port, device.pin, device.name, device.id)
        }
    }

    override fun onDevicesUpdated(deviceList: List<DiscoveredDevice>) {
        discoveredDevices.clear()
        discoveredDevices.addAll(deviceList)

        if (!isConnected) {
            if (discoveredDevices.isEmpty()) {
                tvDeviceName.text = "Searching Wi-Fi..."
                dotStatus.setBackgroundColor(Color.parseColor("#F59E0B"))
            } else if (discoveredDevices.size == 1) {
                val d = discoveredDevices.first()
                tvDeviceName.text = "Found: ${d.name}"
                dotStatus.setBackgroundColor(Color.parseColor("#3B82F6"))
                if (!autoConnectAttempted) {
                    autoConnectAttempted = true
                    connectToDevice(d.ip, d.port, d.pin, d.name, d.id)
                }
            } else {
                tvDeviceName.text = "${discoveredDevices.size} Laptops Found (Tap to Pick)"
                dotStatus.setBackgroundColor(Color.parseColor("#3B82F6"))
            }
        }
    }

    private fun showDevicePicker() {
        if (discoveredDevices.isEmpty()) {
            Toast.makeText(this, "Searching Wi-Fi network for ConKey laptops...", Toast.LENGTH_SHORT).show()
            return
        }
        val names = discoveredDevices.map { "${it.name}\n${it.ip}:${it.port}" }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Select Laptop to Control")
            .setItems(names) { _, which ->
                val selected = discoveredDevices[which]
                connectToDevice(selected.ip, selected.port, selected.pin, selected.name, selected.id)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun connectToDevice(ip: String, port: Int, pin: String, name: String, deviceId: String = "") {
        currentConnectedIp = ip
        currentPin = pin

        prefs.edit()
            .putString("last_host_ip", ip)
            .putString("last_port", port.toString())
            .putString("last_pin", pin)
            .putString("last_device_id", deviceId)
            .putString("last_name", name)
            .apply()

        webSocket?.close(1000, "Switching host")

        val wsUrl = "ws://$ip:$port/ws"
        val request = Request.Builder().url(wsUrl).build()

        tvDeviceName.text = "Connecting to $name..."
        dotStatus.setBackgroundColor(Color.parseColor("#F59E0B"))

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                runOnUiThread {
                    tvDeviceName.text = "Authorizing..."
                }
                val authMsg = JSONObject().apply {
                    put("type", "auth")
                    put("payload", JSONObject().put("pin", currentPin))
                }
                webSocket.send(authMsg.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    if (json.optString("type") == "auth_result") {
                        val success = json.optBoolean("success", false)
                        val serverDevName = json.optString("device_name", name)
                        runOnUiThread {
                            if (success) {
                                isConnected = true
                                tvDeviceName.text = serverDevName
                                dotStatus.setBackgroundColor(Color.parseColor("#10B981"))
                                cardManualSetup.visibility = View.GONE
                                Toast.makeText(this@MainActivity, "Connected to $serverDevName", Toast.LENGTH_SHORT).show()
                            } else {
                                isConnected = false
                                tvDeviceName.text = "Auth Failed"
                                dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                                Toast.makeText(this@MainActivity, "Invalid PIN. Open setup to change PIN.", Toast.LENGTH_LONG).show()
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
                    tvDeviceName.text = "Disconnected"
                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                runOnUiThread {
                    isConnected = false
                    tvDeviceName.text = "Disconnected"
                    dotStatus.setBackgroundColor(Color.parseColor("#EF4444"))
                }
            }
        })
    }

    // --- Tab Switching ---

    private fun setupTabs() {
        tabBtnFullPC.setOnClickListener { switchDeck(deckFullPC, tabBtnFullPC) }
        tabBtnShortcuts.setOnClickListener { switchDeck(deckShortcuts, tabBtnShortcuts) }
        tabBtnFKeys.setOnClickListener { switchDeck(deckFKeys, tabBtnFKeys) }
        tabBtnTouchpad.setOnClickListener { switchDeck(deckTouchpad, tabBtnTouchpad) }
    }

    private fun switchDeck(targetDeck: View, targetBtn: Button) {
        vibrate(15)
        deckFullPC.visibility = View.GONE
        deckShortcuts.visibility = View.GONE
        deckFKeys.visibility = View.GONE
        deckTouchpad.visibility = View.GONE
        targetDeck.visibility = View.VISIBLE

        val tabs = listOf(tabBtnFullPC, tabBtnShortcuts, tabBtnFKeys, tabBtnTouchpad)
        for (btn in tabs) {
            btn.setBackgroundResource(if (btn == targetBtn) R.drawable.bg_btn_accent else R.drawable.bg_btn)
        }
    }

    // --- Full PC Keyboard Setup ---

    private fun setupFullPCKeyboard() {
        btnCtrl = findViewById(R.id.k_ctrl)
        btnAlt = findViewById(R.id.k_alt)
        btnShift = findViewById(R.id.k_shift)
        btnWin = findViewById(R.id.k_win)

        btnCtrl.setOnClickListener { toggleModifier("CTRL") }
        btnAlt.setOnClickListener { toggleModifier("ALT") }
        findViewById<Button>(R.id.k_alt_r).setOnClickListener { toggleModifier("ALT") }
        btnShift.setOnClickListener { toggleModifier("SHIFT") }
        btnWin.setOnClickListener { toggleModifier("WIN") }

        // Row 1
        bindPCKey(R.id.k_esc, "ESCAPE")
        bindPCKey(R.id.k_1, "1")
        bindPCKey(R.id.k_2, "2")
        bindPCKey(R.id.k_3, "3")
        bindPCKey(R.id.k_4, "4")
        bindPCKey(R.id.k_5, "5")
        bindPCKey(R.id.k_6, "6")
        bindPCKey(R.id.k_7, "7")
        bindPCKey(R.id.k_8, "8")
        bindPCKey(R.id.k_9, "9")
        bindPCKey(R.id.k_0, "0")
        bindPCKey(R.id.k_minus, "-")
        bindPCKey(R.id.k_equal, "=")
        bindPCKey(R.id.k_backspace, "BACKSPACE")

        // Row 2
        bindPCKey(R.id.k_tab, "TAB")
        bindPCKey(R.id.k_q, "Q")
        bindPCKey(R.id.k_w, "W")
        bindPCKey(R.id.k_e, "E")
        bindPCKey(R.id.k_r, "R")
        bindPCKey(R.id.k_t, "T")
        bindPCKey(R.id.k_y, "Y")
        bindPCKey(R.id.k_u, "U")
        bindPCKey(R.id.k_i, "I")
        bindPCKey(R.id.k_o, "O")
        bindPCKey(R.id.k_p, "P")
        bindPCKey(R.id.k_lbracket, "[")
        bindPCKey(R.id.k_rbracket, "]")
        bindPCKey(R.id.k_backslash, "\\")

        // Row 3
        bindPCKey(R.id.k_caps, "CAPSLOCK")
        bindPCKey(R.id.k_a, "A")
        bindPCKey(R.id.k_s, "S")
        bindPCKey(R.id.k_d, "D")
        bindPCKey(R.id.k_f, "F")
        bindPCKey(R.id.k_g, "G")
        bindPCKey(R.id.k_h, "H")
        bindPCKey(R.id.k_j, "J")
        bindPCKey(R.id.k_k, "K")
        bindPCKey(R.id.k_l, "L")
        bindPCKey(R.id.k_semicolon, ";")
        bindPCKey(R.id.k_quote, "'")
        bindPCKey(R.id.k_enter, "ENTER")

        // Row 4
        bindPCKey(R.id.k_z, "Z")
        bindPCKey(R.id.k_x, "X")
        bindPCKey(R.id.k_c, "C")
        bindPCKey(R.id.k_v, "V")
        bindPCKey(R.id.k_b, "B")
        bindPCKey(R.id.k_n, "N")
        bindPCKey(R.id.k_m, "M")
        bindPCKey(R.id.k_comma, ",")
        bindPCKey(R.id.k_period, ".")
        bindPCKey(R.id.k_slash, "/")
        bindPCKey(R.id.k_up, "UP")
        bindPCKey(R.id.k_del, "DELETE")

        // Row 5
        bindPCKey(R.id.k_space, "SPACE")
        bindPCKey(R.id.k_left, "LEFT")
        bindPCKey(R.id.k_down, "DOWN")
        bindPCKey(R.id.k_right, "RIGHT")

        // Quick Dead Keys Rescue
        bindDirectText(R.id.q_excl, "!")
        bindDirectText(R.id.q_cap_a, "A")
        bindDirectText(R.id.q_low_a, "a")
        bindDirectText(R.id.q_cap_s, "S")
        bindDirectText(R.id.q_low_s, "s")
        bindDirectText(R.id.q_at, "@")
        bindDirectText(R.id.q_hash, "#")
        bindDirectText(R.id.q_quest, "?")
    }

    private fun toggleModifier(mod: String) {
        vibrate(20)
        when (mod) {
            "CTRL" -> {
                isCtrlActive = !isCtrlActive
                btnCtrl.setBackgroundResource(if (isCtrlActive) R.drawable.bg_btn_modifier_active else R.drawable.bg_btn)
            }
            "ALT" -> {
                isAltActive = !isAltActive
                btnAlt.setBackgroundResource(if (isAltActive) R.drawable.bg_btn_modifier_active else R.drawable.bg_btn)
            }
            "SHIFT" -> {
                isShiftActive = !isShiftActive
                btnShift.setBackgroundResource(if (isShiftActive) R.drawable.bg_btn_modifier_active else R.drawable.bg_btn)
            }
            "WIN" -> {
                isWinActive = !isWinActive
                btnWin.setBackgroundResource(if (isWinActive) R.drawable.bg_btn_modifier_active else R.drawable.bg_btn)
            }
        }
    }

    private fun clearModifiers() {
        if (isCtrlActive || isAltActive || isShiftActive || isWinActive) {
            isCtrlActive = false
            isAltActive = false
            isShiftActive = false
            isWinActive = false
            btnCtrl.setBackgroundResource(R.drawable.bg_btn)
            btnAlt.setBackgroundResource(R.drawable.bg_btn)
            btnShift.setBackgroundResource(R.drawable.bg_btn)
            btnWin.setBackgroundResource(R.drawable.bg_btn)
        }
    }

    private fun bindPCKey(resId: Int, key: String) {
        findViewById<Button>(resId).setOnClickListener {
            vibrate(18)
            val mods = mutableListOf<String>()
            if (isCtrlActive) mods.add("CTRL")
            if (isAltActive) mods.add("ALT")
            if (isShiftActive) mods.add("SHIFT")
            if (isWinActive) mods.add("WIN")

            if (mods.isNotEmpty()) {
                sendCombo(mods, key)
                clearModifiers()
            } else {
                sendKey(key)
            }
        }
    }

    private fun bindDirectText(resId: Int, text: String) {
        findViewById<Button>(resId).setOnClickListener {
            vibrate(18)
            sendText(text)
        }
    }

    // --- Shortcuts Setup ---

    private fun setupShortcuts() {
        bindCombo(R.id.sc_ctrl_c, listOf("CTRL"), "C")
        bindCombo(R.id.sc_ctrl_v, listOf("CTRL"), "V")
        bindCombo(R.id.sc_ctrl_x, listOf("CTRL"), "X")
        bindCombo(R.id.sc_ctrl_a, listOf("CTRL"), "A")
        bindCombo(R.id.sc_ctrl_z, listOf("CTRL"), "Z")
        bindCombo(R.id.sc_ctrl_y, listOf("CTRL"), "Y")
        bindCombo(R.id.sc_ctrl_s, listOf("CTRL"), "S")
        bindCombo(R.id.sc_ctrl_f, listOf("CTRL"), "F")

        bindCombo(R.id.sc_alt_tab, listOf("ALT"), "TAB")
        bindCombo(R.id.sc_alt_f4, listOf("ALT"), "F4")
        bindCombo(R.id.sc_win_d, listOf("WIN"), "D")
        bindCombo(R.id.sc_win_tab, listOf("WIN"), "TAB")
        bindCombo(R.id.sc_win_r, listOf("WIN"), "R")
        bindCombo(R.id.sc_win_e, listOf("WIN"), "E")
        bindCombo(R.id.sc_taskmgr, listOf("CTRL", "SHIFT"), "ESCAPE")
        bindCombo(R.id.sc_win_l, listOf("WIN"), "L")

        bindCombo(R.id.sc_ctrl_t, listOf("CTRL"), "T")
        bindCombo(R.id.sc_ctrl_w, listOf("CTRL"), "W")
        bindCombo(R.id.sc_ctrl_r, listOf("CTRL"), "R")
        bindCombo(R.id.sc_ctrl_shift_t, listOf("CTRL", "SHIFT"), "T")
        bindCombo(R.id.sc_ctrl_p, listOf("CTRL"), "P")
        bindKey(R.id.sc_f5, "F5")
        bindKey(R.id.sc_f11, "F11")
        bindCombo(R.id.sc_ctrl_n, listOf("CTRL"), "N")
    }

    // --- F-Keys & Numpad Setup ---

    private fun setupFKeysAndNumpad() {
        bindKey(R.id.fn_f1, "F1")
        bindKey(R.id.fn_f2, "F2")
        bindKey(R.id.fn_f3, "F3")
        bindKey(R.id.fn_f4, "F4")
        bindKey(R.id.fn_f5, "F5")
        bindKey(R.id.fn_f6, "F6")
        bindKey(R.id.fn_f7, "F7")
        bindKey(R.id.fn_f8, "F8")
        bindKey(R.id.fn_f9, "F9")
        bindKey(R.id.fn_f10, "F10")
        bindKey(R.id.fn_f11, "F11")
        bindKey(R.id.fn_f12, "F12")

        bindKey(R.id.nav_prtscn, "PRINTSCREEN")
        bindKey(R.id.nav_ins, "INSERT")
        bindKey(R.id.nav_home, "HOME")
        bindKey(R.id.nav_pgup, "PAGEUP")
        bindKey(R.id.nav_del, "DELETE")
        bindKey(R.id.nav_end, "END")
        bindKey(R.id.nav_pgdn, "PAGEDOWN")
        bindKey(R.id.nav_pause, "PAUSE")

        bindKey(R.id.num_lock, "NUMLOCK")
        bindKey(R.id.num_div, "NUMPAD_DIVIDE")
        bindKey(R.id.num_mul, "NUMPAD_MULTIPLY")
        bindKey(R.id.num_sub, "NUMPAD_SUBTRACT")
        bindKey(R.id.num_add, "NUMPAD_ADD")
        bindKey(R.id.num_enter, "ENTER")
        bindKey(R.id.num_dot, "NUMPAD_DECIMAL")

        bindKey(R.id.num_7, "NUMPAD7")
        bindKey(R.id.num_8, "NUMPAD8")
        bindKey(R.id.num_9, "NUMPAD9")
        bindKey(R.id.num_4, "NUMPAD4")
        bindKey(R.id.num_5, "NUMPAD5")
        bindKey(R.id.num_6, "NUMPAD6")
        bindKey(R.id.num_1, "NUMPAD1")
        bindKey(R.id.num_2, "NUMPAD2")
        bindKey(R.id.num_3, "NUMPAD3")
        bindKey(R.id.num_0, "NUMPAD0")
        bindDirectText(R.id.num_equal, "=")
    }

    private fun bindKey(resId: Int, key: String) {
        findViewById<Button>(resId).setOnClickListener {
            vibrate(18)
            sendKey(key)
        }
    }

    private fun bindCombo(resId: Int, modifiers: List<String>, key: String) {
        findViewById<Button>(resId).setOnClickListener {
            vibrate(22)
            sendCombo(modifiers, key)
        }
    }

    // --- Touchpad Setup ---

    private fun setupTouchpad() {
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

    // --- Direct Smart Typing Bar ---

    private fun setupDirectTyping() {
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
    }

    // --- Protocol Wire Senders ---

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
