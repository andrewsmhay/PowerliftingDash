(function () {
  "use strict";

  const form = document.getElementById("competition-form");
  const statusEl = document.getElementById("save-status");
  const deleteBtn = document.getElementById("delete-competition-btn");
  const mode = form.dataset.mode || "create";
  const competitionId = form.dataset.competitionId || "";

  const squatInput = document.getElementById("squat_kg");
  const benchInput = document.getElementById("bench_kg");
  const deadliftInput = document.getElementById("deadlift_kg");
  const totalInput = document.getElementById("total_kg");
  let totalTouchedByUser = false;

  function recalculateTotal() {
    if (totalTouchedByUser) return;
    const parts = [squatInput, benchInput, deadliftInput]
      .map((input) => parseFloat(input.value))
      .filter((value) => !Number.isNaN(value));
    if (parts.length === 0) {
      totalInput.value = "";
      return;
    }
    const sum = parts.reduce((acc, value) => acc + value, 0);
    totalInput.value = Math.round(sum * 100) / 100;
  }

  [squatInput, benchInput, deadliftInput].forEach((input) => {
    input.addEventListener("input", recalculateTotal);
  });
  totalInput.addEventListener("input", function () {
    totalTouchedByUser = true;
  });
  // An edit-mode form that already has a saved total should not have it
  // silently overwritten just because the three lift fields render first.
  if (mode === "edit" && totalInput.value !== "") totalTouchedByUser = true;

  function setStatus(message, cls) {
    statusEl.textContent = message;
    statusEl.className = cls || "";
  }

  const TEXT_FIELDS = ["meet_name", "federation", "location", "weight_class", "placing", "notes"];
  const NUMERIC_FIELDS = ["bodyweight_kg", "squat_kg", "bench_kg", "deadlift_kg", "total_kg"];

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const formData = new FormData(form);
    const competitionDate = formData.get("competition_date");
    const values = {};

    TEXT_FIELDS.concat(NUMERIC_FIELDS).forEach((field) => {
      values[field] = formData.get(field);
    });

    const isEdit = mode === "edit";
    const url = isEdit ? "/api/competitions/" + encodeURIComponent(competitionId) : "/api/competitions";
    const method = isEdit ? "PUT" : "POST";

    setStatus("Saving...", "");
    fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ competition_date: competitionDate, values: values }),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => Promise.reject(body));
        return res.json();
      })
      .then((result) => setStatus("Saved competition for " + result.competition_date_ddmmyyyy + ".", "ok"))
      .catch((err) => setStatus("Failed to save: " + (err.detail || JSON.stringify(err)), "error"));
  });

  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      if (!window.confirm("Delete this competition? This cannot be undone.")) return;
      setStatus("Deleting...", "");
      fetch("/api/competitions/" + encodeURIComponent(competitionId), { method: "DELETE" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => Promise.reject(body));
          return res.json();
        })
        .then(() => {
          window.location.href = "/competitions";
        })
        .catch((err) => setStatus("Failed to delete: " + (err.detail || JSON.stringify(err)), "error"));
    });
  }
})();
