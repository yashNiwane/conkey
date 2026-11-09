package com.conkey.app

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log

/**
 * Captures 16 kHz mono PCM16 from the phone microphone and emits ~100 ms
 * chunks for the live Phonon-2 stream.
 *
 * Phonon requires exactly 16 kHz, so the phone resamples by recording at
 * 16 kHz directly (AudioRecord accepts it on all supported devices).
 */
class VoiceStreamer(
    private val onChunk: (ByteArray) -> Unit,
    private val onError: (String) -> Unit,
) {
    companion object {
        private const val TAG = "ConKeyVoice"
        const val SAMPLE_RATE = 16000
        private const val CHUNK_BYTES = 3200 // 100 ms of 16-bit mono audio
    }

    @Volatile
    private var running = false
    private var thread: Thread? = null

    val isRunning: Boolean
        get() = running

    fun start(): Boolean {
        if (running) return true
        running = true
        thread = Thread({ captureLoop() }, "ConKey-Voice").apply {
            priority = Thread.MAX_PRIORITY
            start()
        }
        return true
    }

    fun stop() {
        running = false
        thread?.let { worker ->
            try {
                worker.join(700)
            } catch (e: InterruptedException) {
                Thread.currentThread().interrupt()
            }
        }
        thread = null
    }

    @SuppressLint("MissingPermission")
    private fun captureLoop() {
        val minBuffer = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuffer <= 0) {
            running = false
            onError("This phone cannot record 16 kHz mono audio.")
            return
        }

        val record = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuffer * 4, CHUNK_BYTES * 4),
            )
        } catch (e: Exception) {
            running = false
            onError("Could not open the microphone: ${e.message}")
            return
        }

        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            running = false
            onError("The microphone is busy or unavailable.")
            return
        }

        try {
            record.startRecording()
            if (record.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
                onError("The microphone did not start recording.")
                return
            }

            val buffer = ByteArray(CHUNK_BYTES)
            while (running) {
                val read = record.read(buffer, 0, buffer.size)
                if (read > 0) {
                    onChunk(buffer.copyOf(read))
                } else if (read < 0) {
                    onError("Microphone read failed (code $read).")
                    break
                }
            }
        } catch (e: Exception) {
            if (running) {
                Log.w(TAG, "Voice capture stopped", e)
                onError("Voice capture stopped: ${e.message}")
            }
        } finally {
            running = false
            try {
                record.stop()
            } catch (_: Exception) {
            }
            record.release()
        }
    }
}
