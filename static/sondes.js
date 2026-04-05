var _sondesData = {};

function closeSondeModal() {
  document.getElementById('sonde-modal').style.display = 'none';
}

function openSondeModal(k) {
  var m = document.getElementById('sonde-modal');
  m.style.display = 'flex';
  renderSondeNav(k);
  renderSondeLive(k);
}

function renderSondeNav(active) {
  var nav = document.getElementById('sonde-nav');
  var labels = {voyager1:'🛸 V1',voyager2:'🛸 V2',perseverance:'🤖 Percy',curiosity:'🔬 Curiosity',iss:'🛰️ ISS',jwst:'🔭 JWST',hubble:'🌌 Hubble',parker:'☀️ Parker'};
  var colors = {voyager1:'#00ffe7',voyager2:'#00bfff',perseverance:'#ff6a00',curiosity:'#ff4444',iss:'#39ff14',jwst:'#c084fc',hubble:'#00bfff',parker:'#ffe600'};
  var html = '';
  Object.keys(labels).forEach(function(k) {
    var c = active===k ? colors[k] : '#333';
    var tc = active===k ? colors[k] : '#667788';
    html += '<button onclick="openSondeModal(\''+k+'\')" style="background:transparent;border:1px solid '+c+';color:'+tc+';padding:4px 12px;border-radius:20px;font-family:monospace;font-size:10px;cursor:pointer;margin:2px">'+labels[k]+'</button>';
  });
  nav.innerHTML = html;
}

