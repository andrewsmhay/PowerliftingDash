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

  const DEFAULT_CELL_HEIGHT = 50;
  const MIN_CELL_HEIGHT = 28;
  const LIST_LAYOUT_BREAKPOINT = 700;
  const GRID_COLUMNS = 12;

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

  const SCORE_DATA_KEYS = {
    "score.dots": "dots_score",
    "score.wilks2": "wilks2_score",
    "score.ipf_gl": "ipf_gl_score",
  };

  function scoreCardHtml(widgetId, data) {
    const score = data[SCORE_DATA_KEYS[widgetId]] || {};
    const label = score.label || widgetLabel(widgetId);
    const unit = score.unit || "";
    if (score.reason === "sex_not_configured") {
      return '<div class="card"><div class="card-label">' + label + '</div><div class="card-value">' +
        valueHtml(null, unit) + '</div><div class="card-meta"><span>Configure sex in Settings to calculate this.</span></div></div>';
    }
    const pct = score.progress_pct === null || score.progress_pct === undefined ? 0 : score.progress_pct;
    const progressHtml = '<div class="progress-track"><div class="progress-fill" style="width:' + pct + '%"></div></div>';
    const pctLabelHtml = pctOfTargetHtml(score.target_attainment_pct);
    const metaHtml = '<div class="card-meta"><span>Target <strong>' + (fmt(score.target) ?? "Not set") + " " + unit + '</strong></span>' +
      '<span>Remaining <strong>' + (fmt(score.remaining) ?? "Not set") + " " + unit + "</strong></span></div>";
    const delta = score.delta_from_last_entry;
    let deltaHtml = "";
    if (delta !== null && delta !== undefined) {
      const cls = delta >= 0 ? "positive" : "negative";
      const sign = delta >= 0 ? "+" : "";
      deltaHtml = '<span class="delta-pill ' + cls + '">' + sign + fmt(delta) + " " + unit + " vs last entry</span>";
    }
    // The "% of target" label sits on the same row as the delta pill rather
    // than on its own line: score cards are only 4 rows tall, and an extra
    // line once a target was set pushed the delta pill out of the card.
    const footerHtml = pctLabelHtml || deltaHtml
      ? '<div class="score-footer">' + deltaHtml + pctLabelHtml + "</div>"
      : "";
    return '<div class="card"><div class="card-label">' + label + '</div><div class="card-value">' +
      valueHtml(score.value, unit ? " " + unit : "", 1) + "</div>" +
      progressHtml + metaHtml + footerHtml + "</div>";
  }

  function analyticsCardHtml(widgetId, data) {
    const parts = widgetId.split(".");
    const type = parts[0];
    const lift = parts[1].replace("_bw", "");
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

  const PR_INTERVAL_DATA_KEYS = {
    "pr_interval.squat": "squat",
    "pr_interval.bench": "bench",
    "pr_interval.deadlift": "deadlift",
  };

  function prIntervalCardHtml(widgetId, data) {
    const lift = PR_INTERVAL_DATA_KEYS[widgetId];
    const interval = (data.pr_intervals || {})[lift] || {};
    const label = widgetLabel(widgetId);
    if (interval.avg_days_between_prs === null || interval.avg_days_between_prs === undefined) {
      const metaText = interval.pr_count === 1
        ? "One PR recorded - log another to see a pace."
        : "Not enough PR history yet.";
      return '<div class="card"><div class="card-label">' + label + '</div><div class="card-value">' +
        '<span class="empty">No data</span></div><div class="card-meta"><span>' + metaText + '</span></div></div>';
    }
    const daysSince = interval.days_since_last_pr;
    const metaHtml = '<div class="card-meta"><span>Last PR <strong>' + ukDate(interval.last_pr_date) + '</strong></span>' +
      '<span>Days since <strong>' + (daysSince === null || daysSince === undefined ? "-" : daysSince) + '</strong></span></div>';
    return '<div class="card"><div class="card-label">' + label + '</div><div class="card-value">' +
      fmt(interval.avg_days_between_prs, 0) + '<span class="unit"> days</span></div>' + metaHtml + '</div>';
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

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
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
    if (widgetId === "chart.body_composition") {
      renderBodyComposition(widgetId, container, data);
      return;
    }
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

  function countdownListHtml(widgetId, data) {
    const label = widgetLabel(widgetId);
    const block = data.countdowns_upcoming || { items: [], total: 0 };
    const items = block.items || [];
    if (!items.length) {
      return '<div class="card countdown-list-card"><div class="card-label">' + label + '</div>' +
        '<div class="empty" style="margin-top:10px;">No upcoming events. ' +
        '<a href="/competitions">Add a countdown</a>.</div></div>';
    }
    const cardsHtml = items.map((item) => {
      const location = item.display_location ? '<span>' + escapeHtml(item.display_location) + '</span>' : "";
      return '<div class="countdown-item">' +
        '<div class="countdown-item-time">' + escapeHtml(item.time_until) + '</div>' +
        '<div class="countdown-item-name">' + escapeHtml(item.event_name) + '</div>' +
        '<div class="countdown-item-meta">' + escapeHtml(item.display_date) + (location ? " &middot; " + location : "") + '</div>' +
        '</div>';
    }).join("");
    let moreHtml = "";
    if (block.total > items.length) {
      moreHtml = '<div class="countdown-list-more"><a href="/competitions">+' +
        (block.total - items.length) + ' more on Competition history</a></div>';
    }
    return '<div class="card countdown-list-card"><div class="card-label">' + label + '</div>' +
      '<div class="countdown-list-grid">' + cardsHtml + '</div>' + moreHtml + '</div>';
  }

  // ---------------------------------------------------------------------
  // Meet Prep and Performance widgets
  // ---------------------------------------------------------------------

  const COLOUR_TEAL = CHART_COLORS[0];
  const COLOUR_RUST = CHART_COLORS[1];
  const COLOUR_GOLD = CHART_COLORS[2];
  const COLOUR_ICE = CHART_COLORS[3];
  const COLOUR_PLUM = CHART_COLORS[4];
  const COLOUR_MUTED = "#797876";
  const COLOUR_GRID = "#26241f";
  const DAY_MS = 86400000;

  function dayNumber(isoDate) {
    return Math.round(Date.parse(isoDate + "T00:00:00Z") / DAY_MS);
  }

  function dayLabel(dayValue) {
    const date = new Date(dayValue * DAY_MS);
    const dd = String(date.getUTCDate()).padStart(2, "0");
    const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
    return dd + "/" + mm + "/" + String(date.getUTCFullYear()).slice(2);
  }

  const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function monthLabel(yearMonth) {
    const parts = yearMonth.split("-");
    return MONTH_NAMES[Number(parts[1]) - 1] + " " + parts[0].slice(2);
  }

  function signed(value, decimals, unit) {
    if (value === null || value === undefined) return "-";
    const sign = value > 0 ? "+" : value < 0 ? "−" : "";
    return sign + fmt(Math.abs(value), decimals) + (unit || "");
  }

  function hasValue(value) {
    return value !== null && value !== undefined && !Number.isNaN(value);
  }

  // Draws a dashed vertical line with a caption, e.g. meet day.
  const verticalMarkerPlugin = {
    id: "verticalMarker",
    afterDatasetsDraw(chart) {
      const marker = chart.options.plugins.verticalMarker;
      if (!marker || !hasValue(marker.x)) return;
      const xScale = chart.scales.x;
      const area = chart.chartArea;
      const x = xScale.getPixelForValue(marker.x);
      if (x < area.left - 1 || x > area.right + 1) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = marker.colour || COLOUR_PLUM;
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, area.top);
      ctx.lineTo(x, area.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = marker.colour || COLOUR_PLUM;
      ctx.font = "600 10px -apple-system, Segoe UI, Roboto, sans-serif";
      ctx.textAlign = x > area.right - 60 ? "right" : "left";
      ctx.fillText(marker.label || "", x + (ctx.textAlign === "right" ? -5 : 5), area.top + 10);
      ctx.restore();
    },
  };

  // Writes each DOTS curve's level at its right-hand end.
  const curveLabelPlugin = {
    id: "curveLabels",
    afterDatasetsDraw(chart) {
      const ctx = chart.ctx;
      const area = chart.chartArea;
      ctx.save();
      ctx.font = "10px -apple-system, Segoe UI, Roboto, sans-serif";
      ctx.fillStyle = COLOUR_MUTED;
      ctx.textAlign = "right";
      chart.data.datasets.forEach((dataset, index) => {
        if (!dataset.curveLabel || !chart.isDatasetVisible(index)) return;
        const meta = chart.getDatasetMeta(index);
        for (let i = meta.data.length - 1; i >= 0; i -= 1) {
          const point = meta.data[i];
          if (point.x <= area.right && point.y >= area.top + 8 && point.y <= area.bottom) {
            if (point.x < area.left + 70) break;
            ctx.fillText(dataset.curveLabel, Math.min(point.x, area.right) - 2, point.y - 4);
            break;
          }
        }
      });
      ctx.restore();
    },
  };

  // Zero axes and corner captions for the recomposition quadrant chart.
  const quadrantPlugin = {
    id: "quadrants",
    beforeDatasetsDraw(chart) {
      if (!chart.options.plugins.quadrants) return;
      const ctx = chart.ctx;
      const area = chart.chartArea;
      const x0 = chart.scales.x.getPixelForValue(0);
      const y0 = chart.scales.y.getPixelForValue(0);
      ctx.save();
      ctx.strokeStyle = "#4a4946";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, area.top);
      ctx.lineTo(x0, area.bottom);
      ctx.moveTo(area.left, y0);
      ctx.lineTo(area.right, y0);
      ctx.stroke();
      ctx.font = "600 10.5px -apple-system, Segoe UI, Roboto, sans-serif";
      const corners = [
        { text: "Recomposition", x: area.left + 6, y: area.top + 14, align: "left", colour: QUADRANT_COLOURS.recomposition },
        { text: "Lean gain", x: area.right - 6, y: area.top + 14, align: "right", colour: QUADRANT_COLOURS.lean_gain },
        { text: "Cut", x: area.left + 6, y: area.bottom - 6, align: "left", colour: QUADRANT_COLOURS.cut },
        { text: "Regression", x: area.right - 6, y: area.bottom - 6, align: "right", colour: QUADRANT_COLOURS.regression },
      ];
      corners.forEach((corner) => {
        ctx.fillStyle = corner.colour;
        ctx.textAlign = corner.align;
        ctx.fillText(corner.text, corner.x, corner.y);
      });
      ctx.restore();
    },
  };

  const QUADRANT_COLOURS = {
    recomposition: "#6daa45",
    lean_gain: COLOUR_TEAL,
    cut: COLOUR_GOLD,
    regression: "#d163a7",
  };

  const QUADRANT_LABELS = {
    recomposition: "recomposition",
    lean_gain: "lean gain",
    cut: "cut",
    regression: "regression",
  };

  function baseScale(extra) {
    return Object.assign({
      ticks: { color: COLOUR_MUTED, font: { size: 10 } },
      grid: { color: COLOUR_GRID },
    }, extra || {});
  }

  function baseOptions(extra) {
    const options = {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { position: "bottom", labels: { color: COLOUR_MUTED, boxWidth: 12, font: { size: 11 } } },
      },
    };
    return Object.assign(options, extra || {}, {
      plugins: Object.assign(options.plugins, (extra || {}).plugins || {}),
    });
  }

  function dateAxis(extra) {
    return baseScale(Object.assign({
      type: "linear",
      ticks: { color: COLOUR_MUTED, font: { size: 10 }, maxTicksLimit: 7, callback: (value) => dayLabel(value) },
    }, extra || {}));
  }

  function chartShell(widgetId, container, summaryHtml) {
    let card = container.querySelector(".chart-card.insight-chart");
    if (!card) {
      if (charts[widgetId]) {
        charts[widgetId].destroy();
        delete charts[widgetId];
      }
      container.innerHTML = '<div class="chart-card insight-chart"><div class="card-label">' + widgetLabel(widgetId) +
        '</div><div class="chart-summary"></div><div class="chart-canvas-wrap"><canvas></canvas></div></div>';
      card = container.querySelector(".chart-card");
    }
    card.querySelector(".chart-summary").innerHTML = summaryHtml || "";
    return card.querySelector("canvas");
  }

  function renderInsightChart(widgetId, container, summaryHtml, config) {
    const canvas = chartShell(widgetId, container, summaryHtml);
    const existing = charts[widgetId];
    if (existing && existing.config.type === config.type) {
      existing.data = config.data;
      existing.options = config.options;
      existing.update("none");
      return;
    }
    if (existing) existing.destroy();
    charts[widgetId] = new Chart(canvas, config);
  }

  function renderInsightEmpty(widgetId, container, messageHtml) {
    if (charts[widgetId]) {
      charts[widgetId].destroy();
      delete charts[widgetId];
    }
    container.innerHTML = '<div class="card insight-empty"><div class="card-label">' + widgetLabel(widgetId) +
      '</div><div class="insight-empty-text">' + messageHtml + "</div></div>";
  }

  function statHtml(label, value, tone) {
    return '<span class="chart-stat' + (tone ? " " + tone : "") + '"><span class="chart-stat-label">' + label +
      "</span> " + value + "</span>";
  }

  function meetPrep(data) {
    return data.meet_prep || {};
  }

  function performance(data) {
    return data.performance || {};
  }

  function renderMeetProjection(widgetId, container, data) {
    const prep = meetPrep(data);
    const projection = prep.projection || {};
    const series = projection.series || [];
    if (!series.length) {
      renderInsightEmpty(widgetId, container,
        'Log entries with all three lifts to see your total trend. <a href="/entries/new">Add an entry</a>.');
      return;
    }
    const meetDay = projection.meet_date ? dayNumber(projection.meet_date) : null;
    const historyPoints = series.map((point) => ({ x: dayNumber(point.date), y: point.total }));
    const firstX = historyPoints[0].x;
    const lastX = meetDay !== null ? meetDay : historyPoints[historyPoints.length - 1].x;
    const datasets = [{
      label: "Total", data: historyPoints, borderColor: COLOUR_TEAL, backgroundColor: COLOUR_TEAL,
      pointRadius: 2, borderWidth: 2, tension: 0.25,
    }];
    if (meetDay !== null && hasValue(projection.projected_total) && projection.projection_start_date) {
      datasets.push({
        label: "Projected", data: [
          { x: dayNumber(projection.projection_start_date), y: projection.current_total },
          { x: meetDay, y: projection.projected_total },
        ],
        borderColor: COLOUR_ICE, backgroundColor: COLOUR_ICE, borderDash: [6, 5], pointRadius: (ctx) => (ctx.dataIndex === 1 ? 5 : 0), borderWidth: 2,
      });
    }
    if (hasValue(projection.target_total)) {
      datasets.push({
        label: "Target", data: [{ x: firstX, y: projection.target_total }, { x: lastX, y: projection.target_total }],
        borderColor: COLOUR_GOLD, backgroundColor: COLOUR_GOLD, borderDash: [3, 4], pointRadius: 0, borderWidth: 1.5,
      });
    }
    let summary;
    if (meetDay === null) {
      summary = statHtml("Current total", fmt(projection.current_total) + " kg") +
        '<span class="chart-stat muted">Add a countdown on <a href="/competitions">Competitions</a> to project to meet day.</span>';
    } else if (!hasValue(projection.projected_total)) {
      summary = '<span class="chart-stat muted">Log all three lifts to project a meet-day total.</span>';
    } else {
      const gap = projection.projected_vs_target;
      const tone = !hasValue(gap) ? "" : gap >= 0 ? "positive" : "negative";
      const lifts = projection.lifts || {};
      const liftText = ["squat", "bench", "deadlift"].map((key) => {
        const lift = lifts[key] || {};
        const initial = key === "squat" ? "S" : key === "bench" ? "B" : "D";
        return initial + " " + fmt(lift.projected) + (lift.trend_available ? "" : " (flat)");
      }).join(" · ");
      summary = statHtml("Meet day", fmt(projection.projected_total) + " kg") +
        (hasValue(projection.target_total) ? statHtml("Target", fmt(projection.target_total) + " kg") : "") +
        (hasValue(gap) ? statHtml("Gap", signed(gap, 1, " kg"), tone) : "") +
        '<span class="chart-stat muted">' + liftText + "</span>";
    }
    renderInsightChart(widgetId, container, summary, {
      type: "line",
      data: { datasets: datasets },
      options: baseOptions({
        interaction: { mode: "nearest", intersect: false },
        scales: {
          x: dateAxis({ min: firstX, max: lastX + Math.max(2, Math.round((lastX - firstX) * 0.03)) }),
          y: baseScale({ title: { display: true, text: "kg", color: COLOUR_MUTED } }),
        },
        plugins: {
          tooltip: { callbacks: { title: (items) => items.length ? dayLabel(items[0].parsed.x) : "" } },
          verticalMarker: meetDay !== null ? { x: meetDay, label: "Meet day" } : null,
        },
      }),
      plugins: [verticalMarkerPlugin],
    });
  }

  function nextMeetCardHtml(widgetId, data) {
    const prep = meetPrep(data);
    const meet = prep.next_meet;
    const label = widgetLabel(widgetId);
    if (!meet) {
      return '<div class="card insight-empty"><div class="card-label">' + label + '</div>' +
        '<div class="insight-empty-text">No upcoming meet. <a href="/competitions">Add a countdown</a> ' +
        "and Meet Prep will plan towards it.</div></div>";
    }
    const days = meet.days_until;
    const weeks = Math.floor(days / 7);
    const remainder = days % 7;
    const weeksText = days === 0 ? "Meet day" : weeks + (weeks === 1 ? " week" : " weeks") +
      (remainder ? " " + remainder + (remainder === 1 ? " day" : " days") : "");
    const weightClass = meet.weight_class;
    let classText = "Not set";
    if (weightClass) {
      classText = escapeHtml(weightClass.label) +
        (meet.weight_class_source === "last_meet" ? ' <span class="muted-note">from last meet</span>' : "");
    }
    const projection = prep.projection || {};
    const status = prep.weight_class || {};
    const rows = [
      ["Weight class", classText],
      ["Projected total", hasValue(projection.projected_total) ? fmt(projection.projected_total) + " kg" : "-"],
      ["Target total", hasValue(projection.target_total) ? fmt(projection.target_total) + " kg" : "Not set"],
      ["Projected weigh-in", hasValue(status.projected_weigh_in) ? fmt(status.projected_weigh_in) + " kg" : "-"],
    ];
    return '<div class="card next-meet-card"><div class="card-label">' + label + "</div>" +
      '<div class="next-meet-days">' + days + '<span class="unit">' + (days === 1 ? "day" : "days") + "</span></div>" +
      '<div class="next-meet-weeks">' + weeksText + "</div>" +
      '<div class="next-meet-name">' + escapeHtml(meet.event_name) + "</div>" +
      '<div class="next-meet-meta">' + ukDate(meet.event_date) + (meet.location ? " · " + escapeHtml(meet.location) : "") + "</div>" +
      '<dl class="next-meet-rows">' + rows.map((row) => "<dt>" + row[0] + "</dt><dd>" + row[1] + "</dd>").join("") + "</dl></div>";
  }

  function weightClassSummary(status) {
    const limitText = status.class_label ? escapeHtml(status.class_label) : "";
    const trend = hasValue(status.trend_kg_per_week) ? signed(status.trend_kg_per_week, 2, " kg/week") : "no trend yet";
    switch (status.state) {
      case "on_track":
        return statHtml("Under limit", fmt(status.margin_kg) + " kg", "positive") +
          statHtml("Trend", trend) + statHtml("Weigh-in", fmt(status.projected_weigh_in) + " kg");
      case "drifting_over":
        return statHtml("Under limit", fmt(status.margin_kg) + " kg") +
          statHtml("Trend", trend, "negative") +
          statHtml("Weigh-in", fmt(status.projected_weigh_in) + " kg over " + limitText, "negative");
      case "cutting_on_track":
        return statHtml("Over limit", fmt(Math.abs(status.margin_kg)) + " kg") +
          statHtml("Needed", signed(status.required_kg_per_week, 2, " kg/week")) +
          statHtml("Trend", trend, "positive");
      case "over":
        return statHtml("Over limit", fmt(Math.abs(status.margin_kg)) + " kg", "negative") +
          (hasValue(status.required_kg_per_week) ? statHtml("Needed", signed(status.required_kg_per_week, 2, " kg/week")) : "") +
          statHtml("Trend", trend);
      case "open_class":
        return statHtml("Class", limitText) + '<span class="chart-stat muted">Open class, no limit to make.</span>';
      default:
        return '<span class="chart-stat muted">Add a weight class to your next countdown on ' +
          '<a href="/competitions">Competitions</a> to see the limit.</span>';
    }
  }

  function renderWeightClass(widgetId, container, data) {
    const status = meetPrep(data).weight_class || {};
    const series = status.series || [];
    if (!series.length) {
      renderInsightEmpty(widgetId, container,
        'Log your bodyweight to track it against your weight class. <a href="/entries/new">Add an entry</a>.');
      return;
    }
    const points = series.map((point) => ({ x: dayNumber(point.date), y: point.body_weight }));
    const firstX = points[0].x;
    const meetDay = status.meet_date ? dayNumber(status.meet_date) : null;
    const lastX = meetDay !== null ? Math.max(meetDay, points[points.length - 1].x) : points[points.length - 1].x;
    const datasets = [{
      label: "Bodyweight", data: points, borderColor: COLOUR_TEAL, backgroundColor: COLOUR_TEAL,
      pointRadius: 2, borderWidth: 2, tension: 0.25,
    }];
    if (meetDay !== null && hasValue(status.projected_weigh_in)) {
      datasets.push({
        label: "Trend to weigh-in",
        data: [points[points.length - 1], { x: meetDay, y: status.projected_weigh_in }],
        borderColor: COLOUR_ICE, backgroundColor: COLOUR_ICE, borderDash: [6, 5], pointRadius: (ctx) => (ctx.dataIndex === 1 ? 5 : 0), borderWidth: 2,
      });
    }
    if (hasValue(status.limit_kg)) {
      datasets.push({
        label: "Class limit (" + status.class_label + ")",
        data: [{ x: firstX, y: status.limit_kg }, { x: lastX, y: status.limit_kg }],
        borderColor: COLOUR_RUST, backgroundColor: COLOUR_RUST, pointRadius: 0, borderWidth: 2,
        fill: { target: "end", above: "rgba(209, 99, 167, 0.08)", below: "rgba(209, 99, 167, 0.08)" },
      });
    }
    renderInsightChart(widgetId, container, weightClassSummary(status), {
      type: "line",
      data: { datasets: datasets },
      options: baseOptions({
        interaction: { mode: "nearest", intersect: false },
        scales: {
          x: dateAxis({ min: firstX, max: lastX + Math.max(2, Math.round((lastX - firstX) * 0.03)) }),
          y: baseScale({ title: { display: true, text: "kg", color: COLOUR_MUTED } }),
        },
        plugins: {
          tooltip: { callbacks: { title: (items) => items.length ? dayLabel(items[0].parsed.x) : "" } },
          verticalMarker: meetDay !== null ? { x: meetDay, label: "Weigh-in" } : null,
        },
      }),
      plugins: [verticalMarkerPlugin],
    });
  }

  function targetProgressHtml(widgetId, data) {
    const rows = meetPrep(data).target_progress || [];
    const label = widgetLabel(widgetId);
    if (!rows.length) {
      return '<div class="card insight-empty"><div class="card-label">' + label + "</div>" +
        '<div class="insight-empty-text">No targets set yet. <a href="/targets">Set targets</a> to track progress here.</div></div>';
    }
    const items = rows.map((row) => {
      const pct = row.progress_pct;
      const width = hasValue(pct) ? Math.max(0, Math.min(100, pct)) : 0;
      const tone = row.met ? "met" : hasValue(pct) && pct < 0 ? "behind" : "";
      const pctText = row.met ? "Met" : hasValue(pct) ? fmt(pct, 0) + "%" : "-";
      const unit = row.unit ? (row.unit === "%" ? "%" : " " + row.unit) : "";
      const valueText = (hasValue(row.current) ? fmt(row.current) : "-") + " / " + fmt(row.target) + unit;
      return '<div class="target-row ' + tone + '">' +
        '<div class="target-row-head"><span class="target-row-label">' + escapeHtml(row.label) + "</span>" +
        '<span class="target-row-pct">' + pctText + "</span></div>" +
        '<div class="target-row-track"><div class="target-row-fill" style="width:' + width + '%"></div></div>' +
        '<div class="target-row-value">' + valueText + "</div></div>";
    }).join("");
    const metCount = rows.filter((row) => row.met).length;
    return '<div class="card target-board"><div class="card-label">' + label +
      '<span class="card-label-note">' + metCount + " of " + rows.length + " met · progress from first entry</span></div>" +
      '<div class="target-grid">' + items + "</div></div>";
  }

  function renderStrengthScatter(widgetId, container, data) {
    const scatter = performance(data).strength_scatter || {};
    const entries = scatter.entries || [];
    const meets = scatter.meets || [];
    if (!entries.length && !meets.length) {
      renderInsightEmpty(widgetId, container,
        "Log entries with all three lifts and bodyweight to plot strength against bodyweight.");
      return;
    }
    const datasets = (scatter.dots_curves || []).map((curve) => ({
      type: "line", label: "DOTS " + curve.dots, curveLabel: "DOTS " + curve.dots, isCurve: true,
      data: curve.points.map((point) => ({ x: point.body_weight, y: point.total })),
      borderColor: "#4a4946", borderWidth: 1, borderDash: [3, 4], pointRadius: 0, tension: 0.3,
    }));
    if (entries.length) {
      datasets.push({
        label: "Gym entries", data: entries.slice(0, -1).map((point) => ({ x: point.body_weight, y: point.total, date: point.date })),
        backgroundColor: "rgba(32, 128, 141, 0.55)", borderColor: COLOUR_TEAL, pointRadius: 3,
      });
      const latest = entries[entries.length - 1];
      datasets.push({
        label: "Latest", data: [{ x: latest.body_weight, y: latest.total, date: latest.date }],
        backgroundColor: COLOUR_ICE, borderColor: "#ffffff", borderWidth: 1.5, pointRadius: 6,
      });
    }
    if (meets.length) {
      datasets.push({
        label: "Meets", data: meets.map((point) => ({ x: point.body_weight, y: point.total, date: point.date, name: point.name })),
        backgroundColor: COLOUR_GOLD, borderColor: COLOUR_GOLD, pointStyle: "triangle", pointRadius: 7,
      });
    }
    const allPoints = entries.concat(meets);
    const totals = allPoints.map((point) => point.total);
    const bodyweights = allPoints.map((point) => point.body_weight);
    const latest = entries.length ? entries[entries.length - 1] : meets[meets.length - 1];
    const dots = (data.dots_score || {}).value;
    let summary = statHtml("Latest", fmt(latest.total) + " kg at " + fmt(latest.body_weight) + " kg") +
      (hasValue(dots) ? statHtml("DOTS", fmt(dots)) : "");
    if (!scatter.sex_configured) {
      summary += '<span class="chart-stat muted">Set sex in <a href="/settings">Settings</a> to draw DOTS curves.</span>';
    } else {
      summary += '<span class="chart-stat muted">Moving up and across a curve is real strength, not just mass.</span>';
    }
    renderInsightChart(widgetId, container, summary, {
      type: "scatter",
      data: { datasets: datasets },
      options: baseOptions({
        scales: {
          x: baseScale({
            type: "linear", min: Math.floor(Math.min.apply(null, bodyweights) - 3),
            max: Math.ceil(Math.max.apply(null, bodyweights) + 3),
            title: { display: true, text: "Bodyweight (kg)", color: COLOUR_MUTED },
          }),
          y: baseScale({
            min: Math.floor((Math.min.apply(null, totals) - 25) / 10) * 10,
            max: Math.ceil((Math.max.apply(null, totals) + 25) / 10) * 10,
            title: { display: true, text: "Total (kg)", color: COLOUR_MUTED },
          }),
        },
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: COLOUR_MUTED, boxWidth: 12, font: { size: 11 }, filter: (item, chartData) => !chartData.datasets[item.datasetIndex].isCurve },
          },
          tooltip: {
            filter: (item) => !item.dataset.isCurve,
            callbacks: {
              label: (item) => {
                const raw = item.raw || {};
                const name = raw.name ? raw.name + ", " : "";
                return name + (raw.date ? ukDate(raw.date) + ": " : "") + fmt(raw.y) + " kg at " + fmt(raw.x) + " kg";
              },
            },
          },
        },
      }),
      plugins: [curveLabelPlugin],
    });
  }

  function shortMeetName(row) {
    const name = row.meet_name || "Meet";
    const trimmed = name.length > 18 ? name.slice(0, 17) + "…" : name;
    return [trimmed, ukDate(row.date)];
  }

  function renderGymVsPlatform(widgetId, container, data) {
    const block = performance(data).gym_vs_platform || {};
    const rows = (block.meets || []).slice(-8);
    if (!rows.length) {
      renderInsightEmpty(widgetId, container,
        'Log a meet on <a href="/competitions">Competitions</a>, or sync from OpenPowerlifting, to compare gym and platform totals.');
      return;
    }
    let summary;
    if (hasValue(block.average_carryover_pct)) {
      const tone = block.average_carryover_pct >= 100 ? "positive" : block.average_carryover_pct >= 95 ? "" : "negative";
      summary = statHtml("Average carry-over", fmt(block.average_carryover_pct) + "%", tone) +
        '<span class="chart-stat muted">across ' + block.paired_count + (block.paired_count === 1 ? " meet" : " meets") +
        " with a gym total in the " + block.max_gym_age_days + " days before</span>";
    } else {
      summary = '<span class="chart-stat muted">No gym totals logged in the ' + block.max_gym_age_days +
        " days before these meets, so there is nothing to compare yet.</span>";
    }
    renderInsightChart(widgetId, container, summary, {
      type: "bar",
      data: {
        labels: rows.map(shortMeetName),
        datasets: [
          { label: "Gym total", data: rows.map((row) => row.gym_total), backgroundColor: COLOUR_TEAL, borderRadius: 3 },
          { label: "Meet total", data: rows.map((row) => row.meet_total), backgroundColor: COLOUR_GOLD, borderRadius: 3 },
        ],
      },
      options: baseOptions({
        scales: {
          x: baseScale({ grid: { display: false } }),
          y: baseScale({
            min: Math.max(0, Math.floor((Math.min.apply(null, rows.map((row) => Math.min(row.meet_total, row.gym_total || row.meet_total))) * 0.85) / 50) * 50),
            title: { display: true, text: "kg", color: COLOUR_MUTED },
          }),
        },
        plugins: {
          tooltip: {
            callbacks: {
              title: (items) => items.length ? (rows[items[0].dataIndex].meet_name || "Meet") + ", " + ukDate(rows[items[0].dataIndex].date) : "",
              footer: (items) => {
                const row = items.length ? rows[items[0].dataIndex] : null;
                if (!row || !hasValue(row.carryover_pct)) return "No gym total to compare";
                return "Carry-over " + fmt(row.carryover_pct) + "% (gym " + ukDate(row.gym_date) + ")";
              },
            },
          },
        },
      }),
    });
  }

  function renderLiftBalance(widgetId, container, data) {
    const months = (performance(data).lift_balance || {}).months || [];
    if (!months.length) {
      renderInsightEmpty(widgetId, container, "Log entries with all three lifts to see how your total is split.");
      return;
    }
    const latest = months[months.length - 1];
    const summary = statHtml("Squat", fmt(latest.squat_pct) + "%") + statHtml("Bench", fmt(latest.bench_pct) + "%") +
      statHtml("Deadlift", fmt(latest.deadlift_pct) + "%") +
      '<span class="chart-stat muted">' + monthLabel(latest.month) + ", total " + fmt(latest.total) + " kg</span>";
    const dataset = (label, key, colour) => ({
      label: label, data: months.map((month) => month[key]), backgroundColor: colour, borderWidth: 0, barPercentage: 0.8,
    });
    renderInsightChart(widgetId, container, summary, {
      type: "bar",
      data: {
        labels: months.map((month) => monthLabel(month.month)),
        datasets: [
          dataset("Squat", "squat_pct", COLOUR_TEAL),
          dataset("Bench", "bench_pct", COLOUR_RUST),
          dataset("Deadlift", "deadlift_pct", COLOUR_GOLD),
        ],
      },
      options: baseOptions({
        scales: {
          x: baseScale({ stacked: true, grid: { display: false } }),
          y: baseScale({ stacked: true, min: 0, max: 100, ticks: { color: COLOUR_MUTED, font: { size: 10 }, callback: (value) => value + "%" } }),
        },
        plugins: {
          tooltip: { callbacks: { label: (item) => item.dataset.label + ": " + fmt(item.raw) + "%" } },
        },
      }),
    });
  }

  function renderRecomposition(widgetId, container, data) {
    const periods = (performance(data).recomposition || {}).periods || [];
    if (!periods.length) {
      renderInsightEmpty(widgetId, container,
        "Log bodyweight and fat mass across at least two months to see how your composition is changing.");
      return;
    }
    const latest = periods[periods.length - 1];
    const summary = statHtml(monthLabel(latest.month), signed(latest.lean_change, 1, " kg") + " lean, " +
      signed(latest.fat_change, 1, " kg") + " fat") +
      '<span class="chart-stat ' + (latest.quadrant === "regression" ? "negative" : latest.quadrant === "recomposition" ? "positive" : "") +
      '">' + QUADRANT_LABELS[latest.quadrant] + "</span>";
    const extent = Math.max(1, Math.max.apply(null, periods.map((period) => Math.max(Math.abs(period.lean_change), Math.abs(period.fat_change)))) * 1.25);
    const span = Math.ceil(extent * 2) / 2;
    renderInsightChart(widgetId, container, summary, {
      type: "scatter",
      data: {
        datasets: [{
          label: "Month-on-month change",
          data: periods.map((period) => ({ x: period.fat_change, y: period.lean_change, period: period })),
          backgroundColor: periods.map((period, index) => index === periods.length - 1 ? "#ffffff" : QUADRANT_COLOURS[period.quadrant]),
          borderColor: periods.map((period) => QUADRANT_COLOURS[period.quadrant]),
          borderWidth: periods.map((period, index) => index === periods.length - 1 ? 3 : 1),
          pointRadius: periods.map((period, index) => index === periods.length - 1 ? 7 : 5),
        }],
      },
      options: baseOptions({
        scales: {
          x: baseScale({ type: "linear", min: -span, max: span, title: { display: true, text: "Fat mass change (kg)", color: COLOUR_MUTED } }),
          y: baseScale({ min: -span, max: span, title: { display: true, text: "Lean mass change (kg)", color: COLOUR_MUTED } }),
        },
        plugins: {
          legend: { display: false },
          quadrants: true,
          tooltip: {
            callbacks: {
              label: (item) => {
                const period = item.raw.period;
                return monthLabel(period.month) + ": " + signed(period.lean_change, 2, " kg") + " lean, " +
                  signed(period.fat_change, 2, " kg") + " fat (" + QUADRANT_LABELS[period.quadrant] + ")";
              },
            },
          },
        },
      }),
      plugins: [quadrantPlugin],
    });
  }

  // ---------------------------------------------------------------------
  // Body Composition Over Time: "Separate" small multiples (default) or
  // "Change" since the first entry in view. Bodyweight is several times
  // larger than muscle or fat mass, so a single shared kg axis flattens
  // every trend; both views put each measurement on a readable scale.
  // ---------------------------------------------------------------------

  const BODY_COMPOSITION_MODE_KEY = "pld.bodyComposition.mode";
  const BODY_COMPOSITION_SERIES = [
    { key: "body_weight_mass", label: "Bodyweight", colour: CHART_COLORS[0] },
    { key: "skeletal_muscle_mass", label: "Muscle mass", colour: CHART_COLORS[1] },
    { key: "body_fat_mass", label: "Fat mass", colour: CHART_COLORS[2] },
  ];

  function bodyCompositionMode() {
    try {
      return window.localStorage.getItem(BODY_COMPOSITION_MODE_KEY) === "change" ? "change" : "separate";
    } catch (error) {
      return "separate";
    }
  }

  function setBodyCompositionMode(mode) {
    try {
      window.localStorage.setItem(BODY_COMPOSITION_MODE_KEY, mode);
    } catch (error) {
      // Private browsing can block storage; the toggle still works for this page.
    }
    bodyCompositionModeFallback = mode;
  }

  let bodyCompositionModeFallback = null;

  function currentBodyCompositionMode() {
    return bodyCompositionModeFallback || bodyCompositionMode();
  }

  function destroyWidgetCharts(widgetId) {
    Object.keys(charts).forEach((key) => {
      if (key === widgetId || key.indexOf(widgetId + ":") === 0) {
        charts[key].destroy();
        delete charts[key];
      }
    });
  }

  function shortIsoDate(isoDate) {
    if (!isoDate) return "";
    const parts = String(isoDate).split("-");
    return parts.length === 3 ? parts[2] + "/" + parts[1] + "/" + parts[0].slice(2) : isoDate;
  }

  function firstValue(values) {
    for (let i = 0; i < values.length; i += 1) {
      if (hasValue(values[i])) return { value: values[i], index: i };
    }
    return null;
  }

  function lastValue(values) {
    for (let i = values.length - 1; i >= 0; i -= 1) {
      if (hasValue(values[i])) return values[i];
    }
    return null;
  }

  // Draws a solid line at y = 0 so gains and losses read at a glance.
  const zeroLinePlugin = {
    id: "zeroLine",
    beforeDatasetsDraw(chart) {
      const scale = chart.scales.y;
      if (!scale || scale.min > 0 || scale.max < 0) return;
      const y = scale.getPixelForValue(0);
      const area = chart.chartArea;
      const ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = "#5a5957";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(area.left, y);
      ctx.lineTo(area.right, y);
      ctx.stroke();
      ctx.restore();
    },
  };

  function bodyCompositionShell(widgetId, container, mode) {
    const card = container.querySelector(".chart-card.body-composition");
    if (card && card.dataset.mode === mode) return card;
    destroyWidgetCharts(widgetId);
    const toggle = '<div class="view-toggle" role="group" aria-label="Chart view">' +
      ["separate", "change"].map((value) => '<button type="button" data-mode="' + value + '" aria-pressed="' +
        (value === mode) + '"' + (value === mode ? ' class="active"' : "") + ">" +
        (value === "separate" ? "Separate" : "Change") + "</button>").join("") + "</div>";
    let body;
    if (mode === "separate") {
      body = '<div class="bc-strips">' + BODY_COMPOSITION_SERIES.map((series, index) =>
        '<div class="bc-strip"><div class="bc-strip-head"><span class="bc-strip-name">' +
        '<span class="bc-swatch" style="background:' + series.colour + '"></span>' + series.label +
        '</span><span class="bc-strip-value" data-series="' + index + '"></span></div>' +
        '<div class="bc-strip-canvas"><canvas data-series="' + index + '"></canvas></div></div>').join("") + "</div>";
    } else {
      body = '<div class="chart-summary"></div><div class="chart-canvas-wrap"><canvas></canvas></div>';
    }
    container.innerHTML = '<div class="chart-card body-composition" data-mode="' + mode + '">' +
      '<div class="chart-card-head"><div class="card-label">' + widgetLabel(widgetId) + "</div>" + toggle + "</div>" +
      body + "</div>";
    container.querySelectorAll(".view-toggle button").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        if (button.dataset.mode === currentBodyCompositionMode()) return;
        setBodyCompositionMode(button.dataset.mode);
        const element = container.closest(".grid-stack-item");
        if (element) renderWidgetElement(element);
        else renderBodyComposition(widgetId, container, dashboardData || {});
      });
    });
    return container.querySelector(".chart-card");
  }

  function upsertChart(key, canvas, config) {
    if (charts[key]) {
      charts[key].data = config.data;
      charts[key].options = config.options;
      charts[key].update("none");
      return;
    }
    charts[key] = new Chart(canvas, config);
  }

  function renderBodyComposition(widgetId, container, data) {
    const history = data.history || [];
    const labels = history.map((row) => row.entry_date);
    const seriesValues = BODY_COMPOSITION_SERIES.map((series) => history.map((row) => row[series.key]));
    if (!seriesValues.some((values) => firstValue(values))) {
      destroyWidgetCharts(widgetId);
      container.innerHTML = '<div class="card insight-empty"><div class="card-label">' + widgetLabel(widgetId) +
        '</div><div class="insight-empty-text">Log bodyweight, muscle mass or fat mass to see how your ' +
        'composition changes. <a href="/entries/new">Add an entry</a>.</div></div>';
      return;
    }
    const mode = currentBodyCompositionMode();
    const card = bodyCompositionShell(widgetId, container, mode);
    const xTicks = {
      color: COLOUR_MUTED, font: { size: 10 }, maxTicksLimit: 6, maxRotation: 0,
      callback: function (value) { return shortIsoDate(this.getLabelForValue(value)); },
    };
    const tooltipTitle = (items) => items.length ? ukDate(items[0].label) : "";

    if (mode === "separate") {
      BODY_COMPOSITION_SERIES.forEach((series, index) => {
        const values = seriesValues[index];
        const first = firstValue(values);
        const latest = lastValue(values);
        const valueEl = card.querySelector('.bc-strip-value[data-series="' + index + '"]');
        valueEl.innerHTML = first
          ? "<strong>" + fmt(latest) + " kg</strong> " +
            '<span class="bc-strip-change">' + signed(Math.round((latest - first.value) * 10) / 10, 1, "") + " since " +
            shortIsoDate(labels[first.index]) + "</span>"
          : '<span class="bc-strip-change">No data</span>';
        const isLast = index === BODY_COMPOSITION_SERIES.length - 1;
        upsertChart(widgetId + ":" + series.key, card.querySelector('canvas[data-series="' + index + '"]'), {
          type: "line",
          data: {
            labels: labels,
            datasets: [Object.assign(buildDataset(series.label, values, series.colour), { pointRadius: 0, pointHitRadius: 6 })],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false },
            layout: { padding: { right: 4 } },
            plugins: {
              legend: { display: false },
              tooltip: { callbacks: { title: tooltipTitle, label: (item) => series.label + ": " + fmt(item.raw) + " kg" } },
            },
            scales: {
              x: { display: isLast, ticks: xTicks, grid: { display: false } },
              y: {
                grace: "10%",
                afterFit: (scale) => { scale.width = 38; },
                ticks: { color: COLOUR_MUTED, font: { size: 10 }, maxTicksLimit: 3 },
                grid: { color: COLOUR_GRID },
              },
            },
          },
        });
      });
      return;
    }

    const changes = seriesValues.map((values) => {
      const first = firstValue(values);
      return values.map((value) => (first && hasValue(value) ? Math.round((value - first.value) * 10) / 10 : null));
    });
    const firsts = seriesValues.map(firstValue).filter(Boolean);
    const baselineIndex = Math.min.apply(null, firsts.map((first) => first.index));
    const summaryParts = BODY_COMPOSITION_SERIES.map((series, index) => {
      const latest = lastValue(changes[index]);
      if (!hasValue(latest)) return "";
      const improving = series.key === "body_weight_mass" ? "" : (series.key === "body_fat_mass" ? latest < 0 : latest > 0) ? "positive" : latest === 0 ? "" : "negative";
      return statHtml(series.label, signed(latest, 1, " kg"), improving);
    }).join("");
    card.querySelector(".chart-summary").innerHTML =
      '<span class="chart-stat muted">Since ' + ukDate(labels[baselineIndex]) + "</span>" + summaryParts;
    upsertChart(widgetId, card.querySelector("canvas"), {
      type: "line",
      data: {
        labels: labels,
        datasets: BODY_COMPOSITION_SERIES.map((series, index) =>
          Object.assign(buildDataset(series.label, changes[index], series.colour), { pointRadius: 0, pointHitRadius: 6 })),
      },
      options: Object.assign(chartOptions({
        x: { ticks: xTicks, grid: { display: false } },
        y: {
          grace: "10%",
          ticks: { color: COLOUR_MUTED, font: { size: 10 }, callback: (value) => (value > 0 ? "+" : "") + value },
          grid: { color: COLOUR_GRID },
          title: { display: true, text: "kg change", color: COLOUR_MUTED, font: { size: 10 } },
        },
      }), {
        animation: false,
        plugins: {
          legend: { position: "bottom", labels: { color: COLOUR_MUTED, boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              title: tooltipTitle,
              label: (item) => {
                const actual = seriesValues[item.datasetIndex][item.dataIndex];
                return item.dataset.label + ": " + signed(item.raw, 1, " kg") + " (" + fmt(actual) + " kg)";
              },
            },
          },
        },
      }),
      plugins: [zeroLinePlugin],
    });
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
    score_card: scoreCardHtml,
    ratio_card: analyticsCardHtml,
    rate_card: analyticsCardHtml,
    pr_interval_card: prIntervalCardHtml,
    countdown_list: countdownListHtml,
    next_meet_card: nextMeetCardHtml,
    target_progress_board: targetProgressHtml,
  };

  const chartRenderers = {
    chart: renderStandardChart,
    pr_timeline_chart: renderPrTimeline,
    activity_trend_chart: renderActivityTrend,
    meet_projection_chart: renderMeetProjection,
    weight_class_chart: renderWeightClass,
    strength_scatter_chart: renderStrengthScatter,
    gym_platform_chart: renderGymVsPlatform,
    lift_balance_chart: renderLiftBalance,
    recomposition_chart: renderRecomposition,
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
    const isChart = ["chart", "pr_timeline_chart", "activity_trend_chart"].includes(widget.kind) ||
      Object.prototype.hasOwnProperty.call(chartRenderers, widget.kind);
    if (isChart) return { w: widget.kind === "pr_timeline_chart" ? 4 : 6, h: 8 };
    if (widget.kind === "next_meet_card") return { w: 4, h: 8 };
    if (widget.kind === "target_progress_board") return { w: 6, h: 8 };
    if (widget.kind === "lift_card") return { w: 3, h: 6 };
    if (widget.kind === "countdown_list") return { w: 12, h: 14 };
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
    // Saved positions are always 12-column. On a phone the grid is already
    // in its 1-column list mode, and adding 12-column items there one by one
    // makes each row-0 widget push the earlier ones down, reversing the
    // order. Build at 12 columns, then let GridStack collapse to a list
    // (sorted top-to-bottom, left-to-right). This also keeps the 12-column
    // layout cached, so saving from a phone stores desktop positions.
    const liveColumns = grid.getColumn();
    const collapsed = liveColumns !== GRID_COLUMNS;
    if (collapsed) grid.column(GRID_COLUMNS, "none");
    screen.widgets.forEach((item) => {
      if (allowedIds.has(item.id)) addWidget(item);
      else skippedLayoutItems.push({ id: item.id, x: item.x, y: item.y, w: item.w, h: item.h });
    });
    if (collapsed) grid.column(liveColumns, "list");
    renderAllWidgetContents();
    if (editing) {
      addRemoveControls();
      populateTray();
    }
    applyFitting();
  }

  function isFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }

  function enterFullscreen() {
    const el = document.documentElement;
    const request = el.requestFullscreen || el.webkitRequestFullscreen;
    if (request) request.call(el);
  }

  function exitFullscreen() {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (exit) exit.call(document);
  }

  function toggleFullscreen() {
    if (isFullscreen()) exitFullscreen();
    else enterFullscreen();
  }

  function handleFullscreenChange() {
    const active = isFullscreen();
    document.body.classList.toggle("is-fullscreen", active);
    const btn = document.getElementById("fullscreen-btn");
    if (btn) btn.textContent = active ? "Exit fullscreen" : "Fullscreen";
    window.setTimeout(applyFitting, 50);
  }

  function clearFullscreenScale(gridEl, viewportEl) {
    gridEl.style.transform = "";
    gridEl.style.width = "";
    if (viewportEl) viewportEl.style.height = "";
  }

  function applyFullscreenScale() {
    const gridEl = document.getElementById("dashboard-grid");
    const viewportEl = document.getElementById("dashboard-grid-viewport");
    if (!grid || !gridEl) return;
    if (!isFullscreen() || editing) {
      clearFullscreenScale(gridEl, viewportEl);
      return;
    }
    const screen = activeScreen();
    if (!screen || !screen.widgets.length) {
      clearFullscreenScale(gridEl, viewportEl);
      return;
    }
    // Fullscreen uses the dashboard's true designed row height (never shrunk,
    // so no card content can ever be clipped) and instead fits the whole grid
    // to the viewport with a single uniform scale, which shrinks fonts,
    // padding and borders together rather than cropping anything.
    grid.cellHeight(DEFAULT_CELL_HEIGHT, true);
    const maxRows = currentMaxRow(screen);
    const naturalHeight = maxRows * DEFAULT_CELL_HEIGHT;
    const top = gridEl.getBoundingClientRect().top;
    const bottomPadding = parseFloat(window.getComputedStyle(document.body).paddingBottom) || 0;
    const available = window.innerHeight - top - bottomPadding;
    const scale = Math.min(1, available / naturalHeight);
    if (scale >= 1) {
      clearFullscreenScale(gridEl, viewportEl);
      return;
    }
    gridEl.style.transformOrigin = "top left";
    gridEl.style.transform = `scale(${scale})`;
    gridEl.style.width = (100 / scale) + "%";
    // transform: scale() shrinks what is painted but GridStack keeps managing
    // #dashboard-grid's own inline height at the unscaled size (it reasserts
    // this on its own resize observer, so overriding gridEl.style.height
    // directly gets clobbered). Instead, collapse the height of the plain
    // wrapper div around it, which nothing else touches, so the page's
    // reserved layout space matches what is actually painted.
    if (viewportEl) viewportEl.style.height = (naturalHeight * scale) + "px";
    requestAnimationFrame(() => {
      Object.values(charts).forEach((chart) => chart.resize());
    });
  }

  function applyFitting() {
    fitGridHeight();
    applyFullscreenScale();
  }

  function currentMaxRow(screen) {
    return screen.widgets.reduce((max, item) => Math.max(max, item.y + item.h), 1);
  }

  function anyCardContentClipped() {
    const boxes = document.querySelectorAll(
      "#dashboard-grid .grid-stack-item-content > .card, #dashboard-grid .grid-stack-item-content > .chart-card"
    );
    for (const box of boxes) {
      if (box.scrollHeight - box.clientHeight > 1) return true;
    }
    return false;
  }

  function fitGridHeight() {
    if (!grid) return;
    if (editing || window.innerWidth < LIST_LAYOUT_BREAKPOINT) {
      grid.cellHeight(DEFAULT_CELL_HEIGHT, true);
      return;
    }
    const screen = activeScreen();
    const gridEl = document.getElementById("dashboard-grid");
    if (!screen || !screen.widgets.length || !gridEl) return;
    const maxRows = currentMaxRow(screen);
    const top = gridEl.getBoundingClientRect().top;
    const bottomPadding = parseFloat(window.getComputedStyle(document.body).paddingBottom) || 0;
    const available = window.innerHeight - top - bottomPadding;
    const fitted = Math.floor(available / maxRows);
    let cellHeight = Math.max(MIN_CELL_HEIGHT, Math.min(DEFAULT_CELL_HEIGHT, fitted));
    grid.cellHeight(cellHeight, true);
    // Shrinking cell height is only safe as long as no card's fixed-size content
    // (labels, values, meta rows) gets clipped. Step back up until nothing clips,
    // trading a page-level scrollbar for guaranteed-readable widget content.
    while (cellHeight < DEFAULT_CELL_HEIGHT && anyCardContentClipped()) {
      cellHeight += 1;
      grid.cellHeight(cellHeight, true);
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
      destroyWidgetCharts(element.gridstackNode.id);
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
    applyFitting();
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
      column: GRID_COLUMNS,
      cellHeight: DEFAULT_CELL_HEIGHT,
      margin: 10,
      float: true,
      columnOpts: { breakpoints: [{ w: 700, c: 1, layout: "list" }] },
    }, "#dashboard-grid");
    grid.setStatic(true);
    grid.on("resizestop", (_event, element) => {
      const widgetId = element.gridstackNode && element.gridstackNode.id;
      Object.keys(charts).forEach((key) => {
        if (key === widgetId || key.indexOf(widgetId + ":") === 0) charts[key].resize();
      });
    });
    let resizeDebounce = null;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeDebounce);
      resizeDebounce = window.setTimeout(applyFitting, 150);
    });
    const fullscreenBtn = document.getElementById("fullscreen-btn");
    const fullscreenSupported = !!(
      document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen
    );
    if (fullscreenBtn) {
      if (fullscreenSupported) {
        fullscreenBtn.addEventListener("click", toggleFullscreen);
      } else {
        fullscreenBtn.hidden = true;
      }
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
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
