"use strict";

const byId = (id) => document.getElementById(id);

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "-";
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function formatMeasurementCount(count) {
  return `${count} ${count === 1 ? "measurement" : "measurements"}`;
}

function setText(id, value) {
  byId(id).textContent = value;
}

function addCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value;
  row.appendChild(cell);
}

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

function drawChart(records) {
  const canvas = byId("history-chart");
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth, 320);
  const height = 280;
  canvas.width = width * ratio;
  canvas.height = height * ratio;

  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);

  if (records.length === 0) {
    setText("chart-note", "No measurements");
    return;
  }

  setText("chart-note", formatMeasurementCount(records.length));
  const padding = { top: 20, right: 16, bottom: 26, left: 46 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const download = records.map((record) => Number(record.download_mbps) || 0);
  const upload = records.map((record) => Number(record.upload_mbps) || 0);
  const observedMaximum = Math.max(10, ...download, ...upload);
  const maximum = Math.ceil(observedMaximum * 1.1);

  context.strokeStyle = "#263747";
  context.fillStyle = "#8fa4b8";
  context.font = "12px system-ui";
  context.lineWidth = 1;

  for (let line = 0; line <= 4; line += 1) {
    const y = padding.top + (chartHeight * line) / 4;
    const label = maximum - (maximum * line) / 4;
    context.beginPath();
    context.moveTo(padding.left, y);
    context.lineTo(width - padding.right, y);
    context.stroke();
    context.fillText(label.toFixed(0), 7, y + 4);
  }

  function line(values, color) {
    const points = [];
    context.strokeStyle = color;
    context.lineWidth = 2.5;
    context.beginPath();
    values.forEach((value, index) => {
      const x =
        padding.left +
        (chartWidth * index) / Math.max(values.length - 1, 1);
      const y =
        padding.top + chartHeight - (chartHeight * value) / maximum;
      points.push({ x, y });
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    });
    context.stroke();

    context.fillStyle = color;
    points.forEach(({ x, y }) => {
      context.beginPath();
      context.arc(x, y, 4, 0, Math.PI * 2);
      context.fill();
    });
  }

  line(download, "#66c2ff");
  line(upload, "#62d49d");
}

async function load() {
  const healthElement = byId("health");
  try {
    const [healthResponse, resultsResponse] = await Promise.all([
      fetch("/api/health", { cache: "no-store" }),
      fetch("/api/results?limit=100", { cache: "no-store" }),
    ]);
    if (!healthResponse.ok || !resultsResponse.ok) {
      throw new Error("Dashboard API returned an error");
    }

    const health = await healthResponse.json();
    const results = await resultsResponse.json();
    const records = Array.isArray(results.records) ? results.records : [];
    const latest = records[records.length - 1];

    healthElement.textContent =
      `Healthy - ${formatMeasurementCount(health.measurements)}`;
    healthElement.className = "health ok";

    if (latest) {
      setText("latest-download", formatNumber(latest.download_mbps));
      setText("latest-upload", formatNumber(latest.upload_mbps));
      setText("latest-latency", formatNumber(latest.latency_ms));
      setText("latest-jitter", formatNumber(latest.jitter_ms));
    }

    renderTable(records);
    drawChart(records);
  } catch (error) {
    healthElement.textContent = "Dashboard unavailable";
    healthElement.className = "health error";
    setText("chart-note", "Could not load results");
  }
}

window.addEventListener("resize", () => {
  window.clearTimeout(window.__resizeTimer);
  window.__resizeTimer = window.setTimeout(load, 120);
});

load();
