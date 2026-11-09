"""
Domain models, command parser, and session state machine for ConKey.
Follows principle-model-the-domain and principle-boundary-discipline.
"""

from dataclasses import dataclass, field
import json
import time
from typing import Any, Dict, List, Optional, Set


class ProtocolError(Exception):
    """Raised when an incoming packet violates the protocol schema."""
    pass


@dataclass(frozen=True)
class AuthCommand:
    pin: str


@dataclass(frozen=True)
class TypeTextCommand:
    text: str
    delay: float = 0.0


@dataclass(frozen=True)
class KeyPressCommand:
    key: str
    delay: float = 0.01


@dataclass(frozen=True)
class KeyDownCommand:
    key: str


@dataclass(frozen=True)
class KeyUpCommand:
    key: str


@dataclass(frozen=True)
class KeyComboCommand:
    modifiers: List[str]
    key: str
    delay: float = 0.01


@dataclass(frozen=True)
class MouseMoveCommand:
    dx: int
    dy: int


@dataclass(frozen=True)
class MouseClickCommand:
    button: str = "left"


@dataclass(frozen=True)
class MouseScrollCommand:
    dy: int


@dataclass(frozen=True)
class MouseMoveAbsCommand:
    x: int
    y: int


@dataclass(frozen=True)
class MouseTouchCommand:
    x: int
    y: int
    click: bool = True


@dataclass(frozen=True)
class PingCommand:
    client_time: float


@dataclass(frozen=True)
class VoiceStartCommand:
    """Opens a live 16 kHz mono PCM stream to the laptop's Phonon-2 engine."""

    sample_rate: int = 16000
    audio_format: str = "pcm_s16le"
    auto_type: bool = False


@dataclass(frozen=True)
class VoiceStopCommand:
    """Stops capture, flushes the tail and returns the full transcript."""


@dataclass(frozen=True)
class VoiceCancelCommand:
    """Aborts an in-flight voice session without waiting for a final decode."""


Command = (
    AuthCommand
    | TypeTextCommand
    | KeyPressCommand
    | KeyDownCommand
    | KeyUpCommand
    | KeyComboCommand
    | MouseMoveCommand
    | MouseMoveAbsCommand
    | MouseTouchCommand
    | MouseClickCommand
    | MouseScrollCommand
    | PingCommand
    | VoiceStartCommand
    | VoiceStopCommand
    | VoiceCancelCommand
)


