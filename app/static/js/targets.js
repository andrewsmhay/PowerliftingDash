(function () {
  "use strict";

  const form = document.getElementById("targets-form");
  const statusEl = document.getElementById("save-status");

  function setStatus(message, cls) {
    statusEl.textContent = message;
    statusEl.className = cls || "";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const formData = new FormData(form);
    const values = {};

    formData.forEach((value, key) => {
      if (value === "") return;
      values[key] = value;
    });

    setStatus("Saving...", "");
    fetch("/api/targets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: values }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => Promise.reject(body));
        return res.json();
      })
      .then(() => setStatus("Saved. Dashboard figures have been recalculated.", "ok"))
      .catch((err) => setStatus("Failed to save: " + (err.detail || JSON.stringify(err)), "error"));
  });
})();
