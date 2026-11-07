import pytest
import time
from host.protocol import (
    parse_command,
    ProtocolError,
    AuthCommand,
    TypeTextCommand,
    KeyPressCommand,
    KeyComboCommand,
    MouseMoveCommand,
    MouseClickCommand,
    PingCommand,
    SessionState,
)

def test_parse_auth():
    cmd = parse_command('{"type": "auth", "payload": {"pin": "1234"}}')
    assert isinstance(cmd, AuthCommand)
    assert cmd.pin == "1234"

def test_parse_type_text():
    cmd = parse_command('{"type": "type_text", "payload": {"text": "hello! A S", "delay": 0.05}}')
    assert isinstance(cmd, TypeTextCommand)
    assert cmd.text == "hello! A S"
    assert cmd.delay == 0.05

def test_parse_key_combo():
    cmd = parse_command('{"type": "key_combo", "payload": {"modifiers": ["CTRL"], "key": "C"}}')
    assert isinstance(cmd, KeyComboCommand)
    assert cmd.modifiers == ["CTRL"]
    assert cmd.key == "C"

def test_parse_mouse():
    cmd_move = parse_command('{"type": "mouse_move", "payload": {"dx": 10, "dy": -5}}')
    assert isinstance(cmd_move, MouseMoveCommand)
    assert cmd_move.dx == 10
    assert cmd_move.dy == -5

    cmd_click = parse_command('{"type": "mouse_click", "payload": {"button": "right"}}')
    assert isinstance(cmd_click, MouseClickCommand)
    assert cmd_click.button == "right"

    cmd_abs = parse_command('{"type": "mouse_move_abs", "payload": {"x": 500, "y": 300}}')
    assert cmd_abs.x == 500
    assert cmd_abs.y == 300

    cmd_touch = parse_command('{"type": "mouse_touch", "payload": {"x": 800, "y": 600, "click": true}}')
    assert cmd_touch.x == 800
    assert cmd_touch.y == 600
    assert cmd_touch.click is True

def test_parse_errors():
    with pytest.raises(ProtocolError):
        parse_command("not a json")
    with pytest.raises(ProtocolError):
        parse_command('{"type": "unknown_type"}')
    with pytest.raises(ProtocolError):
        parse_command('{"type": "auth", "payload": {}}')
    with pytest.raises(ProtocolError):
        parse_command('{"type": "key_combo", "payload": {"modifiers": "not a list"}}')

def test_session_state_auth_and_lockout():
    session = SessionState()
    assert not session.authenticated
    assert not session.is_locked_out()

    # Wrong PIN attempts
    for _ in range(4):
        assert not session.authenticate("wrong", "secret_123")
        assert not session.authenticated
        assert not session.is_locked_out()

    # 5th attempt triggers lockout
    assert not session.authenticate("wrong", "secret_123")
    assert session.is_locked_out()
    assert not session.authenticate("secret_123", "secret_123")  # Blocked while locked out

    # Reset lockout for testing success
    session.lockout_until = 0.0
    assert session.authenticate("secret_123", "secret_123")
    assert session.authenticated
    assert session.failed_attempts == 0
