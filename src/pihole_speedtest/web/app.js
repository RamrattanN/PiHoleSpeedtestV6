"use strict";

const byId = (id) => document.getElementById(id);
let allRecords = [];
let zoomStart = 0;
let zoomEnd = 0;
let collectionIntervalMinutes = 60;
let chartMode = localStorage.getItem("pihole-speedtest-chart-mode") || "line";
const chartStates = new Map();

function requestedView() {
  return window.location.hash === "#setup" ? "setup" : "overview";
}

function showView(name, updateHash = false) {
  const setup = name === "setup";
  byId("overview-view").hidden = setup;
  byId("setup-view").hidden = !setup;
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  if (updateHash && window.location.hash !== `#${name}`) window.location.hash = name;
}

function formatNumber(value) { const n = Number(value); return Number.isFinite(n) ? n.toFixed(2) : "-"; }
function formatTime(value) { const d = new Date(value); return Number.isNaN(d.valueOf()) ? value : d.toLocaleString(); }
function formatMeasurementCount(count) { return `${count} ${count === 1 ? "measurement" : "measurements"}`; }
function setText(id, value) { byId(id).textContent = value; }
function addCell(row, value) { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); }

function renderTable(records) {
  const body = byId("results-body");
  body.replaceChildren();
  byId("empty-state").hidden = records.length > 0;
  records.slice().reverse().forEach((record) => {
    const row = document.createElement("tr");
    addCell(row, formatTime(record.recorded_at));
    addCell(row, `${formatNumber(record.download_mbps)} Mbps`);
    addCell(row, `${formatNumber(record.upload_mbps)} Mbps`);
    addCell(row, `${formatNumber(record.latency_ms)} ms`);
    addCell(row, `${formatNumber(record.jitter_ms)} ms`);
    addCell(row, record.server_name || "Not available");
    addCell(row, record.interface_name || "Not available");
    body.appendChild(row);
  });
}

function visibleRecords() { return allRecords.slice(zoomStart, zoomEnd); }
function chartMaximum(records, series, minimum) {
  const values = series.flatMap((item) => records.map((record) => Number(record[item.field]) || 0));
  return Math.ceil(Math.max(minimum, ...values) * 1.1);
}

function buildChartRecords(records) {
  if (records.length < 2) return records.slice();
  const intervalMs = collectionIntervalMinutes * 60 * 1000;
  const plotted = [];
  records.forEach((record, index) => {
    if (index > 0) {
      const previous = Date.parse(records[index - 1].recorded_at);
      const current = Date.parse(record.recorded_at);
      if (Number.isFinite(previous) && Number.isFinite(current) && current > previous) {
        for (
          let timestamp = previous + intervalMs;
          timestamp < current - intervalMs / 2;
          timestamp += intervalMs
        ) {
          plotted.push({
            recorded_at: new Date(timestamp).toISOString(),
            download_mbps: 0,
            upload_mbps: 0,
            latency_ms: 0,
            jitter_ms: 0,
            synthetic_zero: true,
          });
        }
      }
    }
    plotted.push(record);
  });
  return plotted;
}

function chartTimeline(records) {
  const intervalMs = collectionIntervalMinutes * 60 * 1000;
  const timestamps = records.map((record) => Date.parse(record.recorded_at));
  const valid = timestamps.filter(Number.isFinite);
  const first = valid.length ? Math.min(...valid) : 0;
  const last = valid.length ? Math.max(...valid) : first;
  const start = records.length === 1 ? first - intervalMs / 2 : first;
  const end = records.length === 1 ? last + intervalMs / 2 : last;
  return { timestamps, start, end, duration: Math.max(end - start, 1), intervalMs };
}

function formatAxisTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function chartNote(records) {
  return records.length === allRecords.length
    ? formatMeasurementCount(records.length)
    : `${formatMeasurementCount(records.length)} shown of ${allRecords.length}`;
}

function chartBarSpacing(timeline, xPositions) {
  const spacings = [];
  for (let index = 1; index < xPositions.length; index += 1) {
    const previous = timeline.timestamps[index - 1];
    const current = timeline.timestamps[index];
    if (!Number.isFinite(previous) || !Number.isFinite(current)) continue;
    const elapsed = current - previous;
    if (elapsed <= 0 || elapsed > timeline.intervalMs * 1.5) continue;
    const spacing = xPositions[index] - xPositions[index - 1];
    if (spacing > 0) spacings.push(spacing);
  }
  if (spacings.length === 0) return 12;
  spacings.sort((left, right) => left - right);
  const middle = Math.floor(spacings.length / 2);
  return spacings.length % 2
    ? spacings[middle]
    : (spacings[middle - 1] + spacings[middle]) / 2;
}

