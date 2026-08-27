document.addEventListener("DOMContentLoaded", function () {
  const addBtn = document.getElementById("add-countdown-btn");
  const form = document.getElementById("countdown-form");
  if (!addBtn || !form) return;

  const cancelBtn = document.getElementById("countdown-cancel-btn");
  const submitBtn = document.getElementById("countdown-submit-btn");
  const statusEl = document.getElementById("countdown-status");
  const nameInput = document.getElementById("event_name");
  const dateInput = document.getElementById("event_date");
  const countrySelect = document.getElementById("event_country");
  const regionSelect = document.getElementById("event_region");
  const citySelect = document.getElementById("event_city");

  const manageBtn = document.getElementById("manage-locations-btn");
  const managePanel = document.getElementById("location-manager");

  function setStatus(message, cls) {
    if (!statusEl) return;
    statusEl.textContent = message || "";
    statusEl.className = cls || "";
  }

  function ensureOptionExists(select, value) {
    if (!value) return;
    const exists = Array.from(select.options).some((opt) => opt.value === value);
    if (!exists) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      select.appendChild(opt);
    }
  }

  function resetForm() {
    form.dataset.mode = "create";
    form.dataset.editingId = "";
    nameInput.value = "";
    dateInput.value = "";
    countrySelect.value = "";
    regionSelect.value = "";
    citySelect.value = "";
    submitBtn.textContent = "Add countdown";
    setStatus("");
  }

  function openForm() {
    form.style.display = "block";
    if (managePanel) managePanel.style.display = "none";
  }

  function closeForm() {
    form.style.display = "none";
    resetForm();
  }

  addBtn.addEventListener("click", function () {
    resetForm();
    openForm();
  });

  cancelBtn.addEventListener("click", closeForm);

  document.querySelectorAll(".countdown-edit-link").forEach((link) => {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      const row = link.closest("tr");
      if (!row) return;
      resetForm();
      form.dataset.mode = "edit";
      form.dataset.editingId = row.dataset.id;
      nameInput.value = row.dataset.eventName || "";
      dateInput.value = row.dataset.eventDate || "";
      ensureOptionExists(countrySelect, row.dataset.country);
      ensureOptionExists(regionSelect, row.dataset.region);
      ensureOptionExists(citySelect, row.dataset.city);
      countrySelect.value = row.dataset.country || "";
      regionSelect.value = row.dataset.region || "";
      citySelect.value = row.dataset.city || "";
      submitBtn.textContent = "Save changes";
      openForm();
    });
  });

  document.querySelectorAll(".countdown-delete-link").forEach((link) => {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      const row = link.closest("tr");
      if (!row) return;
      if (!window.confirm("Delete this countdown? This cannot be undone.")) return;
      fetch("/api/countdowns/" + row.dataset.id, { method: "DELETE" })
        .then((res) => {
          if (!res.ok) return res.json().then((body) => Promise.reject(body));
          window.location.reload();
        })
        .catch((err) => window.alert("Could not delete countdown: " + (err.detail || "Unknown error")));
    });
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const mode = form.dataset.mode || "create";
    const payload = {
      event_date: dateInput.value.trim(),
      values: {
        event_name: nameInput.value.trim(),
        country: countrySelect.value,
        region: regionSelect.value,
        city: citySelect.value,
      },
    };
    setStatus("Saving...", "");
    submitBtn.disabled = true;
    const url = mode === "edit" ? "/api/countdowns/" + form.dataset.editingId : "/api/countdowns";
    const method = mode === "edit" ? "PUT" : "POST";
    fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((res) => {
        if (!res.ok) return res.json().then((body) => Promise.reject(body));
        return res.json();
      })
      .then(() => {
        window.location.reload();
      })
      .catch((err) => {
        setStatus(err.detail || "Could not save countdown.", "error");
        submitBtn.disabled = false;
      });
  });

  // Location manager - deliberately does not reload the page, so an
  // in-progress "Add countdown" form (open at the same time) never loses
  // what the user has already typed.
  if (manageBtn && managePanel) {
    manageBtn.addEventListener("click", function () {
      const opening = managePanel.style.display === "none" || !managePanel.style.display;
      managePanel.style.display = opening ? "block" : "none";
      if (opening) form.style.display = "none";
    });

    function selectForKind(kind) {
      return document.getElementById("event_" + kind);
    }

    function addChip(kind, id, value) {
      const list = document.getElementById("chips-" + kind);
      if (!list) return;
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.dataset.id = id;
      chip.dataset.value = value;
      chip.textContent = value;
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "chip-remove";
      removeBtn.setAttribute("aria-label", "Remove");
      removeBtn.textContent = "\u00d7";
      wireRemoveButton(removeBtn, kind, chip);
      chip.appendChild(removeBtn);
      list.appendChild(chip);
    }

    function addOption(kind, value) {
      const select = selectForKind(kind);
      if (select) ensureOptionExists(select, value);
    }

    function removeChipAndOption(kind, id, value) {
      const chip = document.querySelector('.chip[data-id="' + id + '"]');
      if (chip) chip.remove();
      const select = selectForKind(kind);
      if (select) {
        const opt = Array.from(select.options).find((option) => option.value === value);
        if (opt) opt.remove();
      }
    }

    function wireRemoveButton(button, kind, chip) {
      button.addEventListener("click", function () {
        if (!window.confirm("Remove this location option? Countdowns already using it keep their saved value.")) return;
        fetch("/api/countdowns/locations/" + chip.dataset.id, { method: "DELETE" })
          .then((res) => {
            if (!res.ok) return res.json().then((body) => Promise.reject(body));
            removeChipAndOption(kind, chip.dataset.id, chip.dataset.value);
          })
          .catch((err) => window.alert("Could not remove location: " + (err.detail || "Unknown error")));
      });
    }

    document.querySelectorAll(".chip-remove").forEach((button) => {
      const chip = button.closest(".chip");
      const list = button.closest(".chip-list");
      if (chip && list) wireRemoveButton(button, list.dataset.kind, chip);
    });

    document.querySelectorAll(".location-add-btn").forEach((button) => {
      button.addEventListener("click", function () {
        const kind = button.dataset.kind;
        const input = document.querySelector('.location-add-input[data-kind="' + kind + '"]');
        const value = (input.value || "").trim();
        if (!value) return;
        button.disabled = true;
        fetch("/api/countdowns/locations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: kind, value: value }),
        })
          .then((res) => {
            if (!res.ok) return res.json().then((body) => Promise.reject(body));
            return res.json();
          })
          .then((result) => {
            if (result.created === true) {
              addChip(kind, result.id, result.value);
              addOption(kind, result.value);
            }
            input.value = "";
          })
          .catch((err) => window.alert("Could not add location: " + (err.detail || "Unknown error")))
          .finally(() => {
            button.disabled = false;
          });
      });
    });
  }
});
