(function(){
  const status = document.getElementById('status');
  const canvas = document.getElementById('chart');
  const ctx = canvas.getContext('2d');

  function draw(records){
    const w = canvas.width = canvas.clientWidth;
    const h = canvas.height = canvas.clientHeight;
    ctx.clearRect(0,0,w,h);
    if(!records || !records.length){
      status.textContent = 'No data yet.';
      return;
    }
    status.textContent = 'Showing ' + records.length + ' samples.  Last update: ' + (records[records.length-1].iso || '');

    const dl = records.map(r => +r.dl||0);
    const ul = records.map(r => +r.ul||0);
    const maxv = Math.max(10, Math.max(...dl, ...ul));
    const xs = w / (records.length-1 || 1);
    const ys = (h-20) / maxv;

    function line(vals){
      ctx.beginPath();
      vals.forEach((v,i)=>{
        const x = i*xs;
        const y = h - v*ys - 10;
        if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      });
      ctx.stroke();
    }
    ctx.lineWidth = 2;
    // default stroke style is fine as per guidelines
    line(dl);
    line(ul);

    // grid
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.2;
    for(let y=0;y<=maxv;y+=Math.max(10, Math.ceil(maxv/5))){
      const yy = h - y*ys - 10;
      ctx.beginPath(); ctx.moveTo(0,yy); ctx.lineTo(w,yy); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function table(records){
    const tbody = document.querySelector('#tbl tbody');
    tbody.innerHTML = '';
    records.slice(-50).reverse().forEach(r=>{
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${r.iso||''}</td><td>${r.dl||''}</td><td>${r.ul||''}</td><td>${r.lat||''}</td><td>${r.jit||''}</td><td>${r.srv||''}</td><td>${r.if||''}</td>`;
      tbody.appendChild(tr);
    });
  }

  fetch('speedtest.json', {cache:'no-store'})
    .then(r => r.json())
    .then(j => { draw(j.records||[]); table(j.records||[]); })
    .catch(_ => { status.textContent = 'Could not load speedtest.json'; });
})();
