"use strict";
const $ = selector => document.querySelector(selector);
const state = {mode:"single",single:null,comparison:null,frame:"vehicle",event:null,pinned:null,busy:false,requestId:0};
let routeView = {zoom:1,panX:0,panY:0};
const colours = ["#62d7e9","#eac477","#78d6a5"];
const eventMeta = {harsh_brake:{label:"Harsh braking",colour:"#ec8890"},harsh_accel:{label:"Harsh acceleration",colour:"#78d6a5"},harsh_corner:{label:"Harsh cornering",colour:"#eac477"}};
const esc = value => String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = (value,digits=2) => Number(value).toFixed(digits);
const direction = (value,pos,neg) => `${num(Math.abs(value),1)}° ${value>=0?pos:neg}`;
const badge = data => `<span class="badge ${data.confidenceLabel.toLowerCase()}" title="Agreement between calibrated forward acceleration and GPS-derived forward motion; not percentage accuracy.">${data.confidenceLabel} confidence · ${num(data.confidence)}</span>`;

function strip(){return `<div class="frame-strip"><div class="frame-step"><span>X / Y / Z</span><strong>Raw phone frame</strong><p>Motion along the phone’s own axes.</p></div><span class="arrow" aria-hidden="true">→</span><div class="frame-step"><span>Rotation R</span><strong>Estimated mounting</strong><p>Gravity and GPS motion establish alignment.</p></div><span class="arrow" aria-hidden="true">→</span><div class="frame-step"><span>Forward / Lateral / Vertical</span><strong>Vehicle frame</strong><p>Motion expressed relative to the car.</p></div></div>`;}

