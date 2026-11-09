import asyncio
import json

import aiohttp
from aiohttp import web, WSMsgType
import pytest

from host.server import ConKeyServer


class FakePhononServer:
    """Minimal stand-in for `fermion serve phonon-2`'s streaming endpoint."""

    def __init__(self):
        self.audio = bytearray()
        self.config = None
        self.port = None
        self.runner = None
        self.app = web.Application()
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/v1/audio/stream", self.handle_stream)

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    async def handle_health(self, request):
        return web.json_response({
            "status": "ok",
            "kind": "speech",
            "model": "FermionResearch/Phonon-2",
            "profile": "five-value",
            "download_bytes": 158127742,
            "decode": {"load_seconds": 0.1, "threads": 4},
            "endpoints": ["/v1/audio/transcriptions", "/v1/audio/stream"],
        })

    async def handle_stream(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        first = await ws.receive()
        assert first.type == WSMsgType.TEXT
        self.config = json.loads(first.data)

        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                self.audio.extend(msg.data)
                await ws.send_json({"type": "partial", "text": "hello"})
            elif msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "end":
                    await ws.send_json({
                        "type": "final",
                        "text": "hello world",
                        "segment": 1,
                    })
                    await ws.send_json({
                        "type": "done",
                        "text": "hello world",
                    })
                    break
        await ws.close()
        return ws


async def receive_until(ws, wanted: str, timeout: float = 5.0) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            msg = await ws.receive()
            assert msg.type == WSMsgType.TEXT, msg
            data = json.loads(msg.data)
            if data.get("type") == wanted:
                return data


@pytest.mark.asyncio
async def test_voice_stream_relay_end_to_end():
    fake = FakePhononServer()
    await fake.start()
    server = ConKeyServer(
        port=8807,
        discovery_port=8806,
        pin="4321",
        voice_enabled=True,
        phonon_port=fake.port,
        phonon_command="__never_spawn__",
    )
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("http://127.0.0.1:8807/ws") as ws:
                greeting = await ws.receive_json()
                assert greeting["type"] == "auth_required"
                assert greeting["voice"] is True

                await ws.send_json({"type": "auth", "payload": {"pin": "4321"}})
                auth = await ws.receive_json()
                assert auth["type"] == "auth_result" and auth["success"] is True

                await ws.send_json({
                    "type": "voice_start",
                    "payload": {
                        "sample_rate": 16000,
                        "format": "pcm_s16le",
                        "auto_type": False,
                    },
                })
                loading = await ws.receive_json()
                assert loading["type"] == "voice_loading"
                ready = await receive_until(ws, "voice_ready")
                assert ready["sample_rate"] == 16000
                assert ready["format"] == "pcm_s16le"
                assert ready["streaming"] is True
                assert fake.config == {
                    "sample_rate": 16000,
                    "format": "pcm_s16le",
                }

                pcm = b"\x00\x01" * 1600  # 100 ms of PCM16
                await ws.send_bytes(pcm)
                partial = await receive_until(ws, "voice_partial")
                assert partial["text"] == "hello"
                assert bytes(fake.audio) == pcm

                await ws.send_json({"type": "voice_stop", "payload": {}})
                final = await receive_until(ws, "voice_final")
                assert final["text"] == "hello world"
                assert final["segment"] == 1
                assert final["typed"] is True
                done = await receive_until(ws, "voice_done")
                assert done["text"] == "hello world"

        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8807/api/voice/status") as resp:
                status = await resp.json()
                assert resp.status == 200
                assert status["available"] is True
                assert status["ready"] is True
                assert status["model"] == "FermionResearch/Phonon-2"
                assert status["stream_active"] is False
    finally:
        await server.stop()
        await fake.stop()


@pytest.mark.asyncio
async def test_voice_start_requires_authentication():
    server = ConKeyServer(
        port=8809,
        discovery_port=8808,
        pin="4321",
        voice_enabled=True,
        phonon_port=65533,
        phonon_command="__never_spawn__",
    )
    await server.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("http://127.0.0.1:8809/ws") as ws:
                await ws.receive_json()
                await ws.send_json({"type": "voice_start", "payload": {}})
                error = await ws.receive_json()
                assert error["type"] == "error"
                assert "Authentication required" in error["message"]
    finally:
        await server.stop()