function renderSondeLive(k) {
  var el = document.getElementById('sonde-live-content');
  var colors = {voyager1:'#00ffe7',voyager2:'#00bfff',perseverance:'#ff6a00',curiosity:'#ff4444',iss:'#39ff14',jwst:'#c084fc',hubble:'#00bfff',parker:'#ffe600'};
  var c = colors[k] || '#00ff88';
  el.innerHTML = '<div style="color:'+c+';font-family:monospace;font-size:11px;text-align:center;padding:40px">⟳ CONNEXION NASA/JPL...</div>';
  
  fetch('/api/sondes').then(function(r){ return r.json(); }).then(function(data) {
    _sondesData = data;
    var d = data[k] || {};
    document.getElementById('sonde-modal-inner').style.borderTopColor = c;
    
    var html = '<div style="font-family:Orbitron,monospace;font-size:13px;color:'+c+';letter-spacing:3px;margin-bottom:16px">'+(d.name||k.toUpperCase())+'</div>';
    
    if(k==='iss') {
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">';
      html += '<div style="background:rgba(57,255,20,0.05);border:1px solid '+c+'33;border-radius:8px;padding:14px">';
      html += '<div style="font-family:monospace;font-size:9px;color:'+c+';letter-spacing:2px;margin-bottom:10px">📡 POSITION LIVE</div>';
      [['LATITUDE',(d.lat||0).toFixed(4)+'°'],['LONGITUDE',(d.lon||0).toFixed(4)+'°'],['ALTITUDE',(d.altitude_km||408)+' km'],['VITESSE',(d.speed_kms||7.66)+' km/s'],['ÉQUIPAGE',(d.crew_count||'?')+' personnes']].forEach(function(row) {
        html += '<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:10px"><span style="color:#4a7a8a;font-family:monospace">'+row[0]+'</span><span style="color:'+c+';font-family:monospace">'+row[1]+'</span></div>';
      });
      html += '</div>';
      html += '<div style="background:rgba(57,255,20,0.05);border:1px solid '+c+'33;border-radius:8px;padding:14px">';
      html += '<div style="font-family:monospace;font-size:9px;color:'+c+';letter-spacing:2px;margin-bottom:8px">👨‍🚀 ÉQUIPAGE</div>';
      (d.crew||[]).forEach(function(name) {
        html += '<div style="padding:5px 8px;margin:3px 0;background:rgba(57,255,20,0.07);border-left:2px solid '+c+';font-family:monospace;font-size:10px;color:#fff;border-radius:0 4px 4px 0">'+name+'</div>';
      });
      html += '</div></div>';
      html += '<div style="margin-top:14px;background:rgba(0,0,0,0.3);border:1px solid '+c+'22;border-radius:8px;overflow:hidden">';
      html += '<div style="font-family:monospace;font-size:9px;color:'+c+';letter-spacing:2px;padding:10px 14px">🗺️ POSITION SUR TERRE</div>';
      html += '<iframe src="https://maps.google.com/maps?q='+(d.lat||0)+','+(d.lon||0)+'&z=3&output=embed" style="width:100%;height:260px;border:none" loading="lazy"></iframe>';
      html += '</div>';
    }
    else if(k==='voyager1'||k==='voyager2') {
      var distLight = ((d.distance_au||163)*149597870.7/299792.458/3600).toFixed(1);
      html += '<div style="text-align:center;padding:24px;background:rgba(0,255,231,0.03);border:1px solid '+c+'22;border-radius:10px;margin-bottom:16px">';
      html += '<div style="font-size:3rem;margin-bottom:8px">🛸</div>';
      html += '<div style="font-family:Orbitron,monospace;font-size:32px;color:'+c+';margin-bottom:6px">'+(d.distance_au||0)+' AU</div>';
      html += '<div style="font-family:monospace;font-size:10px;color:#4a7a8a">soit '+Number(d.distance_km||0).toLocaleString()+' km</div>';
      html += '<div style="font-family:monospace;font-size:11px;color:#ff6a00;margin-top:8px">📻 Signal radio : '+distLight+'h de trajet</div>';
      html += '<div style="margin-top:14px;height:6px;background:rgba(0,255,231,0.08);border-radius:3px;overflow:hidden">';
      html += '<div style="height:100%;width:'+Math.min(100,(d.distance_au||163)/200*100)+'%;background:linear-gradient(90deg,'+c+',#00bfff);border-radius:3px"></div></div>';
      html += '</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">';
      [['VITESSE',(d.speed_kms||17)+' km/s'],['LANCÉE','1977'],['ÉTAT',d.status||'N/A'],['SIGNAL',distLight+'h'],['SOURCE','NASA JPL'],['DESTINATION','Étoiles']].forEach(function(row) {
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid '+c+'22;border-radius:8px;padding:10px;text-align:center"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+row[0]+'</div><div style="font-family:monospace;font-size:11px;color:'+c+'">'+row[1]+'</div></div>';
      });
      html += '</div>';
    }
    else if(k==='perseverance'||k==='curiosity') {
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">';
      html += '<div style="background:rgba(255,106,0,0.06);border:1px solid '+c+'33;border-radius:8px;padding:14px">';
      html += '<div style="font-family:monospace;font-size:9px;color:'+c+';letter-spacing:2px;margin-bottom:10px">📡 TÉLÉMÉTRIE</div>';
      Object.entries(d).filter(function(e){return !['name','status','img_url'].includes(e[0]);}).forEach(function(e) {
        html += '<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:10px"><span style="color:#4a7a8a;font-family:monospace">'+e[0].toUpperCase()+'</span><span style="color:#fff;font-family:monospace">'+String(e[1]).substring(0,25)+'</span></div>';
      });
      html += '</div>';
      html += '<div style="background:rgba(255,106,0,0.06);border:1px solid '+c+'33;border-radius:8px;padding:14px">';
      html += '<div style="font-family:monospace;font-size:9px;color:'+c+';letter-spacing:2px;margin-bottom:8px">📷 DERNIÈRE PHOTO</div>';
      if(d.img_url) html += '<img src="'+d.img_url+'" style="width:100%;border-radius:6px;cursor:pointer" onclick="window.open(\''+d.img_url+'\',\'_blank\')">';
      html += '</div></div>';
      // Photos live
      fetch('https://api.nasa.gov/mars-photos/api/v1/rovers/'+k+'/latest_photos?api_key=DEMO_KEY').then(function(r){return r.json();}).then(function(pd){
        var photos = (pd.latest_photos||[]).slice(0,6);
        if(!photos.length) return;
        var g = '<div style="font-family:monospace;font-size:9px;color:'+c+';letter-spacing:2px;margin-bottom:10px">🔴 GALERIE LIVE MARS — '+photos.length+' PHOTOS</div>';
        g += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">';
        photos.forEach(function(p){
          g += '<div style="border:1px solid '+c+'22;border-radius:6px;overflow:hidden;cursor:pointer" onclick="window.open(\''+p.img_src+'\',\'_blank\')"><img src="'+p.img_src+'" style="width:100%;aspect-ratio:4/3;object-fit:cover"><div style="padding:4px 6px;font-family:monospace;font-size:8px;color:#4a7a8a">'+p.camera.name+'</div></div>';
        });
        g += '</div>';
        el.innerHTML += g;
      }).catch(function(){});
    }
    else {
      var icons = {jwst:'🔭',hubble:'🌌',parker:'☀️'};
      html += '<div style="font-size:3rem;text-align:center;margin:10px 0">'+(icons[k]||'🚀')+'</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:14px">';
      Object.entries(d).filter(function(e){return e[0]!=='name';}).forEach(function(e) {
        var val = Array.isArray(e[1]) ? e[1].map(function(i){return typeof i==='object'?Object.values(i).join(' — '):i;}).join('<br>') : String(e[1]);
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid '+c+'22;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+e[0].toUpperCase()+'</div><div style="font-family:monospace;font-size:11px;color:#fff;word-break:break-word">'+val+'</div></div>';
      });
      html += '</div>';
    }
    
    el.innerHTML = html;
  }).catch(function(e) {
    el.innerHTML = '<div style="color:#ff2d55;font-family:monospace;font-size:11px">ERREUR: '+e.message+'</div>';
  });
}