function drawBarGroup(context, x, chartBottom, bars, groupWidth) {
  const heights = bars.map((bar) => bar.height);
  const nearlyEqual = Math.max(...heights) - Math.min(...heights) <= 3;
  if (nearlyEqual) {
    const seriesGap = bars.length > 1
      ? Math.min(2, Math.max(0.5, groupWidth * 0.08))
      : 0;
    const barWidth = Math.max(
      0.1,
      (groupWidth - seriesGap * (bars.length - 1)) / bars.length,
    );
    const renderedGroupWidth = barWidth * bars.length + seriesGap * (bars.length - 1);
    bars.forEach((bar, index) => {
      context.fillStyle = bar.color;
      context.fillRect(
        x - renderedGroupWidth / 2 + index * (barWidth + seriesGap),
        chartBottom - bar.height,
        barWidth,
        bar.height,
      );
    });
    return;
  }

  bars.slice().sort((left, right) => right.height - left.height).forEach((bar, index) => {
    const layerWidth = index === 0
      ? groupWidth
      : Math.max(0.1, groupWidth * Math.max(0.42, 0.68 - (index - 1) * 0.12));
    context.fillStyle = bar.color;
    context.fillRect(x - layerWidth / 2, chartBottom - bar.height, layerWidth, bar.height);
  });
}

function drawChart(records, options) {
  const canvas = byId(options.canvasId);
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth, 320);
  const height = 280;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  if (records.length === 0) {
    setText(options.noteId, "No measurements");
    chartStates.delete(options.canvasId);
    byId(options.tooltipId).hidden = true;
    return;
  }

  const plottedRecords = buildChartRecords(records);
  const timeline = chartTimeline(plottedRecords);
  setText(options.noteId, chartNote(records));
  const padding = { top: 20, right: 16, bottom: 34, left: 46 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const maximum = chartMaximum(allRecords, options.series, options.minimumMaximum);
  const values = options.series.map((series) => plottedRecords.map((record) => Number(record[series.field]) || 0));
  const xForTimestamp = (timestamp) => padding.left + chartWidth * (timestamp - timeline.start) / timeline.duration;
  const xPositions = timeline.timestamps.map((timestamp, index) => Number.isFinite(timestamp)
    ? xForTimestamp(timestamp)
    : padding.left + chartWidth * index / Math.max(plottedRecords.length - 1, 1));
  chartStates.set(options.canvasId, { records: plottedRecords, options, padding, chartWidth, chartHeight, xPositions });
  context.strokeStyle = "#263747";
  context.fillStyle = "#8fa4b8";
  context.font = "12px system-ui";
  context.lineWidth = 1;
  for (let line = 0; line <= 4; line += 1) {
    const y = padding.top + chartHeight * line / 4;
    context.beginPath(); context.moveTo(padding.left, y); context.lineTo(width - padding.right, y); context.stroke();
    context.fillText((maximum - maximum * line / 4).toFixed(0), 7, y + 4);
  }

  context.fillStyle = "#8fa4b8";
  context.font = "11px system-ui";
  for (let tick = 0; tick <= 4; tick += 1) {
    const timestamp = timeline.start + timeline.duration * tick / 4;
    const label = formatAxisTime(timestamp);
    const x = padding.left + chartWidth * tick / 4;
    context.textAlign = tick === 0 ? "start" : tick === 4 ? "right" : "center";
    context.fillText(label, x, height - 7);
  }
  context.textAlign = "start";

  if (chartMode === "bar") {
    const measuredSpacing = chartBarSpacing(timeline, xPositions);
    const groupWidth = Math.max(1, Math.min(18, measuredSpacing * 0.76));
    plottedRecords.forEach((record, index) => {
      const bars = options.series.map((series, seriesIndex) => ({
        color: series.color,
        height: chartHeight * values[seriesIndex][index] / maximum,
      }));
      drawBarGroup(
        context,
        xPositions[index],
        padding.top + chartHeight,
        bars,
        groupWidth,
      );
    });
    return;
  }

  options.series.forEach((series, seriesIndex) => {
    const points = [];
    context.strokeStyle = series.color; context.lineWidth = 2.5; context.beginPath();
    values[seriesIndex].forEach((value, index) => {
      const x = xPositions[index];
      const y = padding.top + chartHeight - chartHeight * value / maximum;
      const previous = index > 0 ? timeline.timestamps[index - 1] : null;
      const current = timeline.timestamps[index];
      const breaksLine = index === 0 || !Number.isFinite(previous) || !Number.isFinite(current);
      points.push({ x, y }); breaksLine ? context.moveTo(x, y) : context.lineTo(x, y);
    });
    context.stroke(); context.fillStyle = series.color;
    points.forEach(({ x, y }) => { context.beginPath(); context.arc(x, y, 4, 0, Math.PI * 2); context.fill(); });
  });
}

