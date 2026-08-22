(function () {
  "use strict";

  const CHART_COLORS = ["#20808d", "#a84b2f", "#ffc553", "#bce2e7", "#944454"];

  function fmt(value, decimals) {
    if (value === null || value === undefined || Number.isNaN(value)) return null;
    const d = decimals === undefined ? 1 : decimals;
    return Number(value).toFixed(d).replace(/\.0$/, "");
  }

  function valueHtml(value, unit, decimals) {
    const formatted = fmt(value, decimals);
    if (formatted === null) return '<span class="empty">No data</span>';
    return formatted + '<span class="unit">' + unit + "</span>";
  }

  function liftCardHtml(card) {
    const pct = card.progress_pct === null || card.progress_pct === undefined ? 0 : card.progress_pct;
    const targetPct = card.target_attainment_pct;
    const pctLabelHtml = targetPct === null || targetPct === undefined
      ? ""
      : '<span class="progress-pct">' + fmt(targetPct) + "% of target</span>";

    const delta = card.competition_delta;
    const compPct = card.competition_attainment_pct;
    let deltaHtml = "";
    if (delta !== null && delta !== undefined) {
      const cls = delta >= 0 ? "positive" : "negative";
      const sign = delta >= 0 ? "+" : "";
      const compPctText = compPct === null || compPct === undefined ? "" : " (" + fmt(compPct) + "%)";
      deltaHtml = '<span class="delta-pill ' + cls + '">' + sign + fmt(delta) + " kg" + compPctText + " vs competition</span>";
    }

    const pb = card.personal_best;
    const pbHtml = pb === null || pb === undefined
      ? ""
      : '<div class="pb-row">PB (OpenPowerlifting) <strong>' + fmt(pb) + " " + card.unit + "</strong></div>";

    return (
      '<div class="card">' +
      '<div class="card-label">' + card.label + "</div>" +
      '<div class="card-value">' + valueHtml(card.current, card.unit) + "</div>" +
      '<div class="progress-track"><div class="progress-fill" style="width:' + pct + '%"></div></div>' +
      pctLabelHtml +
      '<div class="card-meta"><span>Target <strong>' + (fmt(card.target) ?? "--") + " " + card.unit + '</strong></span>' +
      '<span>Remaining <strong>' + (fmt(card.remaining) ?? "--") + " " + card.unit + "</strong></span></div>" +
      deltaHtml +
      pbHtml +
      "</div>"
    );
  }

  function bodyCardHtml(card) {
    const pct = card.progress_pct === null || card.progress_pct === undefined ? null : card.progress_pct;
    const progressHtml = pct === null ? "" : '<div class="progress-track"><div class="progress-fill" style="width:' + pct + '%"></div></div>';
    return (
      '<div class="card">' +
      '<div class="card-label">' + card.label + "</div>" +
      '<div class="card-value">' + valueHtml(card.current, card.unit) + "</div>" +
      progressHtml +
      '<div class="card-meta"><span>Target <strong>' + (fmt(card.target) ?? "--") + " " + card.unit + '</strong></span>' +
      '<span>To date <strong>' + (fmt(card.to_date) ?? "--") + " " + card.unit + "</strong></span></div>" +
      "</div>"
    );
  }

  function indexCardHtml(card) {
    return (
      '<div class="card">' +
      '<div class="card-label">' + card.label + "</div>" +
      '<div class="card-value">' + valueHtml(card.current, card.unit, 1) + "</div>" +
      '<div class="card-meta"><span>Target <strong>' + (fmt(card.target) ?? "--") + " " + card.unit + '</strong></span>' +
      '<span>To date <strong>' + (fmt(card.to_date) ?? "--") + " " + card.unit + "</strong></span></div>" +
      "</div>"
    );
  }

  function healthCardsHtml(metric) {
    const cards = [
      { label: "Steps", value: metric && metric.steps, unit: "" },
      { label: "Resting heart rate", value: metric && metric.resting_heart_rate, unit: " bpm" },
      { label: "Sleep", value: metric && metric.sleep_minutes === null ? null : metric && metric.sleep_minutes / 60, unit: " hrs", decimals: 1 },
    ];
    return cards.map((card) => (
      '<div class="card">' +
      '<div class="card-label">' + card.label + "</div>" +
      '<div class="card-value">' + valueHtml(card.value, card.unit, card.decimals) + "</div>" +
      '<div class="card-meta"><span>Latest Google Health sync</span></div>' +
      "</div>"
    )).join("");
  }

  function renderEntryCount(count) {
    const badge = document.getElementById("entry-count-badge");
    if (count === null || count === undefined) {
      badge.textContent = "--";
      return;
    }
    badge.textContent = count + (count === 1 ? " entry" : " entries");
  }

  let liftChart = null;
  let bodyChart = null;

  function chartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { color: "#797876", boxWidth: 12, font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: "#5a5957", font: { size: 10 } }, grid: { color: "#26241f" } },
        y: { ticks: { color: "#5a5957", font: { size: 10 } }, grid: { color: "#26241f" } },
      },
    };
  }

  function buildDataset(label, data, color) {
    return {
      label: label,
      data: data,
      borderColor: color,
      backgroundColor: color,
      tension: 0.3,
      pointRadius: 2,
      borderWidth: 2,
      spanGaps: true,
    };
  }

  function renderCharts(history) {
    const labels = history.map((h) => h.entry_date);
    const liftCtx = document.getElementById("chart-lifts");
    const bodyCtx = document.getElementById("chart-body");

    const liftData = {
      labels: labels,
      datasets: [
        buildDataset("Squat", history.map((h) => h.squat), CHART_COLORS[0]),
        buildDataset("Bench", history.map((h) => h.bench), CHART_COLORS[1]),
        buildDataset("Deadlift", history.map((h) => h.deadlift), CHART_COLORS[2]),
      ],
    };
    const bodyData = {
      labels: labels,
      datasets: [
        buildDataset("Body weight", history.map((h) => h.body_weight_mass), CHART_COLORS[0]),
        buildDataset("Muscle mass", history.map((h) => h.skeletal_muscle_mass), CHART_COLORS[1]),
        buildDataset("Fat mass", history.map((h) => h.body_fat_mass), CHART_COLORS[2]),
      ],
    };

    if (liftChart) {
      liftChart.data = liftData;
      liftChart.update();
    } else {
      liftChart = new Chart(liftCtx, { type: "line", data: liftData, options: chartOptions() });
    }

    if (bodyChart) {
      bodyChart.data = bodyData;
      bodyChart.update();
    } else {
      bodyChart = new Chart(bodyCtx, { type: "line", data: bodyData, options: chartOptions() });
    }
  }

  function render(data) {
    const titleEl = document.getElementById("dashboard-title");
    if (titleEl && data.dashboard_title) titleEl.textContent = data.dashboard_title;

    const liftCardsEl = document.getElementById("lift-cards");
    liftCardsEl.innerHTML = data.lift_cards.map(liftCardHtml).join("") + liftCardHtml(
      Object.assign({}, data.total_card, { competition_delta: null, competition_attainment_pct: null })
    );

    const bodyCardsEl = document.getElementById("body-cards");
    bodyCardsEl.innerHTML = data.body_cards.map(bodyCardHtml).join("") + data.index_cards.map(indexCardHtml).join("");

    const healthCardsEl = document.getElementById("health-cards");
    if (healthCardsEl) healthCardsEl.innerHTML = healthCardsHtml(data.latest_health_metric);

    document.getElementById("latest-entry-date").textContent = data.latest_entry_date
      ? "Latest entry: " + data.latest_entry_date
      : "No entries yet";

    renderEntryCount(data.entry_count);
    renderCharts(data.history || []);
  }

  function refresh() {
    fetch("/api/dashboard")
      .then((res) => res.json())
      .then(render)
      .catch((err) => console.error("Failed to refresh dashboard", err));
  }

  refresh();
  const pollSeconds = (window.DASHBOARD_CONFIG && window.DASHBOARD_CONFIG.pollSeconds) || 60;
  setInterval(refresh, pollSeconds * 1000);
})();
