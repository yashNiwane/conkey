import asyncio
import pytest
import aiohttp
from host.server import ConKeyServer

@pytest.mark.asyncio
async def test_server_e2e_ws_flow():
    test_port = 8799
    test_pin = "4321"
    server = ConKeyServer(port=test_port, discovery_port=8798, pin=test_pin)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Test HTTP Info endpoint
            async with session.get(f"http://127.0.0.1:{test_port}/api/info") as resp:
                assert resp.status == 200
                info = await resp.json()
                assert info["service"] == "conkey"
                assert info["pin_required"] is True

            # 1.1 Test APK Download endpoint
            async with session.get(f"http://127.0.0.1:{test_port}/download/conkey.apk") as resp:
                assert resp.status == 200
                assert resp.headers["Content-Type"] == "application/vnd.android.package-archive"
                body = await resp.read()
                assert len(body) > 1000000  # verified APK > 1MB

            # 2. Test WebSocket connection
            async with session.ws_connect(f"http://127.0.0.1:{test_port}/ws") as ws:
                # Initial greeting
                msg = await ws.receive_json()
                assert msg["type"] == "auth_required"

                # Reject unauthenticated action
                await ws.send_json({"type": "type_text", "payload": {"text": "hello"}})
                err = await ws.receive_json()
                assert err["type"] == "error"

                # Send wrong PIN
                await ws.send_json({"type": "auth", "payload": {"pin": "0000"}})
                auth_fail = await ws.receive_json()
                assert auth_fail["type"] == "auth_result"
                assert auth_fail["success"] is False

                # Send correct PIN
                await ws.send_json({"type": "auth", "payload": {"pin": test_pin}})
                auth_ok = await ws.receive_json()
                assert auth_ok["type"] == "auth_result"
                assert auth_ok["success"] is True

                # Send Type Text (e.g. typing exclamation and letters)
                await ws.send_json({"type": "type_text", "payload": {"text": "!A"}})
                ack_type = await ws.receive_json()
                assert ack_type["type"] == "ack"
                assert ack_type["action"] == "type_text"

                # Send Key Combo (Ctrl+C)
                await ws.send_json({"type": "key_combo", "payload": {"modifiers": ["CTRL"], "key": "C"}})
                ack_combo = await ws.receive_json()
                assert ack_combo["type"] == "ack"
                assert ack_combo["action"] == "key_combo"

                # Send Ping
                await ws.send_json({"type": "ping", "payload": {"timestamp": 123456.0}})
                pong = await ws.receive_json()
                assert pong["type"] == "pong"
                assert pong["client_time"] == 123456.0

    finally:
        await server.stop()
