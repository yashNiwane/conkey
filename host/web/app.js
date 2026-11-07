// ConKey Mobile Web Client
let ws = null;
let isAuthenticated = false;
let reconnectTimer = null;

const statusBadge = document.getElementById("statusBadge");
const statusText = document.getElementById("statusText");
const authCard = document.getElementById("authCard");
const pinInput = document.getElementById("pinInput");
const connectBtn = document.getElementById("connectBtn");
const textInput = document.getElementById("textInput");
const trackpad = document.getElementById("trackpad");

function vibrate(ms = 25) {
  if (navigator.vibrate) {
    try { navigator.vibrate(ms); } catch (e) {}
  }
}

function updateStatus(connected, text) {
  if (connected) {
    statusBadge.className = "status-badge connected";
    statusText.textContent = text || "Connected";
    authCard.style.display = "none";
  } else {
    statusBadge.className = "status-badge";
    statusText.textContent = text || "Disconnected";
    authCard.style.display = "block";
    isAuthenticated = false;
  }
}

function send(type, payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type, payload }));
}

function sendCombo(modifiers, key) {
  vibrate();
  send("key_combo", { modifiers, key });
}

function sendKey(key) {
  vibrate();
  send("key_press", { key });
}

function sendText(text) {
  if (!text) return;
  send("type_text", { text });
}

function connect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);

  const loc = window.location;
  const wsUrl = (loc.protocol === "https:" ? "wss://" : "ws://") + loc.host + "/ws";

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    updateStatus(false, "Authorizing...");
    const urlParams = new URLSearchParams(window.location.search);
    const pin = urlParams.get("pin") || pinInput.value.trim() || localStorage.getItem("conkey_pin") || "";
    if (pin) {
      pinInput.value = pin;
      send("auth", { pin });
    }
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "auth_result") {
        if (data.success) {
          isAuthenticated = true;
          localStorage.setItem("conkey_pin", pinInput.value.trim());
          updateStatus(true, "Ready");
        } else {
          alert("Authentication failed: " + data.message);
          updateStatus(false, "Auth Failed");
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  ws.onclose = () => {
    updateStatus(false, "Disconnected");
    reconnectTimer = setTimeout(connect, 3000);
  };

  ws.onerror = () => {
    ws.close();
  };
}

// Handlers
connectBtn.addEventListener("click", () => {
  const pin = pinInput.value.trim();
  if (pin) {
    send("auth", { pin });
  }
});

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

document.getElementById("sendTextBtn").addEventListener("click", () => {
  const val = textInput.value;
  if (val) {
    vibrate();
    sendText(val);
    textInput.value = "";
  }
});

// Dead-keys quick bar
document.querySelectorAll("[data-type-text]").forEach(btn => {
  btn.addEventListener("click", () => {
    vibrate();
    sendText(btn.getAttribute("data-type-text"));
  });
});

document.querySelectorAll("[data-key]").forEach(btn => {
  btn.addEventListener("click", () => {
    sendKey(btn.getAttribute("data-key"));
  });
});

document.querySelectorAll("[data-combo]").forEach(btn => {
  btn.addEventListener("click", () => {
    const raw = btn.getAttribute("data-combo");
    const parts = raw.split("+");
    const key = parts.pop();
    sendCombo(parts, key);
  });
});

// Tabs
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    vibrate(15);
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    btn.classList.add("active");
    const target = document.getElementById(btn.getAttribute("data-tab"));
    if (target) target.classList.add("active");
  });
});

// Trackpad implementation
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
      // 2 finger scroll
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
      // Tap to click
      vibrate(15);
      send("mouse_click", { button: "left" });
    }
  });

  document.getElementById("btnLeftClick")?.addEventListener("click", () => {
    vibrate();
    send("mouse_click", { button: "left" });
  });

  document.getElementById("btnRightClick")?.addEventListener("click", () => {
    vibrate();
    send("mouse_click", { button: "right" });
  });
}

// Start
window.addEventListener("DOMContentLoaded", connect);
