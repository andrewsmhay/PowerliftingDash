(function () {
  "use strict";

  const CHART_COLORS = ["#20808d", "#a84b2f", "#ffc553", "#bce2e7", "#944454"];
  const HEALTH_FORMATS = {
    steps: { unit: "", decimals: 0 },
    resting_heart_rate: { unit: " bpm", decimals: 0 },
    sleep_minutes: { unit: " hrs", decimals: 1, transform: (value) => value / 60 },
    distance_km: { unit: " km", decimals: 2 },
    floors_climbed: { unit: "", decimals: 0 },
    active_minutes: { unit: " min", decimals: 0 },
    active_zone_minutes: { unit: " min", decimals: 0 },
    calories_burned: { unit: " kcal", decimals: 0 },
    heart_rate_variability_ms: { unit: " ms", decimals: 0 },
    vo2_max: { unit: " ml/kg/min", decimals: 1 },
    respiratory_rate: { unit: " br/min", decimals: 1 },
    oxygen_saturation_pct: { unit: "%", decimals: 1 },
  };

  let grid;
  let editing = false;
  let catalog = [];
  let savedLayout = [];
  let currentWidgetIds = [];
  let skippedLayoutItems = [];
  let dashboardData = null;
  let charts = {};

  function fmt(value, decimals) {
    if (value === null || value === undefined || Number.isNaN(value)) return null;
    const digits = decimals === undefined ? 1 : decimals;
    return Number(value).toFixed(digits).replace(/\.0$/, "");
  }

  function valueHtml(value, unit, decimals) {
    const formatted = fmt(value, decimals);
    if (formatted === null) return '<span class="empty">No data</span>';
    return formatted + '<span class="unit">' + unit + "</span>";
  }

  function liftCardHtml(card) {
    const pct = card.progress_pct === null || card.progress_pct === undefined ? 0 : card.progress_pct;
    const pctLabelHtml = pctOfTargetHtml(card.target_attainment_pct);
    const delta = card.competition_delta;
    const compPct = card.competition_attainment_pct;
    let deltaHtml = "";
    if (delta !== null && delta !== undefined) {
      const cls = delta >= 0 ? "positive" : "negative";
      const sign = delta >= 0 ? "+" : "";
      const compPctText = compPct === null || compPct === undefined ? "" : " (" + fmt(compPct) + "%)";
      deltaHtml = '<span class="delta-pill ' + cls + '">' + sign + fmt(delta) + " kg" + compPctText + " vs competition</span>";
    }
    const personalBest = card.personal_best;
    const personalBestHtml = personalBest === null || personalBest === undefined
      ? ""
      : '<div class="pb-row">PB (OpenPowerlifting) <strong>' + fmt(personalBest) + " " + card.unit + "</strong></div>";
    return '<div class="card">' +
      '<div class="card-label">' + card.label + "</div>" +
      '<div class="card-value">' + valueHtml(card.current, card.unit) + "</div>" +
      '<div class="progress-track"><div class="progress-fill" style="width:' + pct + '%"></div></div>' +
      pctLabelHtml +
      '<div class="card-meta"><span>Target <strong>' + (fmt(card.target) ?? "Not set") + " " + card.unit + '</strong></span>' +
      '<span>Remaining <strong>' + (fmt(card.remaining) ?? "Not set") + " " + card.unit + "</strong></span></div>" +
      deltaHtml + personalBestHtml + "</div>";
  }

  function pctOfTargetHtml(targetPct) {
    return targetPct === null || targetPct === undefined
      ? ""
      : '<span class="progress-pct">' + fmt(targetPct) + "% of target</span>";
  }

  function bodyCardHtml(card) {
    const pct = card.progress_pct === null || card.progress_pct === undefined ? null : card.progress_pct;
    const progressHtml = pct === null ? "" : '<div class="progress-track"><div class="progress-fill" style="width:' + pct + '%"></div></div>';
    const hasTarget = card.target !== null && card.target !== undefined;
    const hasToDate = card.to_date !== null && card.to_date !== undefined;
    const targetHtml = hasTarget ? '<span>Target <strong>' + fmt(card.target) + " " + card.unit + "</strong></span>" : "";
    const toDateHtml = hasToDate ? '<span>To date <strong>' + fmt(card.to_date) + " " + card.unit + "</strong></span>" : "";
    const metaHtml = hasTarget || hasToDate
      ? '<div class="card-meta">' + targetHtml + toDateHtml + "</div>"
      : "";
    return '<div class="card">' +
      '<div class="card-label">' + card.label + "</div>" +
      '<div class="card-value">' + valueHtml(card.current, card.unit) + "</div>" +
      progressHtml +
      pctOfTargetHtml(card.target_attainment_pct) +
      metaHtml + "</div>";
  }

  function indexCardHtml(card) {
    return '<div class="card">' +
      '<div class="card-label">' + card.label + "</div>" +
      '<div class="card-value">' + valueHtml(card.current, card.unit, 1) + "</div>" +
      pctOfTargetHtml(card.target_attainment_pct) +
      '<div class="card-meta"><span>Target <strong>' + (fmt(card.target) ?? "Not set") + " " + card.unit + '</strong></span>' +
      '<span>To date <strong>' + (fmt(card.to_date) ?? "Not set") + " " + card.unit + "</strong></span></div></div>";
  }

  function healthCardHtml(widgetId, data) {
    const field = widgetId.split(".")[1];
    const format = HEALTH_FORMATS[field];
    const metric = data.latest_health_metric || {};
    let value = metric[field];
    if (value !== null && value !== undefined && format.transform) value = format.transform(value);
    return '<div class="card">' +
      '<div class="card-label">' + widgetLabel(widgetId) + "</div>" +
      '<div class="card-value">' + valueHtml(value, format.unit, format.decimals) + "</div>" +
      '<div class="card-meta"><span>Latest Google Health sync</span></div></div>';
  }

  function analyticsCardHtml(widgetId, data) {
    const parts = widgetId.split(".");
    const type = parts[0];
    const lift = parts[1].replace("_bw", "");
    if (type === "score") {
      const score = data.dots_score || {};
      const hint = score.reason === "sex_not_configured"
        ? '<div class="card-meta"><span>Configure sex in Settings to calculate this.</span></div>'
        : "";
      return '<div class="card"><div class="card-label">DOTS Score</div><div class="card-value">' +
        valueHtml(score.value, score.unit ? " " + score.unit : "", 1) + "</div>" + hint + "</div>";
    }
    if (type === "ratio") {
      const ratio = (data.ratios || {})[lift] || {};
      const text = ratio.value === null || ratio.value === undefined
        ? '<span class="empty">No data</span>'
        : fmt(ratio.value, 2) + '<span class="unit">x</span>';
      return '<div class="card"><div class="card-label">' + widgetLabel(widgetId) +
        '</div><div class="card-value">' + text +
        '</div><div class="card-meta"><span>Bodyweight ratio</span></div></div>';
    }
    const rate = ((data.rate_of_change || {})[lift] || {}).kg_per_week;
    let rateText = '<span class="empty">No data</span>';
    if (rate !== null && rate !== undefined) {
      const cls = rate >= 0 ? "positive" : "negative";
      const sign = rate > 0 ? "+" : "";
      rateText = '<span class="rate-value ' + cls + '">' + sign + fmt(rate, 2) + '<span class="unit"> kg/week</span></span>';
    }
    const projection = ((data.projected_dates || {})[lift] || {});
    let projectionText = "No data";
    if (projection.state === "target_met") projectionText = "Target already met";
    if (projection.state === "not_on_track") projectionText = "Not on track at current rate";
    if (projection.state === "too_far") projectionText = "More than 10 years away at current rate";
    if (projection.state === "projected") projectionText = ukDate(projection.date);
    return '<div class="card"><div class="card-label">' + widgetLabel(widgetId) +
      '</div><div class="card-value">' + rateText +
      '</div><div class="card-meta"><span>Recent trend</span></div>' +
      '<div class="pb-row">Projected target date <strong>' + projectionText + "</strong></div></div>";
  }

  function ukDate(isoDate) {
    if (!isoDate) return "No data";
    const parts = isoDate.split("-");
    return parts.length === 3 ? parts[2] + "/" + parts[1] + "/" + parts[0] : isoDate;
  }

  function widgetLabel(widgetId) {
    const widget = catalog.find((item) => item.id === widgetId);
    return widget ? widget.label : widgetId;
  }

  function chartOptions(extraScales) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { color: "#797876", boxWidth: 12, font: { size: 11 } } } },
      scales: Object.assign({
        x: { ticks: { color: "#797876", font: { size: 10 } }, grid: { color: "#26241f" } },
        y: { ticks: { color: "#797876", font: { size: 10 } }, grid: { color: "#26241f" } },
      }, extraScales || {}),
    };
  }

  function buildDataset(label, values, colour) {
    return {
      label: label,
      data: values,
      borderColor: colour,
      backgroundColor: colour,
      tension: 0.3,
      pointRadius: 2,
      borderWidth: 2,
      spanGaps: true,
    };
  }

  function ensureChart(widgetId, container, data, options) {
    let canvas = container.querySelector("canvas");
    if (!canvas) {
      container.innerHTML = '<div class="chart-card"><div class="card-label">' + widgetLabel(widgetId) +
        '</div><div class="chart-canvas-wrap"><canvas></canvas></div></div>';
      canvas = container.querySelector("canvas");
    }
    if (charts[widgetId]) {
      charts[widgetId].data = data;
      charts[widgetId].update();
      return;
    }
    charts[widgetId] = new Chart(canvas, { type: "line", data: data, options: options });
  }

  function renderStandardChart(widgetId, container, data) {
    const history = data.history || [];
    const labels = history.map((row) => row.entry_date);
    const isLiftChart = widgetId === "chart.lifts";
    const datasets = isLiftChart
      ? [
        buildDataset("Squat", history.map((row) => row.squat), CHART_COLORS[0]),
        buildDataset("Bench", history.map((row) => row.bench), CHART_COLORS[1]),
        buildDataset("Deadlift", history.map((row) => row.deadlift), CHART_COLORS[2]),
      ]
      : [
        buildDataset("Body weight", history.map((row) => row.body_weight_mass), CHART_COLORS[0]),
        buildDataset("Muscle mass", history.map((row) => row.skeletal_muscle_mass), CHART_COLORS[1]),
        buildDataset("Fat mass", history.map((row) => row.body_fat_mass), CHART_COLORS[2]),
      ];
    ensureChart(widgetId, container, { labels: labels, datasets: datasets }, chartOptions());
  }

  function renderPrTimeline(widgetId, container, data) {
    const lift = widgetId.split(".")[1];
    const history = data.history || [];
    let runningMax = Number.NEGATIVE_INFINITY;
    const values = history.map((row) => row[lift]);
    const isPr = values.map((value) => {
      const result = value !== null && value !== undefined && value > runningMax;
      if (value !== null && value !== undefined) runningMax = Math.max(runningMax, value);
      return result;
    });
    const liftCard = (data.lift_cards || []).find((card) => card.id === "lift." + lift) || {};
    const referenceLines = [];
    if (liftCard.target !== null && liftCard.target !== undefined) {
      referenceLines.push({
        label: "Target", data: values.map(() => liftCard.target), borderColor: CHART_COLORS[2],
        borderDash: [6, 5], pointRadius: 0, borderWidth: 1.5,
      });
    }
    if (liftCard.competition !== null && liftCard.competition !== undefined) {
      referenceLines.push({
        label: "Competition", data: values.map(() => liftCard.competition), borderColor: CHART_COLORS[4],
        borderDash: [2, 4], pointRadius: 0, borderWidth: 1.5,
      });
    }
    const liftDataset = buildDataset(liftCard.label || lift, values, CHART_COLORS[0]);
    liftDataset.pointRadius = isPr.map((value) => value ? 5 : 2);
    liftDataset.pointBackgroundColor = isPr.map((value) => value ? "#ffc553" : "#797876");
    ensureChart(widgetId, container, {
      labels: history.map((row) => row.entry_date), datasets: [liftDataset].concat(referenceLines),
    }, chartOptions());
  }

  function renderActivityTrend(widgetId, container, data) {
    const history = data.health_history || [];
    const labels = history.map((row) => row.entry_date);
    const restingHeartRate = buildDataset("Resting heart rate", history.map((row) => row.resting_heart_rate), CHART_COLORS[0]);
    const variability = buildDataset("Heart rate variability", history.map((row) => row.heart_rate_variability_ms), CHART_COLORS[1]);
    const sleep = buildDataset("Sleep", history.map((row) => row.sleep_minutes === null || row.sleep_minutes === undefined ? null : row.sleep_minutes / 60), CHART_COLORS[2]);
    restingHeartRate.yAxisID = "y";
    variability.yAxisID = "y";
    sleep.yAxisID = "y1";
    ensureChart(widgetId, container, { labels: labels, datasets: [restingHeartRate, variability, sleep] }, chartOptions({
      y1: {
        position: "right", ticks: { color: "#797876", font: { size: 10 } },
        grid: { drawOnChartArea: false }, title: { display: true, text: "Hours", color: "#797876" },
      },
    }));
  }

  const cardRenderers = {
    lift_card: (widgetId, data) => {
      const card = widgetId === "lift.total"
        ? Object.assign({}, data.total_card, { competition_delta: null, competition_attainment_pct: null })
        : (data.lift_cards || []).find((item) => item.id === widgetId);
      return liftCardHtml(card || { label: widgetLabel(widgetId), unit: "kg" });
    },
    body_card: (widgetId, data) => bodyCardHtml((data.body_cards || []).find((item) => item.id === widgetId) || { label: widgetLabel(widgetId), unit: "kg" }),
    index_card: (widgetId, data) => indexCardHtml((data.index_cards || []).find((item) => item.id === widgetId) || { label: widgetLabel(widgetId), unit: "" }),
    health_card: healthCardHtml,
    dots_card: analyticsCardHtml,
    ratio_card: analyticsCardHtml,
    rate_card: analyticsCardHtml,
  };

  const chartRenderers = {
    chart: renderStandardChart,
    pr_timeline_chart: renderPrTimeline,
    activity_trend_chart: renderActivityTrend,
  };

  function widgetById(widgetId) {
    return catalog.find((widget) => widget.id === widgetId);
  }

  function renderWidgetElement(element) {
    if (!dashboardData || !element || !element.gridstackNode) return;
    const widgetId = element.gridstackNode.id;
    const widget = widgetById(widgetId);
    if (!widget) return;
    const content = element.querySelector(".grid-stack-item-content");
    if (!content) return;
    if (cardRenderers[widget.kind]) {
      content.innerHTML = cardRenderers[widget.kind](widgetId, dashboardData);
    } else if (chartRenderers[widget.kind]) {
      chartRenderers[widget.kind](widgetId, content, dashboardData);
    }
    if (editing) addRemoveControl(element);
  }

  function renderAllWidgetContents() {
    grid.getGridItems().forEach(renderWidgetElement);
    currentWidgetIds = grid.getGridItems().map((element) => element.gridstackNode.id);
  }

  function destroyCharts() {
    Object.values(charts).forEach((chart) => chart.destroy());
    charts = {};
  }

  function defaultWidgetSize(widget) {
    const isChart = ["chart", "pr_timeline_chart", "activity_trend_chart"].includes(widget.kind);
    if (isChart) return { w: widget.kind === "pr_timeline_chart" ? 4 : 6, h: 8 };
    if (widget.kind === "lift_card") return { w: 3, h: 6 };
    return { w: 3, h: 4 };
  }

  function activeScreen() {
    return screens[activeScreenIndex];
  }

  function addWidget(item) {
    const element = grid.addWidget({
      id: item.id,
      x: item.x,
      y: item.y,
      w: item.w,
      h: item.h,
      content: "",
    });
    return element;
  }

  function rebuildGrid() {
    const screen = activeScreen();
    if (!screen) return;
    destroyCharts();
    grid.removeAll(true);
    screen.skipped = [];
    skippedLayoutItems = screen.skipped;
    const allowedIds = new Set(catalog.map((widget) => widget.id));
    screen.widgets.forEach((item) => {
      if (allowedIds.has(item.id)) addWidget(item);
      else skippedLayoutItems.push({ id: item.id, x: item.x, y: item.y, w: item.w, h: item.h });
    });
    renderAllWidgetContents();
    if (editing) {
      addRemoveControls();
      populateTray();
    }
  }

  function liveScreenWidgets() {
    const positions = grid.save(false, false).map((item) => ({
      id: item.id, x: item.x, y: item.y, w: item.w, h: item.h,
    }));
    const ids = new Set(positions.map((item) => item.id));
    skippedLayoutItems.forEach((item) => {
      if (!ids.has(item.id)) positions.push(item);
    });
    return positions;
  }

  function storeActiveScreen() {
    const screen = activeScreen();
    if (!screen || !grid) return;
    screen.widgets = liveScreenWidgets();
    const visibleIds = new Set(grid.getGridItems().map((item) => item.gridstackNode.id));
    screen.skipped = screen.widgets.filter((item) => !visibleIds.has(item.id));
    skippedLayoutItems = screen.skipped;
  }

  function addRemoveControl(element) {
    const content = element.querySelector(".grid-stack-item-content");
    if (!content || content.querySelector(".widget-remove")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "widget-remove";
    button.setAttribute("aria-label", "Remove " + element.gridstackNode.id);
    button.textContent = "×";
    button.addEventListener("click", () => {
      const widgetId = element.gridstackNode.id;
      if (charts[widgetId]) {
        charts[widgetId].destroy();
        delete charts[widgetId];
      }
      grid.removeWidget(element);
      currentWidgetIds = grid.getGridItems().map((gridItem) => gridItem.gridstackNode.id);
      populateTray();
    });
    content.appendChild(button);
  }

  function addRemoveControls() {
    grid.getGridItems().forEach(addRemoveControl);
  }

  function removeRemoveControls() {
    document.querySelectorAll(".widget-remove").forEach((button) => button.remove());
  }

  function populateTray() {
    const tray = document.getElementById("widget-tray");
    const activeIds = new Set(grid.getGridItems().map((element) => element.gridstackNode.id));
    const available = catalog.filter((widget) => !activeIds.has(widget.id));
    const byCategory = available.reduce((groups, widget) => {
      (groups[widget.category] = groups[widget.category] || []).push(widget);
      return groups;
    }, {});
    if (!available.length) {
      tray.innerHTML = '<div class="widget-tray-empty">Every available widget is already on this screen.</div>';
      return;
    }
    tray.innerHTML = Object.entries(byCategory).map(([category, widgets]) =>
      '<section class="widget-tray-group"><h2>' + category + "</h2>" +
      widgets.map((widget) => '<div class="widget-tray-item"><span>' + widget.label +
        '</span><button type="button" class="tray-add" data-widget-id="' + widget.id + '">Add</button></div>').join("") +
      "</section>"
    ).join("");
    tray.querySelectorAll(".tray-add").forEach((button) => {
      button.addEventListener("click", () => {
        const widget = widgetById(button.dataset.widgetId);
        if (!widget) return;
        const size = defaultWidgetSize(widget);
        addWidget({ id: widget.id, w: size.w, h: size.h });
        renderAllWidgetContents();
        populateTray();
      });
    });
  }

  function startRotationTimer() {
    stopRotationTimer();
    if (editing || screens.length < 2) return;
    rotationTimer = window.setInterval(() => {
      goToScreen((activeScreenIndex + 1) % screens.length);
    }, Math.max(rotationSeconds, 5) * 1000);
  }

  function stopRotationTimer() {
    if (rotationTimer) window.clearInterval(rotationTimer);
    rotationTimer = null;
  }

  function goToScreen(index) {
    if (!screens.length) return;
    const nextIndex = ((index % screens.length) + screens.length) % screens.length;
    if (editing) storeActiveScreen();
    activeScreenIndex = nextIndex;
    rebuildGrid();
    renderScreenTabs();
    startRotationTimer();
  }

  function uniqueScreenId() {
    const existing = new Set(screens.map((screen) => screen.id));
    let suffix = screens.length + 1;
    let screenId = "screen-" + suffix;
    while (existing.has(screenId)) {
      suffix += 1;
      screenId = "screen-" + suffix;
    }
    return screenId;
  }

  function addScreen() {
    storeActiveScreen();
    screens.push({ id: uniqueScreenId(), name: "New screen", widgets: [], skipped: [] });
    goToScreen(screens.length - 1);
  }

  function removeScreen(index) {
    if (screens.length <= 1) return;
    storeActiveScreen();
    screens.splice(index, 1);
    if (index < activeScreenIndex) activeScreenIndex -= 1;
    if (activeScreenIndex >= screens.length) activeScreenIndex = screens.length - 1;
    rebuildGrid();
    renderScreenTabs();
  }

  function renderScreenTabs() {
    const tabs = document.getElementById("screen-tabs");
    tabs.innerHTML = "";
    screens.forEach((screen, index) => {
      const tab = document.createElement(editing ? "div" : "button");
      tab.className = "screen-tab" + (index === activeScreenIndex ? " active" : "");
      if (!editing) {
        tab.type = "button";
        tab.textContent = screen.name;
        tab.addEventListener("click", () => goToScreen(index));
      } else {
        const input = document.createElement("input");
        input.type = "text";
        input.className = "screen-name-input";
        input.value = screen.name;
        input.setAttribute("aria-label", "Screen name");
        input.addEventListener("input", () => {
          screen.name = input.value;
        });
        input.addEventListener("focus", () => {
          if (index !== activeScreenIndex) goToScreen(index);
        });
        tab.appendChild(input);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "screen-remove";
        remove.setAttribute("aria-label", "Remove " + screen.name);
        remove.textContent = "×";
        remove.disabled = screens.length === 1;
        remove.addEventListener("click", () => removeScreen(index));
        tab.appendChild(remove);
      }
      tabs.appendChild(tab);
    });
    if (editing) {
      const add = document.createElement("button");
      add.type = "button";
      add.className = "screen-add";
      add.textContent = "Add screen";
      add.addEventListener("click", addScreen);
      tabs.appendChild(add);
    }
  }

  function setEditing(active) {
    editing = active;
    const editButton = document.getElementById("edit-dashboard-btn");
    const saveButton = document.getElementById("save-dashboard-btn");
    const cancelButton = document.getElementById("cancel-dashboard-btn");
    const resetButton = document.getElementById("reset-dashboard-btn");
    const tray = document.getElementById("widget-tray");
    editButton.hidden = active;
    saveButton.hidden = !active;
    cancelButton.hidden = !active;
    resetButton.hidden = !active;
    tray.hidden = !active;
    document.body.classList.toggle("dashboard-editing", active);
    grid.setStatic(!active);
    if (active) {
      stopRotationTimer();
      addRemoveControls();
      populateTray();
    } else {
      removeRemoveControls();
      tray.innerHTML = "";
      startRotationTimer();
    }
    renderScreenTabs();
    requestAnimationFrame(() => {
      Object.values(charts).forEach((chart) => chart.resize());
    });
  }

  function updateChrome(data) {
    const title = document.getElementById("dashboard-title");
    const date = document.getElementById("latest-entry-date");
    const badge = document.getElementById("entry-count-badge");
    if (data.dashboard_title) title.textContent = data.dashboard_title;
    date.textContent = data.latest_entry_date ? "Latest entry: " + data.latest_entry_date : "No entries yet";
    badge.textContent = data.entry_count === null || data.entry_count === undefined
      ? "Unavailable"
      : data.entry_count + (data.entry_count === 1 ? " entry" : " entries");
  }

  function requestJson(path, options) {
    return fetch(path, options).then((response) => {
      if (!response.ok) return response.json().then((body) => Promise.reject(body));
      return response.json();
    });
  }

  function refresh() {
    if (editing) return;
    requestJson("/api/dashboard")
      .then((data) => {
        dashboardData = data;
        updateChrome(data);
        renderAllWidgetContents();
      })
      .catch((error) => console.error("Failed to refresh dashboard", error));
  }

  function applyLayoutResponse(result) {
    screens = result.screens.map((screen) => ({
      id: screen.id,
      name: screen.name,
      widgets: screen.widgets || [],
      skipped: [],
    }));
    activeScreenIndex = 0;
    rotationSeconds = Number(result.rotation_seconds) || rotationSeconds;
    rebuildGrid();
    renderScreenTabs();
    startRotationTimer();
  }

  function loadSavedLayout() {
    return requestJson("/api/dashboard/layout").then((result) => {
      applyLayoutResponse(result);
      return result;
    });
  }

  function saveLayout() {
    storeActiveScreen();
    const payload = {
      screens: screens.map((screen) => ({
        id: screen.id,
        name: screen.name,
        widgets: screen.widgets,
      })),
    };
    return requestJson("/api/dashboard/layout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(() => {
      setEditing(false);
    });
  }

  function initialise() {
    grid = GridStack.init({
      column: 12,
      cellHeight: 50,
      margin: 10,
      float: true,
      columnOpts: { breakpoints: [{ w: 700, c: 1, layout: "list" }] },
    }, "#dashboard-grid");
    grid.setStatic(true);
    grid.on("resizestop", (_event, element) => {
      const widgetId = element.gridstackNode && element.gridstackNode.id;
      const chart = charts[widgetId];
      if (chart && element.querySelector("canvas")) chart.resize();
    });
    document.getElementById("edit-dashboard-btn").addEventListener("click", () => setEditing(true));
    document.getElementById("save-dashboard-btn").addEventListener("click", () => {
      saveLayout().catch((error) => window.alert("Could not save dashboard: " + (error.detail || "Unknown error")));
    });
    document.getElementById("cancel-dashboard-btn").addEventListener("click", () => {
      setEditing(false);
      loadSavedLayout().catch((error) => console.error("Could not restore dashboard", error));
    });
    document.getElementById("reset-dashboard-btn").addEventListener("click", () => {
      requestJson("/api/dashboard/layout/reset", { method: "POST" })
        .then(() => {
          setEditing(false);
          return loadSavedLayout();
        })
        .catch((error) => window.alert("Could not reset dashboard: " + (error.detail || "Unknown error")));
    });
    Promise.all([
      requestJson("/api/widgets/catalog"),
      requestJson("/api/dashboard/layout"),
      requestJson("/api/dashboard"),
    ]).then(([catalogResponse, layoutResponse, data]) => {
      catalog = catalogResponse.widgets;
      dashboardData = data;
      updateChrome(data);
      applyLayoutResponse(layoutResponse);
    }).catch((error) => console.error("Could not load dashboard", error));
  }

  let screens = [];
  let activeScreenIndex = 0;
  let rotationSeconds = (window.DASHBOARD_CONFIG && window.DASHBOARD_CONFIG.rotationSeconds) || 30;
  let rotationTimer = null;

  initialise();
  const pollSeconds = (window.DASHBOARD_CONFIG && window.DASHBOARD_CONFIG.pollSeconds) || 60;
  setInterval(refresh, pollSeconds * 1000);
})();