async function refreshLogs(){
  const previous = ["single-log","first-log","second-log"].map(id=>[id,$(`#${id}`).value]);
  try{
    const response=await fetch("/api/logs"); if(!response.ok)throw Error("Recording library could not be read.");
    const {logs}=await response.json();
    for(const [id,old] of previous){const select=$(`#${id}`);select.innerHTML=logs.map(log=>`<option value="${esc(log.value)}">${esc(log.label)}</option>`).join("");if(logs.some(log=>log.value===old))select.value=old;}
    if(!previous[2][1] && logs.length>1)$("#second-log").selectedIndex=1;
    $("#library-count").textContent=`${logs.length} saved recording${logs.length===1?"":"s"}`;
    if(!logs.length)$("#library-count").textContent="Add GNSS Logger .txt files to validation/data/own_drives, then refresh.";
    updateButtons();
  }catch(error){$("#library-count").textContent=error.message;}
}
function updateButtons(){document.querySelectorAll("form button").forEach(button=>button.disabled=state.busy||!$("#single-log").options.length);}
function setMode(mode){
  state.mode=mode; state.event=null;state.pinned=null;
  document.querySelectorAll("[data-mode]").forEach(button=>{button.classList.toggle("active",button.dataset.mode===mode);button.setAttribute("aria-current",button.dataset.mode===mode?"page":"false");});
  $("#analyse-form").hidden=mode!=="single";$("#compare-form").hidden=mode!=="compare";$(".library").hidden=mode==="method";
  $("#page-title").textContent={single:"Analyse a drive",compare:"Compare two drives",method:"How it works"}[mode];
  $("#section-label").textContent={single:"Drive workspace",compare:"Cross-device validation",method:"The calibration method"}[mode];
  $("#feedback").innerHTML="";render();
}
function render(){
  if(state.busy){$("#content").innerHTML='<div class="busy"><span class="spinner" aria-hidden="true"></span><div>Calibrating recording'+(state.mode==="compare"?'s':'')+'…<p class="small muted">Reading sensors, estimating mounting, and checking motion.</p></div></div>';return;}
  if(state.mode==="method")return renderMethod();
  if(state.mode==="compare")return renderCompare();
  renderSingle();
}
async function run(endpoint,payload){
  if(state.busy)return;
  const mode=state.mode,id=++state.requestId;state.busy=true;state.event=null;state.pinned=null;$("#feedback").innerHTML="";updateButtons();render();
  try{
    const response=await fetch(endpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const data=await response.json();if(!response.ok)throw Error(data.error||"The recording could not be analysed.");
    if(id!==state.requestId)return;
    if(mode==="single"){state.single=data;routeView={zoom:1,panX:0,panY:0};}else state.comparison=data;
  }catch(error){
    if(mode==="single")state.single=null;else state.comparison=null;
    if(state.mode===mode)$("#feedback").innerHTML=`<div class="error"><strong>Choose another recording or check this log.</strong><p>${esc(error.message)}</p></div>`;
  }finally{state.busy=false;updateButtons();render();}
}

function renderSingle(){
  const d=state.single;
  if(!d){$("#content").innerHTML=`<section class="welcome"><h2>From the phone’s position<br>to the vehicle’s motion.</h2><p>Select a saved drive on the left. RetroSense estimates how the phone was mounted and translates its sensor signals into forward, lateral, and vertical vehicle motion.</p>${strip()}<p class="welcome-foot">Use a drive with a stationary start, acceleration, and turns. Results appear here after analysis.</p></section>`;return;}
  const m=d.mounting;
  $("#content").innerHTML=`
    <div class="result-heading"><div><h2 class="record-name">${esc(d.log)}</h2><p class="file-path">${esc(d.path)}</p></div>${badge(d)}</div>
    <section class="stats" aria-label="Drive summary"><div class="stat"><span>Recording</span><strong>${num(d.durationS,0)}<small>s</small></strong></div><div class="stat"><span>Distance</span><strong>${num(d.distanceKm)}<small>km</small></strong></div><div class="stat"><span>Peak GPS speed</span><strong>${num(d.peakSpeedKmh,1)}<small>km/h</small></strong></div><div class="stat"><span>Stationary samples used</span><strong>${d.stationarySamples.toLocaleString()}</strong></div></section>
    <div class="overview"><section><div class="section-head"><h2>Drive route</h2><span>Top-down · north up</span></div><div class="route-toolbar" role="group" aria-label="Route zoom controls"><button id="route-out" aria-label="Zoom out" title="Zoom out">−</button><output id="route-zoom" aria-label="Route zoom level">1×</output><button id="route-in" aria-label="Zoom in" title="Zoom in">+</button><button id="route-fit" title="Reset zoom and position">Fit drive</button><span>Scroll to zoom · drag to pan</span></div><div class="plot-wrap"><canvas id="route" tabindex="0" role="img" aria-label="Interactive north-up vehicle route. Scroll or use plus and minus to zoom, arrow keys to pan, and 0 to fit the drive. Red is slow and green is fast."></canvas></div><p class="note">Discrete GPS fixes connected by speed. This shows where the vehicle travelled, not the calibration itself.</p></section>
    <section><div class="section-head"><h2>Recovered phone mounting</h2><span>Phone → vehicle</span></div><div class="mount-panel"><div class="mounting"><div class="mount-row"><span>Phone top direction</span><strong>${direction(m.heading,"left of forward","right of forward")}</strong></div><div class="mount-row"><span>Phone top tilt</span><strong>${direction(m.tilt,"downward","upward")}</strong></div><div class="mount-row"><span>Right edge</span><strong>${direction(m.edge,"higher","lower")}</strong></div><p class="rotation-line">Technical rotation<br>Roll ${num(m.roll,1)}° &nbsp; Pitch ${num(m.pitch,1)}° &nbsp; Yaw ${num(m.yaw,1)}°</p></div><div><p class="note">Gravity establishes tilt. Driving motion and GPS establish the vehicle’s forward direction.</p><div class="axis-strip"><span>Phone XYZ</span><b>→ R →</b><strong>Vehicle FLV</strong></div></div></div></section></div>
    <div class="motion-layout"><section><div class="section-head"><h2>Motion signal</h2><div class="segmented" aria-label="Signal coordinate frame"><button data-frame="vehicle">Vehicle frame</button><button data-frame="raw">Raw phone frame</button></div></div><div class="plot-wrap"><canvas id="motion" role="img" aria-label="Acceleration over time with detected event windows"></canvas></div><p class="note" id="event-note" aria-live="polite"></p><p class="note" id="frame-note"></p></section>
    <section><div class="section-head"><h2>Detected events</h2><span>Hover to locate</span></div><div class="event-controls">${Object.entries(eventMeta).map(([key,value])=>`<button class="event-row" data-event="${key}" aria-pressed="false"><span>${value.label}</span><b>${d.events[key]}</b></button>`).join("")}</div><div class="peaks"><div class="peak"><span>Peak forward acceleration</span><strong>${num(d.motion.forward)} m/s²</strong></div><div class="peak"><span>Peak braking</span><strong>${num(d.motion.braking)} m/s²</strong></div><div class="peak"><span>Peak lateral acceleration</span><strong>${num(d.motion.lateral)} m/s²</strong></div></div><p class="note">Threshold counts, without a trip safety score. Events must last ≥${d.thresholds.durationS} s while moving above ${d.thresholds.speedMps} m/s.</p></section></div>
    <p class="confidence-note">Confidence ${num(d.confidence)} measures agreement with GPS-derived forward motion. It is a consistency check, not percentage accuracy.</p>`;
  document.querySelectorAll("[data-frame]").forEach(button=>button.addEventListener("click",()=>{state.frame=button.dataset.frame;drawMotion();}));
  document.querySelectorAll("[data-event]").forEach(button=>{
    const key=button.dataset.event;
    button.addEventListener("mouseenter",()=>{state.event=key;drawMotion();});
    button.addEventListener("mouseleave",()=>{state.event=null;drawMotion();});
    button.addEventListener("focus",()=>{state.event=key;drawMotion();});
    button.addEventListener("blur",()=>{state.event=null;drawMotion();});
    button.addEventListener("click",()=>{state.pinned=state.pinned===key?null:key;drawMotion();});
  });
  bindRouteNavigation();
  requestAnimationFrame(()=>{drawRoute();drawMotion();});
}

function renderCompare(){
  const d=state.comparison;
  if(!d){$("#content").innerHTML=`<section class="welcome"><h2>Different mounts.<br>The same vehicle motion.</h2><p>Select two phones’ recordings from the same drive. Each phone is calibrated independently before their vehicle-motion measurements are compared.</p>${strip()}<p class="welcome-foot">A comparison supports consistency across mounts. It does not establish absolute accuracy.</p></section>`;return;}
  const devices=[d.first,d.second].map((phone,i)=>`<article class="device"><p class="muted small">Phone ${i===0?"A":"B"}</p><h2>${esc(phone.log)}</h2>${badge(phone)}<div class="mount-row"><span>Top direction</span><strong>${direction(phone.mounting.heading,"left of forward","right of forward")}</strong></div><div class="mount-row"><span>Top tilt</span><strong>${direction(phone.mounting.tilt,"downward","upward")}</strong></div><p class="note">${num(phone.durationS,0)} s recorded · ${num(phone.distanceKm)} km</p></article>`).join("");
  const metricRows=[["forward","Peak forward acceleration"],["braking","Peak braking"],["lateral","Peak lateral acceleration"]].map(([key,label])=>`<tr><td>${label}</td><td>${num(d.first.motion[key])} m/s²</td><td>${num(d.second.motion[key])} m/s²</td><td>${num(d.differences[key])} m/s²</td></tr>`).join("");
  const eventRows=Object.entries(eventMeta).map(([key,item])=>`<tr><td>${item.label} events</td><td>${d.first.events[key]}</td><td>${d.second.events[key]}</td><td>${d.first.events[key]===d.second.events[key]?"Match":Math.abs(d.first.events[key]-d.second.events[key])+" difference"}</td></tr>`).join("");
  $("#content").innerHTML=`<section class="comparison"><div class="devices">${devices}</div><div class="table-scroll"><table><caption class="note" style="text-align:left;padding-bottom:14px">Independently calibrated vehicle-frame measurements</caption><thead><tr><th>Measurement</th><th>Phone A</th><th>Phone B</th><th>Absolute difference</th></tr></thead><tbody>${metricRows}${eventRows}</tbody></table></div><p class="comparison-note">The mounting estimates describe each phone’s own position. After calibration, both recordings use vehicle-forward and lateral axes, so their measurements can be compared. ${d.eventMatch?"All three event counts match.":"Some event counts differ; inspect each recording before drawing conclusions."} Similar peaks and counts support consistency but do not prove the complete signals match.</p></section>`;
}

function renderMethod(){
  $("#content").innerHTML=`<article class="method"><h2>From raw sensors to vehicle motion</h2><p>A route plot shows where the phone travelled. RetroSense uses the IMU and GPS together to estimate how the phone was mounted, then converts phone-axis acceleration into vehicle-forward, lateral, and vertical motion.</p>${strip()}<section><h2>What the six axes do</h2><p>The accelerometer measures along three phone axes: X, Y, and Z. The gyroscope measures rotation around those same three axes. Gravity during still periods establishes tilt; GPS speed and course help establish forward direction. Gyroscope measurements help identify still periods.</p><p class="note">Harsh events use calibrated acceleration. The current system does not calculate jerk on all six axes.</p></section><section><h2>Reading the motion plot</h2><p>Raw phone frame follows the phone’s orientation. Vehicle frame maps the same measurements to the car’s forward, left, and up directions. Forward and lateral signals use the event detector’s 0.5-second smoothing. Vertical acceleration retains gravity, so a level stationary vehicle reads about 9.8 m/s² upward.</p></section><section><h2>What confidence means</h2><p>Confidence measures how well calibrated forward acceleration agrees with forward motion estimated from GPS speed. It is not a percentage accuracy score and does not directly grade the phone or its mount. Lower confidence can result from GPS noise, sensor variation, or a drive with less useful motion.</p><div class="thresholds"><span>Strong ≥0.60</span><span>Moderate ≥0.35</span><span>Limited ≥0.15</span><span>Weak &lt;0.15</span></div><p class="note">These are descriptive labels chosen for this dashboard. The 0.15 threshold belongs to the calibration’s sign-check safeguard; exceeding it does not independently validate the mounting estimate.</p></section><section><h2>Detecting events</h2><p>The existing detector finds sustained braking, acceleration, and lateral acceleration above its configured thresholds while the vehicle is moving. Hover, keyboard-focus, or click an event count to highlight all its detected time windows. Click again to clear a pinned highlight.</p></section><section><h2>What this version does</h2><p>RetroSense analyses previously recorded GNSS Logger files on this computer. It estimates mounting and reports motion measurements and event counts. Live warnings, iPhone log adapters, and pothole detection remain future work.</p></section></article>`;
}

function canvasContext(id){
  const canvas=$(id);if(!canvas)return null;
  const {width,height}=canvas.getBoundingClientRect(),ratio=window.devicePixelRatio||1;
  canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
  const ctx=canvas.getContext("2d");ctx.scale(ratio,ratio);ctx.font='11px Bahnschrift,"Segoe UI",sans-serif';
  return {ctx,width,height};
}
function speedColour(fraction){
  const t=Math.max(0,Math.min(1,fraction)),stops=[[236,136,144],[234,196,119],[120,214,165]];
  const index=t<.5?0:1,local=t<.5?t*2:(t-.5)*2;
  return `rgb(${stops[index].map((c,i)=>Math.round(c+(stops[index+1][i]-c)*local)).join(",")})`;
}
function routeEventSpans(points,windows){
  // Clip each event to its surrounding GPS segments. Sub-second events can
  // occur between fixes; do not require an exact GPS sample inside the window.
  return windows.map(([start,end])=>{
    const spans=[];
    for(let i=1;i<points.length;i++){
      const a=points[i-1],b=points[i],dt=b.time-a.time;
      if(!Number.isFinite(dt)||dt<=0||dt>5||b.time<start||a.time>end)continue;
      const lo=Math.max(start,a.time),hi=Math.min(end,b.time);
      if(hi<=lo)continue;
      const at=time=>({x:a.x+(b.x-a.x)*(time-a.time)/dt,y:a.y+(b.y-a.y)*(time-a.time)/dt});
      spans.push({start:at(lo),end:at(hi)});
    }
    return spans;
  });
}

function zoomRoute(factor,anchorX=0,anchorY=0){
  const next=Math.max(1,Math.min(64,routeView.zoom*factor)),ratio=next/routeView.zoom;
  routeView.panX=anchorX-(anchorX-routeView.panX)*ratio;
  routeView.panY=anchorY-(anchorY-routeView.panY)*ratio;
  routeView.zoom=next;
  if(next===1){routeView.panX=0;routeView.panY=0;}
  drawRoute();
}

function bindRouteNavigation(){
  const canvas=$("#route");let drag=null;
  $("#route-in").addEventListener("click",()=>zoomRoute(1.5));
  $("#route-out").addEventListener("click",()=>zoomRoute(1/1.5));
  $("#route-fit").addEventListener("click",()=>{routeView={zoom:1,panX:0,panY:0};drawRoute();});
  canvas.addEventListener("wheel",event=>{
    const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
    if(x<44||x>rect.width-25||y<31||y>rect.height-65)return;
    event.preventDefault();
    const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?rect.height:1);
    zoomRoute(Math.exp(-Math.max(-250,Math.min(250,delta))*.003),x-(44+rect.width-25)/2,y-(31+rect.height-65)/2);
  },{passive:false});
  canvas.addEventListener("pointerdown",event=>{
    if(event.button!==0)return;
    drag={x:event.clientX,y:event.clientY};canvas.setPointerCapture(event.pointerId);canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove",event=>{
    if(!drag)return;
    routeView.panX+=event.clientX-drag.x;routeView.panY+=event.clientY-drag.y;
    drag={x:event.clientX,y:event.clientY};drawRoute();
  });
  const endDrag=()=>{drag=null;canvas.classList.remove("dragging");};
  canvas.addEventListener("pointerup",endDrag);canvas.addEventListener("pointercancel",endDrag);canvas.addEventListener("lostpointercapture",endDrag);
  canvas.addEventListener("keydown",event=>{
    const keys=["+","=","-","0","Home","ArrowLeft","ArrowRight","ArrowUp","ArrowDown"];
    if(!keys.includes(event.key))return;event.preventDefault();
    if(event.key==="+"||event.key==="=")zoomRoute(1.5);
    else if(event.key==="-")zoomRoute(1/1.5);
    else if(event.key==="0"||event.key==="Home")$("#route-fit").click();
    else{routeView.panX+=event.key==="ArrowLeft"?35:event.key==="ArrowRight"?-35:0;routeView.panY+=event.key==="ArrowUp"?35:event.key==="ArrowDown"?-35:0;drawRoute();}
  });
}

