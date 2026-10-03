/* Decorative visuals only: never writes research records or changes agent state. */
(() => {
  'use strict';
  const stage = document.getElementById('scModelStage');
  const motionButton = document.getElementById('scMotionToggle');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reduced.matches;
  try { paused = paused || localStorage.getItem('scholarscout.visuals.paused') === 'true'; } catch (_) { /* storage may be unavailable */ }
  let refreshScene = () => {};
  function motionUI() {
    document.documentElement.classList.toggle('sc-motion-paused', paused);
    motionButton.textContent = paused ? 'Resume motion' : 'Pause motion';
    motionButton.setAttribute('aria-pressed', String(paused));
    refreshScene();
  }
  motionButton.addEventListener('click', () => {
    paused = !paused;
    try { localStorage.setItem('scholarscout.visuals.paused', String(paused)); } catch (_) { /* optional preference */ }
    motionUI();
  });
  reduced.addEventListener('change', event => { paused = event.matches; motionUI(); });
  motionUI();
  document.getElementById('visualStartAgent').addEventListener('click', () => document.getElementById('headerStartAgentBtn').click());
  document.getElementById('visualBrowseUniversities').addEventListener('click', () => document.getElementById('nav-tab-universities').click());

  const iconPaths = {
    jobs: '<path d="M7 5H5v16h14V5h-2M9 3h6v4H9zM8 12h8M8 16h5"/>',
    campus: '<path d="m2 9 10-6 10 6H2ZM4 21h16M5 18V11m5 7V11m4 7V11m5 7V11"/>',
    award: '<path d="M8 3h8v7a4 4 0 0 1-8 0V3Zm0 2H4v3a4 4 0 0 0 4 4m8-7h4v3a4 4 0 0 1-4 4m-4 2v5m-4 2h8"/>',
    faculty: '<path d="m9 3 4 0 0 6-4 0zm2 6v4m2-7a7 7 0 0 1 4 12H6m6 0v3M7 21h10M5 14h5"/>',
    star: '<path d="m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>'
  };
  function icon(path, cls='') { return `<svg class="${cls}" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`; }
  ['jobs','campus','award','faculty','star','mail'].forEach((key,i) => {
    const el = document.querySelectorAll('.metric-icon-wrap')[i];
    if (el) el.innerHTML = icon(iconPaths[key]);
  });
  const navKeys=['jobs','campus','star','jobs','campus','award','faculty','star','mail','jobs'];
  document.querySelectorAll('.nav-icon').forEach((el,i)=>{el.innerHTML=icon(iconPaths[navKeys[i]]);});
  const emptyPaths = '<path d="m3 8 9-5 9 5-9 5-9-5ZM6 11v6l6 4 6-4v-6M12 13v8"/><circle cx="19" cy="4" r="1"/><path d="M3 17v3m-1-1h3"/>';
  document.querySelectorAll('.empty-icon').forEach(el => { el.innerHTML = icon(emptyPaths, 'sc-empty-art'); });
  document.querySelectorAll('.tab-content:not(#tab-overview) > .screen-header').forEach(header => {
    const img = document.createElement('img');
    img.className = 'sc-header-art'; img.src = '/static/assets/research-campus.webp'; img.alt = ''; img.width = 110; img.height = 65; img.loading = 'lazy';
    header.append(img);
  });
  // Observe real values; the animation never substitutes synthetic counters.
  const metrics = document.querySelector('.metrics-grid');
  new MutationObserver(changes => {
    for (const change of changes) {
      const el = change.target.nodeType === Node.TEXT_NODE ? change.target.parentElement : change.target;
      if (el.classList?.contains('metric-number')) {
        el.classList.remove('sc-datum-changed');
        requestAnimationFrame(() => el.classList.add('sc-datum-changed'));
      }
    }
  }).observe(metrics, {subtree:true, childList:true, characterData:true});
  new ResizeObserver(entries => {
    document.documentElement.style.setProperty('--sc-header-height', `${entries[0].target.offsetHeight}px`);
  }).observe(document.querySelector('.app-header'));

  function fallback() {
    stage.classList.remove('sc-ready');
    stage.setAttribute('aria-label','Academic campus illustration');
    document.querySelector('.sc-scene-tabs').hidden = true;
    document.getElementById('scModelHint').textContent = 'Academic campus · Concept illustration';
  }
  if (!window.THREE) { fallback(); return; }
  const T = window.THREE;
  let renderer;
  try { renderer = new T.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'low-power'}); }
  catch (_) { fallback(); return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  renderer.setClearColor(0x000000,0);
  stage.append(renderer.domElement);
  renderer.domElement.setAttribute('aria-hidden','true');
  stage.classList.add('sc-ready');
  const scene = new T.Scene();
  const camera = new T.PerspectiveCamera(36,1,.1,100);
  camera.position.set(0,.35,7.5); camera.lookAt(0,0,0);
  scene.add(new T.HemisphereLight(0xd4ffed,0x09223a,2.4));
  const key = new T.DirectionalLight(0xeaf8ff,3.3); key.position.set(-3,5,4); scene.add(key);
  const rim = new T.DirectionalLight(0x64d6b0,2.5); rim.position.set(4,1,-2); scene.add(rim);
  const globe = new T.Group(); globe.rotation.z = -.14; scene.add(globe);
  const earthMaterial = new T.MeshStandardMaterial({color:0x236f68, roughness:.65,metalness:.3});
  globe.add(new T.Mesh(new T.SphereGeometry(1.53,64,40),earthMaterial));
  const gridMaterial = new T.LineBasicMaterial({color:0x76b7a4,transparent:true,opacity:.2});
  function line(points,material,parent) { const l = new T.Line(new T.BufferGeometry().setFromPoints(points),material); parent.add(l); return l; }
  for (let lat=-60;lat<=60;lat+=30) {
    const a=T.MathUtils.degToRad(lat), points=[];
    for (let i=0;i<=128;i++) { const b=i/128*Math.PI*2; points.push(new T.Vector3(Math.cos(a)*Math.cos(b)*1.54,Math.sin(a)*1.54,Math.cos(a)*Math.sin(b)*1.54)); }
    line(points,gridMaterial,globe);
  }
  for(let lon=0;lon<180;lon+=30) {
    const a=T.MathUtils.degToRad(lon),points=[];
    for(let i=0;i<=128;i++) { const b=i/128*Math.PI*2;points.push(new T.Vector3(Math.cos(b)*Math.cos(a)*1.54,Math.sin(b)*1.54,Math.cos(b)*Math.sin(a)*1.54)); }
    line(points,gridMaterial,globe);
  }
  // Local public-domain Natural Earth land geometry, drawn into an equirectangular texture.
  fetch('/static/assets/land.geojson').then(r=>{if(!r.ok)throw new Error('Map unavailable');return r.json();}).then(data=>{
    const canvas=document.createElement('canvas');canvas.width=2048;canvas.height=1024;
    const ctx=canvas.getContext('2d'); ctx.fillStyle='#123e47';ctx.fillRect(0,0,2048,1024);ctx.fillStyle='#7cc1a4';
    for(const feature of data.features) {
      const polygons=feature.geometry.type==='MultiPolygon'?feature.geometry.coordinates:[feature.geometry.coordinates];
      for(const polygon of polygons) {
        ctx.beginPath();
        for(const ring of polygon) {ring.forEach(([lon,lat],i)=>{const x=(lon+180)/360*2048,y=(90-lat)/180*1024;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.closePath();}
        ctx.fill('evenodd');
      }
    }
    const texture = new T.CanvasTexture(canvas);texture.colorSpace=T.SRGBColorSpace;
    earthMaterial.map=texture;earthMaterial.color.set(0xffffff);earthMaterial.needsUpdate=true;draw();
  }).catch(()=>{/* Graticule sphere remains useful if texture is unavailable. */});
  const orbitMaterial=new T.MeshStandardMaterial({color:0xd9bf87,metalness:.65,roughness:.3});
  const orbit=new T.Mesh(new T.TorusGeometry(1.96,.012,8,160),orbitMaterial);orbit.rotation.x=1.13;orbit.rotation.y=.35;globe.add(orbit);
  const satellite = new T.Mesh(new T.SphereGeometry(.065,16,12),new T.MeshStandardMaterial({color:0xffe4a8,emissive:0x5a3815,metalness:.4,roughness:.25}));globe.add(satellite);
  const orbit2=new T.Mesh(new T.TorusGeometry(1.82,.006,6,128),new T.MeshBasicMaterial({color:0x8fe7d0,transparent:true,opacity:.35}));orbit2.rotation.set(.4,.7,.5);globe.add(orbit2);

  // Actual procedural 3D university: plinth, stairs, columns, pediment, dome, research wing.
  const campus = new T.Group(); campus.visible=false; campus.rotation.set(.1,-.5,0); scene.add(campus);
  const ivory=new T.MeshStandardMaterial({color:0xeae4cf,roughness:.65});
  const stone=new T.MeshStandardMaterial({color:0x91aba2,roughness:.7});
  const dark=new T.MeshStandardMaterial({color:0x123c43,roughness:.35,metalness:.5});
  const glass=new T.MeshStandardMaterial({color:0x68c6c0,roughness:.15,metalness:.65,transparent:true,opacity:.72});
  function mesh(geometry,material,x,y,z,parent=campus) {const object=new T.Mesh(geometry,material);object.position.set(x,y,z);parent.add(object);return object;}
  function box(w,h,d,mat,x,y,z) {return mesh(new T.BoxGeometry(w,h,d),mat,x,y,z);}
  mesh(new T.CylinderGeometry(1.85,1.92,.2,64),dark,0,-.85,0);
  mesh(new T.TorusGeometry(1.87,.015,8,100),orbitMaterial,0,-.77,0).rotation.x=Math.PI/2;
  box(2.4,.12,1.45,stone,0,-.68,0);
  for(let i=0;i<4;i++)box(1.75,.085,.25+(4-i)*.15,ivory,-.25,-.65+i*.085,.73-i*.06);
  box(1.75,.98,.83,ivory,-.25,-.08,-.2);
  box(1.94,.11,1.3,ivory,-.25,.5,.0);
  for(let i=0;i<5;i++) {
    const x=-1.0+i*.375;
    mesh(new T.CylinderGeometry(.055,.07,.87,16),ivory,x,-.02,.54);
    box(.17,.08,.17,stone,x,-.46,.54);box(.16,.06,.16,ivory,x,.43,.54);
    if(i<4)box(.18,.43,.02,dark,x+.16,-.04,.226);
  }
  const triangle=new T.Shape();triangle.moveTo(-1.04,0);triangle.lineTo(0,.47);triangle.lineTo(1.04,0);triangle.closePath();
  mesh(new T.ExtrudeGeometry(triangle,{depth:1.17,bevelEnabled:false}),ivory,-.25,.555,-.58);
  mesh(new T.CylinderGeometry(.34,.38,.19,32),stone,-.25,.87,-.12);
  mesh(new T.SphereGeometry(.36,32,16,0,Math.PI*2,0,Math.PI/2),glass,-.25,.965,-.12);
  mesh(new T.CylinderGeometry(.012,.017,.2,8),orbitMaterial,-.25,1.35,-.12);
  box(.53,1.02,1.02,glass,1.0,-.08,-.1);
  for(let y=-.54;y<=.46;y+=.25)box(.59,.035,1.06,ivory,1,y,-.1);
  for(let z=-.57;z<=.5;z+=.25)box(.025,1.02,.025,ivory,1.285,-.08,z);
  for(const [x,z] of [[-1.4,.35],[-1.35,-.65],[1.43,.55]]) {
    mesh(new T.CylinderGeometry(.024,.035,.29,8),orbitMaterial,x,-.51,z);
    mesh(new T.IcosahedronGeometry(.21,1),new T.MeshStandardMaterial({color:0x65a88a,roughness:.9}),x,-.27,z);
  }
  let active=globe, frame=0, visible=true, dragging=false, previousX=0, previousY=0,last=0,phase=0;
  function draw(){renderer.render(scene,camera);}
  function animate(time) {
    frame=0;
    const delta=Math.min((time-(last||time))/1000,.05);last=time;
    if(!dragging) {active.rotation.y+=delta*.12;phase+=delta*.25;}
    satellite.position.set(1.96*Math.cos(phase),.8*Math.sin(phase),1.79*Math.sin(phase));
    draw();
    if(!paused&&visible&&!document.hidden)frame=requestAnimationFrame(animate);
  }
  refreshScene=()=>{cancelAnimationFrame(frame);frame=0;last=0;draw();if(!paused&&visible&&!document.hidden)frame=requestAnimationFrame(animate);};
  new ResizeObserver(()=>{const w=stage.clientWidth,h=stage.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);camera.aspect=w/h;camera.position.z=w/h<1.1?8.8:7.5;camera.updateProjectionMatrix();draw();}).observe(stage);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;refreshScene();},{threshold:.05}).observe(stage);
  document.addEventListener('visibilitychange',refreshScene);
  stage.addEventListener('pointerdown',e=>{dragging=true;previousX=e.clientX;previousY=e.clientY;stage.setPointerCapture(e.pointerId);});
  stage.addEventListener('pointermove',e=>{if(!dragging)return;active.rotation.y+=(e.clientX-previousX)*.008;active.rotation.x=T.MathUtils.clamp(active.rotation.x+(e.clientY-previousY)*.004,-.65,.65);previousX=e.clientX;previousY=e.clientY;draw();});
  ['pointerup','pointercancel','lostpointercapture'].forEach(name=>stage.addEventListener(name,()=>{dragging=false;}));
  stage.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();if(e.key==='ArrowLeft')active.rotation.y-=.15;if(e.key==='ArrowRight')active.rotation.y+=.15;if(e.key==='ArrowUp')active.rotation.x=Math.max(-.65,active.rotation.x-.1);if(e.key==='ArrowDown')active.rotation.x=Math.min(.65,active.rotation.x+.1);draw();});
  document.querySelectorAll('[data-sc-model]').forEach(button=>button.addEventListener('click',()=>{
    const isGlobe=button.dataset.scModel==='globe';globe.visible=isGlobe;campus.visible=!isGlobe;active=isGlobe?globe:campus;
    document.querySelectorAll('[data-sc-model]').forEach(other=>{const selected=other===button;other.classList.toggle('selected',selected);other.setAttribute('aria-pressed',String(selected));});
    stage.setAttribute('aria-label',`Decorative 3D ${isGlobe?'globe':'university campus model'}. Drag or use arrow keys to rotate. Concept illustration, not live research data.`);draw();
  }));
  renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();cancelAnimationFrame(frame);visible=false;fallback();});
  renderer.domElement.addEventListener('webglcontextrestored',()=>{document.querySelector('.sc-scene-tabs').hidden=false;stage.classList.add('sc-ready');visible=true;refreshScene();});
  refreshScene();
})();