function loadSondes() {
  var g = document.getElementById('sondes-grid');
  if(!g) return;
  if(g.dataset.loaded) return;
  g.innerHTML = '<div style="color:#00ff88;font-family:monospace;font-size:11px;padding:20px">⟳ Connexion NASA/JPL...</div>';
  
  fetch('/api/sondes').then(function(r){ return r.json(); }).then(function(d) {
    _sondesData = d;
    g.dataset.loaded = '1';
    var colors = {voyager1:'#00ffe7',voyager2:'#00bfff',perseverance:'#ff6a00',curiosity:'#ff4444',iss:'#39ff14',jwst:'#c084fc',hubble:'#00bfff',parker:'#ffe600'};
    va,iss:'🛰️',jwst:'🔭',hubble:'🌌',parker:'☀️'};
    var html = '';
    Object.keys(d).forEach(function(k) {
      if(k==='generated_at'||!d[k]) return;
      var v = d[k];
      var c = colors[k]||'#00ff88';
      var rows = '';
      Object.entries(v).filter(function(e){return !['name','status','crew','targets','news','img_url'].includes(e[0]);}).slice(0,4).forEach(function(e) {
        rows += '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:10px"><span style="color:#4a7a8a;font-family:monospace">'+e[0].toUpperCase()+'</span><span style="color:#fff;font-family:monospace">'+String(e[1]).substring(0,22)+'</span></div>';
      });
      html += '<div onclick="openSondeModal(\''+k+'\')" style="cursor:pointer;background:rgba(0,20,40,0.85);border:1px solid '+c+'22;border-top:2px solid '+c+';border-radius:8px;padding:14px;transition:all 0.2s" onmouseover="this.style.transform=\'translateY(-3px)\';this.style.boxShadow=\'0 6px 24px '+c+'22\'" onmouseout="this.style.transform=\'\';this.style.boxShadow=\'\'">';
      html += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">';
      html += '<span style="font-size:1.3rem">'+(icons[k]||'🚀')+'</span>';
      html += '<div><div style="font-family:Orbitron,monospace;font-size:11px;color:#fff;letter-spacing:2px">'+(v.name||k.toUpperCase())+'</div>';
      html += '<div style="font-size:9px;color:'+c+';letter-spacing:1px;margin-top:2px">'+(v.status||'')+'</div></div>';
      html += '<div style="margin-left:auto;font-family:monospace;font-size:8px;color:'+c+';border:1px solid '+c+'44;padding:2px 8px;border-radius:10px">▶ LIVE</div>';
      html += '</div>'+rows+'</div>';
    });
    g.innerHTML = html || '<div style="color:#ff2d55;font-family:monospace;font-size:11px;padding:20px">Aucune donnée</div>';
  }).catch(function(e) {
    g.innerHTML = '<div style="color:#ff2d55;font-family:monospace;font-size:11px;padding:20px">ERREUR API: '+e.message+'</div>';
  });
}