function drawRoute(){
  const plot=canvasContext("#route"),points=state.single?.route;if(!plot||!points?.length)return;
  const {ctx,width:w,height:h}=plot,p={left:44,right:25,top:31,bottom:65};
  const xs=points.map(d=>d.x),ys=points.map(d=>d.y),speeds=points.map(d=>d.speed);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const scale=Math.min((w-p.left-p.right)/Math.max(maxX-minX,.001),(h-p.top-p.bottom)/Math.max(maxY-minY,.001))*.9*routeView.zoom;
  const cx=(p.left+w-p.right)/2,cy=(p.top+h-p.bottom)/2;
  const x=v=>cx+routeView.panX+(v-(minX+maxX)/2)*scale,y=v=>cy+routeView.panY-(v-(minY+maxY)/2)*scale;
  $("#route-zoom").textContent=`${num(routeView.zoom,1)}×`;
  $("#route-out").disabled=routeView.zoom<=1;$("#route-in").disabled=routeView.zoom>=64;
  ctx.strokeStyle="#20313d";ctx.lineWidth=1;
  for(let i=0;i<=4;i++){const xx=p.left+i*(w-p.left-p.right)/4,yy=p.top+i*(h-p.top-p.bottom)/4;ctx.beginPath();ctx.moveTo(xx,p.top);ctx.lineTo(xx,h-p.bottom);ctx.stroke();ctx.beginPath();ctx.moveTo(p.left,yy);ctx.lineTo(w-p.right,yy);ctx.stroke();}
  const slow=Math.min(...speeds),fast=Math.max(...speeds),range=Math.max(fast-slow,.001);
  ctx.save();ctx.beginPath();ctx.rect(p.left,p.top,w-p.left-p.right,h-p.top-p.bottom);ctx.clip();
  ctx.lineWidth=2.7;ctx.lineCap="round";
  for(let i=1;i<points.length;i++){ctx.strokeStyle=speedColour(((points[i-1].speed+points[i].speed)/2-slow)/range);ctx.beginPath();ctx.moveTo(x(points[i-1].x),y(points[i-1].y));ctx.lineTo(x(points[i].x),y(points[i].y));ctx.stroke();}
  const eventKey=state.event||state.pinned;
  if(eventKey){
    const groups=routeEventSpans(points,state.single.eventWindows[eventKey]||[]);
    for(const [index,spans] of groups.entries()){
      if(!spans.length)continue;
      // A dark halo and numbered markers distinguish events from speed colours.
      for(const span of spans){
        for(const [colour,lineWidth] of [["#0b1117",9],[eventMeta[eventKey].colour,5]]){
          ctx.strokeStyle=colour;ctx.lineWidth=lineWidth;ctx.beginPath();ctx.moveTo(x(span.start.x),y(span.start.y));ctx.lineTo(x(span.end.x),y(span.end.y));ctx.stroke();
        }
      }
      const middle=spans[Math.floor(spans.length/2)],px=x((middle.start.x+middle.end.x)/2),py=y((middle.start.y+middle.end.y)/2);
      ctx.fillStyle=eventMeta[eventKey].colour;ctx.strokeStyle="#0b1117";ctx.lineWidth=2;ctx.beginPath();ctx.arc(px,py,9,0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.fillStyle="#0b1117";ctx.textAlign="center";ctx.fillText(String(index+1),px,py+4);ctx.textAlign="left";
    }
  }
  const start=points[0],end=points.at(-1);
  ctx.fillStyle="#111b24";ctx.strokeStyle="#e8f0f4";ctx.lineWidth=2;ctx.beginPath();ctx.arc(x(start.x),y(start.y),4,0,2*Math.PI);ctx.fill();ctx.stroke();
  ctx.fillStyle="#e8f0f4";ctx.fillRect(x(end.x)-3,y(end.y)-3,6,6);
  ctx.restore();
  if(eventKey){
    const groups=routeEventSpans(points,state.single.eventWindows[eventKey]||[]),mapped=groups.filter(spans=>spans.length).length;
    ctx.fillStyle=eventMeta[eventKey].colour;ctx.fillText(`${eventMeta[eventKey].label}: ${mapped}/${groups.length} located`,p.left,h-8);
  }
  ctx.fillStyle="#96aab8";ctx.fillText("N ↑",w-45,18);ctx.fillText("○ Start    ▪ End",p.left,18);
  const keyWidth=Math.min(140,w/3),keyX=w-p.right-keyWidth,keyY=h-28;
  for(let i=0;i<keyWidth;i++){ctx.fillStyle=speedColour(i/(keyWidth-1));ctx.fillRect(keyX+i,keyY,1,5);}
  ctx.fillStyle="#96aab8";ctx.textAlign="left";ctx.fillText(`${num(slow,0)}`,keyX,keyY-6);ctx.textAlign="right";ctx.fillText(`${num(fast,0)} km/h`,keyX+keyWidth,keyY-6);ctx.textAlign="left";
  const km=(w-p.left-p.right)/scale/5,barLength=km*scale;ctx.strokeStyle="#96aab8";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(p.left,h-28);ctx.lineTo(p.left+barLength,h-28);ctx.stroke();ctx.fillText(`${num(km,2)} km`,p.left,h-36);
}

function drawMotion(){
  const plot=canvasContext("#motion"),d=state.single;if(!plot||!d)return;
  const key=state.event||state.pinned,raw=state.frame==="raw";
  drawRoute();
  document.querySelectorAll("[data-frame]").forEach(button=>{button.classList.toggle("active",button.dataset.frame===state.frame);button.setAttribute("aria-pressed",String(button.dataset.frame===state.frame));});
  document.querySelectorAll("[data-event]").forEach(button=>{button.classList.toggle("selected",button.dataset.event===key);button.setAttribute("aria-pressed",String(button.dataset.event===state.pinned));});
  $("#event-note").textContent=key?`${d.events[key]} ${eventMeta[key].label.toLowerCase()} window${d.events[key]===1?"":"s"} highlighted on the motion signal and route${state.pinned===key?" · click again to clear":""}. Route markers estimate positions between GPS fixes; gaps over 5 s are left unmarked.`:"Hover over an event count to locate it on both the motion signal and route. Click to keep the highlights visible.";
  $("#frame-note").textContent=raw?"Phone X, Y, Z depend on placement. Raw acceleration includes gravity.":"Forward and lateral use the detector’s smoothed acceleration. Vertical includes gravity (~9.8 m/s² at rest).";
  const {ctx,width:w,height:h}=plot,p={l:47,r:19,t:39,b:33};
  const samples=raw?d.signals.raw:d.signals.vehicle,times=d.signals.time;
  // Use a common range for both frames so toggling does not disguise changes.
  const all=[...d.signals.raw.flat(),...d.signals.vehicle.flat()];
  const low=Math.min(-1,...all),high=Math.max(1,...all),extra=(high-low)*.08;
  const min=low-extra,max=high+extra;
  const tx=time=>p.l+(time-times[0])/Math.max(times.at(-1)-times[0],.001)*(w-p.l-p.r);
  const vy=value=>p.t+(max-value)/(max-min)*(h-p.t-p.b);
  ctx.fillStyle="#96aab8";
  for(let i=0;i<=4;i++){const value=min+i*(max-min)/4,yy=vy(value);ctx.strokeStyle="#263540";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(p.l,yy);ctx.lineTo(w-p.r,yy);ctx.stroke();ctx.textAlign="right";ctx.fillText(num(value,1),p.l-7,yy+4);}
  ctx.textAlign="left";ctx.fillText("m/s²",8,18);
  for(let i=0;i<=4;i++){const time=times[0]+i*(times.at(-1)-times[0])/4;ctx.textAlign=i===4?"right":"left";ctx.fillText(`${num(time,0)} s`,tx(time),h-12);}ctx.textAlign="left";
  if(key){ctx.fillStyle=eventMeta[key].colour+"30";for(const [start,end] of d.eventWindows[key]||[]){const left=tx(start),right=tx(end);ctx.fillRect(left,p.t,Math.max(4,right-left),h-p.t-p.b);ctx.strokeStyle=eventMeta[key].colour;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,p.t);ctx.lineTo(left,h-p.b);ctx.stroke();}}
  ctx.save();ctx.beginPath();ctx.rect(p.l,p.t,w-p.l-p.r,h-p.t-p.b);ctx.clip();
  for(let axis=0;axis<3;axis++){ctx.strokeStyle=colours[axis];ctx.lineWidth=1.2;ctx.beginPath();samples.forEach((sample,i)=>i?ctx.lineTo(tx(times[i]),vy(sample[axis])):ctx.moveTo(tx(times[i]),vy(sample[axis])));ctx.stroke();}ctx.restore();
  (raw?["Phone X","Phone Y","Phone Z"]:["Forward","Lateral","Vertical"]).forEach((label,i)=>{ctx.fillStyle=colours[i];ctx.fillRect(p.l+i*85,15,9,2);ctx.fillText(label,p.l+15+i*85,20);});
}

document.querySelectorAll("[data-mode]").forEach(button=>button.addEventListener("click",()=>setMode(button.dataset.mode)));
$(".brand").addEventListener("click",event=>{event.preventDefault();setMode("single");});
$("#refresh").addEventListener("click",refreshLogs);
$("#analyse-form").addEventListener("submit",event=>{event.preventDefault();run("/api/analyze",{log:$("#single-log").value});});
$("#compare-form").addEventListener("submit",event=>{event.preventDefault();run("/api/compare",{first:$("#first-log").value,second:$("#second-log").value});});
let resizeTimer;window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(state.mode==="single"&&state.single&&!state.busy){drawRoute();drawMotion();}},100);});
setMode("single");refreshLogs();