function renderCharts() {
  const records = visibleRecords();
  drawChart(records, { canvasId: "history-chart", tooltipId: "history-tooltip", noteId: "chart-note", minimumMaximum: 10,
    series: [
      { field: "download_mbps", label: "Download", unit: "Mbps", color: "#66c2ff" },
      { field: "upload_mbps", label: "Upload", unit: "Mbps", color: "#62d49d" },
    ] });
  drawChart(records, { canvasId: "latency-chart", tooltipId: "latency-tooltip", noteId: "latency-chart-note", minimumMaximum: 10,
    series: [
      { field: "latency_ms", label: "Latency", unit: "ms", color: "#ffb86b" },
      { field: "jitter_ms", label: "Jitter", unit: "ms", color: "#c792ea" },
    ] });
}

function hideChartTooltip(canvas) {
  const state = chartStates.get(canvas.id);
  if (state) byId(state.options.tooltipId).hidden = true;
}

function showChartTooltip(event, canvas) {
  const state = chartStates.get(canvas.id);
  if (!state || state.records.length === 0) return;
  const bounds = canvas.getBoundingClientRect();
  const x = event.clientX - bounds.left;
  const y = event.clientY - bounds.top;
  const { padding, chartWidth, chartHeight, records, options, xPositions } = state;
  if (x < padding.left || x > padding.left + chartWidth || y < padding.top || y > padding.top + chartHeight) {
    hideChartTooltip(canvas);
    return;
  }

  const index = xPositions.reduce((nearest, position, candidate) => (
    Math.abs(position - x) < Math.abs(xPositions[nearest] - x) ? candidate : nearest
  ), 0);
  const record = records[index];
  const tooltip = byId(options.tooltipId);
  const title = document.createElement("strong");
  title.textContent = formatTime(record.recorded_at);
  const rows = options.series.map((series) => {
    const row = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.style.background = series.color;
    row.append(swatch, `${series.label}: ${formatNumber(record[series.field])} ${series.unit}`);
    return row;
  });
  tooltip.replaceChildren(title, ...rows);
  tooltip.style.left = `${Math.max(105, Math.min(bounds.width - 105, x))}px`;
  tooltip.style.top = `${Math.max(96, y)}px`;
  tooltip.hidden = false;
}

function changeZoom(action) {
  const total = allRecords.length;
  if (total < 2) return;
  if (action === "reset") { zoomStart = 0; zoomEnd = total; }
  else {
    const current = zoomEnd - zoomStart;
    const next = action === "in" ? Math.max(5, Math.floor(current * 0.75)) : Math.min(total, Math.ceil(current / 0.75));
    const center = (zoomStart + zoomEnd) / 2;
    zoomStart = Math.max(0, Math.round(center - next / 2)); zoomEnd = Math.min(total, zoomStart + next);
    zoomStart = Math.max(0, zoomEnd - next);
  }
  renderCharts();
}

function panZoom(deltaPixels, width) {
  const visible = zoomEnd - zoomStart;
  if (visible >= allRecords.length || width <= 0) return;
  const shift = Math.round(-deltaPixels / width * visible);
  const nextStart = Math.max(0, Math.min(allRecords.length - visible, zoomStart + shift));
  zoomStart = nextStart; zoomEnd = nextStart + visible; renderCharts();
}

async function postJson(path, payload) {
  return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
}

function setCollectionMessage(value) {
  setText("collection-message", value);
}

function setCollectionButtonsDisabled(disabled) {
  document.querySelectorAll("[data-run-speedtest]").forEach((button) => { button.disabled = disabled; });
}

async function waitForCollection() {
  for (let attempt = 0; attempt < 190; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    const response = await fetch("/api/collection-status", { cache: "no-store" });
    const status = await response.json();
    if (status.state === "running") { setCollectionMessage(status.message); continue; }
    setCollectionButtonsDisabled(false);
    setCollectionMessage(status.message || "Speed test finished.");
    if (status.state === "succeeded") await load();
    return;
  }
  setCollectionButtonsDisabled(false);
  setCollectionMessage("The speed test is still running. Check status again shortly.");
}

async function runSpeedtest() {
  setCollectionButtonsDisabled(true);
  setCollectionMessage("Starting an official Ookla speed test.");
  try {
    const response = await postJson("/api/collect", {});
    const result = await response.json();
    if (!response.ok) {
      setCollectionButtonsDisabled(false);
      setCollectionMessage(result.error || "The speed test could not be started.");
      return;
    }
    setCollectionMessage(result.message);
    await waitForCollection();
  } catch (error) {
    setCollectionButtonsDisabled(false);
    setCollectionMessage("The dashboard could not start the speed test.");
  }
}

