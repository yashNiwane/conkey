// ConKey Mobile Web Client with Full PC Layout and Sticky Modifiers
let ws = null;
let isAuthenticated = false;
let reconnectTimer = null;

// Sticky modifier states
let isCtrlActive = false;
let isAltActive = false;
let isShiftActive = false;
let isWinActive = false;

const statusDot = document.getElementById("statusDot");
const deviceNameEl = document.getElementById("deviceName");
const textInput = document.getElementById("textInput");
const trackpad = document.getElementById("trackpad");

function vibrate(ms = 20) {
  if (navigator.vibrate) {
    try { navigator.vibrate(ms); } catch (e) {}
  }
}

function updateStatus(connected, text) {
  if (connected) {
    statusDot.className = "status-dot connected";
    deviceNameEl.textContent = text || "{{DEVICE_NAME}}";
    isAuthenticated = true;
  } else {
    statusDot.className = "status-dot";
    deviceNameEl.textContent = text || "Connecting...";
    isAuthenticated = false;
  }
}

function send(type, payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type, payload }));
}

function sendCombo(modifiers, key) {
  vibrate(22);
  send("key_combo", { modifiers, key });
}

function sendKey(key) {
  vibrate(18);
  const mods = [];
  if (isCtrlActive) mods.push("CTRL");
  if (isAltActive) mods.push("ALT");
  if (isShiftActive) mods.push("SHIFT");
  if (isWinActive) mods.push("WIN");

  if (mods.length > 0) {
    sendCombo(mods, key);
    clearModifiers();
  } else {
    send("key_press", { key });
  }
}

function sendText(text) {
  if (!text) return;
  vibrate(18);
  send("type_text", { text });
}

function toggleModifier(mod, btn) {
  vibrate(20);
  if (mod === "CTRL") isCtrlActive = !isCtrlActive;
  if (mod === "ALT") isAltActive = !isAltActive;
  if (mod === "SHIFT") isShiftActive = !isShiftActive;
  if (mod === "WIN") isWinActive = !isWinActive;
  syncModifierButtons();
}

function clearModifiers() {
  if (isCtrlActive || isAltActive || isShiftActive || isWinActive) {
    isCtrlActive = false;
    isAltActive = false;
    isShiftActive = false;
    isWinActive = false;
    syncModifierButtons();
  }
}

function syncModifierButtons() {
  document.querySelectorAll("[data-mod]").forEach(btn => {
    const m = btn.getAttribute("data-mod");
    let active = false;
    if (m === "CTRL") active = isCtrlActive;
    if (m === "ALT") active = isAltActive;
    if (m === "SHIFT") active = isShiftActive;
    if (m === "WIN") active = isWinActive;
    if (active) {
      btn.classList.add("btn-modifier-active");
    } else {
      btn.classList.remove("btn-modifier-active");
    }
  });
}

function connect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);

  const loc = window.location;
  const wsUrl = (loc.protocol === "https:" ? "wss://" : "ws://") + loc.host + "/ws";

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusDot.className = "status-dot connecting";
    const urlParams = new URLSearchParams(window.location.search);
    const pin = urlParams.get("pin") || "{{SERVER_PIN}}";
    send("auth", { pin });
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "auth_result") {
        if (data.success) {
          updateStatus(true, data.device_name || "{{DEVICE_NAME}}");
        } else {
          updateStatus(false, "Auth Failed");
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  ws.onclose = () => {
    updateStatus(false, "Disconnected");
    reconnectTimer = setTimeout(connect, 2500);
  };

  ws.onerror = () => {
    ws.close();
  };
}

// Handlers
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    const val = textInput.value;
    if (val) {
      sendText(val);
      textInput.value = "";
    }
    sendKey("ENTER");
  }
});

document.getElementById("sendTextBtn")?.addEventListener("click", () => {
  const val = textInput.value;
  if (val) {
    sendText(val);
    textInput.value = "";
  }
});

// Modifiers
document.querySelectorAll("[data-mod]").forEach(btn => {
  btn.addEventListener("click", () => {
    toggleModifier(btn.getAttribute("data-mod"), btn);
  });
});

// Keys
document.querySelectorAll("[data-key]").forEach(btn => {
  btn.addEventListener("click", () => {
    sendKey(btn.getAttribute("data-key"));
  });
});

// Text buttons
document.querySelectorAll("[data-text]").forEach(btn => {
  btn.addEventListener("click", () => {
    sendText(btn.getAttribute("data-text"));
  });
});

// Combos
document.querySelectorAll("[data-combo]").forEach(btn => {
  btn.addEventListener("click", () => {
    const raw = btn.getAttribute("data-combo");
    const parts = raw.split("+");
    const key = parts.pop();
    sendCombo(parts, key);
  });
});

// Deck tabs
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    vibrate(15);
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".deck").forEach(d => d.classList.remove("active"));
    btn.classList.add("active");
    const target = document.getElementById(btn.getAttribute("data-target"));
    if (target) target.classList.add("active");
  });
});

// Trackpad
let lastTouchX = 0;
let lastTouchY = 0;
let touchStartTime = 0;

if (trackpad) {
  trackpad.addEventListener("touchstart", (e) => {
    if (e.touches.length === 1) {
      lastTouchX = e.touches[0].clientX;
      lastTouchY = e.touches[0].clientY;
      touchStartTime = Date.now();
      trackpad.classList.add("active");
    }
  }, { passive: true });

  trackpad.addEventListener("touchmove", (e) => {
    if (e.touches.length === 1) {
      const currentX = e.touches[0].clientX;
      const currentY = e.touches[0].clientY;
      const dx = Math.round((currentX - lastTouchX) * 1.5);
      const dy = Math.round((currentY - lastTouchY) * 1.5);
      if (dx !== 0 || dy !== 0) {
        send("mouse_move", { dx, dy });
        lastTouchX = currentX;
        lastTouchY = currentY;
      }
    } else if (e.touches.length === 2) {
      const currentY = e.touches[0].clientY;
      const dy = Math.round((currentY - lastTouchY) / 10);
      if (dy !== 0) {
        send("mouse_scroll", { dy });
        lastTouchY = currentY;
      }
    }
  }, { passive: true });

  trackpad.addEventListener("touchend", (e) => {
    trackpad.classList.remove("active");
    const elapsed = Date.now() - touchStartTime;
    if (elapsed < 200 && e.changedTouches.length === 1) {
      vibrate(15);
      send("mouse_click", { button: "left" });
    }
  });

  document.getElementById("btnLeftClick")?.addEventListener("click", () => {
    vibrate(18);
    send("mouse_click", { button: "left" });
  });

  document.getElementById("btnRightClick")?.addEventListener("click", () => {
    vibrate(18);
    send("mouse_click", { button: "right" });
  });
}

window.addEventListener("DOMContentLoaded", connect);
