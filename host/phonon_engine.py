"""
Phonon-2 streaming speech engine integration.

Runs Fermion Research's Phonon-2 ASR model as a local ``fermion serve``
subprocess and consumes its WebSocket streaming protocol
(``GET /v1/audio/stream``).

Phonon-2 is an English-only, ~158 MB int6-quantized Parakeet TDT model.
The stream accepts 16 kHz mono PCM, emits rolling partial hypotheses every
~0.5 s and finalizes a segment after ~0.7 s of silence (or at 30 s).
The model and the ``fermion-research`` package are third-party components;
see THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import time
from typing import Awaitable, Callable, Deque, Optional

import aiohttp

logger = logging.getLogger("conkey.phonon")

DEFAULT_MODEL = "phonon-2"
DEFAULT_PORT = 8010
DEFAULT_HOST = "127.0.0.1"
SAMPLE_RATE = 16000
SUPPORTED_FORMATS = ("pcm_s16le", "pcm_f32le")
STREAM_PATH = "/v1/audio/stream"
HEALTH_PATH = "/health"


class PhononUnavailable(RuntimeError):
    """The Phonon model server could not be reached or started."""


class PhononStreamError(RuntimeError):
    """A live Phonon transcription stream failed."""


def _script_candidates() -> list[Path]:
    """Places the ``fermion`` console script can live without PATH setup."""
    candidates: list[Path] = []
    exe_dir = Path(sys.executable).parent
    candidates.extend(
        [
            exe_dir / "fermion.exe",
            exe_dir / "fermion",
            exe_dir / "Scripts" / "fermion.exe",
            exe_dir / "Scripts" / "fermion",
        ]
    )
    try:
        users = site.getusersitepackages()
        if isinstance(users, str):
            users = [users]
        for packages in users:
            candidates.append(Path(packages).parent / "Scripts" / "fermion.exe")
            candidates.append(Path(packages).parent / "Scripts" / "fermion")
    except Exception:
        pass
    candidates.extend(
        [
            Path.home() / ".local" / "bin" / "fermion",
            Path.home() / "AppData" / "Roaming" / "Python" / "Scripts" / "fermion.exe",
        ]
    )
    return candidates


def find_fermion_command(explicit: Optional[str] = None) -> Optional[list[str]]:
    """
    Returns the argv prefix that runs the Fermion CLI, or ``None``.

    An explicit command wins (an absolute path or a name resolved on PATH).
    Otherwise the usual console-script locations are checked, and finally a
    ``python -c`` entry point is used so the integration still works when the
    script directory is not on PATH.
    """
    if explicit:
        path = Path(explicit)
        if path.exists():
            return [str(path)]
        found = shutil.which(explicit)
        if found:
            return [found]
        if " " in explicit:
            return explicit.split()
        return None

    found = shutil.which("fermion")
    if found:
        return [found]
    for candidate in _script_candidates():
        if candidate.exists():
            return [str(candidate)]

    try:
        import fermion  # noqa: F401
    except Exception:
        return None
    return [
        sys.executable,
        "-c",
        "from fermion.cli import main; raise SystemExit(main())",
    ]


@dataclass
class PhononSettings:
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    threads: int = 0
    command: str = ""
    startup_timeout: float = 120.0

    @classmethod
    def from_config(cls, cfg) -> "PhononSettings":
        return cls(
            model=getattr(cfg, "phonon_model", DEFAULT_MODEL) or DEFAULT_MODEL,
            port=int(getattr(cfg, "phonon_port", DEFAULT_PORT) or DEFAULT_PORT),
            threads=int(getattr(cfg, "phonon_threads", 0) or 0),
            command=str(getattr(cfg, "phonon_command", "") or ""),
        )


class PhononSupervisor:
    """
    Owns the optional local ``fermion serve`` process.

    An already-running server on the configured port is reused and never
    stopped by this object. The first voice session starts the server if it
    is not running, which keeps host startup fast and tests offline.
    """

    def __init__(self, settings: PhononSettings):
        self.settings = settings
        self._session: Optional[aiohttp.ClientSession] = None
        self._process: Optional[asyncio.subprocess.Process] = None
        self._owned = False
        self._lock = asyncio.Lock()
        self._stderr_task: Optional[asyncio.Task] = None
        self._recent_log: Deque[str] = deque(maxlen=24)
        self._last_error: Optional[str] = None
        self._health_cache: Optional[dict] = None
        self._health_cache_at = 0.0
        self._closed = False

    # ------------------------------------------------------------------ urls
    @property
    def base_url(self) -> str:
        return f"http://{self.settings.host}:{self.settings.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.settings.host}:{self.settings.port}{STREAM_PATH}"

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    async def http_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=90)
            )
        return self._session

    async def health(self, *, use_cache: bool = False) -> Optional[dict]:
        """Returns the Phonon health object, or ``None`` if not reachable."""
        now = time.monotonic()
        if use_cache and self._health_cache and now - self._health_cache_at < 2.0:
            return self._health_cache
        try:
            session = await self.http_session()
            async with session.get(
                self.base_url + HEALTH_PATH,
                timeout=aiohttp.ClientTimeout(total=2.5),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not isinstance(data, dict) or data.get("kind") != "speech":
                    return None
                self._health_cache = data
                self._health_cache_at = now
                return data
        except Exception:
            return None

    # --------------------------------------------------------------- process
    def _server_argv(self) -> list[str]:
        prefix = find_fermion_command(self.settings.command)
        if not prefix:
            raise PhononUnavailable(
                "The Phonon speech engine is not installed. Run "
                "`python -m pip install fermion-research`, then "
                "`python host/voice_setup.py`."
            )
        argv = prefix + [
            "serve",
            self.settings.model,
            "--host",
            self.settings.host,
            "--port",
            str(self.settings.port),
        ]
        if self.settings.threads > 0:
            argv += ["--threads", str(self.settings.threads)]
        return argv

    async def _drain_stderr(self, stream: Optional[asyncio.StreamReader]) -> None:
        if stream is None:
            return
        while True:
            try:
                raw = await stream.readline()
            except (asyncio.CancelledError, Exception):
                return
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            self._recent_log.append(line)
            lowered = line.lower()
            if any(word in lowered for word in ("error", "failed", "traceback", "serving", "ready")):
                logger.info("phonon: %s", line)
            else:
                logger.debug("phonon: %s", line)

    async def ensure_ready(self) -> dict:
        """Starts the model server if needed and returns its health card."""
        if self._closed:
            raise PhononUnavailable("The Phonon supervisor is closed.")
        health = await self.health()
        if health:
            self._last_error = None
            return health

        async with self._lock:
            health = await self.health()
            if health:
                self._last_error = None
                return health

            argv = self._server_argv()
            logger.info("Starting Phonon-2: %s", " ".join(argv))
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            env = os.environ.copy()
            if self.settings.threads > 0:
                env["FERMION_CPU_THREADS"] = str(self.settings.threads)
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    **kwargs,
                )
            except FileNotFoundError as exc:
                raise PhononUnavailable(
                    f"Could not start the Phonon engine: {exc}. Run "
                    "`python -m pip install fermion-research`."
                ) from exc
            except Exception as exc:
                raise PhononUnavailable(f"Could not start the Phonon engine: {exc}") from exc

            self._owned = True
            self._stderr_task = asyncio.create_task(
                self._drain_stderr(self._process.stderr)
            )

            deadline = time.monotonic() + max(5.0, self.settings.startup_timeout)
            while time.monotonic() < deadline:
                proc = self._process
                if proc is not None and proc.returncode is not None:
                    tail = " | ".join(list(self._recent_log)[-4:])
                    self._last_error = (
                        f"The Phonon engine exited during startup (code {proc.returncode})."
                        + (f" {tail}" if tail else "")
                    )
                    raise PhononUnavailable(self._last_error)
                health = await self.health()
                if health:
                    self._last_error = None
                    logger.info(
                        "Phonon-2 ready on %s (model load %.1fs)",
                        self.base_url,
                        float(health.get("decode", {}).get("load_seconds") or 0.0),
                    )
                    return health
                await asyncio.sleep(0.4)

            self._last_error = (
                "Phonon-2 did not become ready in time. The first run may need to "
                "download the model; run `python host/voice_setup.py`."
            )
            raise PhononUnavailable(self._last_error)

    async def stop(self) -> None:
        """Stops a server this supervisor started; leaves external ones up."""
        self._closed = True
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
        if self._owned and self._process and self._process.returncode is None:
            logger.info("Stopping Phonon-2")
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None
        self._owned = False
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None


class PhononStream:
    """
    One live transcription stream over Phonon's WebSocket endpoint.

    ``feed()`` accepts raw PCM in the format announced at ``start()``.
    Partial hypotheses replace one another; ``on_final`` receives one
    completed segment. ``end()`` flushes the tail and waits for ``done``.
    """

    def __init__(
        self,
        supervisor: PhononSupervisor,
        *,
        audio_format: str = "pcm_s16le",
        on_partial: Optional[Callable[[str], Awaitable[None]]] = None,
        on_final: Optional[Callable[[str, int], Awaitable[None]]] = None,
        on_done: Optional[Callable[[str], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        if audio_format not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported Phonon audio format: {audio_format}")
        self._supervisor = supervisor
        self._format = audio_format
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_done = on_done
        self._on_error = on_error
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._receiver: Optional[asyncio.Task] = None
        self._done = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._done_text = ""
        self._error: Optional[str] = None
        self._closed = False

    @property
    def done_text(self) -> str:
        return self._done_text

    @property
    def error(self) -> Optional[str]:
        return self._error

    async def start(self) -> None:
        session = await self._supervisor.http_session()
        try:
            self._ws = await session.ws_connect(
                self._supervisor.ws_url,
                heartbeat=15.0,
                max_msg_size=4 * 1024 * 1024,
            )
        except Exception as exc:
            raise PhononStreamError(f"Could not open the Phonon stream: {exc}") from exc
        await self._ws.send_json(
            {"sample_rate": SAMPLE_RATE, "format": self._format}
        )
        self._receiver = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except Exception:
                        logger.warning("Ignoring malformed Phonon message: %r", msg.data[:200])
                        continue
                    await self._handle_message(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    raise PhononStreamError(f"Phonon stream error: {ws.exception()}")
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closed and self._error is None and not self._done_text:
                self._error = str(exc) or exc.__class__.__name__
                await self._notify_error(self._error)
        finally:
            self._done.set()

    async def _handle_message(self, data: dict) -> None:
        kind = data.get("type")
        if kind == "partial":
            text = str(data.get("text", ""))
            if text and self._on_partial:
                await self._on_partial(text)
        elif kind == "final":
            text = str(data.get("text", ""))
            segment = int(data.get("segment", 0) or 0)
            if text and self._on_final:
                await self._on_final(text, segment)
        elif kind == "done":
            self._done_text = str(data.get("text", ""))
            if self._on_done:
                await self._on_done(self._done_text)
            self._done.set()
        elif kind == "error":
            self._error = str(data.get("message", "Phonon stream error"))
            await self._notify_error(self._error)
            self._done.set()

    async def _notify_error(self, message: str) -> None:
        if self._on_error:
            try:
                await self._on_error(message)
            except Exception:
                logger.exception("Voice error callback failed")

    async def feed(self, pcm: bytes) -> None:
        if not pcm:
            return
        if self._closed or self._ws is None or self._ws.closed:
            raise PhononStreamError("The Phonon stream is closed.")
        async with self._send_lock:
            await self._ws.send_bytes(pcm)

    async def end(self, timeout: float = 20.0) -> str:
        if self._closed:
            return self._done_text
        if self._ws is None or self._ws.closed:
            raise PhononStreamError("The Phonon stream is closed.")
        try:
            await self._ws.send_json({"type": "end"})
        except Exception as exc:
            raise PhononStreamError(f"Could not finish the Phonon stream: {exc}") from exc
        try:
            await asyncio.wait_for(self._done.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PhononStreamError("Phonon did not finish the transcript in time.") from exc
        if self._error:
            raise PhononStreamError(self._error)
        return self._done_text

    async def cancel(self) -> None:
        self._closed = True
        if self._receiver:
            self._receiver.cancel()
            try:
                await self._receiver
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._receiver = None
        if self._ws is not None and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        self._done.set()
