package com.conkey.app

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

data class DiscoveredDevice(
    val id: String,
    val name: String,
    val ip: String,
    val port: Int,
    val pin: String,
    var lastSeen: Long = System.currentTimeMillis()
)

class DiscoveryClient(private val context: Context) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private var scheduler: ScheduledExecutorService? = null
    private var listenSocket: DatagramSocket? = null
    private var isRunning = false

    private val devices = ConcurrentHashMap<String, DiscoveredDevice>()

    interface Listener {
        fun onDevicesUpdated(deviceList: List<DiscoveredDevice>)
        fun onDeviceFound(device: DiscoveredDevice)
    }

    private var listener: Listener? = null

    fun setListener(listener: Listener?) {
        this.listener = listener
    }

    fun start() {
        if (isRunning) return
        isRunning = true
        scheduler = Executors.newScheduledThreadPool(2)

        // 1. Listen loop for beacons and replies
        scheduler?.execute {
            listenLoop()
        }

        // 2. Periodic broadcast probe sender (every 2 seconds)
        scheduler?.scheduleWithFixedDelay({
            sendProbe()
            pruneStaleDevices()
        }, 0, 2000, TimeUnit.MILLISECONDS)
    }

    fun stop() {
        isRunning = false
        try {
            listenSocket?.close()
        } catch (e: Exception) {
            // ignore
        }
        scheduler?.shutdownNow()
        scheduler = null
    }

    private fun listenLoop() {
        try {
            listenSocket = DatagramSocket(8766)
            listenSocket?.broadcast = true
            val buffer = ByteArray(2048)

            while (isRunning) {
                val packet = DatagramPacket(buffer, buffer.size)
                listenSocket?.receive(packet)

                val text = String(packet.data, 0, packet.length).trim()
                if (text.startsWith("{") && text.endsWith("}")) {
                    try {
                        val json = JSONObject(text)
                        if (json.optString("service") == "conkey") {
                            val id = json.optString("device_id", packet.address.hostAddress ?: "")
                            val name = json.optString("name", json.optString("hostname", "Laptop"))
                            val ip = json.optString("ip", packet.address.hostAddress ?: "127.0.0.1")
                            val port = json.optInt("port", 8765)
                            val pin = json.optString("pin", "2026")

                            val device = DiscoveredDevice(
                                id = id,
                                name = name,
                                ip = ip,
                                port = port,
                                pin = pin,
                                lastSeen = System.currentTimeMillis()
                            )

                            val isNew = !devices.containsKey(id)
                            devices[id] = device

                            mainHandler.post {
                                if (isNew) {
                                    listener?.onDeviceFound(device)
                                }
                                listener?.onDevicesUpdated(devices.values.toList())
                            }
                        }
                    } catch (e: Exception) {
                        // ignore malformed packet
                    }
                }
            }
        } catch (e: Exception) {
            // Socket closed or network change
        }
    }

    private fun sendProbe() {
        var socket: DatagramSocket? = null
        try {
            socket = DatagramSocket()
            socket.broadcast = true
            val payload = "CONKEY_DISCOVER".toByteArray()

            // Try subnet broadcast and 255.255.255.255
            val broadcastIp = getBroadcastAddress() ?: InetAddress.getByName("255.255.255.255")
            val packet = DatagramPacket(payload, payload.size, broadcastIp, 8766)
            socket.send(packet)
        } catch (e: Exception) {
            // ignore broadcast failures
        } finally {
            socket?.close()
        }
    }

    private fun pruneStaleDevices() {
        val now = System.currentTimeMillis()
        var changed = false
        val it = devices.entries.iterator()
        while (it.hasNext()) {
            val entry = it.next()
            if (now - entry.value.lastSeen > 8000) {
                it.remove()
                changed = true
            }
        }
        if (changed) {
            mainHandler.post {
                listener?.onDevicesUpdated(devices.values.toList())
            }
        }
    }

    private fun getBroadcastAddress(): InetAddress? {
        return try {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            val dhcp = wifi?.dhcpInfo ?: return null
            val broadcast = (dhcp.ipAddress and dhcp.netmask) or dhcp.netmask.inv()
            val quads = ByteArray(4)
            for (k in 0..3) {
                quads[k] = ((broadcast shr k * 8) and 0xFF).toByte()
            }
            InetAddress.getByAddress(quads)
        } catch (e: Exception) {
            null
        }
    }
}
