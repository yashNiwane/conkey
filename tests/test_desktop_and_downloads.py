import os
from pathlib import Path
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from host.server import ConKeyServer
from host import keyboard_driver
from host import linux_keyboard


class TestDownloadsAndDesktop(AioHTTPTestCase):
    async def get_application(self):
        self.server = ConKeyServer(port=8769, pin="1234", voice_enabled=False)
        return self.server.app

    async def test_api_downloads(self):
        resp = await self.client.request("GET", "/api/downloads")
        assert resp.status == 200
        data = await resp.json()
        assert "downloads" in data
        platforms = {item["platform"] for item in data["downloads"]}
        assert "android" in platforms
        assert "windows" in platforms
        assert "linux" in platforms

    async def test_download_routes_exist(self):
        # Test windows download route
        resp_win = await self.client.request("HEAD", "/download/conkey-windows.zip")
        assert resp_win.status == 200
        assert resp_win.headers.get("Content-Type") == "application/zip"

        # Test linux download route
        resp_linux = await self.client.request("HEAD", "/download/conkey-linux.tar.gz")
        assert resp_linux.status == 200
        assert resp_linux.headers.get("Content-Type") == "application/gzip"

        # Test android download route
        resp_apk = await self.client.request("HEAD", "/download/conkey.apk")
        assert resp_apk.status == 200
        assert "package-archive" in resp_apk.headers.get("Content-Type", "")

    def test_linux_keyboard_mappings(self):
        # Verify essential key mappings in Linux Key Map
        assert "CTRL" in linux_keyboard.LINUX_KEY_MAP
        assert "ALT" in linux_keyboard.LINUX_KEY_MAP
        assert "ENTER" in linux_keyboard.LINUX_KEY_MAP
        assert "SPACE" in linux_keyboard.LINUX_KEY_MAP
        assert linux_keyboard.LINUX_KEY_MAP["A"] == 30
        assert linux_keyboard.LINUX_KEY_MAP["ENTER"] == 28

        # Test xdotool mapping
        assert linux_keyboard.XDOTOOL_MAP["CTRL"] == "Control_L"
        assert linux_keyboard.XDOTOOL_MAP["ALT"] == "Alt_L"
        assert linux_keyboard.XDOTOOL_MAP["ENTER"] == "Return"
        assert linux_keyboard.XDOTOOL_MAP["SPACE"] == "space"

    def test_keyboard_driver_routing(self):
        # On this OS, driver should have valid callable functions
        assert callable(keyboard_driver.key_down)
        assert callable(keyboard_driver.key_up)
        assert callable(keyboard_driver.type_text)
        assert callable(keyboard_driver.sync_live_text)
        assert callable(keyboard_driver.mouse_move)
        assert callable(keyboard_driver.mouse_click)
