(function () {
  "use strict";

  const form = document.getElementById("entry-form");
  const statusEl = document.getElementById("save-status");
  const deleteBtn = document.getElementById("delete-entry-btn");
  const mode = form.dataset.mode || "create";
  const entryId = form.dataset.entryId || "";

  function setStatus(message, cls) {
    statusEl.textContent = message;
    statusEl.className = cls || "";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const formData = new FormData(form);
    const entryDate = formData.get("entry_date");
    const values = {};

    formData.forEach((value, key) => {
      if (key === "entry_date") return;
      // Create mode: an untouched/blank field means "not recording this
      // metric today" - it must be omitted so weight-only or goals-only
      // saves don't wipe out the other section. Edit mode sends every
      // field, including "" to explicitly clear a value that was wrong.
      if (mode === "create" && value === "") return;
      values[key] = value;
    });

    const isEdit = mode === "edit";
    const url = isEdit ? "/api/entries/" + encodeURIComponent(entryId) : "/api/entries";
    const method = isEdit ? "PUT" : "POST";

    setStatus("Saving...", "");
    fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entry_date: entryDate, values: values }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => Promise.reject(body));
        return res.json();
      })
      .then((result) => setStatus("Saved entry for " + result.entry_date_ddmmyyyy + ".", "ok"))
      .catch((err) => setStatus("Failed to save: " + (err.detail || JSON.stringify(err)), "error"));
  });

  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      if (!window.confirm("Delete this entry? This cannot be undone.")) return;
      setStatus("Deleting...", "");
      fetch("/api/entries/" + encodeURIComponent(entryId), { method: "DELETE" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => Promise.reject(body));
          return res.json();
        })
        .then(() => {
          window.location.href = "/entries";
        })
        .catch((err) => setStatus("Failed to delete: " + (err.detail || JSON.stringify(err)), "error"));
    });
  }
})();
