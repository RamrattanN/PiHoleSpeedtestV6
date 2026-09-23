"use strict";

const byId = (id) => document.getElementById(id);
let allRecords = [];
let zoomStart = 0;
let zoomEnd = 0;
let chartMode = localStorage.getItem("pihole-speedtest-chart-mode") || "line";

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
  if (records.length === 0) { setText(options.noteId, "No measurements"); return; }

  setText(options.noteId, records.length === allRecords.length
    ? formatMeasurementCount(records.length)
    : `${formatMeasurementCount(records.length)} shown of ${allRecords.length}`);
  const padding = { top: 20, right: 16, bottom: 26, left: 46 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const maximum = chartMaximum(allRecords, options.series, options.minimumMaximum);
  const values = options.series.map((series) => records.map((record) => Number(record[series.field]) || 0));
  context.strokeStyle = "#263747";
  context.fillStyle = "#8fa4b8";
  context.font = "12px system-ui";
  context.lineWidth = 1;
  for (let line = 0; line <= 4; line += 1) {
    const y = padding.top + chartHeight * line / 4;
    context.beginPath(); context.moveTo(padding.left, y); context.lineTo(width - padding.right, y); context.stroke();
    context.fillText((maximum - maximum * line / 4).toFixed(0), 7, y + 4);
  }

  if (chartMode === "bar") {
    const groupWidth = chartWidth / Math.max(records.length, 1);
    const barWidth = Math.max(1, Math.min(16, groupWidth / options.series.length - 1));
    options.series.forEach((series, seriesIndex) => {
      context.fillStyle = series.color;
      values[seriesIndex].forEach((value, index) => {
        const barHeight = chartHeight * value / maximum;
        const left = padding.left + index * groupWidth + (groupWidth - barWidth * options.series.length) / 2 + seriesIndex * barWidth;
        context.fillRect(left, padding.top + chartHeight - barHeight, barWidth, barHeight);
      });
    });
    return;
  }

  options.series.forEach((series, seriesIndex) => {
    const points = [];
    context.strokeStyle = series.color; context.lineWidth = 2.5; context.beginPath();
    values[seriesIndex].forEach((value, index) => {
      const x = padding.left + chartWidth * index / Math.max(records.length - 1, 1);
      const y = padding.top + chartHeight - chartHeight * value / maximum;
      points.push({ x, y }); index === 0 ? context.moveTo(x, y) : context.lineTo(x, y);
    });
    context.stroke(); context.fillStyle = series.color;
    points.forEach(({ x, y }) => { context.beginPath(); context.arc(x, y, 4, 0, Math.PI * 2); context.fill(); });
  });
}

function renderCharts() {
  const records = visibleRecords();
  drawChart(records, { canvasId: "history-chart", noteId: "chart-note", minimumMaximum: 10,
    series: [{ field: "download_mbps", color: "#66c2ff" }, { field: "upload_mbps", color: "#62d49d" }] });
  drawChart(records, { canvasId: "latency-chart", noteId: "latency-chart-note", minimumMaximum: 10,
    series: [{ field: "latency_ms", color: "#ffb86b" }, { field: "jitter_ms", color: "#c792ea" }] });
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

async function authorizedPost(path, payload) {
  return fetch(path, { method: "POST", headers: { "Content-Type": "application/json",
    "Authorization": `Bearer ${byId("admin-token").value.trim()}` }, body: JSON.stringify(payload) });
}

function installControls() {
  const helpDialog = byId("help-dialog");
  byId("open-help").addEventListener("click", () => helpDialog.showModal());
  byId("close-help").addEventListener("click", () => helpDialog.close());
  helpDialog.addEventListener("click", (event) => {
    if (event.target === helpDialog) helpDialog.close();
  });
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
    const setup = button.dataset.view === "setup";
    byId("overview-view").hidden = setup; byId("setup-view").hidden = !setup;
    document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item === button));
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
    canvas.addEventListener("wheel", (event) => {
      event.preventDefault(); changeZoom(event.deltaY < 0 ? "in" : "out");
    }, { passive: false });
    let dragStart = null;
    canvas.addEventListener("pointerdown", (event) => {
      dragStart = event.clientX; canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointerup", (event) => {
      if (dragStart !== null) panZoom(event.clientX - dragStart, canvas.clientWidth);
      dragStart = null;
    });
  });

  const showTable = byId("show-table");
  showTable.checked = localStorage.getItem("pihole-speedtest-show-table") !== "false";
  byId("measurement-table").hidden = !showTable.checked;
  showTable.addEventListener("change", () => {
    localStorage.setItem("pihole-speedtest-show-table", String(showTable.checked));
    byId("measurement-table").hidden = !showTable.checked;
  });
  byId("save-frequency").addEventListener("click", async () => {
    const response = await authorizedPost("/api/settings", { collection_interval_minutes: Number(byId("collection-frequency").value) });
    const result = await response.json(); setText("settings-message", response.ok ? "Capture frequency saved." : result.error);
  });
  const updateResetButton = () => { byId("reset-data").disabled = !byId("reset-acknowledgement").checked || byId("reset-confirmation").value !== "RESET"; };
  byId("reset-acknowledgement").addEventListener("change", updateResetButton);
  byId("reset-confirmation").addEventListener("input", updateResetButton);
  byId("reset-data").addEventListener("click", async () => {
    const response = await authorizedPost("/api/reset", { confirmation: "RESET" });
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
