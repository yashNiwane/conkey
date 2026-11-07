import asyncio
import json
import pytest
import aiohttp
from host.server import ConKeyServer
from host.config import load_config

@pytest.mark.asyncio
async def test_device_discovery_card_and_api():
    server = ConKeyServer(port=8795, discovery_port=8794, device_name="Test Rig (ave)")
    await server.start()

    try:
        card = server.get_device_card()
        assert card["service"] == "conkey"
        assert card["name"] == "Test Rig (ave)"
        assert card["port"] == 8795
        assert card["version"] == "2.0"
        assert "ip" in card

        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8795/api/device") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["name"] == "Test Rig (ave)"
                assert data["service"] == "conkey"
    finally:
        await server.stop()
