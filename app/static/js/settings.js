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
