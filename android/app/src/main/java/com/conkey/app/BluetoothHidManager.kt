package com.conkey.app

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHidDevice
import android.bluetooth.BluetoothHidDeviceAppSdpSettings
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.util.Log
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * ConKey Serverless Bluetooth HID Manager
 *
 * Implements standard USB HID over Bluetooth (HID Device Profile).
 * When paired with any laptop, Windows/Mac/Linux automatically loads
 * standard generic HID drivers (hidbth.sys / kbdclass.sys).
 * ZERO client software or background scripts needed on the laptop.
 */
class BluetoothHidManager(
    private val context: Context,
    private val listener: HidStateListener
) {

    interface HidStateListener {
        fun onAppRegistered(registered: Boolean)
        fun onDeviceConnected(device: BluetoothDevice)
        fun onDeviceDisconnected(device: BluetoothDevice)
        fun onDeviceConnecting(device: BluetoothDevice)
        fun onError(message: String)
    }

    private val bluetoothAdapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var hidDevice: BluetoothHidDevice? = null
    private var isAppRegistered = false
    private var activeDevice: BluetoothDevice? = null

    private val reportExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    companion object {
        private const val TAG = "ConKeyHid"

        const val REPORT_ID_KEYBOARD: Byte = 1
        const val REPORT_ID_MOUSE: Byte = 2

        // Modifier Masks
        const val MOD_LCTRL: Byte = 0x01
        const val MOD_LSHIFT: Byte = 0x02
        const val MOD_LALT: Byte = 0x04
        const val MOD_LGUI: Byte = 0x08
        const val MOD_RCTRL: Byte = 0x10
        const val MOD_RSHIFT: Byte = 0x20
        const val MOD_RALT: Byte = 0x40
        const val MOD_RGUI: Byte = 0x80.toByte()

        // Standard USB HID Composite Descriptor (Report ID 1: Keyboard, Report ID 2: Mouse)
        private val HID_REPORT_DESCRIPTOR = byteArrayOf(
            // Keyboard (Report ID 1)
            0x05.toByte(), 0x01.toByte(), // Usage Page (Generic Desktop)
            0x09.toByte(), 0x06.toByte(), // Usage (Keyboard)
            0xA1.toByte(), 0x01.toByte(), // Collection (Application)
            0x85.toByte(), 0x01.toByte(), //   Report ID (1)
            0x05.toByte(), 0x07.toByte(), //   Usage Page (Key Codes)
            0x19.toByte(), 0xE0.toByte(), //   Usage Minimum (224 - Left Control)
            0x29.toByte(), 0xE7.toByte(), //   Usage Maximum (231 - Right GUI)
            0x15.toByte(), 0x00.toByte(), //   Logical Minimum (0)
            0x25.toByte(), 0x01.toByte(), //   Logical Maximum (1)
            0x75.toByte(), 0x01.toByte(), //   Report Size (1 bit)
            0x95.toByte(), 0x08.toByte(), //   Report Count (8 -> 1 modifier byte)
            0x81.toByte(), 0x02.toByte(), //   Input (Data, Variable, Absolute)
            0x95.toByte(), 0x01.toByte(), //   Report Count (1)
            0x75.toByte(), 0x08.toByte(), //   Report Size (8 bits)
            0x81.toByte(), 0x01.toByte(), //   Input (Constant -> 1 reserved byte)
            0x95.toByte(), 0x05.toByte(), //   Report Count (5)
            0x75.toByte(), 0x01.toByte(), //   Report Size (1 bit)
            0x05.toByte(), 0x08.toByte(), //   Usage Page (LEDs)
            0x19.toByte(), 0x01.toByte(), //   Usage Minimum (1)
            0x29.toByte(), 0x05.toByte(), //   Usage Maximum (5)
            0x91.toByte(), 0x02.toByte(), //   Output (Data, Variable, Absolute -> LEDs)
            0x95.toByte(), 0x01.toByte(), //   Report Count (1)
            0x75.toByte(), 0x03.toByte(), //   Report Size (3 bits)
            0x91.toByte(), 0x01.toByte(), //   Output (Constant -> LED padding)
            0x95.toByte(), 0x06.toByte(), //   Report Count (6)
            0x75.toByte(), 0x08.toByte(), //   Report Size (8 bits)
            0x15.toByte(), 0x00.toByte(), //   Logical Minimum (0)
            0x25.toByte(), 0x65.toByte(), //   Logical Maximum (101)
            0x05.toByte(), 0x07.toByte(), //   Usage Page (Key Codes)
            0x19.toByte(), 0x00.toByte(), //   Usage Minimum (0)
            0x29.toByte(), 0x65.toByte(), //   Usage Maximum (101)
            0x81.toByte(), 0x00.toByte(), //   Input (Data, Array -> 6 keys)
            0xC0.toByte(),               // End Collection

            // Mouse (Report ID 2)
            0x05.toByte(), 0x01.toByte(), // Usage Page (Generic Desktop)
            0x09.toByte(), 0x02.toByte(), // Usage (Mouse)
            0xA1.toByte(), 0x01.toByte(), // Collection (Application)
            0x85.toByte(), 0x02.toByte(), //   Report ID (2)
            0x09.toByte(), 0x01.toByte(), //   Usage (Pointer)
            0xA1.toByte(), 0x00.toByte(), //   Collection (Physical)
            0x05.toByte(), 0x09.toByte(), //     Usage Page (Buttons)
            0x19.toByte(), 0x01.toByte(), //     Usage Minimum (Button 1)
            0x29.toByte(), 0x03.toByte(), //     Usage Maximum (Button 3)
            0x15.toByte(), 0x00.toByte(), //     Logical Minimum (0)
            0x25.toByte(), 0x01.toByte(), //     Logical Maximum (1)
            0x95.toByte(), 0x03.toByte(), //     Report Count (3)
            0x75.toByte(), 0x01.toByte(), //     Report Size (1 bit)
            0x81.toByte(), 0x02.toByte(), //     Input (Data, Variable, Absolute -> 3 buttons)
            0x95.toByte(), 0x01.toByte(), //     Report Count (1)
            0x75.toByte(), 0x05.toByte(), //     Report Size (5 bits)
            0x81.toByte(), 0x01.toByte(), //     Input (Constant -> padding)
            0x05.toByte(), 0x01.toByte(), //     Usage Page (Generic Desktop)
            0x09.toByte(), 0x30.toByte(), //     Usage (X)
            0x09.toByte(), 0x31.toByte(), //     Usage (Y)
            0x15.toByte(), 0x81.toByte(), //     Logical Minimum (-127)
            0x25.toByte(), 0x7F.toByte(), //     Logical Maximum (127)
            0x75.toByte(), 0x08.toByte(), //     Report Size (8 bits)
            0x95.toByte(), 0x02.toByte(), //     Report Count (2)
            0x81.toByte(), 0x06.toByte(), //     Input (Data, Variable, Relative -> dX, dY)
            0x09.toByte(), 0x38.toByte(), //     Usage (Wheel)
            0x15.toByte(), 0x81.toByte(), //     Logical Minimum (-127)
            0x25.toByte(), 0x7F.toByte(), //     Logical Maximum (127)
            0x75.toByte(), 0x08.toByte(), //     Report Size (8 bits)
            0x95.toByte(), 0x01.toByte(), //     Report Count (1)
            0x81.toByte(), 0x06.toByte(), //     Input (Data, Variable, Relative -> Wheel)
            0xC0.toByte(),               //   End Collection
            0xC0.toByte()                // End Collection
        )

        // Comprehensive Key Name to USB HID Usage ID Mapping
        val KEY_MAP = mapOf(
            // Letters
            "A" to 0x04.toByte(), "B" to 0x05.toByte(), "C" to 0x06.toByte(), "D" to 0x07.toByte(),
            "E" to 0x08.toByte(), "F" to 0x09.toByte(), "G" to 0x0A.toByte(), "H" to 0x0B.toByte(),
            "I" to 0x0C.toByte(), "J" to 0x0D.toByte(), "K" to 0x0E.toByte(), "L" to 0x0F.toByte(),
            "M" to 0x10.toByte(), "N" to 0x11.toByte(), "O" to 0x12.toByte(), "P" to 0x13.toByte(),
            "Q" to 0x14.toByte(), "R" to 0x15.toByte(), "S" to 0x16.toByte(), "T" to 0x17.toByte(),
            "U" to 0x18.toByte(), "V" to 0x19.toByte(), "W" to 0x1A.toByte(), "X" to 0x1B.toByte(),
            "Y" to 0x1C.toByte(), "Z" to 0x1D.toByte(),

            // Numbers
            "1" to 0x1E.toByte(), "2" to 0x1F.toByte(), "3" to 0x20.toByte(), "4" to 0x21.toByte(),
            "5" to 0x22.toByte(), "6" to 0x23.toByte(), "7" to 0x24.toByte(), "8" to 0x25.toByte(),
            "9" to 0x26.toByte(), "0" to 0x27.toByte(),

            // Standard Keys
            "ENTER" to 0x28.toByte(), "RETURN" to 0x28.toByte(),
            "ESCAPE" to 0x29.toByte(), "ESC" to 0x29.toByte(),
            "BACKSPACE" to 0x2A.toByte(), "BKSP" to 0x2A.toByte(),
            "TAB" to 0x2B.toByte(),
            "SPACE" to 0x2C.toByte(), " " to 0x2C.toByte(),
            "-" to 0x2D.toByte(), "_" to 0x2D.toByte(),
            "=" to 0x2E.toByte(), "+" to 0x2E.toByte(),
            "[" to 0x2F.toByte(), "{" to 0x2F.toByte(),
            "]" to 0x30.toByte(), "}" to 0x30.toByte(),
            "\\" to 0x31.toByte(), "|" to 0x31.toByte(),
            ";" to 0x33.toByte(), ":" to 0x33.toByte(),
            "'" to 0x34.toByte(), "\"" to 0x34.toByte(),
            "`" to 0x35.toByte(), "~" to 0x35.toByte(),
            "," to 0x36.toByte(), "<" to 0x36.toByte(),
            "." to 0x37.toByte(), ">" to 0x37.toByte(),
            "/" to 0x38.toByte(), "?" to 0x38.toByte(),
            "CAPSLOCK" to 0x39.toByte(), "CAPS" to 0x39.toByte(),

            // Function Keys
            "F1" to 0x3A.toByte(), "F2" to 0x3B.toByte(), "F3" to 0x3C.toByte(), "F4" to 0x3D.toByte(),
            "F5" to 0x3E.toByte(), "F6" to 0x3F.toByte(), "F7" to 0x40.toByte(), "F8" to 0x41.toByte(),
            "F9" to 0x42.toByte(), "F10" to 0x43.toByte(), "F11" to 0x44.toByte(), "F12" to 0x45.toByte(),

            // Navigation Cluster
            "PRINTSCREEN" to 0x46.toByte(), "PRTSCN" to 0x46.toByte(),
            "SCROLLLOCK" to 0x47.toByte(),
            "PAUSE" to 0x48.toByte(),
            "INSERT" to 0x49.toByte(), "INS" to 0x49.toByte(),
            "HOME" to 0x4A.toByte(),
            "PAGEUP" to 0x4B.toByte(), "PGUP" to 0x4B.toByte(),
            "DELETE" to 0x4C.toByte(), "DEL" to 0x4C.toByte(),
            "END" to 0x4D.toByte(),
            "PAGEDOWN" to 0x4E.toByte(), "PGDN" to 0x4E.toByte(),
            "RIGHT" to 0x4F.toByte(),
            "LEFT" to 0x50.toByte(),
            "DOWN" to 0x51.toByte(),
            "UP" to 0x52.toByte(),

            // Numpad Keys
            "NUMLOCK" to 0x53.toByte(),
            "NUM_DIV" to 0x54.toByte(),
            "NUM_MUL" to 0x55.toByte(),
            "NUM_SUB" to 0x56.toByte(),
            "NUM_ADD" to 0x57.toByte(),
            "NUM_ENTER" to 0x58.toByte(),
            "NUM_1" to 0x59.toByte(), "NUM_2" to 0x5A.toByte(), "NUM_3" to 0x5B.toByte(),
            "NUM_4" to 0x5C.toByte(), "NUM_5" to 0x5D.toByte(), "NUM_6" to 0x5E.toByte(),
            "NUM_7" to 0x5F.toByte(), "NUM_8" to 0x60.toByte(), "NUM_9" to 0x61.toByte(),
            "NUM_0" to 0x62.toByte(), "NUM_DOT" to 0x63.toByte()
        )
    }

    private val hidCallback = object : BluetoothHidDevice.Callback() {
        override fun onAppStatusChanged(pluggedDevice: BluetoothDevice?, registered: Boolean) {
            Log.i(TAG, "HID App Status Changed: registered=$registered, device=${pluggedDevice?.name}")
            isAppRegistered = registered
            listener.onAppRegistered(registered)
            if (registered && pluggedDevice != null) {
                activeDevice = pluggedDevice
                listener.onDeviceConnected(pluggedDevice)
            }
        }

        override fun onConnectionStateChanged(device: BluetoothDevice, state: Int) {
            val devName = try { device.name ?: device.address } catch (e: SecurityException) { device.address }
            Log.i(TAG, "HID Connection State Changed: $devName -> state=$state")
            when (state) {
                BluetoothProfile.STATE_CONNECTED -> {
                    activeDevice = device
                    listener.onDeviceConnected(device)
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    if (activeDevice?.address == device.address) {
                        activeDevice = null
                    }
                    listener.onDeviceDisconnected(device)
                }
                BluetoothProfile.STATE_CONNECTING -> {
                    listener.onDeviceConnecting(device)
                }
            }
        }

        override fun onGetReport(device: BluetoothDevice, type: Byte, id: Byte, bufferSize: Int) {
            Log.d(TAG, "onGetReport: type=$type, id=$id, bufferSize=$bufferSize")
            if (id == REPORT_ID_KEYBOARD) {
                replyReport(device, type, id, ByteArray(8))
            } else if (id == REPORT_ID_MOUSE) {
                replyReport(device, type, id, ByteArray(4))
            }
        }

        override fun onSetReport(device: BluetoothDevice, type: Byte, id: Byte, data: ByteArray) {
            Log.d(TAG, "onSetReport: type=$type, id=$id, len=${data.size}")
        }

        override fun onSetProtocol(device: BluetoothDevice, protocol: Byte) {
            Log.d(TAG, "onSetProtocol: protocol=$protocol")
        }

        override fun onInterruptData(device: BluetoothDevice, reportId: Byte, data: ByteArray) {
            Log.d(TAG, "onInterruptData: reportId=$reportId")
        }

        override fun onVirtualCableUnplug(device: BluetoothDevice) {
            Log.i(TAG, "onVirtualCableUnplug: $device")
            activeDevice = null
            listener.onDeviceDisconnected(device)
        }
    }

    private val profileListener = object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
            if (profile == BluetoothProfile.HID_DEVICE) {
                Log.i(TAG, "Bluetooth HID Device profile proxy connected")
                hidDevice = proxy as BluetoothHidDevice
                registerHidApp()
            }
        }

        override fun onServiceDisconnected(profile: Int) {
            if (profile == BluetoothProfile.HID_DEVICE) {
                Log.w(TAG, "Bluetooth HID Device profile proxy disconnected")
                hidDevice = null
                isAppRegistered = false
                listener.onAppRegistered(false)
            }
        }
    }

    /**
     * Start the Bluetooth HID Service Listener
     */
    fun start() {
        if (bluetoothAdapter == null) {
            listener.onError("Bluetooth is not supported on this device.")
            return
        }
        try {
            bluetoothAdapter.getProfileProxy(context, profileListener, BluetoothProfile.HID_DEVICE)
        } catch (e: Exception) {
            Log.e(TAG, "Error obtaining HID profile proxy: ${e.message}", e)
            listener.onError("Failed to initialize Bluetooth HID Profile: ${e.message}")
        }
    }

    @SuppressLint("MissingPermission")
    private fun registerHidApp() {
        val hid = hidDevice ?: return
        if (isAppRegistered) return

        try {
            val sdpSettings = BluetoothHidDeviceAppSdpSettings(
                "ConKey Keyboard",
                "ConKey Bluetooth HID Keyboard & Touchpad",
                "ConKey",
                BluetoothHidDevice.SUBCLASS1_COMBO,
                HID_REPORT_DESCRIPTOR
            )

            val success = hid.registerApp(
                sdpSettings,
                null, // inQos
                null, // outQos
                reportExecutor,
                hidCallback
            )
            Log.i(TAG, "Bluetooth HID registerApp called, returned: $success")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to register Bluetooth HID App: ${e.message}", e)
            listener.onError("Failed to register HID descriptor: ${e.message}")
        }
    }

    fun isConnected(): Boolean {
        return activeDevice != null && hidDevice != null && isAppRegistered
    }

    fun getConnectedDevice(): BluetoothDevice? = activeDevice

    @SuppressLint("MissingPermission")
    fun connectDevice(device: BluetoothDevice) {
        val hid = hidDevice ?: return
        reportExecutor.execute {
            try {
                Log.i(TAG, "Connecting HID to device: ${device.name ?: device.address}")
                hid.connect(device)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to connect HID device: ${e.message}", e)
                listener.onError("Could not connect to device: ${e.message}")
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun disconnectDevice() {
        val hid = hidDevice
        val dev = activeDevice
        if (hid != null && dev != null) {
            reportExecutor.execute {
                try {
                    hid.disconnect(dev)
                } catch (e: Exception) {
                    Log.w(TAG, "Error disconnecting device: ${e.message}")
                }
                activeDevice = null
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun replyReport(device: BluetoothDevice, type: Byte, id: Byte, data: ByteArray) {
        try {
            hidDevice?.replyReport(device, type, id, data)
        } catch (e: Exception) {
            Log.w(TAG, "Error in replyReport: ${e.message}")
        }
    }

    // =========================================================================
    // KEYBOARD INPUT DISPATCHING
    // =========================================================================

    fun sendKeyPress(keyName: String) {
        val upperKey = keyName.uppercase().trim()
        val keyCode = KEY_MAP[upperKey] ?: KEY_MAP[keyName] ?: run {
            if (keyName.length == 1) {
                val c = keyName[0]
                if (c in 'a'..'z') KEY_MAP[c.uppercase()]
                else null
            } else null
        }

        if (keyCode == null) {
            Log.w(TAG, "Unknown key name for HID: $keyName")
            return
        }

        var mod: Byte = 0
        if (keyName.length == 1 && keyName[0].isUpperCase()) {
            mod = MOD_LSHIFT
        }

        sendRawKeyboardReport(mod, keyCode)
    }

    fun sendKeyCombo(modifiers: List<String>, keyName: String) {
        var modMask: Byte = 0
        for (m in modifiers) {
            when (m.uppercase().trim()) {
                "CTRL", "CONTROL", "LCTRL" -> modMask = (modMask.toInt() or MOD_LCTRL.toInt()).toByte()
                "RCTRL" -> modMask = (modMask.toInt() or MOD_RCTRL.toInt()).toByte()
                "SHIFT", "LSHIFT" -> modMask = (modMask.toInt() or MOD_LSHIFT.toInt()).toByte()
                "RSHIFT" -> modMask = (modMask.toInt() or MOD_RSHIFT.toInt()).toByte()
                "ALT", "LALT" -> modMask = (modMask.toInt() or MOD_LALT.toInt()).toByte()
                "RALT", "ALTGR" -> modMask = (modMask.toInt() or MOD_RALT.toInt()).toByte()
                "WIN", "GUI", "SUPER", "WINDOWS", "CMD" -> modMask = (modMask.toInt() or MOD_LGUI.toInt()).toByte()
            }
        }

        val upperKey = keyName.uppercase().trim()
        val keyCode = KEY_MAP[upperKey] ?: KEY_MAP[keyName] ?: 0.toByte()

        sendRawKeyboardReport(modMask, keyCode)
    }

    private fun sendRawKeyboardReport(modifier: Byte, keyCode: Byte) {
        val dev = activeDevice ?: return
        val hid = hidDevice ?: return

        reportExecutor.execute {
            try {
                // Key Down Report: [Modifier, Reserved, Key1, Key2, Key3, Key4, Key5, Key6]
                val downReport = ByteArray(8)
                downReport[0] = modifier
                downReport[1] = 0
                downReport[2] = keyCode

                hid.sendReport(dev, REPORT_ID_KEYBOARD.toInt(), downReport)

                // Brief hold time for host OS key detection
                Thread.sleep(12)

                // Key Up (All Keys Released) Report
                val upReport = ByteArray(8)
                hid.sendReport(dev, REPORT_ID_KEYBOARD.toInt(), upReport)

                Thread.sleep(6)
            } catch (e: Exception) {
                Log.w(TAG, "Error sending HID keyboard report: ${e.message}")
            }
        }
    }

    fun sendText(text: String) {
        val dev = activeDevice ?: return
        val hid = hidDevice ?: return

        reportExecutor.execute {
            for (char in text) {
                val pair = getHidCodeForChar(char) ?: continue
                val mod = pair.first
                val code = pair.second

                try {
                    val downReport = ByteArray(8)
                    downReport[0] = mod
                    downReport[1] = 0
                    downReport[2] = code
                    hid.sendReport(dev, REPORT_ID_KEYBOARD.toInt(), downReport)
                    Thread.sleep(10)

                    val upReport = ByteArray(8)
                    hid.sendReport(dev, REPORT_ID_KEYBOARD.toInt(), upReport)
                    Thread.sleep(8)
                } catch (e: Exception) {
                    Log.w(TAG, "Error typing text character: ${e.message}")
                }
            }
        }
    }

    private fun getHidCodeForChar(c: Char): Pair<Byte, Byte>? {
        return when (c) {
            in 'a'..'z' -> Pair(0.toByte(), (0x04 + (c - 'a')).toByte())
            in 'A'..'Z' -> Pair(MOD_LSHIFT, (0x04 + (c - 'A')).toByte())
            in '1'..'9' -> Pair(0.toByte(), (0x1E + (c - '1')).toByte())
            '0' -> Pair(0.toByte(), 0x27.toByte())
            ' ' -> Pair(0.toByte(), 0x2C.toByte())
            '\n' -> Pair(0.toByte(), 0x28.toByte())
            '\t' -> Pair(0.toByte(), 0x2B.toByte())
            '!' -> Pair(MOD_LSHIFT, 0x1E.toByte())
            '@' -> Pair(MOD_LSHIFT, 0x1F.toByte())
            '#' -> Pair(MOD_LSHIFT, 0x20.toByte())
            '$' -> Pair(MOD_LSHIFT, 0x21.toByte())
            '%' -> Pair(MOD_LSHIFT, 0x22.toByte())
            '^' -> Pair(MOD_LSHIFT, 0x23.toByte())
            '&' -> Pair(MOD_LSHIFT, 0x24.toByte())
            '*' -> Pair(MOD_LSHIFT, 0x25.toByte())
            '(' -> Pair(MOD_LSHIFT, 0x26.toByte())
            ')' -> Pair(MOD_LSHIFT, 0x27.toByte())
            '-' -> Pair(0.toByte(), 0x2D.toByte())
            '_' -> Pair(MOD_LSHIFT, 0x2D.toByte())
            '=' -> Pair(0.toByte(), 0x2E.toByte())
            '+' -> Pair(MOD_LSHIFT, 0x2E.toByte())
            '[' -> Pair(0.toByte(), 0x2F.toByte())
            '{' -> Pair(MOD_LSHIFT, 0x2F.toByte())
            ']' -> Pair(0.toByte(), 0x30.toByte())
            '}' -> Pair(MOD_LSHIFT, 0x30.toByte())
            '\\' -> Pair(0.toByte(), 0x31.toByte())
            '|' -> Pair(MOD_LSHIFT, 0x31.toByte())
            ';' -> Pair(0.toByte(), 0x33.toByte())
            ':' -> Pair(MOD_LSHIFT, 0x33.toByte())
            '\'' -> Pair(0.toByte(), 0x34.toByte())
            '"' -> Pair(MOD_LSHIFT, 0x34.toByte())
            '`' -> Pair(0.toByte(), 0x35.toByte())
            '~' -> Pair(MOD_LSHIFT, 0x35.toByte())
            ',' -> Pair(0.toByte(), 0x36.toByte())
            '<' -> Pair(MOD_LSHIFT, 0x36.toByte())
            '.' -> Pair(0.toByte(), 0x37.toByte())
            '>' -> Pair(MOD_LSHIFT, 0x37.toByte())
            '/' -> Pair(0.toByte(), 0x38.toByte())
            '?' -> Pair(MOD_LSHIFT, 0x38.toByte())
            else -> null
        }
    }

    // =========================================================================
    // MOUSE & TOUCHPAD INPUT DISPATCHING
    // =========================================================================

    fun sendMouseMove(dx: Float, dy: Float) {
        val dev = activeDevice ?: return
        val hid = hidDevice ?: return

        val clampedX = dx.toInt().coerceIn(-127, 127).toByte()
        val clampedY = dy.toInt().coerceIn(-127, 127).toByte()

        reportExecutor.execute {
            try {
                val report = ByteArray(4)
                report[0] = 0 // No button pressed during glide
                report[1] = clampedX
                report[2] = clampedY
                report[3] = 0 // No wheel
                hid.sendReport(dev, REPORT_ID_MOUSE.toInt(), report)
            } catch (e: Exception) {
                Log.w(TAG, "Error sending mouse move: ${e.message}")
            }
        }
    }

    fun sendMouseClick(button: String) {
        val dev = activeDevice ?: return
        val hid = hidDevice ?: return

        val buttonMask: Byte = when (button.lowercase()) {
            "right" -> 0x02
            "middle" -> 0x04
            else -> 0x01 // Left
        }

        val isDouble = button.lowercase() == "double"

        reportExecutor.execute {
            try {
                val clickDown = ByteArray(4).apply { this[0] = buttonMask }
                val clickUp = ByteArray(4)

                hid.sendReport(dev, REPORT_ID_MOUSE.toInt(), clickDown)
                Thread.sleep(20)
                hid.sendReport(dev, REPORT_ID_MOUSE.toInt(), clickUp)

                if (isDouble) {
                    Thread.sleep(40)
                    hid.sendReport(dev, REPORT_ID_MOUSE.toInt(), clickDown)
                    Thread.sleep(20)
                    hid.sendReport(dev, REPORT_ID_MOUSE.toInt(), clickUp)
                }
            } catch (e: Exception) {
                Log.w(TAG, "Error sending mouse click: ${e.message}")
            }
        }
    }

    fun sendMouseScroll(dy: Float) {
        val dev = activeDevice ?: return
        val hid = hidDevice ?: return

        val wheelVal = dy.toInt().coerceIn(-127, 127).toByte()

        reportExecutor.execute {
            try {
                val report = ByteArray(4)
                report[0] = 0
                report[1] = 0
                report[2] = 0
                report[3] = wheelVal
                hid.sendReport(dev, REPORT_ID_MOUSE.toInt(), report)
            } catch (e: Exception) {
                Log.w(TAG, "Error sending mouse scroll: ${e.message}")
            }
        }
    }

    fun stop() {
        disconnectDevice()
        try {
            hidDevice?.unregisterApp()
            bluetoothAdapter?.closeProfileProxy(BluetoothProfile.HID_DEVICE, hidDevice)
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping HID manager: ${e.message}")
        }
        reportExecutor.shutdown()
    }
}
