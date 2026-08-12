(function () {
  "use strict";

  const form = document.getElementById("settings-form");
  const statusEl = document.getElementById("save-status");
  const syncBtn = document.getElementById("sync-now-btn");

  function setStatus(message, cls) {
    statusEl.textContent = message;
    statusEl.className = cls || "";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const formData = new FormData(form);
    const payload = {};
    formData.forEach((value, key) => {
      if (key === "sync_interval_minutes") {
        payload[key] = parseInt(value, 10);
      } else {
        payload[key] = value;
      }
    });

    setStatus("Saving...", "");
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => Promise.reject(body));
        return res.json();
      })
      .then(() => setStatus("Saved. Reloading...", "ok"))
      .then(() => setTimeout(() => window.location.reload(), 700))
      .catch((err) => setStatus("Failed to save: " + (err.detail || JSON.stringify(err)), "error"));
  });

  syncBtn.addEventListener("click", function () {
    setStatus("Syncing...", "");
    fetch("/api/sync", { method: "POST" })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => Promise.reject(body));
        return res.json();
      })
      .then((result) => setStatus(result.message, result.status === "ok" ? "ok" : "error"))
      .catch((err) => setStatus("Sync failed: " + (err.detail || JSON.stringify(err)), "error"));
  });
})();
