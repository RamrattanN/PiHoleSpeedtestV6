(function(){
  function draw(dl, ul, labels){
    var canvas = document.getElementById("speedtest-dashboard");
    if(!canvas){
      var main = document.querySelector('main, #content, body') || document.body;
      var host = document.createElement('div');
      host.id = "speedtest-widget";
      host.style = "margin:12px 0; padding:12px; border:1px solid #ddd; border-radius:8px; max-width: 980px;";
      host.innerHTML = '<div style="font-weight:600;margin-bottom:8px;">Speedtest</div><canvas id="speedtest-dashboard" height="160"></canvas><div id="speedtest-note" style="font-size:12px;color:#666;margin-top:6px;">Loading…</div>';
      main.insertBefore(host, main.firstChild);
      canvas = document.getElementById("speedtest-dashboard");
    }
    var ctx = canvas.getContext("2d");
    if(window.__stDash){ window.__stDash.destroy(); }
    window.__stDash = new Chart(ctx, {
      type: "line",
      data: { labels: labels, datasets: [
        { label: "Download", data: dl, fill: false, tension: 0.2 },
        { label: "Upload", data: ul, fill: false, tension: 0.2 }
      ]},
      options: { responsive: true, maintainAspectRatio: false, elements: { point: { radius: 2 } },
                 plugins: { legend: { display: true, position: "top" } },
                 scales: { x: { ticks: { autoSkip: true, maxTicksLimit: 8 } } } }
    });
  }
  function start(){
    function afterChart(){
      fetch("/admin/speedtest/speedtest.json", {cache:"no-store"})
        .then(r=>r.json()).then(j=>{
          var recs = (j.records||[]).slice(-100);
          var labels = recs.map(r=>r.iso);
          var dl = recs.map(r=>+r.dl||0);
          var ul = recs.map(r=>+r.ul||0);
          draw(dl, ul, labels);
          var note = document.getElementById("speedtest-note");
          if(note){ note.textContent = "Samples " + recs.length + "  Last " + (j.last_run||""); }
        }).catch(_=>{
          var note = document.getElementById("speedtest-note");
          if(note){ note.textContent = "No data yet"; }
        });
    }
    if(typeof Chart === "undefined"){
      var s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/chart.js";
      s.onload = afterChart;
      document.head.appendChild(s);
    } else { afterChart(); }
  }
  if(document.readyState === "loading"){ document.addEventListener("DOMContentLoaded", start); } else { start(); }
})();