function installControls() {
  if (new URLSearchParams(window.location.search).get("embed") === "1") document.body.classList.add("embedded");
  showView(requestedView());
  window.addEventListener("hashchange", () => showView(requestedView()));
  const helpDialog = byId("help-dialog");
  byId("open-help").addEventListener("click", () => helpDialog.showModal());
  byId("close-help").addEventListener("click", () => helpDialog.close());
  helpDialog.addEventListener("click", (event) => {
    if (event.target === helpDialog) helpDialog.close();
  });
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
    showView(button.dataset.view, true);
  }));
  document.querySelectorAll("[data-chart-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.chartMode === chartMode);
    button.addEventListener("click", () => {
      chartMode = button.dataset.chartMode; localStorage.setItem("pihole-speedtest-chart-mode", chartMode);
      document.querySelectorAll("[data-chart-mode]").forEach((item) => item.classList.toggle("active", item === button));
      renderCharts();
    });
  });
  document.querySelectorAll("[data-zoom]").forEach((button) => button.addEventListener("click", () => changeZoom(button.dataset.zoom)));
  document.querySelectorAll("canvas").forEach((canvas) => {
    let dragStart = null;
    canvas.addEventListener("pointermove", (event) => {
      if (dragStart === null) showChartTooltip(event, canvas);
    });
    canvas.addEventListener("pointerleave", () => hideChartTooltip(canvas));
    canvas.addEventListener("wheel", (event) => {
      event.preventDefault(); changeZoom(event.deltaY < 0 ? "in" : "out");
    }, { passive: false });
    canvas.addEventListener("pointerdown", (event) => {
      hideChartTooltip(canvas);
      dragStart = event.clientX; canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointerup", (event) => {
      if (dragStart !== null) panZoom(event.clientX - dragStart, canvas.clientWidth);
      dragStart = null;
    });
    canvas.addEventListener("pointercancel", () => { dragStart = null; });
  });

  const showTable = byId("show-table");
  showTable.checked = localStorage.getItem("pihole-speedtest-show-table") !== "false";
  byId("measurement-table").hidden = !showTable.checked;
  showTable.addEventListener("change", () => {
    localStorage.setItem("pihole-speedtest-show-table", String(showTable.checked));
    byId("measurement-table").hidden = !showTable.checked;
  });
  byId("save-frequency").addEventListener("click", async () => {
    const response = await postJson("/api/settings", { collection_interval_minutes: Number(byId("collection-frequency").value) });
    const result = await response.json(); setText("settings-message", response.ok ? "Capture frequency saved." : result.error);
  });
  document.querySelectorAll("[data-run-speedtest]").forEach((button) => {
    button.addEventListener("click", runSpeedtest);
  });
  const updateResetButton = () => { byId("reset-data").disabled = !byId("reset-acknowledgement").checked || byId("reset-confirmation").value !== "RESET"; };
  byId("reset-acknowledgement").addEventListener("change", updateResetButton);
  byId("reset-confirmation").addEventListener("input", updateResetButton);
  byId("reset-data").addEventListener("click", async () => {
    const response = await postJson("/api/reset", { confirmation: "RESET" });
    const result = await response.json();
    setText("reset-message", response.ok ? `History reset. Recovery backup: ${result.backup}` : result.error);
    if (response.ok) await load();
  });
}

async function load() {
  const healthElement = byId("health");
  try {
    const [healthResponse, resultsResponse, settingsResponse] = await Promise.all([
      fetch("/api/health", { cache: "no-store" }), fetch("/api/results?limit=100", { cache: "no-store" }),
      fetch("/api/settings", { cache: "no-store" }),
    ]);
    if (!healthResponse.ok || !resultsResponse.ok || !settingsResponse.ok) throw new Error("Dashboard API returned an error");
    const health = await healthResponse.json(); const results = await resultsResponse.json(); const settings = await settingsResponse.json();
    allRecords = Array.isArray(results.records) ? results.records : []; zoomStart = 0; zoomEnd = allRecords.length;
    collectionIntervalMinutes = Number(settings.collection_interval_minutes) || 60;
    byId("collection-frequency").value = String(settings.collection_interval_minutes);
    const latest = allRecords[allRecords.length - 1];
    healthElement.textContent = `Healthy - ${formatMeasurementCount(health.measurements)}`; healthElement.className = "health ok";
    if (latest) { setText("latest-download", formatNumber(latest.download_mbps)); setText("latest-upload", formatNumber(latest.upload_mbps)); setText("latest-latency", formatNumber(latest.latency_ms)); setText("latest-jitter", formatNumber(latest.jitter_ms)); }
    renderTable(allRecords); renderCharts();
  } catch (error) {
    healthElement.textContent = "Dashboard unavailable"; healthElement.className = "health error";
    setText("chart-note", "Could not load results"); setText("latency-chart-note", "Could not load results");
  }
}

window.addEventListener("resize", () => { window.clearTimeout(window.__resizeTimer); window.__resizeTimer = window.setTimeout(renderCharts, 120); });
installControls(); load();