def parse_command(raw_json: str | bytes | dict) -> Command:
    """
    Parses and validates incoming raw payload at the system boundary.
    Internal execution trusts the resulting typed command.
    """
    if isinstance(raw_json, (str, bytes)):
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as err:
            raise ProtocolError(f"Malformed JSON: {err}") from err
    elif isinstance(data := raw_json, dict):
        pass
    else:
        raise ProtocolError("Payload must be JSON string or dict")

    if not isinstance(data, dict):
        raise ProtocolError("Message root must be a JSON object")

    cmd_type = data.get("type")
    payload = data.get("payload", {})

    if not isinstance(cmd_type, str):
        raise ProtocolError("Missing or non-string 'type' field")
    if not isinstance(payload, dict):
        raise ProtocolError("'payload' must be an object")

    if cmd_type == "auth":
        pin = payload.get("pin")
        if not isinstance(pin, str) or not pin.strip():
            raise ProtocolError("Auth payload requires non-empty string 'pin'")
        return AuthCommand(pin=pin.strip())

    if cmd_type == "type_text":
        text = payload.get("text")
        if not isinstance(text, str):
            raise ProtocolError("type_text requires string 'text'")
        delay = float(payload.get("delay", 0.0))
        return TypeTextCommand(text=text, delay=max(0.0, min(delay, 1.0)))

    if cmd_type == "key_press":
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ProtocolError("key_press requires string 'key'")
        delay = float(payload.get("delay", 0.01))
        return KeyPressCommand(key=key.strip(), delay=max(0.0, min(delay, 1.0)))

    if cmd_type == "key_down":
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ProtocolError("key_down requires string 'key'")
        return KeyDownCommand(key=key.strip())

    if cmd_type == "key_up":
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise ProtocolError("key_up requires string 'key'")
        return KeyUpCommand(key=key.strip())

    if cmd_type == "key_combo":
        mods = payload.get("modifiers")
        key = payload.get("key", "")
        if not isinstance(mods, list) or not all(isinstance(m, str) for m in mods):
            raise ProtocolError("key_combo requires list of string 'modifiers'")
        if not isinstance(key, str):
            raise ProtocolError("key_combo requires string 'key'")
        delay = float(payload.get("delay", 0.01))
        return KeyComboCommand(modifiers=mods, key=key.strip(), delay=max(0.0, min(delay, 1.0)))

    if cmd_type == "mouse_move":
        try:
            dx = int(payload.get("dx", 0))
            dy = int(payload.get("dy", 0))
        except (ValueError, TypeError) as err:
            raise ProtocolError("mouse_move dx and dy must be integers") from err
        return MouseMoveCommand(dx=dx, dy=dy)

    if cmd_type == "mouse_click":
        btn = payload.get("button", "left")
        if not isinstance(btn, str):
            raise ProtocolError("mouse_click button must be string")
        return MouseClickCommand(button=btn)

    if cmd_type == "mouse_scroll":
        try:
            dy = int(payload.get("dy", 0))
        except (ValueError, TypeError) as err:
            raise ProtocolError("mouse_scroll dy must be integer") from err
        return MouseScrollCommand(dy=dy)

    if cmd_type == "mouse_move_abs":
        try:
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
        except (ValueError, TypeError) as err:
            raise ProtocolError("mouse_move_abs x and y must be integers") from err
        return MouseMoveAbsCommand(x=x, y=y)

    if cmd_type == "mouse_touch":
        try:
            x = int(payload.get("x", 0))
            y = int(payload.get("y", 0))
            click = bool(payload.get("click", True))
        except (ValueError, TypeError) as err:
            raise ProtocolError("mouse_touch coordinates must be integers") from err
        return MouseTouchCommand(x=x, y=y, click=click)

    if cmd_type == "ping":
        client_time = float(payload.get("timestamp", time.time()))
        return PingCommand(client_time=client_time)

    if cmd_type == "voice_start":
        try:
            sample_rate = int(payload.get("sample_rate", 16000))
        except (ValueError, TypeError) as err:
            raise ProtocolError("voice_start sample_rate must be an integer") from err
        if sample_rate != 16000:
            raise ProtocolError(
                "voice_start requires 16 kHz audio; resample on the client"
            )
        audio_format = payload.get("format", "pcm_s16le")
        if audio_format not in ("pcm_s16le", "pcm_f32le"):
            raise ProtocolError(
                "voice_start format must be 'pcm_s16le' or 'pcm_f32le'"
            )
        return VoiceStartCommand(
            sample_rate=sample_rate,
            audio_format=audio_format,
            auto_type=bool(payload.get("auto_type", False)),
        )

    if cmd_type == "voice_stop":
        return VoiceStopCommand()

    if cmd_type == "voice_cancel":
        return VoiceCancelCommand()

    raise ProtocolError(f"Unsupported command type: '{cmd_type}'")


@dataclass
class SessionState:
    """State machine managing connection security, authentication, and modifier tracking."""
    authenticated: bool = False
    failed_attempts: int = 0
    lockout_until: float = 0.0
    active_modifiers: Set[str] = field(default_factory=set)

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_SEC = 30.0

    def is_locked_out(self) -> bool:
        return time.time() < self.lockout_until

    def authenticate(self, candidate_pin: str, correct_pin: str) -> bool:
        if self.is_locked_out():
            return False

        if candidate_pin == correct_pin:
            self.authenticated = True
            self.failed_attempts = 0
            return True

        self.failed_attempts += 1
        if self.failed_attempts >= self.MAX_FAILED_ATTEMPTS:
            self.lockout_until = time.time() + self.LOCKOUT_DURATION_SEC
        return False
