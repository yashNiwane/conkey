package com.conkey.app

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.Executors

class DiscoveryClient {
    private val executor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())

    interface Callback {
        fun onDiscovered(ip: String, port: Int, hostname: String)
        fun onFailed(error: String)
    }

    fun discover(callback: Callback) {
        executor.execute {
            var socket: DatagramSocket? = null
            try {
                socket = DatagramSocket()
                socket.broadcast = true
                socket.soTimeout = 2000

                val payload = "CONKEY_DISCOVER".toByteArray()
                val packet = DatagramPacket(
                    payload,
                    payload.size,
                    InetAddress.getByName("255.255.255.255"),
                    8766
                )
                socket.send(packet)

                val buffer = ByteArray(1024)
                val responsePacket = DatagramPacket(buffer, buffer.size)
                socket.receive(responsePacket)

                val responseStr = String(responsePacket.data, 0, responsePacket.length)
                val json = JSONObject(responseStr)
                if (json.optString("service") == "conkey") {
                    val hostIp = responsePacket.address.hostAddress ?: "127.0.0.1"
                    val port = json.optInt("port", 8765)
                    val hostname = json.optString("hostname", "Laptop")

                    mainHandler.post {
                        callback.onDiscovered(hostIp, port, hostname)
                    }
                    return@execute
                }
                mainHandler.post {
                    callback.onFailed("Unknown service response")
                }
            } catch (e: Exception) {
                mainHandler.post {
                    callback.onFailed(e.localizedMessage ?: "Discovery failed")
                }
            } finally {
                socket?.close()
            }
        }
    }
}
