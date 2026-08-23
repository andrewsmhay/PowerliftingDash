document.addEventListener("DOMContentLoaded", function () {
  const syncBtn = document.getElementById("sync-opl-btn");
  const statusEl = document.getElementById("sync-status");

  if (!syncBtn) return;

  function setStatus(message, cls) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = cls || "";
  }

  syncBtn.addEventListener("click", function () {
    setStatus("Syncing with OpenPowerlifting...", "");
    syncBtn.disabled = true;
    fetch("/api/competitions/sync-openpowerlifting", { method: "POST" })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => Promise.reject(body));
        return res.json();
      })
      .then((body) => {
        const importedText = body.imported === 1 ? "1 meet" : body.imported + " meets";
        const skippedText = body.skipped === 1 ? "1 already logged" : body.skipped + " already logged";
        setStatus("Imported " + importedText + " (" + skippedText + "). Reloading...", "ok");
        setTimeout(() => window.location.reload(), 900);
      })
      .catch((err) => {
        setStatus("Sync failed: " + (err.detail || JSON.stringify(err)), "error");
        syncBtn.disabled = false;
      });
  });
});
