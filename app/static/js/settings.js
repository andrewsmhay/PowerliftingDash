(function () {
  "use strict";

  const form = document.getElementById("settings-form");
  const statusEl = document.getElementById("save-status");

  function setStatus(message, cls) {
    statusEl.textContent = message;
    statusEl.className = cls || "";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const formData = new FormData(form);
    const payload = {};
    formData.forEach((value, key) => {
      payload[key] = value;
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
      .then((result) => {
        if (result.openpowerlifting_warning) {
          setStatus("Saved, but personal bests could not be fetched: " + result.openpowerlifting_warning, "error");
          setTimeout(() => window.location.reload(), 2500);
        } else {
          setStatus("Saved. Reloading...", "ok");
          setTimeout(() => window.location.reload(), 700);
        }
      })
      .catch((err) => setStatus("Failed to save: " + (err.detail || JSON.stringify(err)), "error"));
  });

  const refreshOplBtn = document.getElementById("refresh-opl-btn");
  if (refreshOplBtn) {
    refreshOplBtn.addEventListener("click", function () {
      setStatus("Fetching personal bests...", "");
      refreshOplBtn.disabled = true;
      fetch("/api/openpowerlifting/refresh", { method: "POST" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => Promise.reject(body));
          return res.json();
        })
        .then(() => setStatus("Personal bests updated. Reloading...", "ok"))
        .then(() => setTimeout(() => window.location.reload(), 700))
        .catch((err) => {
          setStatus("Failed to fetch personal bests: " + (err.detail || JSON.stringify(err)), "error");
          refreshOplBtn.disabled = false;
        });
    });
  }

  const confirmCheckbox = document.getElementById("confirm-delete-all");
  const deleteAllBtn = document.getElementById("delete-all-btn");

  if (confirmCheckbox && deleteAllBtn) {
    confirmCheckbox.addEventListener("change", function () {
      deleteAllBtn.disabled = !confirmCheckbox.checked;
    });

    deleteAllBtn.addEventListener("click", function () {
      if (!confirmCheckbox.checked) return;
      setStatus("Deleting all entries...", "");
      fetch("/api/entries/delete-all", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => Promise.reject(body));
          return res.json();
        })
        .then((result) => setStatus("Deleted " + result.removed + " entries. Reloading...", "ok"))
        .then(() => setTimeout(() => window.location.reload(), 700))
        .catch((err) => setStatus("Failed to delete: " + (err.detail || JSON.stringify(err)), "error"));
    });
  }
})();

// Google Health controls are separate from personal profile settings so OAuth
// credentials can be saved before the browser is redirected to Google.
(function () {
  "use strict";

  const statusEl = document.getElementById("save-status");
  const setupForm = document.getElementById("google-health-setup-form");
  const categoriesForm = document.getElementById("google-health-categories-form");
  const syncedEl = document.getElementById("google-health-last-synced");

  function setStatus(message, cls) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = cls || "";
  }

  function request(path, payload) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    }).then((res) => {
      if (!res.ok) return res.json().then((body) => Promise.reject(body));
      return res.json();
    });
  }

  if (syncedEl && syncedEl.dataset.timestamp) {
    const then = new Date(syncedEl.dataset.timestamp);
    const seconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
    const value = seconds < 60 ? "just now" : seconds < 3600 ? Math.floor(seconds / 60) + " minutes ago" : Math.floor(seconds / 3600) + " hours ago";
    if (!Number.isNaN(then.getTime())) syncedEl.textContent = value;
  }

  if (setupForm) {
    setupForm.addEventListener("submit", function (event) {
      event.preventDefault();
      const clientId = document.getElementById("google_health_client_id").value.trim();
      const clientSecret = document.getElementById("google_health_client_secret").value.trim();
      if (!clientId || !clientSecret) {
        setStatus("Enter both Google Health OAuth fields.", "error");
        return;
      }
      setStatus("Saving Google Health credentials...", "");
      request("/api/settings", { google_health_client_id: clientId, google_health_client_secret: clientSecret })
        .then(() => { window.location.href = "/google-health/connect"; })
        .catch((err) => setStatus("Failed to save Google Health credentials: " + (err.detail || JSON.stringify(err)), "error"));
    });
  }

  if (categoriesForm) {
    let selected = ["body_composition", "activity", "cardio", "sleep"];
    try { selected = JSON.parse(document.getElementById("google-health-enabled-categories").value); } catch (err) { selected = []; }
    categoriesForm.querySelectorAll("input[name=google_health_category]").forEach((checkbox) => {
      checkbox.checked = selected.includes(checkbox.value);
    });
    categoriesForm.addEventListener("submit", function (event) {
      event.preventDefault();
      const categories = Array.from(categoriesForm.querySelectorAll("input[name=google_health_category]:checked")).map((checkbox) => checkbox.value);
      request("/api/settings", { google_health_enabled_categories: JSON.stringify(categories) })
        .then(() => setStatus("Google Health categories saved.", "ok"))
        .catch((err) => setStatus("Failed to save categories: " + (err.detail || JSON.stringify(err)), "error"));
    });
  }

  const syncButton = document.getElementById("sync-google-health-btn");
  if (syncButton) {
    syncButton.addEventListener("click", function () {
      syncButton.disabled = true;
      setStatus("Synchronising Google Health...", "");
      request("/api/google-health/sync")
        .then(() => setStatus("Google Health synchronised. Reloading...", "ok"))
        .then(() => setTimeout(() => window.location.reload(), 700))
        .catch((err) => { setStatus("Google Health sync failed: " + (err.detail || JSON.stringify(err)), "error"); syncButton.disabled = false; });
    });
  }

  const disconnectButton = document.getElementById("disconnect-google-health-btn");
  if (disconnectButton) {
    disconnectButton.addEventListener("click", function () {
      disconnectButton.disabled = true;
      request("/api/google-health/disconnect")
        .then(() => { window.location.reload(); })
        .catch((err) => { setStatus("Failed to disconnect Google Health: " + (err.detail || JSON.stringify(err)), "error"); disconnectButton.disabled = false; });
    });
  }
})();
