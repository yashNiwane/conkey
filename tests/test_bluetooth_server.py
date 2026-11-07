import time
from host.bt_server import BluetoothServer, get_local_bluetooth_mac

def test_local_bluetooth_mac_detected():
    mac = get_local_bluetooth_mac()
    assert mac is not None
    assert len(mac) == 17
    assert mac.count(":") == 5

def test_bluetooth_server_start_stop():
    # Use channel 5 for test to avoid collision
    bt = BluetoothServer(channel=5)
    try:
        bt.start()
        time.sleep(0.2)
        assert bt.running is True
    finally:
        bt.stop()
        assert bt.running is False
