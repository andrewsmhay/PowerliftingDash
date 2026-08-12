(function () {
  "use strict";

  const form = document.getElementById("entry-form");
  const statusEl = document.getElementById("save-status");

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
      if (value === "") return;
      values[key] = value;
    });

    setStatus("Saving...", "");
    fetch("/api/entries", {
      method: "POST",
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
})();
