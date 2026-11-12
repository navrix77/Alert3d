// усі інфо-вікна на мапі (приліт, КАБ, пуск…) отримують велику кнопку «Закрити»: ✕ угорі перекривала плашка «Наживо»
try{if(window.maplibregl&&!maplibregl.Popup.prototype._kc){const _ad=maplibregl.Popup.prototype.addTo;maplibregl.Popup.prototype._kc=1;maplibregl.Popup.prototype.addTo=function(m){const r=_ad.call(this,m);try{const el=this.getElement(),c=el&&el.querySelector('.maplibregl-popup-content');if(c&&el.classList.contains('kab-pop')&&!c.querySelector('.kp-close')){const b=document.createElement('button');b.type='button';b.className='kp-close';b.textContent='Закрити';const shut=ev=>{try{ev.preventDefault();ev.stopPropagation();}catch(e){}if(this._shut)return;this._shut=1;this.remove();};['touchend','pointerup','click'].forEach(n=>b.addEventListener(n,shut,{passive:false}));c.appendChild(b);const x=el.querySelector('.maplibregl-popup-close-button');if(x)['touchend','pointerup','click'].forEach(n=>x.addEventListener(n,shut,{passive:false}));['touchstart','touchmove','pointerdown','mousedown','wheel'].forEach(n=>el.addEventListener(n,ev=>ev.stopPropagation(),{passive:true}));}}catch(e){}return r;};}}catch(e){}
(()=>{
'use strict';
const $=s=>document.querySelector(s);
const D2R=Math.PI/180,KX=111.32*Math.cos(49*D2R),KY=110.57;
const xy=([lon,lat])=>[(lon-31.5)*KX,(lat-49)*KY];
const ll=([x,y])=>[x/KX+31.5,49+y/KY];
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const brg=(a,b)=>(Math.atan2(b[0]-a[0],b[1]-a[1])/D2R+360)%360;
const angd=(a,b)=>{let d=Math.abs(a-b)%360;return d>180?360-d:d;};
const fmt=t=>new Date(t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
const fmtS=t=>new Date(t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SIDE=['на північ','на північний схід','на схід','на південний схід','на південь','на південний захід','на захід','на північний захід'];
const FROM=['з півночі','з північного сходу','зі сходу','з південного сходу','з півдня','з південного заходу','з заходу','з північного заходу'];
const toast=m=>{const t=$('#toast');t.textContent=m;t.hidden=false;clearTimeout(toast.h);toast.h=setTimeout(()=>t.hidden=true,2600);};

let homeSaved=null,FOLHOME=false,SNAP=null,recvAt=0,offset=0,sel=null,follow=false,home=null,setHomeMode=false,tilt=(()=>{try{if(!localStorage.getItem('mapv2')){localStorage.setItem('mapv2','1');localStorage.setItem('t3d','0');}}catch(e){}return localStorage.getItem('t3d')==='1';})(),base=(()=>{try{if(localStorage.getItem('base2')==='navryx'){localStorage.setItem('base2','night');const p=JSON.parse(localStorage.getItem('pref')||'{}');if(p.base==='navryx'){delete p.base;localStorage.setItem('pref',JSON.stringify(p));}}}catch(e){}return localStorage.getItem('base2')||'night';})();
function applySaver(){const on=window.NXPERF&&NXPERF.saver;['hillshade','bld3d'].forEach(id=>{if(map.getLayer(id))map.setLayoutProperty(id,'visibility',on?'none':'visible');});const c=$('#st-saver');if(c){c.checked=!!(window.NXPERF&&localStorage.getItem('saver')==='1');c.onchange=e=>NXPERF.setSaver(e.target.checked);}}
document.addEventListener('nxsaver',()=>{try{applySaver();}catch(e){}});
function syncReal3d(){applySaver();const r=$('#st-real3d-row');if(r)r.hidden=!(CFG&&CFG.gtilesKey);const c=$('#st-real3d');if(c){c.checked=!!(window.Real3D&&Real3D.active());c.onchange=async e=>{if(e.target.checked){const ok=await Real3D.on();if(!ok){e.target.checked=false;toast('3D-моделі зараз недоступні');}}else Real3D.off();};}}
window.NX={snap:()=>SNAP,focusType:t=>focusType(t),toast:m=>toast(m),open:id=>openSheet(id),note:n=>note(n),
  map:()=>map,pos:id=>{const d=DISP.get(id);return d?d.p:null;},home:()=>home,homeObl:()=>homeObl(),now:()=>Date.now()/1000+offset,src:k=>(SNAP&&SNAP.sources&&SNAP.sources[k]?.name)||k};
try{home=JSON.parse(localStorage.getItem('home')||'null');}catch(e){}
const DISP=new Map();
const PREFL=()=>{try{return Object.assign({launch:true},JSON.parse(localStorage.getItem('pref')||'{}'));}catch(e){return {launch:true};}};
const isBal=tr=>tr.type==='ballistic'||tr.type==='banderol';// 04.11 власник: Бандероль веде себе як балістика (без траєкторії й відліку)
const TYPES_KMH=t=>({shahed:170,jet:450,molniya:120,cruise:800,ballistic:2000,kab:600})[t]||200;

/* ---------- карта ---------- */
const ESRI='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
let CFG={vectorStyle:'https://tiles.openfreemap.org/styles/liberty'};
const INTRO=!sessionStorage.getItem('intro');
/* ---------- без WebGL карта не стартує: текстовий режим замість вічної заставки (аудит 02.11) ---------- */
const hasGL=(()=>{try{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl'));}catch(e){return false;}})();
if(!hasGL||!window.maplibregl){liteMode();return;}
// запобіжник: якщо за 15 с мапа так і не отримала даних (помилка в коді, старий index у кеші телефона тощо),
// показуємо текстовий режим із тими самими даними, а не вічне «Підключення…»
window.addEventListener('error',e=>{(window.__errs=window.__errs||[]).push(String(e.message||e));});
setTimeout(()=>{if(!window.__snapOK&&!document.getElementById('lite'))liteMode(true);},15000);
function liteMode(fallback){
  const ix=document.getElementById('intro');if(ix)ix.remove();document.body.classList.remove('intro');
  const el=document.createElement('div');el.id='lite';document.body.appendChild(el);
  const st=document.createElement('style');st.textContent='#lite{position:fixed;inset:0;overflow:auto;background:#07090E;color:#E8ECF4;font:15px/1.45 system-ui,sans-serif;padding:16px;z-index:9999}#lite h1{font-size:20px;margin:0 0 4px}#lite .n{color:#9AA4B8;font-size:13px}#lite h2{font-size:15px;margin:18px 0 6px;color:#fff}#lite li{margin:3px 0}#lite .on{color:#ff6b6b}#lite button{margin-top:8px;padding:8px 14px;border-radius:10px;border:1px solid #2B6BFF;background:#13224A;color:#fff;font:inherit}';document.head.appendChild(st);
  const N=window.TYPE_NAME||{};const e=x=>String(x??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const hm=t=>new Date(t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  let last=0;
  const draw=s=>{last=Date.now();const now=s.now;const O=s.official||{};const obl=Object.keys(s.levels||{}).sort();const part=(O.alert_obl||[]).filter(o=>!obl.includes(o));
    const act=(s.tracks||[]).filter(t=>t.status==='active').sort((a,b)=>b.last-a.last);
    el.innerHTML='<h1>NAVRYX SKY · текстовий режим</h1><div class=n>'+(fallback?'Карта не змогла отримати дані (збій оновлення). Дані ті самі, наживо':'Карта не запускається на цьому пристрої (немає WebGL / графічного прискорення). Дані ті самі, наживо')+'. Станом на '+hm(now)+'.</div>'+
      '<h2>Офіційні тривоги</h2>'+(obl.length?'<ul>'+obl.map(o=>'<li class=on>'+e(o)+' обл., уся область</li>').join('')+'</ul>':'<div class=n>Тривог на всю область немає.</div>')+
      (part.length?'<div class=n>Тривога в частині області: '+part.map(e).join(', ')+'</div>':'')+
      '<h2>Цілі за повідомленнями моніторів ('+act.length+')</h2>'+(act.length?'<ul>'+act.slice(0,60).map(t=>'<li><b>'+e(N[t.type]||t.type)+(t.count>1?' ×'+t.count:'')+'</b>'+(t.next?' → '+e(t.next):'')+' <span class=n>· '+Math.max(0,Math.round((now-t.last)/60))+' хв тому · '+(t.conf>=0.5?'підтверджено':'непідтверджено')+'</span></li>').join('')+'</ul>':'<div class=n>Активних цілей немає. Це не відбій, орієнтуйтеся на офіційні сигнали.</div>')+
      '<button onclick="location.reload()">Спробувати карту ще раз</button>';};
  const poll=()=>fetch('/api/state',{cache:'no-store'}).then(r=>r.json()).then(draw).catch(()=>{el.innerHTML='<h1>NAVRYX SKY</h1><div class=n>Немає звʼязку з сервером. Це не відбій.</div>';});
  try{const ws=new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws');ws.onmessage=m=>{try{draw(JSON.parse(m.data));}catch(x){}};}catch(x){}
  poll();setInterval(()=>{if(Date.now()-last>25000)poll();},15000);}
// старт (03.11, ревізія візуалу): кадр 0 — 2D, північ угорі, вся Україна по центру екрана; перехід у 3D — коли прийдуть цілі (introFly).
// повторний запуск протягом 5 хв — камера там, де її закрили, без прольоту
const UA_BOUNDS=[[22.1,44.2],[40.3,52.45]];
const REDUCE=(()=>{try{return matchMedia('(prefers-reduced-motion: reduce)').matches;}catch(e){return false;}})();
const LASTCAM=null; // 03.11: старт завжди однаковий (2D по центру → 3D), без «там, де закрили»
let map;try{map=new maplibregl.Map({container:'map',pixelRatio:Math.min(window.devicePixelRatio||1,3),fadeDuration:150,maxTileCacheSize:200,style:{version:8,sources:{},layers:[{id:'bg',type:'background',paint:{'background-color':'#03050A'}}]},center:LASTCAM?LASTCAM.c:[31.2,48.4],zoom:LASTCAM?LASTCAM.z:(innerWidth<640?3.9:5.2),pitch:LASTCAM?LASTCAM.p:0,bearing:0,attributionControl:{compact:true},maxPitch:65,minZoom:2.8,maxBounds:[[2,28],[62,74]]});}catch(err){console.warn('map init',err);liteMode();return;}window.tryvogaMap=map;
// центр країни між верхніми плашками й нижньою панеллю; цю ж камеру тримає й перехід у 3D (03.11: «не по центру» — камера їхала на дім, Харків біля краю)
let START_CAM=null,introDone=false;
// Україна у верхній половині екрана (відступ знизу більший: там панель дому й док); перераховуємо після load/resize,
// бо на телефоні розмір вікна в момент створення мапи ще не остаточний (03.11: мапа сиділа внизу)
// масштаб «вся Україна по ширині екрана» (як на еталонному скріні): ≈3,86 на телефоні шириною 390; на великих екранах обмежує висота
function uaZoom(){return Math.min(Math.log2((innerWidth-20)/25.4),Math.log2(Math.max(200,innerHeight-260)/18.4));}
function fitStart(){if(introDone)return;try{if(localStorage.getItem('mode_tac')==='1'){const cm={center:[31.5,48.5],zoom:uaZoom()};START_CAM=cm;map.jumpTo({...cm,pitch:0,bearing:0});return;}const c=map.cameraForBounds(UA_BOUNDS,{padding:{top:Math.round(innerHeight*0.09),bottom:Math.round(innerHeight*0.33),left:10,right:10}});if(c){START_CAM={center:c.center,zoom:c.zoom};map.jumpTo({center:c.center,zoom:c.zoom,pitch:0,bearing:0});}}catch(e){}}
fitStart();map.once('load',fitStart);window.addEventListener('resize',fitStart);
map.on('moveend',()=>{try{const c=map.getCenter();localStorage.setItem('cam_last',JSON.stringify({c:[c.lng,c.lat],z:map.getZoom(),p:map.getPitch(),t:Date.now()}));}catch(e){}});
// спливаючі вікна на мапі завжди цілком на екрані: після відкриття зсуваємо мапу, якщо вікно вилазить за край (03.11: «обрізає вікно»)
try{const _add=maplibregl.Popup.prototype.addTo;maplibregl.Popup.prototype.addTo=function(m){const r=_add.call(this,m);const pp=this;
  setTimeout(()=>{try{const el=pp.getElement();if(!el)return;const b=el.getBoundingClientRect(),pad=10,top=(document.querySelector('header.top')||{getBoundingClientRect:()=>({bottom:0})}).getBoundingClientRect().bottom+6;
    let dx=0,dy=0;if(b.right>innerWidth-pad)dx=b.right-innerWidth+pad;if(b.left-dx<pad)dx=b.left-pad;if(b.top<top)dy=b.top-top;
    if(dx||dy)m.panBy([dx,dy],{duration:350});}catch(e){}},60);return r;};}catch(e){}
let TACHL=null;let MEAS={on:false,pts:[]},ENEMY=null,ENEMY_SET=false;const TACF=(()=>{try{return Object.assign({hide:[],fresh:0,src:'',alerts:true,scale:'',enemy:true,reach:true},JSON.parse(localStorage.getItem('tac_f')||'{}'));}catch(e){return {hide:[],fresh:0,src:'',alerts:true,scale:'',enemy:true,reach:true};}})();
const tacSave=()=>{try{localStorage.setItem('tac_f',JSON.stringify(TACF));}catch(e){}};
function tacOK(tr,serverT){if(sel===tr.id)return true;if(TACF.hide.includes(tr.type))return false;
  if(TACF.fresh){const a=((tr.ev&&tr.ev.age)||0)+Math.max(0,serverT-SNAP.now);if(a>TACF.fresh*60)return false;}
  if(TACF.src){const P=(tr.ev&&tr.ev.prim&&tr.ev.prim.length?tr.ev.prim:tr.srcs)||[];if(!P.includes(TACF.src))return false;}return true;}
let TAC=false;try{TAC=localStorage.getItem('mode_tac')==='1';}catch(e){}window.FXTAC=TAC;
async function styleFor(kind){
  const vec=await fetch(CFG.vectorStyle).then(r=>r.json());
  // підписи українською: name:uk → name (OSM) замість латиниці
  const UK=['coalesce',['get','name:uk'],['get','name']];
  vec.layers.forEach(l=>{if(l.type==='symbol'&&l.layout&&l.layout['text-field']&&JSON.stringify(l.layout['text-field']).includes('name'))l.layout['text-field']=UK;});
  if(kind==='tac'||kind==='tacl'){// тактична основа: «світла» (день) або «нічна» (темна) за темою застосунку; приглушені дороги й рельєф, чіткі назви
    const LT=kind==='tacl',P=LT?{bg:'#E9EEF4',land:'#F4F6FA',park:'#EEF1F6',water:'#CADCEA',wway:'#BBD0E2',bnd:'#9AA6B8',road:'#D5DBE5',txt:'#1B2433',ctry:'#5B6678',halo:'#FFFFFF'}
      :{bg:'#0E1521',land:'#1B2639',park:'#1A2436',water:'#0C121B',wway:'#0F1722',bnd:'#4A5B76',road:'#2B384D',txt:'#E3E9F3',ctry:'#8FA0B8',halo:'#0A0F17'};
    const L=[];for(const l0 of vec.layers){const l=JSON.parse(JSON.stringify(l0));l.paint=l.paint||{};
      if(l.type==='background'){l.paint['background-color']=P.bg;L.push(l);}
      else if(l.type==='fill'){if(/building|housenumber/.test(l.id))continue;const w=/water/.test(l.id);l.paint['fill-color']=w?P.water:/park|wood|forest|grass|landcover|landuse/.test(l.id)?P.park:P.land;delete l.paint['fill-pattern'];l.paint['fill-opacity']=1;L.push(l);}
      else if(l.type==='line'){if(/bridge_|tunnel_|aeroway|rail|ferry|path|track|service|minor/.test(l.id)&&!/major|trunk|motorway|primary/.test(l.id))continue;
        const b=/boundary/.test(l.id),w=/waterway|river|stream/.test(l.id);l.paint['line-color']=b?P.bnd:w?P.wway:P.road;l.paint['line-opacity']=b?0.85:0.9;delete l.paint['line-dasharray'];if(b)l.paint['line-dasharray']=[3,2];L.push(l);}
      else if(l.type==='symbol'){if(!/place|city|town|village|suburb|state|country|island/.test(l.id)||/road|poi|housenumber|ref/.test(l.id))continue;
        l.paint['text-color']=/state|country/.test(l.id)?P.ctry:P.txt;l.paint['text-halo-color']=P.halo;l.paint['text-halo-width']=1.6;L.push(l);}
    }
    vec.layers=L;return vec;}
  if(kind==='map')return vec;
  const NIGHT=kind==='night';
  // супутник + підписи й дороги з векторної карти
  const keep=vec.layers.filter(l=>l.type==='symbol'||/boundary|road_(trunk|motorway|primary)|highway/.test(l.id)).map(l=>{
    const L=JSON.parse(JSON.stringify(l));
    if(L.type==='symbol'&&L.paint){L.paint['text-color']=NIGHT?'#E9EEF7':'#FFFFFF';L.paint['text-halo-color']='rgba(0,0,0,.9)';L.paint['text-halo-width']=1.6;}
    if(L.type==='line'&&L.paint){L.paint['line-opacity']=NIGHT?0.22:0.55;if(NIGHT&&/road|highway/.test(L.id))L.paint['line-color']='#D99A45';}
    return L;});
  const out={version:8,glyphs:vec.glyphs,sources:{...vec.sources,esri:{type:'raster',tiles:[ESRI],tileSize:256,maxzoom:19,attribution:'© Esri, Maxar, Earthstar Geographics'}},
    layers:[{id:'bg',type:'background',paint:{'background-color':'#03050A'}},
      {id:'esri',type:'raster',source:'esri',paint:NIGHT?{'raster-saturation':-0.15,'raster-brightness-max':['interpolate',['linear'],['zoom'],4,0.62,7,0.6,10,0.62,13,0.7],'raster-brightness-min':0.02,'raster-contrast':0.08,'raster-opacity':1}:{'raster-saturation':-0.1,'raster-brightness-max':0.9}},
      ...(NIGHT?[{id:'lights',type:'raster',source:'lights',maxzoom:10,paint:{'raster-opacity':['interpolate',['linear'],['zoom'],4,0.22,7,0.15,9,0],'raster-saturation':-0.1,'raster-contrast':0.25,'raster-resampling':'linear'}}]:[]),...keep]};
  if(NIGHT){out.sources.lights={type:'raster',tiles:['https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png'],tileSize:256,maxzoom:8,attribution:'NASA Black Marble'};}
  out.sky={'sky-color':'#04060C','horizon-color':'#1B2A4A','fog-color':'#04060C','sky-horizon-blend':0.7,'horizon-fog-blend':0.85,'fog-ground-blend':0.35,'atmosphere-blend':['interpolate',['linear'],['zoom'],0,1,5,0.75,8,0.2]};
  if(vec.sprite)out.sprite=vec.sprite;return out;
}
function wantBase(th){return TAC?(PREF.tacSat?'sat':(th==='day'?'tacl':'tac')):(PREF.base&&PREF.base!=='tac'&&PREF.base!=='tacl'?PREF.base:(th==='night'?'night':'map'));}

/* ---------- тактична панель: масштаби й фільтри ---------- */
function oblBox(n){const f=(OBLF||[]).find(x=>x.properties.n===n);if(!f)return null;let a=[1e9,1e9,-1e9,-1e9];const w=c=>typeof c[0]==='number'?(a=[Math.min(a[0],c[0]),Math.min(a[1],c[1]),Math.max(a[2],c[0]),Math.max(a[3],c[1])]):c.forEach(w);w(f.geometry.coordinates);return a;}
function tacObl(n){TACF.obl=n||'';TACF.scale='oblast';tacSave();const b=n&&oblBox(n);if(b)map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:{top:170,bottom:120,left:30,right:60},duration:700,maxZoom:9});else tacScale('oblast');tacBarSync();}
function tacOblFill(){const sl=$('#tac-ob');if(!sl||sl.dataset.f||!OBLF)return;sl.dataset.f='1';OBLF.map(f=>f.properties.n).sort((a,b)=>a.localeCompare(b,'uk')).forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;sl.appendChild(o);});sl.value=TACF.obl||'';}
document.addEventListener('change',e=>{if(e.target&&e.target.id==='tac-ob')tacObl(e.target.value);});
function tacScale(v){TACF.scale=v;if(v!=='oblast')TACF.obl='';tacSave();const H=home||[31.5,49];
  if(v==='oblast'&&TACF.obl&&oblBox(TACF.obl)){const b=oblBox(TACF.obl);map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:{top:170,bottom:120,left:30,right:60},duration:700,maxZoom:9});}else if(v==='near')map.flyTo({center:H,zoom:9.6,duration:700});else if(v==='oblast')map.flyTo({center:H,zoom:7.2,duration:700});else map.flyTo({center:[31.5,48.5],zoom:uaZoom(),duration:700});
  const b=document.querySelector('#rad-scope button[data-v="'+({near:'near',oblast:'oblast',country:'country'}[v])+'"]');if(b)b.click();// озвучення радіо змінюється разом із масштабом
  tacBarSync();}
function tacBarSync(){const bar=$('#tac-bar');if(!bar)return;bar.hidden=!TAC;setTimeout(()=>tacPad(true),60);tacOblFill();const so=$('#tac-ob');if(so)so.value=TACF.obl||'';bar.querySelectorAll('[data-sc]').forEach(b=>b.classList.toggle('on',b.dataset.sc===TACF.scale));
  const n=TACF.hide.length+(TACF.fresh?1:0)+(TACF.src?1:0)+(TACF.alerts?0:1)+(TACF.enemy?0:1)+(TACF.reach?0:1);const f=$('#tac-f');if(f)f.textContent='Фільтри'+(n?' · '+n:'');}
// у тактичному режимі центр мапи — вільна зона між верхньою панеллю й нижньою докою
function tacPad(anim){try{if(window.__padLock)return;let t=0,b=0;if(TAC){const bar=$('#tac-bar');if(bar&&!bar.hidden){let y=0,e=bar;while(e&&e!==document.body){y+=e.offsetTop;e=e.offsetParent;}t=Math.max(0,Math.round(y+bar.offsetHeight-(map.getContainer().getBoundingClientRect().top||0)));}b=96;}
  const o={top:t,bottom:b,left:0,right:0},c=map.getPadding();if(Math.abs(c.top-o.top)<2&&Math.abs(c.bottom-o.bottom)<2)return;
  if(anim&&window.__introAt&&Date.now()-window.__introAt>7000)map.easeTo({padding:o,duration:450});else map.setPadding(o);}catch(e){}}
window.addEventListener('resize',()=>tacPad(false));
function tacPanelTop(){const b=$('#tac-bar');if(b)document.documentElement.style.setProperty('--tac-top',Math.round(b.getBoundingClientRect().bottom+6)+'px');}
function tacFilterPanel(){const pn=$('#tac-flt');if(!pn)return;tacPanelTop();if(!pn.hidden){pn.hidden=true;return;}
  const types=[...new Set((SNAP&&SNAP.tracks||[]).filter(t=>t.status==='active').map(t=>t.type))];const srcs=new Map();
  for(const t of (SNAP&&SNAP.tracks||[]).filter(t=>t.status==='active'))for(const k of ((t.ev&&t.ev.prim&&t.ev.prim.length?t.ev.prim:t.srcs)||[]))srcs.set(k,(SNAP.sources[k]&&SNAP.sources[k].name)||k);
  const chip=(a,on,l)=>'<button class="tc'+(on?' on':'')+'" '+a+'>'+esc(l)+'</button>';
  pn.innerHTML='<h5>Типи цілей</h5><div>'+types.map(t=>chip('data-ty="'+t+'"',!TACF.hide.includes(t),TYPE_NAME[t]||t)).join('')+'</div>'+
    '<h5>Свіжість</h5><div>'+[[0,'Усі'],[10,'до 10 хв'],[30,'до 30 хв'],[60,'до години']].map(x=>chip('data-fr="'+x[0]+'"',TACF.fresh===x[0],x[1])).join('')+'</div>'+
    '<h5>Джерело</h5><div>'+chip('data-sr=""',!TACF.src,'Усі')+[...srcs].map(x=>chip('data-sr="'+esc(x[0])+'"',TACF.src===x[0],x[1])).join('')+'</div>'+
    '<h5>Офіційні тривоги</h5><div>'+chip('data-al="1"',TACF.alerts,'Показувати')+chip('data-al="0"',!TACF.alerts,'Сховати')+'</div>'+'<h5>Позначки ворога (OpenStreetMap)</h5><div>'+chip('data-en="1"',TACF.enemy,'Показувати')+chip('data-en="0"',!TACF.enemy,'Сховати')+'</div>'+'<h5>Радіуси досяжності вибраної цілі</h5><div>'+chip('data-rc="1"',TACF.reach,'Показувати')+chip('data-rc="0"',!TACF.reach,'Сховати')+'</div>';pn.hidden=false;}
document.addEventListener('click',e=>{const b=e.target.closest('#tac-bar [data-sc],#tac-flt .tc,#tac-f,#tac-lg,#tac-ms');if(!b)return;if(b.id==='tac-ms')return measToggle();if(b.id==='tac-lg')return tacLegend();
  if(b.dataset.sc)return tacScale(b.dataset.sc);if(b.id==='tac-f')return tacFilterPanel();
  if(b.dataset.ty){const i=TACF.hide.indexOf(b.dataset.ty);if(i>=0)TACF.hide.splice(i,1);else TACF.hide.push(b.dataset.ty);}
  else if(b.dataset.fr!=null)TACF.fresh=+b.dataset.fr;else if(b.dataset.sr!=null)TACF.src=b.dataset.sr;else if(b.dataset.al!=null)TACF.alerts=b.dataset.al==='1';else if(b.dataset.en!=null)TACF.enemy=b.dataset.en==='1';else if(b.dataset.rc!=null)TACF.reach=b.dataset.rc==='1';
  tacSave();applyLayers();tacBarSync();$('#tac-flt').hidden=true;tacFilterPanel();});

/* ---------- тактичні символи NATO APP-6(E): єдиний генератор web/app06.js, малює milsymbol ---------- */
function loadApp06(){return window.__a6||(window.__a6=new Promise(res=>{const a=document.createElement('script');a.src='/vendor/milsymbol.js';
  a.onload=()=>{const b=document.createElement('script');b.src='/app06.js';b.onload=()=>res(window.App06||null);b.onerror=()=>res(null);document.head.appendChild(b);};a.onerror=()=>res(null);document.head.appendChild(a);}));}
const SYMP=new Set();
// вертикальна колонка значків цілей справа (замість блоку «Мій дім»): щільно, найновіші зверху
function tacRail(L){return;const el=$('#tac-rail');if(!el)return;const A=window.App06;if(!TAC||!A||!L.length){el.hidden=true;return;}
  L=L.sort((a,b)=>a.m-b.m).slice(0,14);const k=L.map(x=>x.id+x.aff+x.type+x.n+x.m+(sel===x.id?'*':'')).join('|');if(el.dataset.k===k)return;el.dataset.k=k;
  el.innerHTML=L.map(x=>{let v='';try{v=A.svg({type:x.type,affiliation:x.aff,hd:null,count:x.n>1?x.n:undefined,size:30});}catch(e){}return '<button data-id="'+x.id+'"'+(sel===x.id?' class="on"':'')+' aria-label="Ціль">'+v+'<i>'+(x.m<1?'<1':x.m)+'</i></button>';}).join('');el.hidden=false;}
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('#tac-rail button');if(b)openSheet(b.dataset.id);});
// світла тактична тема (день): темний текст і лінії на світлій основі
function tacPaint(){try{const day=TAC&&!PREF.tacSat&&effTheme()==='day',tx=day?'#1B2433':'#E6EBF2',hl=day?'rgba(255,255,255,.95)':'rgba(10,12,16,.92)';
  const T=(id,c,h)=>{if(map.getLayer(id)){map.setPaintProperty(id,'text-color',c);map.setPaintProperty(id,'text-halo-color',h);}};
  T('tac-age',tx,hl);T('enemy-sym',tx,hl);T('reach-t',tx,hl);T('meas-t',day?'#1B2433':'#FFFFFF',hl);
  if(map.getLayer('reach-l'))map.setPaintProperty('reach-l','line-color',day?'#33425A':'#E6EBF2');
  if(map.getLayer('meas-l'))map.setPaintProperty('meas-l','line-color',day?'#1B2433':'#FFFFFF');
  if(map.getLayer('meas-p')){map.setPaintProperty('meas-p','circle-color',day?'#FFFFFF':'#14171C');map.setPaintProperty('meas-p','circle-stroke-color',day?'#1B2433':'#FFFFFF');}}catch(e){}}
function tacImg(spec){const A=window.App06;if(!A)return null;const b=A.build(spec);if(map.hasImage(b.key)||SYMP.has(b.key))return b.key;SYMP.add(b.key);
  try{const y=A.symbol(spec),an=y.getAnchor(),sz=y.getSize(),W=Math.ceil(2*Math.max(an.x,sz.width-an.x)),H=Math.ceil(2*Math.max(an.y,sz.height-an.y));// рамка завжди в центрі зображення, тож стоїть точно на координаті
    const im=new Image();im.onload=()=>{try{const c=document.createElement('canvas');c.width=W*2;c.height=H*2;const g=c.getContext('2d');g.drawImage(im,(W/2-an.x)*2,(H/2-an.y)*2,sz.width*2,sz.height*2);
      if(!map.hasImage(b.key))map.addImage(b.key,g.getImageData(0,0,c.width,c.height),{pixelRatio:2});}catch(e){}};
    im.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(y.asSVG());}catch(e){}
  return b.key;}
// належність цілі за даними (кількість незалежних джерел, достовірність, ШІ), не за виглядом
function tacAff(tr){const A=window.App06;return A?A.affiliationOf({indep:tr.n_indep!=null?tr.n_indep:((tr.ev&&tr.ev.prim)||[]).length,idLvl:tr.id_lvl,ai:tr.ai}):'suspect';}
function tacLegend(){const pn=$('#tac-legend'),A=window.App06;if(!pn)return;tacPanelTop();if(!pn.hidden){pn.hidden=true;return;}
  if(!A){pn.innerHTML='<p>Бібліотеку символів ще не завантажено. Спробуйте за мить.</p>';pn.hidden=false;loadApp06().then(()=>{if(!pn.hidden){pn.hidden=true;tacLegend();}});return;}
  const sv=(spec,m)=>{try{return A.svg(Object.assign({size:26,mono:m},spec));}catch(e){return '';}};
  const row=(spec,t,d)=>'<div class="lg-r"><span class="lg-s">'+sv(spec,false)+'</span><span class="lg-s">'+sv(spec,true)+'</span><span><b>'+esc(t)+'</b><small>'+esc(d)+'</small></span></div>';
  const used=new Map();for(const t of (SNAP&&SNAP.tracks||[]).filter(t=>t.status==='active'))used.set(t.type,tacAff(t));for(const g of (SNAP&&SNAP.strat||[]))used.set(g.icon,A.affiliationOf({indep:(g.srcs||[]).length}));
  let h='<h5>Умовні знаки</h5><p class="lg-n">Зліва колір, поруч той самий символ без кольору: належність видно за формою рамки.</p><h5>Належність (рамка)</h5>';
  h+=A.affiliations().filter(a=>a.aff==='hostile').map(a=>row({type:'unknown',affiliation:a.aff},a.ua+' · '+a.name,'усі цілі над Україною, незалежно від кількості джерел')).join('');
  h+='<h5>Типи на мапі зараз</h5>'+([...used].length?[...used].map(([t,a])=>{const e=A.entryOf(t);return row({type:t,affiliation:a},(A.MODEL[t]||t),e.std+(e.exact?'':' (найближча сутність)'));}).join(''):'<p class="lg-n">Активних цілей немає.</p>');
  h+='<h5>Поля символу</h5>'+row({type:'tu95',affiliation:'hostile',hd:60,count:4},'Напрямок і кількість','лінія від рамки: напрямок руху, лише коли відомий; число: кількість');
  h+='<h5>Поля SKY (не частина символу)</h5><p class="lg-n">«N хв»: вік повідомлення. Біла точка: назване місце. Пунктир і коло: оцінка SKY. Блідість: давність, а не знищення. Рамка й знак не змінюються від давності, оцінки чи невідомого типу.</p>';
  h+='<h5>Інше на мапі</h5><p class="lg-n">Позначки ворога: аеродроми з OpenStreetMap (ODbL), позначка — стандартний знак аеродрому. Кола 30 і 60 хв: найбільша відстань за швидкістю цілі, розрахунок SKY, а не прогноз маршруту. Лінійка: відстань у км і NM та істинний азимут.</p><p class="lg-n"><b>Дані з відкритих джерел</b>: надходять із затримкою, можуть бути неповними чи помилковими. Відсутність позначки не означає відсутності загрози.</p>';h+='<p class="lg-n">Координати: WGS-84, система цілевказання MGRS (сітка UTM). Масштабні лінійки в км і морських милях (NM). Точність MGRS відповідає точності місця: ≥10 км — 10 км, ≥1 км — 1 км, краще — 100 м.</p><p class="lg-n">Знаки малює milsymbol 3.0.5 (MIT).</p>';pn.innerHTML=h;pn.hidden=false;}
// лінійний масштаб у кілометрах і морських милях
function tacScaleBars(){try{if(TAC&&!map._tacScale){map._tacScale=[new maplibregl.ScaleControl({unit:'metric',maxWidth:90}),new maplibregl.ScaleControl({unit:'nautical',maxWidth:90})];map._tacScale.forEach(c=>map.addControl(c,'bottom-left'));}
  else if(!TAC&&map._tacScale){map._tacScale.forEach(c=>map.removeControl(c));map._tacScale=null;}}catch(e){}}

/* ---------- лінійка, радіуси досяжності, позначки ворога (DeepState) ---------- */
const hav=(a,b)=>{const R=6371.0088,r=Math.PI/180,dl=(b[1]-a[1])*r,dn=(b[0]-a[0])*r,x=Math.sin(dl/2)**2+Math.cos(a[1]*r)*Math.cos(b[1]*r)*Math.sin(dn/2)**2;return 2*R*Math.asin(Math.sqrt(x));};
const brgTrue=(a,b)=>{const r=Math.PI/180,y=Math.sin((b[0]-a[0])*r)*Math.cos(b[1]*r),x=Math.cos(a[1]*r)*Math.sin(b[1]*r)-Math.sin(a[1]*r)*Math.cos(b[1]*r)*Math.cos((b[0]-a[0])*r);return (Math.atan2(y,x)/r+360)%360;};
const dest=(p,az,km)=>{const r=Math.PI/180,d=km/6371.0088,la=p[1]*r,lo=p[0]*r,b=az*r,la2=Math.asin(Math.sin(la)*Math.cos(d)+Math.cos(la)*Math.sin(d)*Math.cos(b)),lo2=lo+Math.atan2(Math.sin(b)*Math.sin(d)*Math.cos(la),Math.cos(d)-Math.sin(la)*Math.sin(la2));return [lo2/r,la2/r];};
const f1=v=>(Math.round(v*10)/10).toFixed(1).replace('.',',');
function measDraw(){if(!map.getSource('meas'))return;const F=[],P=MEAS.pts;let tot=0;
  P.forEach(p=>F.push({type:'Feature',properties:{k:'p'},geometry:{type:'Point',coordinates:p}}));
  if(P.length>1)F.push({type:'Feature',properties:{k:'l'},geometry:{type:'LineString',coordinates:P}});
  for(let i=1;i<P.length;i++){const km=hav(P[i-1],P[i]);tot+=km;const mid=[(P[i-1][0]+P[i][0])/2,(P[i-1][1]+P[i][1])/2];
    F.push({type:'Feature',properties:{k:'t',l:f1(km)+' км · '+f1(km/1.852)+' NM · '+Math.round(brgTrue(P[i-1],P[i]))+'°'},geometry:{type:'Point',coordinates:mid}});}
  if(P.length>2)F.push({type:'Feature',properties:{k:'t',l:'Разом '+f1(tot)+' км · '+f1(tot/1.852)+' NM'},geometry:{type:'Point',coordinates:P[P.length-1]}});
  map.getSource('meas').setData({type:'FeatureCollection',features:F});}
function measToggle(){if(!MEAS.on){MEAS.on=true;MEAS.pts=[];toast('Лінійка: торкайтеся точок на мапі. Ще раз кнопка: очистити');}else{MEAS.on=false;MEAS.pts=[];}
  measDraw();const b=$('#tac-ms');if(b)b.classList.toggle('on',MEAS.on);map.getCanvas().style.cursor=MEAS.on?'crosshair':'';}
// найбільша відстань, яку ціль могла б подолати за 30 і 60 хв за своєю швидкістю: розрахунок SKY, не прогноз маршруту
function reachData(serverT){if(!TAC||!TACF.reach||!sel)return EMPTY;const tr=SNAP.tracks.find(t=>t.id===sel),d=DISP.get(sel);if(!tr||!d||tr.status!=='active'||isBal(tr))return EMPTY;
  const v=tr.speed||TYPES_KMH(tr.type),F=[];for(const m of [30,60]){const R=Math.min(900,v*m/60);if(!(R>1))continue;const ring=[];for(let a=0;a<=360;a+=5)ring.push(dest(d.p,a,R));
    F.push({type:'Feature',properties:{k:'f'},geometry:{type:'Polygon',coordinates:[ring]}});F.push({type:'Feature',properties:{k:'l'},geometry:{type:'LineString',coordinates:ring}});
    F.push({type:'Feature',properties:{k:'t',l:m+' хв ≈ '+Math.round(R)+' км · розрахунок'},geometry:{type:'Point',coordinates:ring[0]}});}
  return {type:'FeatureCollection',features:F};}
const ENEMY_TYPE={airfield:'enemy_airfield',hq:'enemy_hq'};
function enemyLoad(){if(ENEMY!==null)return;ENEMY=[];loadApp06().then(A=>{if(!A)return;fetch('/data/enemy_objects.geojson',{cache:'no-cache'}).then(r=>r.json()).then(j=>{ENEMY=(j.features||[]);ENEMY_SET=false;}).catch(()=>{ENEMY=null;});});}
async function afldIcon(){if(map.hasImage('afld'))return;try{const r=await fetch('/sprites/afld.png'),b=await createImageBitmap(await r.blob());if(!map.hasImage('afld'))map.addImage('afld',b,{pixelRatio:4});}catch(e){}}
function enemyApply(){afldIcon();if(!window.App06||!ENEMY||!map.getSource('enemy'))return;
  const nowS=Date.now()/1000+offset,Ls=(PREFL().launch?(SNAP&&SNAP.launches)||[]:[]).filter(L=>nowS-L.t<3*3600);
  const nearL=(f,sec)=>Ls.some(L=>nowS-L.t<sec&&hav([L.lon,L.lat],f.geometry.coordinates)<15);
  let list,key;
  if(TAC){// тактичний режим: усі ключові аеродроми; поруч із активним пуском приглушуємо значок, щоб не дублювати позначку пуску
    list=ENEMY.map(f=>({f,dim:nearL(f,3*3600)?1:0,hot:0}));key='t'+list.map(x=>x.dim).join('');}
  else{// звичайний режим: аеродроми приховані; підсвічуємо лише в момент пуску й 30 хвилин після
    list=ENEMY.filter(f=>f.properties.c==='airfield'&&nearL(f,1800)).map(f=>({f,dim:0,hot:1}));key='n'+list.map(x=>x.f.properties.n).join('|');}
  if(ENEMY_SET&&enemyApply.k===key)return;enemyApply.k=key;
  map.getSource('enemy').setData({type:'FeatureCollection',features:list.map(({f,dim,hot})=>({type:'Feature',geometry:f.geometry,properties:Object.assign({},f.properties,{img:(!TAC&&f.properties.c==='airfield')?'afld':tacImg({type:ENEMY_TYPE[f.properties.c]||'enemy_object',affiliation:'hostile'}),v:dim?'':f.properties.n,dim,hot})}))});ENEMY_SET=true;}
// тактичний режим тільки 2D: нахил вимкнено і заблоковано; після виходу повертаємо те, що було
let TILT_BEFORE=null;
function tac2d(on){try{if(on){if(!TACF.scale&&!TACF.obl)setTimeout(()=>tacScale('country'),500);if(TILT_BEFORE===null)TILT_BEFORE=tilt;if(tilt)set3d(false,true);map.setMaxPitch(0);map.easeTo({pitch:0,bearing:0,duration:400});}
  else{map.setMaxPitch(map._mp0||60);if(TILT_BEFORE){set3d(true,true);}TILT_BEFORE=null;}}catch(e){}}
function setTac(on){const was=TAC;TAC=!!on;if(TAC!==was)tac2d(TAC);ENEMY_SET=false;try{if(SNAP)renderCounters();}catch(e){}window.FXTAC=TAC;document.body.classList.toggle('tac',TAC);enemyLoad();if(TAC){loadApp06();}if(!TAC&&$('#tac-legend'))$('#tac-legend').hidden=true;tacScaleBars();try{localStorage.setItem('mode_tac',TAC?'1':'0');}catch(e){}document.body.classList.toggle('tac',TAC);tacBarSync();
  setBase(wantBase(effTheme()));setTimeout(()=>{syncSettingsUI();applyLayers();tacBarSync();},80);if(!TAC&&$('#tac-flt'))$('#tac-flt').hidden=true;toast(TAC?'Тактична мапа':'Звичайна мапа');}
async function setBase(kind){SYMP.clear();ENEMY_SET=false;base=kind;localStorage.setItem('base2',kind);map.setStyle(await styleFor(kind),{diff:false});}

function addImages(){
  // реалістичні спрайти цілей (вид згори, ніс на північ) + тіні
  for(const t of Object.keys(TYPE_COLOR))for(const v of ['','-d','-sh']){const id='t-'+t+v;if(map.hasImage(id))continue;
    map.loadImage('sprites/t-'+t+v+'.png?v=ref17').then(r=>{if(!map.hasImage(id))map.addImage(id,r.data,{pixelRatio:Math.max(1,r.data.width/80)});})/*розмір ~80 px незалежно від файлу*/.catch(()=>{const c=drawTarget(t,44,{dim:v==='-d'});if(!map.hasImage(id))map.addImage(id,c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});});}
  if(!map.hasImage('home')){const c=drawHome(40);map.addImage('home',c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});}
  if(!map.hasImage('chip')){const s=48,c=document.createElement('canvas');c.width=c.height=s;const x=c.getContext('2d');x.fillStyle='rgba(12,15,22,.9)';x.beginPath();x.roundRect(2,2,s-4,s-4,22);x.fill();x.lineWidth=2;x.strokeStyle='rgba(255,255,255,.35)';x.stroke();map.addImage('chip',x.getImageData(0,0,s,s),{pixelRatio:2,stretchX:[[14,34]],stretchY:[[14,34]],content:[10,8,38,40]});}
}
const EMPTY={type:'FeatureCollection',features:[]};
// біжучі штрихи (ant path): зсув візерунка кроками, бо MapLibre не має dash-offset
const FLOW_DASH=[[0,4,3],[0.5,4,2.5],[1,4,2],[1.5,4,1.5],[2,4,1],[2.5,4,0.5],[3,4,0],[0,0.5,3,3.5],[0,1,3,3],[0,1.5,3,2.5],[0,2,3,2],[0,2.5,3,1.5],[0,3,3,1],[0,3.5,3,0.5]];
function addRelief(){
  // об'єм: рельєф (висоти Terrarium/AWS) + тіньовий відмив + 3D-будівлі в містах
  try{
    if(!map.getSource('dem-hs'))map.addSource('dem-hs',{type:'raster-dem',tiles:['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],encoding:'terrarium',tileSize:256,maxzoom:12,attribution:'Рельєф: Mapzen/AWS Terrain'});
    const firstSym=(map.getStyle().layers.find(l=>l.type==='symbol')||{}).id;
    const night=base!=='map'&&document.documentElement.dataset.theme!=='day';
    if(!map.getLayer('hillshade'))map.addLayer({id:'hillshade',type:'hillshade',source:'dem-hs',paint:{'hillshade-exaggeration':night?0.55:0.4,'hillshade-shadow-color':night?'#000000':'#3a3328','hillshade-highlight-color':night?'rgba(150,170,210,.35)':'#ffffff','hillshade-accent-color':night?'#05070c':'#5a4a36','hillshade-illumination-direction':315}},firstSym);
    const vs=Object.keys(map.getStyle().sources).find(k=>map.getStyle().sources[k].type==='vector');
    if(vs&&!map.getLayer('bld3d'))map.addLayer({id:'bld3d',type:'fill-extrusion',source:vs,'source-layer':'building',minzoom:12.5,
      paint:{// бетон/цегла: відтінок залежить від висоти (панельні багатоповерхівки світліші, приватний сектор тепліший)
        'fill-extrusion-color':night
          ?['interpolate',['linear'],['coalesce',['get','render_height'],8],3,'#4a4642',15,'#5b5955',40,'#6a6965',80,'#7a7b7d']
          :['interpolate',['linear'],['coalesce',['get','render_height'],8],3,'#cbbfae',15,'#d8d3cb',40,'#e2e1de',80,'#eceef0'],
        'fill-extrusion-height':['interpolate',['linear'],['zoom'],12.5,0,13.6,['coalesce',['get','render_height'],['get','height'],8]],
        'fill-extrusion-base':['coalesce',['get','render_min_height'],0],
        'fill-extrusion-opacity':1,'fill-extrusion-vertical-gradient':true}},firstSym);
    // освітлення як від низького сонця: чіткі затінені й освітлені грані
    try{map.setLight({anchor:'map',position:[1.35,210,35],color:night?'#fff1dc':'#fff3e0',intensity:night?0.42:0.55});}catch(e){}
  }catch(e){console.warn('relief',e);}
}
// Детально, лише Україна: дрібні підписи, дороги й будівлі за кордоном не малюємо (великі міста та країни лишаються)
let UAGEO=null;
function uaDetail(){
  const go=()=>{const st=map.getStyle();if(!st)return;const vs=Object.keys(st.sources).filter(k=>st.sources[k].type==='vector');
    const IN=['within',UAGEO];const KEEP=/country|continent|state|ocean|sea|water_name|marine/;
    st.layers.forEach(l=>{if(!vs.includes(l.source)||l._ua||KEEP.test(l.id))return;
      if(l.type!=='symbol'&&l.type!=='line'&&l.type!=='fill-extrusion')return;
      if(l.type==='fill-extrusion'){return;}  // будівлі, лише на великих масштабах, де й так Україна
      if(/boundary|admin/.test(l.id))return;
      let f=IN;if(/city|capital/.test(l.id))f=['any',IN,['<=',['coalesce',['get','rank'],99],3]];
      try{const old=map.getFilter(l.id);map.setFilter(l.id,old?['all',old,f]:f);}catch(e){}});};
  if(UAGEO)go();else fetch('/data/ua.geojson').then(r=>r.json()).then(g=>{UAGEO=g.geometry;go();}).catch(()=>{});}
function addOverlays(){
  addRelief();uaDetail();try{applySaver();}catch(e){}
  const st=map.getStyle();if(!st||!st.glyphs||map.getSource('obl'))return;
  addImages();
  const LV=['coalesce',['feature-state','lvl'],0];
  map.addSource('obl',{type:'geojson',data:'/data/oblasts.geojson',promoteId:'n'});
  map.addSource('ra',{type:'geojson',data:'/data/raions.geojson',generateId:true});
  map.addSource('occ',{type:'geojson',data:'/data/occupied.geojson',attribution:'Зона контролю: VIINA 2.0 (ODbL)'});
  if(!map.hasImage('hatch')){const c=document.createElement('canvas');c.width=c.height=16;const x=c.getContext('2d');x.strokeStyle='rgba(20,0,6,.55)';x.lineWidth=3;x.beginPath();x.moveTo(-4,20);x.lineTo(20,-4);x.moveTo(-4,4);x.lineTo(4,-4);x.moveTo(12,20);x.lineTo(20,12);x.stroke();map.addImage('hatch',x.getImageData(0,0,16,16),{pixelRatio:2});}
  map.addSource('sel',{type:'geojson',data:EMPTY});map.addSource('mepos',{type:'geojson',data:EMPTY});map.addSource('lpred',{type:'geojson',data:EMPTY});map.addSource('myplaces',{type:'geojson',data:EMPTY});
  map.addSource('ticks',{type:'geojson',data:EMPTY});
  map.addSource('holo',{type:'geojson',data:EMPTY});map.addSource('hrom',{type:'geojson',data:EMPTY});map.addSource('comets',{type:'geojson',data:EMPTY,lineMetrics:true});
  ['zones','trails','preds','targets','home','chains','lsites'].forEach(id=>map.addSource(id,{type:'geojson',data:EMPTY}));
  map.addLayer({id:'obl-fill',type:'fill',source:'obl',paint:{'fill-color':['match',LV,2,'#C8102E',1,'#E8B300','#000'],'fill-opacity':['match',LV,2,0.1,1,0.1,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-fill',type:'fill',source:'ra',paint:{'fill-color':['match',LV,2,'#B3122E',1,'#E0A800','#000'],'fill-opacity':['match',LV,2,0.16,1,0.1,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-line',type:'line',source:'ra',minzoom:5.5,paint:{'line-color':['match',LV,2,'#FF6B7D',1,'#FFC940','#fff'],'line-opacity':['interpolate',['linear'],['zoom'],5.5,['match',LV,0,0.2,0.9],9,['match',LV,0,0.5,0.9]],'line-width':['interpolate',['linear'],['zoom'],6,['match',LV,0,0.5,1.2],10,['match',LV,0,1.2,2.2]]}});
  // режим балістичної загрози: решта мапи спокійніша, названі області чіткі (без миготіння)
  map.addLayer({id:'bal-dim',type:'fill',source:'obl',layout:{visibility:'none'},paint:{'fill-color':'#000','fill-opacity':0.38}});
  map.addLayer({id:'bal-hl',type:'line',source:'obl',layout:{visibility:'none','line-join':'round'},paint:{'line-color':'#fff','line-width':['interpolate',['linear'],['zoom'],4,1.6,8,3],'line-opacity':0.95}});syncBalLayers.k=null;
  map.addLayer({id:'occ-fill',type:'fill',source:'occ',paint:{'fill-color':['match',['get','k'],'occupied','#2A0710','#3A3A3A'],'fill-opacity':['match',['get','k'],'occupied',0.5,0.3]}});
  map.addLayer({id:'occ-hatch',type:'fill',source:'occ',filter:['==',['get','k'],'occupied'],paint:{'fill-pattern':'hatch','fill-opacity':0.3}});
  map.addLayer({id:'occ-line',type:'line',source:'occ',filter:['==',['get','k'],'occupied'],paint:{'line-color':'#B24A5C','line-width':['interpolate',['linear'],['zoom'],5,1,9,2],'line-opacity':0.7}});
  map.addSource('outside',{type:'geojson',data:'/data/outside.geojson',tolerance:0.2,buffer:256});
  // напис навскіс, напівпрозоро, над територією РФ (у площині карти)
  map.addSource('rf-mark',{type:'geojson',data:{type:'FeatureCollection',features:[[39.2,53.6],[44.5,50.4],[36.2,56.9],[46.5,55.4]].map(c=>({type:'Feature',properties:{},geometry:{type:'Point',coordinates:c}}))}});map.addLayer({id:'outside',type:'fill',source:'outside',paint:{'fill-color':'#02040a','fill-opacity':['interpolate',['linear'],['zoom'],4,0.55,8,0.6]}});
  map.addLayer({id:'rf-mark',type:'symbol',source:'rf-mark',maxzoom:7.5,layout:{'text-field':'ДЕРЖАВА-ТЕРОРИСТ','text-font':['Noto Sans Bold'],
    'text-size':['interpolate',['exponential',1.6],['zoom'],3,11,5,22,7,38],'text-letter-spacing':0.18,'text-max-width':40,'text-rotate':-22,'text-rotation-alignment':'map','text-pitch-alignment':'map',
    'text-allow-overlap':true,'text-ignore-placement':true},paint:{'text-color':'rgba(255,90,90,0.12)','text-halo-color':'rgba(0,0,0,0.15)','text-halo-width':1}});
  map.addSource('by-mark',{type:'geojson',data:{type:'FeatureCollection',features:[[27.6,53.4],[29.4,52.2]].map(c=>({type:'Feature',properties:{},geometry:{type:'Point',coordinates:c}}))}});
  map.addLayer({id:'by-mark',type:'symbol',source:'by-mark',maxzoom:7.5,layout:{'text-field':'ПОСІПАКИ ТЕРОРИСТІВ','text-font':['Noto Sans Bold'],
    'text-size':['interpolate',['exponential',1.6],['zoom'],3,9,5,18,7,32],'text-letter-spacing':0.16,'text-max-width':40,'text-rotate':-18,'text-rotation-alignment':'map','text-pitch-alignment':'map',
    'text-allow-overlap':true,'text-ignore-placement':true},paint:{'text-color':'rgba(255,150,90,0.11)','text-halo-color':'rgba(0,0,0,0.15)','text-halo-width':1}});syncOutside();
  map.addLayer({id:'obl-line',type:'line',source:'obl',paint:{'line-color':'#fff','line-width':['interpolate',['linear'],['zoom'],4,1,9,2.2],'line-opacity':0.9}});
  // «пам'ятні місця»: крейсер «Москва» на дні та Кримський міст
  if(!map.hasImage('moskva')){const c=document.createElement('canvas');c.width=120;c.height=60;const x=c.getContext('2d');
    x.translate(60,34);x.rotate(-0.38);x.fillStyle='rgba(150,170,190,.85)';x.strokeStyle='rgba(255,255,255,.7)';x.lineWidth=1.5;
    x.beginPath();x.moveTo(-44,0);x.lineTo(40,0);x.lineTo(48,-6);x.lineTo(-38,-6);x.closePath();x.fill();x.stroke();
    x.fillRect(-18,-14,22,8);x.fillRect(-6,-22,6,8);x.fillRect(10,-11,12,5);
    x.rotate(0.38);x.strokeStyle='rgba(120,200,255,.55)';x.lineWidth=2;for(let k=0;k<3;k++){x.beginPath();x.moveTo(-52+k*6,10+k*6);x.quadraticCurveTo(-30+k*6,4+k*6,-8,10+k*6);x.quadraticCurveTo(14,16+k*6,36-k*6,10+k*6);x.stroke();}
    map.addImage('moskva',x.getImageData(0,0,120,60),{pixelRatio:2});}
  map.addSource('memo',{type:'geojson',data:{type:'FeatureCollection',features:[
    {type:'Feature',properties:{i:'moskva',k:'moskva',l:'крейсер «Москва»\nна дні з 14.04.2022'},geometry:{type:'Point',coordinates:[30.93,45.17]}},
    {type:'Feature',properties:{i:'',k:'bridge',l:'Кримський міст\nЗАЧЕКАЙ ЩЕ ТРОХИ'},geometry:{type:'Point',coordinates:[36.51,45.31]}}]}});
  map.addLayer({id:'memo-br',type:'line',source:{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[[36.44,45.25],[36.52,45.30],[36.60,45.36]]}}},paint:{'line-color':'rgba(255,90,90,.55)','line-width':2.5,'line-dasharray':[1,1]}});
  map.addLayer({id:'memo',type:'symbol',source:'memo',minzoom:4.6,layout:{'icon-image':['get','i'],'icon-size':['interpolate',['linear'],['zoom'],5,0.8,8,1.25],'icon-allow-overlap':true,'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':['interpolate',['linear'],['zoom'],5,9.5,8,12],'text-letter-spacing':0.08,'text-offset':[0,1.3],'text-anchor':'top','text-rotate':-8,'text-optional':true,'text-max-width':20},paint:{'text-color':'rgba(255,215,140,.75)','text-halo-color':'rgba(0,0,0,.8)','text-halo-width':1.3,'icon-opacity':0.85}});
  map.addSource('ru',{type:'geojson',data:EMPTY});map.addSource('hits',{type:'geojson',data:EMPTY});
  // приліт по РФ, живе багаття: анімоване полум'я (оновлюється ~12 разів/с, лише коли карта й так перемальовується)
  if(!map.hasImage('hit')){const S=72;const fire={width:S,height:S,data:new Uint8Array(S*S*4),t0:performance.now(),lt:0,
    onAdd(){this.c=document.createElement('canvas');this.c.width=this.c.height=S;this.x=this.c.getContext('2d',{willReadFrequently:true});this.draw(0);},
    draw(t){const x=this.x;x.clearRect(0,0,S,S);const cx=S/2,by=S*0.78;
      // відсвіт на землі
      let g=x.createRadialGradient(cx,by,2,cx,by,S*0.46);g.addColorStop(0,'rgba(255,140,40,.55)');g.addColorStop(1,'rgba(255,80,0,0)');x.fillStyle=g;x.beginPath();x.ellipse(cx,by,S*0.46,S*0.2,0,0,7);x.fill();
      // язики полум'я
      const tongues=[[0,1,1],[-7,0.72,1.7],[7,0.78,2.3],[-3,0.55,3.1],[4,0.5,0.6]];
      for(const [dx,h,ph] of tongues){const fl=0.82+0.18*Math.sin(t*9+ph*3)*Math.sin(t*5.3+ph),H=S*0.5*h*fl,W=S*0.13*(0.7+0.3*h),sw=Math.sin(t*6+ph*2)*3*h;
        g=x.createLinearGradient(0,by,0,by-H);g.addColorStop(0,'rgba(255,240,170,.95)');g.addColorStop(0.35,'rgba(255,170,40,.9)');g.addColorStop(0.75,'rgba(255,70,10,.75)');g.addColorStop(1,'rgba(200,20,0,0)');
        x.fillStyle=g;x.beginPath();x.moveTo(cx+dx-W,by);x.quadraticCurveTo(cx+dx-W*0.9+sw*0.5,by-H*0.55,cx+dx+sw,by-H);x.quadraticCurveTo(cx+dx+W*0.9+sw*0.5,by-H*0.55,cx+dx+W,by);x.closePath();x.fill();}
      // іскри
      for(let i=0;i<4;i++){const k=((t*0.9+i*0.27)%1),sx=cx+Math.sin(i*2.1+t*2)*8*k,sy=by-S*0.25-k*S*0.4;x.fillStyle='rgba(255,210,120,'+(1-k).toFixed(2)+')';x.beginPath();x.arc(sx,sy,1.4,0,7);x.fill();}
      // дрова
      x.strokeStyle='rgba(60,30,15,.9)';x.lineWidth=3;x.lineCap='round';x.beginPath();x.moveTo(cx-11,by+3);x.lineTo(cx+11,by-1);x.moveTo(cx-11,by-1);x.lineTo(cx+11,by+3);x.stroke();
      this.data.set(x.getImageData(0,0,S,S).data);},
    render(){const now=performance.now();if(now-this.lt<80)return false;this.lt=now;this.draw((now-this.t0)/1000);return true;}};
    map.addImage('hit',fire,{pixelRatio:2});}
  map.addLayer({id:'ru-glow',type:'circle',source:'ru',minzoom:3,filter:['!',['!=',['get','sum'],null]],paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,['+',10,['*',2,['coalesce',['get','c'],3]]],8,['+',30,['*',4,['coalesce',['get','c'],3]]]],'circle-color':'#2F7BFF','circle-blur':1,'circle-opacity':0.22,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'ru-dot',type:'circle',source:'ru',filter:['!',['!=',['get','sum'],null]],paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,1.8,7,3.5],'circle-color':'#FFD500','circle-stroke-color':'#2F7BFF','circle-stroke-width':['interpolate',['linear'],['zoom'],4,1,7,2],'circle-opacity':0.85}});
  map.addLayer({id:'ru-t',type:'symbol',source:'ru',minzoom:6.5,filter:['!',['!=',['get','sum'],null]],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':['case',['!=',['get','sum'],null],12,10.5],'text-max-width':16,'text-offset':['case',['!=',['get','sum'],null],['literal',[0,0]],['literal',[0,1.1]]],'text-anchor':['case',['!=',['get','sum'],null],'center','top'],'text-allow-overlap':false},paint:{'text-color':'rgba(255,227,107,.8)','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'hits',type:'symbol',source:'hits',layout:{'icon-image':'hit','icon-size':['interpolate',['linear'],['zoom'],4,['*',['case',['all',['get','wb'],['get','fresh']],1.45,['get','wb'],1.15,1],0.9],7,['*',['case',['all',['get','wb'],['get','fresh']],1.45,['get','wb'],1.15,1],1.5],10,['*',['case',['all',['get','wb'],['get','fresh']],1.45,['get','wb'],1.15,1],2]],'symbol-sort-key':['case',['get','wb'],10,0],'icon-allow-overlap':true,'text-field':['step',['zoom'],'',6.5,['get','l']],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,1.5],'text-anchor':'top','text-max-width':14,'text-optional':true},paint:{'text-color':['case',['get','wb'],'#FF9F2E','#FFE36B'],'text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  map.addSource('xr',{type:'geojson',data:EMPTY});
  map.addLayer({id:'xr-dim',type:'background',layout:{visibility:'none'},paint:{'background-color':'#02040A','background-opacity':0.55}});
  // рентген: 1-2-3, де ціль назвали канали (по черзі), суцільна лінія, шлях за повідомленнями; пунктир, оцінка SKY / заявлений курс
  map.addLayer({id:'xr-edge',type:'line',source:'xr',filter:['==',['get','k'],'path'],layout:{visibility:'none','line-cap':'round','line-join':'round'},paint:{'line-color':'#EAF0FF','line-width':3,'line-opacity':0.9}});
  map.addLayer({id:'xr-edge2',type:'line',source:'xr',filter:['in',['get','k'],['literal',['nowl','destl']]],layout:{visibility:'none','line-cap':'round'},paint:{'line-dasharray':[1.2,1.6],'line-color':['match',['get','k'],'nowl','#B48CFF','#F5B83D'],'line-width':2.5,'line-opacity':0.95}});
  map.addLayer({id:'xr-node',type:'circle',source:'xr',filter:['==',['geometry-type'],'Point'],layout:{visibility:'none'},paint:{'circle-radius':['match',['get','k'],'step',12,'now',9,'dest',7,6],'circle-color':['match',['get','k'],'step','#2B6BFF','now','rgba(180,140,255,.35)','dest','rgba(245,184,61,.25)','#fff'],'circle-stroke-color':['match',['get','k'],'step','#FFFFFF','now','#B48CFF','dest','#F5B83D','#fff'],'circle-stroke-width':2}});
  map.addLayer({id:'xr-t',type:'symbol',source:'xr',filter:['!=',['get','l'],null],layout:{visibility:'none','text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':['match',['get','k'],'step',13,12],'text-offset':['match',['get','k'],'step',['literal',[0,0]],['literal',[0,1.5]]],'text-anchor':['match',['get','k'],'step','center','top'],'text-allow-overlap':true,'text-max-width':14},paint:{'text-color':['match',['get','k'],'step','#FFFFFF','now','#E3D4FF','dest','#FFD27A','#fff'],'text-halo-color':['match',['get','k'],'step','rgba(0,0,0,0)','#000'],'text-halo-width':1.6}});
  map.addLayer({id:'zones',type:'circle',source:'zones',paint:{'circle-radius':['interpolate',['linear'],['zoom'],5,5,9,13,12,18],'circle-color':TYPE_COLOR.kab,'circle-opacity':0.16,'circle-stroke-color':TYPE_COLOR.kab,'circle-stroke-width':1.6,'circle-stroke-opacity':0.9,'circle-blur':0.1}});
  // загроза КАБ: маленький значок авіабомби над пунктом і підпис, замість великих помаранчевих кіл
  if(!map.hasImage('kab-mini')){const im=new Image();im.onload=()=>{if(!map.hasImage('kab-mini'))map.addImage('kab-mini',im,{pixelRatio:Math.max(1,im.naturalWidth/40)});};im.src='sprites/t-kab.png?v=ref17';}
  map.addLayer({id:'zones-t',type:'symbol',source:'zones',layout:{'icon-image':'kab-mini','icon-rotate':['get','r'],'icon-rotation-alignment':'map','icon-size':['interpolate',['linear'],['zoom'],5,0.5,9,0.9],'icon-allow-overlap':true,'text-field':['step',['zoom'],'',7,'загроза КАБ'],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,1.6],'text-anchor':'top','text-optional':true},paint:{'text-color':TYPE_COLOR.kab,'text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.4}});
  // ворожа тактична авіація (носії КАБ) і зона пусків
  ['avia','avia-z','avia-l'].forEach(id=>{if(!map.getSource(id))map.addSource(id,{type:'geojson',data:EMPTY});});
  if(!map.hasImage('su34')){const c=document.createElement('canvas');c.width=c.height=96;const x=c.getContext('2d');x.translate(48,48);
    const p=new Path2D('M0,-40 L4,-30 L5,-12 L34,8 L34,14 L5,8 L4,24 L14,32 L14,36 L0,33 L-14,36 L-14,32 L-4,24 L-5,8 L-34,14 L-34,8 L-5,-12 L-4,-30 Z');
    x.shadowColor='#FF2E2E';x.shadowBlur=10;x.fillStyle='#FF3B3B';x.fill(p);x.shadowBlur=0;x.lineWidth=2;x.strokeStyle='#fff';x.stroke(p);
    map.addImage('su34',x.getImageData(0,0,96,96),{pixelRatio:3});}
  map.addLayer({id:'avia-z',type:'fill',source:'avia-z',paint:{'fill-color':'#FF2E2E','fill-opacity':['*',0.16,['-',1,['get','f']]]}});
  map.addLayer({id:'avia-zl',type:'line',source:'avia-z',paint:{'line-color':'#FF5A5A','line-width':1.4,'line-dasharray':[2,2],'line-opacity':['*',0.9,['-',1,['get','f']]]}});
  map.addLayer({id:'avia-l',type:'line',source:'avia-l',paint:{'line-color':'#22E1FF','line-width':1.3,'line-dasharray':[1,2.2],'line-opacity':0.7}});
  map.addLayer({id:'avia',type:'symbol',source:'avia',layout:{'icon-image':'su34','icon-size':['interpolate',['linear'],['zoom'],4,0.7,8,1.1],'icon-rotate':['get','r'],'icon-rotation-alignment':'map','icon-allow-overlap':true,
    'text-field':['step',['zoom'],'',5.2,['get','l']],'text-font':['Noto Sans Bold'],'text-size':10.5,'text-max-width':12,'text-offset':[0,1.7],'text-anchor':'top','text-optional':true},paint:{'icon-opacity':['-',1,['*',0.6,['get','f']]],'text-color':'#FF9A9A','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.5}});
  try{stratEnsure();}catch(e){console.warn('strat',e);}
  if(!map._kabClick){map._kabClick=1;map.on('click','zones-t',e=>{const f=e.features&&e.features[0];if(!f||!SNAP)return;const z=SNAP.zones[f.properties.zi];if(!z)return;
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'320px',className:'kab-pop',offset:18}).setLngLat(f.geometry.coordinates).setHTML(kabInfo(z)).addTo(map);});
  map.on('click','avia',e=>{const f=e.features&&e.features[0];if(!f||!SNAP)return;const a=(SNAP.avia||[])[f.properties.ai];if(!a)return;
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'320px',className:'kab-pop avia-pop',offset:20}).setLngLat(f.geometry.coordinates).setHTML(aviaInfo(a)).addTo(map);});
  map.on('mouseenter','avia',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','avia',()=>map.getCanvas().style.cursor='');
  map.on('click','ru-dot',e=>{const f=e.features&&e.features[0];if(!f||!SNAP)return;const ev=(SNAP.ru||[]).slice().sort((a,b)=>b.t-a.t)[0];if(!ev)return;const p=f.properties;
    const per=!ev.period?'':/ноч/.test(ev.period)?'за ніч':/дня/.test(ev.period)?'за день':/суток/.test(ev.period)?'за добу':'';
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'300px',className:'kab-pop ru-pop',offset:12}).setLngLat(f.geometry.coordinates).setHTML(
     '<div class="kp"><small>НАШІ ДРОНИ НАД РФ</small><h4>'+esc(p.n||'')+'</h4>'+
     '<div class="kp-r"><span>Запущено</span><b>точну кількість не публікують; РФ сама визнала щонайменше '+(p.cnt||'кілька')+' над регіоном</b></div>'+
     '<div class="kp-r"><span>Усього</span><b>≥ '+ev.total+' над '+ev.regions.length+' рег. · '+(per||'останнє зведення')+' · '+hm(ev.t)+'</b></div>'+
     '<div class="kp-r"><span>Прильоти</span><b>багаття на мапі, за Генштабом ЗСУ та ASTRA</b></div>'+
     (ev.link?'<div class="kp-ev"><a href="'+esc(ev.link)+'" target="_blank" rel="noopener" style="color:inherit">допис-першоджерело ↗</a></div>':'')+'</div>').addTo(map);});
  map.on('click','lsites',e=>{const f=e.features&&e.features[0];if(!f||!SNAP||!f.properties.lid)return;const L=(SNAP.launches||[]).find(x=>x.id===f.properties.lid);if(!L)return;const w=launchWhat(L);const nm=k=>(SNAP.sources&&SNAP.sources[k]&&SNAP.sources[k].name)||k;
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'320px',className:'kab-pop avia-pop',offset:12}).setLngLat(f.geometry.coordinates).setHTML(
     '<div class="kp"><small>'+(isTO(L)?'НОСІЇ В ПОВІТРІ':'ПУСК ПО УКРАЇНІ')+'</small><h4>'+esc(L.site)+'</h4>'+
     (isTO(L)?'<div class="kp-r"><span>Пуски</span><b>джерела про пуск ракет ще не повідомили</b></div>':'<div class="kp-r"><span>Що</span><b>'+esc(w.full)+'</b></div>')+
     (L.count?'<div class="kp-r"><span>'+(isTO(L)?'Бортів (як написало джерело)':'Кількість')+'</span><b>'+L.count+'</b></div>':'')+(L.carrier?'<div class="kp-r"><span>Носій</span><b>'+esc(L.carrier)+'</b></div>':'')+
     '<div class="kp-r"><span>Коли</span><b>'+fmt(L.t)+'</b></div>'+'<div class="kp-r"><span>Цілей привʼязано</span><b>'+(L.tracks||0)+'</b></div>'+
     ((L.ev||[]).length?'<div class="kp-ev">'+L.ev.slice(-3).reverse().map(e=>'<div><i>'+fmt(e.t)+' · '+esc(nm(e.src))+'</i>'+esc(e.text||'')+'</div>').join('')+'</div>':'')+'</div>').addTo(map);});
  map.on('mouseenter','lsites',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','lsites',()=>map.getCanvas().style.cursor='');
  map.on('click','hits',e=>{const f=e.features&&e.features[0];if(!f)return;const h=HITS[f.properties.hi];if(!h)return;
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'300px',className:'kab-pop ru-pop',offset:12}).setLngLat(f.geometry.coordinates).setHTML(
     '<div class="kp"><small>'+(h.src==='ASTRA'?'ПРИЛІТ НАШИХ ДРОНІВ':'УРАЖЕНО СИЛАМИ ОБОРОНИ')+'</small><h4>'+esc(h.place)+'</h4>'+
     '<div class="kp-r"><span>Що</span><b>'+esc(h.what)+'</b></div>'+
     '<div class="kp-r"><span>Коли</span><b>'+new Date(h.t*1000).toLocaleString('uk-UA',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+' · '+(()=>{const m=Math.max(0,Math.round((Date.now()/1000+offset-h.t)/60));return m<60?m+' хв тому':Math.floor(m/60)+' год '+(m%60)+' хв тому';})()+'</b></div>'+
     '<div class="kp-r"><span>Джерело</span><b>'+esc(h.src||'Генштаб ЗСУ')+'</b></div>'+
     '<div class="kp-ev"><div>'+esc(h.detail||'')+'</div>'+(h.link?'<a href="'+esc(h.link)+'" target="_blank" rel="noopener" style="color:inherit">першоджерело ↗</a>':'')+'</div></div>').addTo(map);});
  map.on('mouseenter','hits',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','hits',()=>map.getCanvas().style.cursor='');
  map.on('mouseenter','ru-dot',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','ru-dot',()=>map.getCanvas().style.cursor='');
  map.on('mouseenter','zones-t',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','zones-t',()=>map.getCanvas().style.cursor='');}
  map.addLayer({id:'chains',type:'line',source:'chains',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':['case',['get','s'],2.6,1.4],'line-dasharray':[2,1.6],'line-opacity':['get','o']}});
  map.addLayer({id:'lsites',type:'circle',source:'lsites',paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,['case',['get','est'],3,4],7,['case',['get','est'],5,7]],'circle-color':['case',['get','est'],'rgba(255,77,77,0.25)','#FF3B3B'],'circle-stroke-color':'#fff','circle-stroke-width':['case',['get','est'],1.2,2],'circle-pitch-alignment':'map'}});
  map.addLayer({id:'lsites-t',type:'symbol',source:'lsites',minzoom:5,layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11,'text-max-width':14,'text-offset':[0,1.1],'text-anchor':'top','text-allow-overlap':false,'text-optional':true},paint:{'text-color':'#FFB3B3','text-halo-color':'#0B0F17','text-halo-width':2}});
  map.addLayer({id:'trails',type:'line',source:'trails',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':3,'line-dasharray':[0.1,2.2],'line-opacity':['get','o']}});
  // біла крапка «тут її назвали канали» (факт), окремо від оцінки положення значком; блідне з віком повідомлення
  map.addLayer({id:'tg-named',type:'circle',source:'trails',filter:['==',['get','nm'],1],paint:{'circle-radius':3.6,'circle-color':'#FFFFFF','circle-opacity':['get','o'],'circle-stroke-color':'rgba(0,0,0,.75)','circle-stroke-width':1,'circle-stroke-opacity':['get','o']}});
  map.addLayer({id:'ticks-c',type:'circle',source:'ticks',paint:{'circle-radius':4,'circle-color':['get','c'],'circle-stroke-color':'#0B0F17','circle-stroke-width':2,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'ticks-t',type:'symbol',source:'ticks',layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,-1.1],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  // «жива» мапа без вигаданих позицій: напрямок руху — біжучими штрихами на ~8 хв уперед (лише де курс відомий),
  // а нерухомі цілі (місце невідоме або лише оцінене) «дихають» кільцем: рухати їх бектест не дозволяє (03.11: точність гірша)
  if(!map.getSource('flow'))map.addSource('flow',{type:'geojson',data:EMPTY});
  if(!map.getSource('pulse'))map.addSource('pulse',{type:'geojson',data:EMPTY});
  if(!map.getLayer('flow'))map.addLayer({id:'flow',type:'line',source:'flow',layout:{'line-cap':'butt'},paint:{'line-color':['get','c'],'line-width':['interpolate',['linear'],['zoom'],4,1.6,9,2.6],'line-opacity':0.85,'line-dasharray':[0,4,3]}});
  if(!map.getLayer('pulse'))map.addLayer({id:'pulse',type:'circle',source:'pulse',paint:{'circle-radius':10,'circle-color':'rgba(0,0,0,0)','circle-stroke-color':['get','c'],'circle-stroke-width':1.6,'circle-stroke-opacity':0.6,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'preds',type:'line',source:'preds',layout:{'line-cap':'round'},paint:{'line-color':['get','c'],'line-width':2,'line-dasharray':[1.5,2],'line-opacity':0.9}});
  map.addLayer({id:'preds-dst',type:'circle',source:'preds',filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':5,'circle-color':'rgba(0,0,0,.35)','circle-stroke-color':['get','c'],'circle-stroke-width':2}});
  map.addLayer({id:'preds-dl',type:'symbol',source:'preds',filter:['==',['geometry-type'],'Point'],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-anchor':'top','text-offset':[0,0.9],'text-optional':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  // вибрана ціль: де її бачили востаннє за повідомленням (нерухома точка з часом) і де вона за розрахунком SKY, з'єднані пунктиром.
  // Так видно, що відомо з повідомлення, а що домалювала система (03.11)
  if(!map.getSource('selrep'))map.addSource('selrep',{type:'geojson',data:EMPTY});
  if(!map.getSource('tac'))map.addSource('tac',{type:'geojson',data:EMPTY});
  for(const sid of ['meas','reach','enemy'])if(!map.getSource(sid))map.addSource(sid,sid==='enemy'?{type:'geojson',data:EMPTY,attribution:'Позначки ворога: © OpenStreetMap contributors'}:{type:'geojson',data:EMPTY});
  map.addLayer({id:'selrep-l',type:'line',source:'selrep',filter:['==',['geometry-type'],'LineString'],layout:{'line-cap':'round'},paint:{'line-color':'#fff','line-width':1.4,'line-opacity':0.85,'line-dasharray':[1,2.2]}});
  map.addLayer({id:'selrep-p',type:'circle',source:'selrep',filter:['==',['get','k'],'rep'],paint:{'circle-radius':4.5,'circle-color':'#fff','circle-stroke-color':'#0B0F17','circle-stroke-width':2,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'selrep-t',type:'symbol',source:'selrep',filter:['==',['geometry-type'],'Point'],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':['case',['==',['get','k'],'rep'],['literal',[0,-1.3]],['literal',[0,2.9]]],'text-max-width':30,'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6,'text-halo-blur':0.4}});
  map.addLayer({id:'home',type:'symbol',source:'home',layout:{'icon-image':'home','icon-size':['interpolate',['linear'],['zoom'],4,0.38,6,0.55,8,0.85,10,1],'icon-allow-overlap':true,'text-field':['step',['zoom'],'',7,'Дім'],'text-font':['Noto Sans Bold'],'text-size':13,'text-offset':[0,1.7],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'tg-course',type:'symbol',source:'targets',filter:['all',['!=',['get','next'],null],['!=',['get','next'],''],['==',['get','active'],true],['any',['get','thr'],['==',['get','sk'],0],['all',['>=',['zoom'],7],!TAC]]],layout:{'text-field':['concat',['case',['>',['get','count'],1],['concat','×',['to-string',['get','count']],'  '],''],['case',['==',['get','type'],'ballistic'],'загроза: ','→ '],['get','next'],['case',['all',['get','est'],['==',['get','sk'],0]],' · місце не названо',''],['case',['==',['get','pair'],'lancet'],' · загроза Ланцет','']],'text-font':['Noto Sans Bold'],'text-size':['interpolate',['linear'],['zoom'],6,11,10,12.5],'text-max-width':40,'text-variable-anchor':['left','right','bottom','top'],'text-radial-offset':['interpolate',['linear'],['zoom'],2,1.9,5,2.3,7,2.8,9.5,3.4,12,3.8],'text-justify':'auto','icon-allow-overlap':false,'text-allow-overlap':false,'text-optional':false,'symbol-sort-key':['get','sk']},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6,'text-halo-blur':0.4}});
  const TGS=['interpolate',['linear'],['zoom'],4,0.55,7,0.85,9,1.15,12,1.55];
  // голограма тривоги: об'єми над районами (червоні вищі), «дихають»
  const firstLbl=(map.getStyle().layers.find(l=>l.type==='symbol')||{}).id;
  map.addLayer({id:'holo',type:'fill-extrusion',source:'holo',maxzoom:8.5,paint:{'fill-extrusion-color':['match',['get','l'],2,'#FF2D3D','#FFB020'],'fill-extrusion-height':['interpolate',['linear'],['zoom'],5,['match',['get','l'],2,12000,4500],7.5,['match',['get','l'],2,1500,600],8.5,0],'fill-extrusion-base':0,'fill-extrusion-opacity':0.26,'fill-extrusion-vertical-gradient':true}},firstLbl);
  // громади з тривогою, справжні межі громади (КАТОТТГ + OSM), а не коло
  if(!map.getSource('hp'))map.addSource('hp',{type:'geojson',data:HPDATA||EMPTY,attribution:'Межі громад: КАТОТТГ, © OpenStreetMap (ODbL)'});HPPREV={};lastRa='';
  map.addLayer({id:'hp-f',type:'fill',source:'hp',paint:{'fill-color':['match',['coalesce',['feature-state','l'],0],2,'#FF2D3D','#FFB020'],'fill-opacity':['match',['coalesce',['feature-state','l'],0],0,0,0.34]}},firstLbl);
  map.addLayer({id:'hp-l',type:'line',source:'hp',paint:{'line-color':['match',['coalesce',['feature-state','l'],0],2,'#FF7A84','#FFD27A'],'line-width':1.6,'line-opacity':['match',['coalesce',['feature-state','l'],0],0,0,0.95]}},firstLbl);
  map.addLayer({id:'hrom',type:'circle',source:'hrom',filter:['!=',['get','poly'],1],paint:{'circle-radius':['interpolate',['exponential',2],['zoom'],5,3,8,22,11,170],'circle-color':['match',['get','l'],2,'#FF2D3D','#FFB020'],'circle-opacity':0.32,'circle-stroke-color':['match',['get','l'],2,'#FF6B76','#FFD27A'],'circle-stroke-width':1.2,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'hrom-t',type:'symbol',source:'hrom',minzoom:8,layout:{'text-field':['concat','тривога: ',['get','n']],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,1.4]},paint:{'text-color':'#FFD0D4','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.4}});
  map.addLayer({id:'holo-top',type:'line',source:'holo',paint:{'line-color':['match',['get','l'],2,'#FF6B76','#FFD27A'],'line-width':1.2,'line-opacity':0.8}},firstLbl);
  map.addLayer({id:'ra-glow',type:'line',source:'ra',paint:{'line-color':'#FF3B4E','line-width':['interpolate',['linear'],['zoom'],5,2,9,5],'line-blur':['interpolate',['linear'],['zoom'],5,2,9,5],'line-opacity':['case',['==',LV,2],0.5,0]}});
  // коло «де ціль може бути насправді» (68% випадків), з реальної похибки позиції (бектест), росте з часом без нових повідомлень
  map.addLayer({id:'tg-unc',type:'circle',source:'targets',filter:['all',['==',['get','active'],true],['!=',['get','u0'],null],['any',['==',['get','sk'],0],['get','thr'],['>=',['zoom'],8]]],
    paint:{'circle-radius':['interpolate',['exponential',2],['zoom'],0,['get','u0'],22,['*',['get','u0'],4194304]],'circle-color':['get','c'],'circle-opacity':0.07,
      'circle-stroke-color':['get','c'],'circle-stroke-width':1,'circle-stroke-opacity':0.45,'circle-pitch-alignment':'map'}},firstLbl);
  map.addLayer({id:'tg-hit',type:'circle',source:'targets',filter:['==',['get','active'],true],paint:{'circle-radius':22,'circle-opacity':0,'circle-stroke-opacity':0}});
  try{if(window.FxLayer&&!map.getLayer('fx'))map.addLayer(window.FxLayer);}catch(e){console.warn('fx',e);}
  // тактичний режим: факт (назване місце, суцільна точка) окремо від оцінки SKY (значок, пунктир), вік повідомлення біля цілі
  map.addLayer({id:'tac-ln',type:'line',source:'tac',filter:['==',['get','k'],'ln'],layout:{'line-cap':'butt'},paint:{'line-color':['get','c'],'line-width':1.4,'line-dasharray':[2,2],'line-opacity':['*',0.8,['get','o']]}});
  map.addLayer({id:'tac-fact',type:'circle',source:'tac',filter:['==',['get','k'],'fact'],paint:{'circle-radius':4.5,'circle-color':['get','c'],'circle-stroke-color':'#FFFFFF','circle-stroke-width':1.6,'circle-opacity':['get','o'],'circle-stroke-opacity':['get','o']}});
  map.addLayer({id:'reach-f',type:'fill',source:'reach',filter:['==',['get','k'],'f'],paint:{'fill-color':'#FFFFFF','fill-opacity':0.04}});
  map.addLayer({id:'reach-l',type:'line',source:'reach',filter:['==',['get','k'],'l'],paint:{'line-color':'#E6EBF2','line-width':1.2,'line-dasharray':[4,3],'line-opacity':0.7}});
  map.addLayer({id:'reach-t',type:'symbol',source:'reach',filter:['==',['get','k'],'t'],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':10.5,'text-anchor':'bottom','text-allow-overlap':false},paint:{'text-color':'#E6EBF2','text-halo-color':'rgba(10,12,16,.92)','text-halo-width':1.5}});
  map.addLayer({id:'enemy-sym',type:'symbol',source:'enemy',minzoom:4.5,layout:{'icon-image':['get','img'],'icon-size':['interpolate',['linear'],['zoom'],5,0.6,9,0.85],'icon-allow-overlap':false,'text-field':['step',['zoom'],'',5,['get','v']],'text-font':['Noto Sans Bold'],'text-size':10,'text-anchor':'top','text-offset':[0,1.3],'text-optional':true},paint:{'text-color':'#E6EBF2','text-halo-color':'rgba(10,12,16,.92)','text-halo-width':1.4,'icon-opacity':['case',['==',['get','hot'],1],0,['==',['get','dim'],1],0.28,0.9]}});
  map.addLayer({id:'enemy-hot',type:'circle',source:'enemy',filter:['==',['get','hot'],1],paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,16,9,28],'circle-color':'rgba(255,59,59,.16)','circle-stroke-color':'#FF3B3B','circle-stroke-width':2,'circle-pitch-alignment':'map'}},'enemy-sym');
  map.addLayer({id:'meas-l',type:'line',source:'meas',filter:['==',['get','k'],'l'],paint:{'line-color':'#FFFFFF','line-width':2,'line-opacity':0.95}});
  map.addLayer({id:'meas-p',type:'circle',source:'meas',filter:['==',['get','k'],'p'],paint:{'circle-radius':5,'circle-color':'#14171C','circle-stroke-color':'#FFFFFF','circle-stroke-width':2}});
  map.addLayer({id:'meas-t',type:'symbol',source:'meas',filter:['==',['get','k'],'t'],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11.5,'text-anchor':'bottom','text-offset':[0,-0.4],'text-allow-overlap':true},paint:{'text-color':'#FFFFFF','text-halo-color':'rgba(10,12,16,.95)','text-halo-width':2}});
  tacPaint();
  map.addLayer({id:'tac-hl2',type:'circle',source:'tac',filter:['==',['get','k'],'hl2'],paint:{'circle-radius':16,'circle-color':'rgba(255,59,59,0)','circle-stroke-color':'#FF4A4A','circle-stroke-width':2.4,'circle-stroke-opacity':0,'circle-opacity':0,'circle-pitch-alignment':'viewport'}});
  map.addLayer({id:'tac-hl',type:'circle',source:'tac',filter:['==',['get','k'],'hl'],paint:{'circle-radius':18,'circle-color':'rgba(255,255,255,0.10)','circle-stroke-color':'#FFFFFF','circle-stroke-width':2.4,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'tac-sel',type:'circle',source:'tac',filter:['==',['get','k'],'sel'],paint:{'circle-radius':22,'circle-color':'rgba(0,0,0,0)','circle-stroke-color':'#FFFFFF','circle-stroke-width':1.6,'circle-stroke-opacity':0.9,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'tac-sym',type:'symbol',source:'tac',filter:['==',['get','k'],'sym'],layout:{'icon-image':['get','img'],'icon-size':['interpolate',['linear'],['zoom'],4,0.72,8,0.9,11,1.1],'icon-allow-overlap':true,'icon-ignore-placement':true,'icon-rotation-alignment':'viewport','text-field':['get','v'],'text-font':['Noto Sans Bold'],'text-size':10.5,'text-anchor':'top','text-offset':[0,1.5],'text-optional':true},paint:{'icon-opacity':['get','o'],'text-color':'#E6EBF2','text-halo-color':'rgba(10,12,16,.92)','text-halo-width':1.5,'text-opacity':['get','o']}});
  map.addLayer({id:'tac-age',type:'symbol',source:'tac',filter:['==',['get','k'],'age'],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11,'text-anchor':'left','text-offset':[1.9,0],'text-optional':true},paint:{'text-color':'#E6EBF2','text-halo-color':'rgba(10,12,16,.92)','text-halo-width':1.5,'text-opacity':['get','o']}});
  map.addLayer({id:'tg-n',type:'symbol',source:'targets',filter:['all',['>',['get','count'],1],['!',['!=',['get','next'],null]]],layout:{'text-field':['concat','×',['to-string',['get','count']]],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[2,6,2,6],'text-anchor':'top','text-offset':['interpolate',['linear'],['zoom'],2,['literal',[0,1.30]],5,['literal',[0,1.68]],7,['literal',[0,2.04]],9.5,['literal',[0,2.48]]],'text-allow-overlap':true,'icon-allow-overlap':true},paint:{'text-color':'#fff'}});
  if(map.getLayer('tg-course'))map.moveLayer('tg-course');
  let lastTap={id:null,t:0};
  map.on('click','tg-hit',e=>{if(MEAS.on)return;const f=e.features[0],id=f.properties.id,now=Date.now();
    if(lastTap.id===id&&now-lastTap.t<420){lastTap={id:null,t:0};// 2 тапи по цілі: стеження вкл/викл
      if(follow&&sel===id){stopFollow('Стеження вимкнено');}else{sel=id;startFollow();}
      try{const b=$('#sh-follow');if(b){b.classList.toggle('on',follow);b.textContent=follow?'Зупинити':'Стежити';}}catch(_){}return;}
    lastTap={id,t:now};openSheet(id);});
  // 08.11: довге натискання на короткодальню ціль (FPV/«Молнія»/«Ланцет») — зона ризику: віяло вперед на залишок дальності від лінії пуску
  {let lpT=null,lpP=null;const cancel=()=>{clearTimeout(lpT);lpT=null;};
   const start=e=>{cancel();lpP=e.point;lpT=setTimeout(()=>{lpT=null;const fs=map.queryRenderedFeatures([[lpP.x-24,lpP.y-24],[lpP.x+24,lpP.y+24]],{layers:['tg-hit']});if(!fs.length||!SNAP)return;
      const tr=SNAP.tracks.find(t=>t.id===fs[0].properties.id);if(!tr||!tr.zone){toast('Зона ризику є лише для FPV, «Молнії» та «Ланцета»');return;}
      if(!map.getSource('fpvz')){map.addSource('fpvz',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
        map.addLayer({id:'fpvz-f',type:'fill',source:'fpvz',paint:{'fill-color':'#19D3FF','fill-opacity':0.22}},'tg-hit');
        map.addLayer({id:'fpvz-l',type:'line',source:'fpvz',paint:{'line-color':'#5CE1FF','line-width':2.5,'line-dasharray':[2,1.5]}},'tg-hit');}
      map.getSource('fpvz').setData({type:'FeatureCollection',features:[{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[tr.zone.poly]}}]});
      try{navigator.vibrate&&navigator.vibrate(25);}catch(_){}
      toast('Зона ризику: ціль летить від лінії пуску, ще до ~'+tr.zone.km+' км уздовж курсу');
      clearTimeout(window.__fpvzT);window.__fpvzT=setTimeout(()=>{try{map.getSource('fpvz').setData({type:'FeatureCollection',features:[]});}catch(_){}},20000);},550);};
   map.on('mousedown',start);map.on('touchstart',start);['mouseup','touchend','touchcancel','dragstart','move'].forEach(ev=>map.on(ev,cancel));}
  map.on('dblclick','tg-hit',e=>{e.preventDefault();});// без зуму карти при подвійному тапі по цілі
  if(!map._measClick){map._measClick=1;map.on('click',e=>{if(!MEAS.on)return;MEAS.pts.push([e.lngLat.lng,e.lngLat.lat]);measDraw();});}
  map.on('mouseenter','tg-hit',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','tg-hit',()=>map.getCanvas().style.cursor='');
  map.addLayer({id:'lpred',type:'line',source:'lpred',filter:['==',['geometry-type'],'LineString'],layout:{'line-cap':'round'},paint:{'line-color':['get','c'],'line-width':2,'line-dasharray':[0.6,2.2],'line-opacity':0.75}});
  map.addLayer({id:'lpred-t',type:'symbol',source:'lpred',filter:['==',['geometry-type'],'Point'],minzoom:6,layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,-1],'text-allow-overlap':false},paint:{'text-color':['get','c'],'text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.4,'text-opacity':0.9}});
  map.addLayer({id:'me-ring',type:'fill',source:'mepos',filter:['==',['geometry-type'],'Polygon'],paint:{'fill-color':'#3B9BFF','fill-opacity':0.07}});
  map.addLayer({id:'me-ring-l',type:'line',source:'mepos',filter:['==',['geometry-type'],'Polygon'],paint:{'line-color':'#5AB0FF','line-width':1.4,'line-dasharray':[2,2],'line-opacity':0.85}});
  map.addLayer({id:'me-dot-h',type:'circle',source:'mepos',filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':16,'circle-color':'#3B9BFF','circle-opacity':0.22,'circle-blur':0.6}});
  map.addLayer({id:'me-dot',type:'circle',source:'mepos',filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':6.5,'circle-color':'#2F8BFF','circle-stroke-color':'#fff','circle-stroke-width':2.2}});
  map.addLayer({id:'myplaces',type:'circle',source:'myplaces',paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,3,8,6],'circle-color':'#B07CFF','circle-stroke-color':'#fff','circle-stroke-width':['interpolate',['linear'],['zoom'],4,1.2,8,2]}});
  map.addLayer({id:'myplaces-t',type:'symbol',source:'myplaces',minzoom:6,layout:{'text-field':['get','n'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,1.1],'text-anchor':'top','text-allow-overlap':false},paint:{'text-color':'#fff','text-halo-color':'rgba(40,10,70,.9)','text-halo-width':1.8}});
  lastLv='';lastRa='';CUTK='';syncHome();syncMe();syncPlaces();
  if(TAC){TILT_BEFORE=tilt;tilt=false;try{map.setMaxPitch(0);}catch(e){}}else if(tilt)set3d(true,'keep');
  if(!map._scaleAdded&&innerWidth>640){map.addControl(new maplibregl.ScaleControl({unit:'metric',maxWidth:110}),'bottom-left');map._scaleAdded=true;}
}
map.on('style.load',addOverlays);
// кінематографічне інтро: з космосу, на Україну вночі, поки збираються дані
let introT0=Date.now();if(INTRO)document.body.classList.add('intro');
function introFly(skip){if(introDone)return;introDone=true;sessionStorage.setItem('intro','1');const el=$('#intro');
  const mob=innerWidth<640;
  // кінцевий стан: 3D з наближенням до дому; без дому — до геопозиції (визначається під час паузи); без обох — центр країни з нахилом
  const sc=START_CAM||{center:map.getCenter(),zoom:map.getZoom()};
  const camFor=()=>{if(TAC)return {center:[31.5,48.5],zoom:uaZoom(),pitch:0,bearing:0};// тактичний режим стартує з огляду всієї України
    const tgt=home||window.__GEOPOS||null;return tgt?{center:tgt,zoom:mob?7.2:7.8,pitch:mob?45:52,bearing:0}:{center:sc.center,zoom:sc.zoom+0.3,pitch:mob?45:52,bearing:0};};
  if(TAC){try{map.jumpTo(camFor());tacPad(false);window.__tacCam=1;}catch(e){}}// камера на Україні готується ПІД заставкою, користувач цього не бачить
  const LG=window.__stlog=window.__stlog||[];const lg=m=>LG.push(m+'@'+Math.round((Date.now()-introT0)/100)/10);
  // переліт на «Дім» власною покадровою анімацією (не залежить від flyTo/«зменшення руху»): 4,5 с, плавний розгін і гальмування; переривається лише дотиком уже під час руху
  // плавна камера покадрово (не залежить від flyTo/«зменшення руху»): центр, масштаб, нахил за D мс із м'яким розгоном і гальмуванням; переривається лише дотиком уже під час руху
  const smoothCam=(c,D)=>{const c0=map.getCenter(),z0=map.getZoom(),p0=map.getPitch(),b0=map.getBearing(),ts=performance.now(),T0=Date.now();window.__padLock=1;lg('політ');
    const step=now=>{if((window.__touch||0)>T0){window.__padLock=0;lg('перервано');return;}const e=Math.min(1,(now-ts)/D),k=-(Math.cos(Math.PI*e)-1)/2;
      try{map.jumpTo({center:[c0.lng+(c.center[0]-c0.lng)*k,c0.lat+(c.center[1]-c0.lat)*k],zoom:z0+(c.zoom-z0)*k,pitch:p0+((c.pitch||0)-p0)*k,bearing:b0+((c.bearing||0)-b0)*k});}catch(x){lg('помилка');window.__padLock=0;return;}
      if(e<1)requestAnimationFrame(step);else{window.__padLock=0;lg('готово');}};requestAnimationFrame(step);};
  const flyHome=()=>{const t0=Date.now(),tr=()=>{const tg=home||window.__GEOPOS;if(!tg){if(Date.now()-t0<4500){setTimeout(tr,300);return;}lg('немає_цілі');return;}smoothCam({center:tg,zoom:7.4,pitch:0,bearing:0},4500);};tr();};
  // огляд: мапа стоїть на всій країні, усі цілі пульсують кільцями, щоб користувач охопив ситуацію, і лише потім переліт на «Дім»
  const tacSurvey=ms=>{const t0=performance.now(),id='tac-hl2';const step=now=>{if(!map.getLayer(id))return;const e=now-t0;if(e>=ms){map.setPaintProperty(id,'circle-stroke-opacity',0);return;}
    const ph=(e%1100)/1100,fade=Math.min(1,e/300)*Math.min(1,(ms-e)/400);map.setPaintProperty(id,'circle-radius',14+22*ph);map.setPaintProperty(id,'circle-stroke-opacity',(1-ph)*0.95*fade);requestAnimationFrame(step);};requestAnimationFrame(step);};
  const finish=()=>{tacPad(false);document.body.classList.remove('intro');document.body.classList.add('intro-in');setTimeout(()=>document.body.classList.remove('intro-in'),2500);
    ['lsites-t','tg-n','tg-course','ru-t','hits'].forEach(id=>{if(map.getLayer(id))map.setLayoutProperty(id,'visibility','visible');});};
  // переліт у 3D. 03.11: раніше залежав від INTRO (sessionStorage): після повторного відкриття застосунку мапа лишалася у 2D назавжди
  const go=()=>{if(Date.now()-(window.__touch||0)<5000){finish();return;}  // користувач уже сам рухає мапу — не смикаємо
    const c=camFor();if(TAC){if(!window.__tacCam)map.jumpTo(c);}else smoothCam(c,4500);window.__introAt=Date.now();tilt=!TAC;setTimeout(finish,30);
    if(TAC){// огляд України, потім плавно на точку «Дім», а без неї на геопозицію
      const t0=Date.now(),tryZoom=()=>{if(Date.now()-(window.__touch||0)<5000)return;const tg=home||window.__GEOPOS;
        if(tg){const fly=()=>map.flyTo({center:tg,zoom:7.4,duration:2200,essential:true,curve:1.2});fly();setTimeout(()=>{if(Date.now()-(window.__touch||0)<5000)return;const c=map.getCenter();if(Math.abs(c.lng-tg[0])>0.8||Math.abs(c.lat-tg[1])>0.8||map.getZoom()<6.8)fly();},2800);return;}
        if(Date.now()-t0<4500)setTimeout(tryZoom,400);};
      setTimeout(tryZoom,300);}};
  if(skip){if(el)el.remove();document.body.classList.remove('intro');go();return;}
  // поки стоїмо й летимо, без підписів пусків і цілей (каша), вони проявляються в кінці польоту
  ['lsites-t','tg-n','tg-course','ru-t','hits'].forEach(id=>{if(map.getLayer(id))map.setLayoutProperty(id,'visibility','none');});
  const wait=(el&&INTRO)?Math.max(0,3900-(Date.now()-introT0)):0;   // логотип встигає зіграти (лише при першому запуску в сесії)
  // без дому: за час паузи питаємо геопозицію (тихо, 4 с), щоб було куди наближатися
  if(!home&&navigator.geolocation){try{navigator.geolocation.getCurrentPosition(p=>{window.__GEOPOS=[p.coords.longitude,p.coords.latitude];},()=>{},{enableHighAccuracy:false,timeout:4000,maximumAge:600000});}catch(e){}}
  setTimeout(()=>{if(el){el.classList.add('out');setTimeout(()=>el.remove(),1400);}document.body.classList.remove('intro');
    // поки мапа стоїть у 2D, усі цілі пульсують кільцями кольору свого типу: за 5 с видно, що де летить
    window.FXHLALL={t0:performance.now(),until:performance.now()+3600};map.triggerRepaint();
    if(TAC){window.__introAt=Date.now();tilt=false;finish();lg('огляд');tacSurvey(3600);setTimeout(flyHome,3700);}else{lg('огляд');setTimeout(go,3600);}},wait);}
// живий статус у заставці
{let n=0;const st=$('#intro-st');const tick=setInterval(()=>{if(introDone||!st){clearInterval(tick);return;}n++;
  if(SNAP){const h=SNAP.health||{},c=(h.channels||{});const act=SNAP.tracks.filter(t=>t.status==='active').length;// так само, як лічильники вгорі: треки, без ×N
    st.textContent=(c.channels?c.live+' з '+c.channels+' джерел наживо · ':'')+(act?'цілей у повітрі: '+act:'небо поки чисте');}else st.textContent=['Підключаюсь до джерел…','Читаю монітори…','Збираю картину неба…'][n%3];},450);}
// перехід запускається, коли прийшли дані (перший знімок) і карта готова, а не за таймером; 7 с — запобіжник, якщо дані не йдуть
map.once('idle',()=>{if(SNAP)introFly(false);});
setTimeout(()=>introFly(false),7000);
{const el=$('#intro');if(el){if(!INTRO)el.remove();else el.onclick=()=>introFly(true);}}map.on('styledata',()=>{if(map.isStyleLoaded()&&!map.getSource('obl'))addOverlays();if(map.getSource('obl')&&!lastLv)syncLevels();});
/* ---------- дім: змінюється лише свідомо (Налаштування → «Змінити дім»), лише на суші України ---------- */
let homeArmT=null;
function armHome(){setHomeMode=true;$('#b-home').classList.add('on');toast('Торкніться карти, щоб позначити дім (30 с)');clearTimeout(homeArmT);
  homeArmT=setTimeout(()=>{if(setHomeMode){setHomeMode=false;$('#b-home').classList.remove('on');toast('Дім не змінено');}},30000);}
function disarmHome(){setHomeMode=false;clearTimeout(homeArmT);$('#b-home').classList.remove('on');}
map.on('click',e=>{if(!setHomeMode)return;
  // дотик по цілі, пуску, пам'ятному знаку тощо, це перегляд, а не вибір дому (02.11: дім «з'їхав» у море на крейсер «Москва»)
  const OBJ=new Set(['targets','zones','lsites','hits','memo','ru','rf-mark','by-mark','chains','preds','trails','myplaces','comets','sel','selrep','home','lpred','mepos']);
  if(map.queryRenderedFeatures([[e.point.x-12,e.point.y-12],[e.point.x+12,e.point.y+12]]).some(f=>OBJ.has(f.source)))return;
  if(!map.queryRenderedFeatures(e.point,{layers:['obl-fill']}).length){toast('Дім можна позначити лише на території України');return;}
  try{if(home)localStorage.setItem('home_prev',JSON.stringify(home));}catch(x){}
  home=[e.lngLat.lng,e.lngLat.lat];localStorage.setItem('home',JSON.stringify(home));if(FOLHOME){homeSaved=home;home=FOL.pos.slice();}disarmHome();syncHome();try{homeRow();}catch(x){}toast('Дім збережено');});
// перевірка збереженого дому: поза Україною (у морі), повертаємо попередній або просимо позначити знову
fetch('/data/raions.geojson').then(r=>r.json()).then(g=>{window.__RAGJ=g;homeObl.k=null;}).catch(()=>{});
fetch('/data/oblasts.geojson').then(r=>r.json()).then(g=>{window.__OBLGJ=g;homeObl.k=null;if(!home)return;
  const inRing=(pt,r)=>{let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const [xi,yi]=r[i],[xj,yj]=r[j];if(((yi>pt[1])!==(yj>pt[1]))&&(pt[0]<(xj-xi)*(pt[1]-yi)/(yj-yi)+xi))c=!c;}return c;};
  const inUA=pt=>g.features.some(f=>{const G=f.geometry;const P=G.type==='Polygon'?[G.coordinates]:G.coordinates;return P.some(poly=>inRing(pt,poly[0]));});
  if(inUA(home))return;let prev=null;try{prev=JSON.parse(localStorage.getItem('home_prev')||'null');}catch(x){}
  if(prev&&inUA(prev)){home=prev;localStorage.setItem('home',JSON.stringify(home));syncHome();toast('Дім був поза Україною, повернув попередній');}
  else{home=null;localStorage.removeItem('home');syncHome();toast('Дім був позначений поза Україною (у морі). Позначте його знову: Налаштування → «Змінити дім»');}}).catch(()=>{});
fetch('/api/config').then(r=>r.json()).then(c=>{CFG={...CFG,...c};window.NXCFG=CFG;syncReal3d();}).catch(()=>{}).finally(()=>setBase(base==='__init'?'night':base));

let HPDATA=null,HPPREV={},HPLOADING=false;
function syncHromadas(H){
  const keys=Object.keys(H);
  if(keys.length&&!HPDATA){if(!HPLOADING){HPLOADING=true;fetch('/data/hromadas.geojson').then(r=>r.json()).then(d=>{HPDATA=d;if(map.getSource('hp'))map.getSource('hp').setData(d);HPPREV={};lastRa='';}).catch(()=>{HPLOADING=false;});}return;}
  if(!map.getSource('hp')||!HPDATA)return;
  for(const id of Object.keys(HPPREV))if(!H[id])try{map.setFeatureState({source:'hp',id:+id},{l:0});}catch(e){}
  for(const id of keys)if(HPPREV[id]!==H[id])try{map.setFeatureState({source:'hp',id:+id},{l:H[id]});}catch(e){}
  HPPREV=Object.assign({},H);
}
/* ---------- позиція цілі в момент часу ---------- */
// вибрана ціль: остання позиція з повідомлення і поточна оцінка (див. шари selrep-*)
function selRep(serverT){const tr=sel&&SNAP.tracks.find(t=>t.id===sel),d=sel&&DISP.get(sel);
  if(!tr||!d||tr.status!=='active'||!tr.trail||!tr.trail.length)return EMPTY;
  if(isBal(tr))return {type:'FeatureCollection',features:[{type:'Feature',properties:{k:'here',l:'Повідомлення · '+fmt(tr.last||tr.first)},geometry:{type:'Point',coordinates:d.p}}]};
  const q=tr.trail[tr.trail.length-1],rp=[q[0],q[1]],age=Math.max(0,serverT-(q[2]||tr.last||serverT)),km=dist(xy(rp),xy(d.p));
  const mins=Math.round(age/60),ago=mins<2?'щойно':mins+' хв тому';
  // ціль не зрушила від названого місця: одна позначка під ціллю, без точки й пунктиру
  if(km<1)return {type:'FeatureCollection',features:[{type:'Feature',properties:{k:'here',l:'Повідомлення · '+fmt(q[2]||tr.last)+(mins>=2?' · '+ago:'')},geometry:{type:'Point',coordinates:d.p}}]};
  // на екрані зовсім поруч (дрібний масштаб): один підпис замість двох, що налазять
  {const A=map.project(rp),B=map.project(d.p);if(Math.hypot(A.x-B.x,A.y-B.y)<48)return {type:'FeatureCollection',features:[{type:'Feature',properties:{k:'here',l:'Повідомлення · '+fmt(q[2]||tr.last)+' · далі оцінка'},geometry:{type:'Point',coordinates:d.p}}]};}
  const F=[{type:'Feature',properties:{k:'rep',l:'Повідомлення · '+fmt(q[2]||tr.last)},geometry:{type:'Point',coordinates:rp}}];
  {F.push({type:'Feature',properties:{k:'ln'},geometry:{type:'LineString',coordinates:[rp,d.p]}});
    F.push({type:'Feature',properties:{k:'est',l:'Оцінка · дані '+ago},geometry:{type:'Point',coordinates:d.p}});}
  return {type:'FeatureCollection',features:F};}
function posAt(tr,serverT){
  // балістика: канали не дають координат, висоти й часу виявлення. Значок стоїть на території, яку назвали
  // («на Харків» = загроза Харкову, а не ракета над центром міста), без руху й домальованої траєкторії (03.11)
  if(isBal(tr))return {p:(tr.nopos&&tr.route&&tr.route.length)?[tr.route[0][0],tr.route[0][1]]:[tr.lon,tr.lat],hd:tr.hd};
  if(tr.status!=='active')return {p:[tr.lon,tr.lat],hd:tr.hd};
  if(!tr.speed)return {p:[tr.lon,tr.lat],hd:tr.hd};// кадр машини часу: позиція вже на той момент
  // місце лише оцінене («курсом на X», і вже в X), а нового пункту немає: далі не «ведемо» ціль навмання
  if(tr.pos_est&&!tr.route.length&&!tr.next)return {p:[tr.lon,tr.lat],hd:tr.hd};
  // зміщення за час від останньої названої позиції, та сама модель, що на сервері (map_disp, бектест):
  // шахед ≈ паспортна×0.7 перші 10 хв, далі повільніше (√часу); сервер уже просунув ціль до моменту ts
  const dm=tr.dm||[ (tr.vmap||tr.speed)/tr.speed,1];const D=sec=>{const h=Math.max(0,sec)/60;return (h<=10||dm[1]===1)?tr.speed*h/60*dm[0]:tr.speed*10/60*dm[0]*Math.pow(h/10,dm[1]);};
  const done=D(tr.ts-tr.last);
  let km=Math.max(0,D(serverT-tr.last)-done);
  const SHOW={shahed:25,molniya:4,fpv:2,fpvf:3,lancet:4,jet:6,cruise:2,ballistic:1}[tr.type]??25;// хв: ціль рухається курсом, доки не прийде нове повідомлення (зона «де може бути» росте)
  const cap=Math.max(0,D(SHOW*60)-done);
  if(!tr.route.length)km=Math.min(km,cap);
  const pts=[xy([tr.lon,tr.lat]),...tr.route.map(xy)];
  if(pts.length===1){if(tr.hd==null)return {p:[tr.lon,tr.lat],hd:tr.hd};const r=tr.hd*D2R;return {p:ll([pts[0][0]+Math.sin(r)*km,pts[0][1]+Math.cos(r)*km]),hd:tr.hd};}
  let acc=0;for(let i=1;i<pts.length;i++){const d=dist(pts[i-1],pts[i]);if(acc+d>=km){const f=(km-acc)/(d||1);const q=[pts[i-1][0]+(pts[i][0]-pts[i-1][0])*f,pts[i-1][1]+(pts[i][1]-pts[i-1][1])*f];return {p:ll(q),hd:brg(pts[i-1],pts[i])};}acc+=d;}
  // пункт пройдено, далі тим самим курсом
  const n=pts.length,h=brg(pts[n-2],pts[n-1]),r=h*D2R,ex=Math.min(km-acc,cap);
  return {p:ll([pts[n-1][0]+Math.sin(r)*ex,pts[n-1][1]+Math.cos(r)*ex]),hd:h};
}
const HD_Q={channels:[0,0,0,0,0,5,7,10,14,19,22,28,32,42,50,56,63,82,93,145],learned:[0,0,0,0,0,0,0,0,12,14,18,19,25,26,29,46,55,69,78,110],
  movement:[4,6,7,7,10,13,13,23,26,26,34,36,76,94,97,97,97,156,158,164],all:[0,0,0,0,0,4,7,12,14,18,22,26,32,42,49,56,71,88,97,150]};
// радіус «де може бути» (км, 68%): бектест 26.10–02.11, шахед ≈11 км одразу після названої позиції, +~1.1 км/хв;
// реактивний ≈14 км, +~3 км/хв (похибка назв пунктів і затримка каналів)
const UNC={uav:[11,1.1,45],shahed:[11,1.1,45],jet:[14,3,90],geran5:[14,3,90],molniya:[8,0.8,30],recon:[8,0.8,30],banderol:[14,3,90],cruise:[15,4,120]};
function uncKm(tr,ageSec){const u=UNC[tr.type];if(!u||isBal(tr))return 0;return Math.min(u[2],u[0]+u[1]*Math.max(0,ageSec)/60);}
function pToward(src,delta,dkm){const q=HD_Q[{from:'movement',course:'all'}[src]||src]||HD_Q.all;const w=Math.atan(15/Math.max(dkm,15))*180/Math.PI;
  let s=0;for(const e of q)s+=0.5*(Math.abs(delta-e)<=w)+0.5*(Math.abs(delta+e)<=w);return s/q.length;}
function homeRel(tr,p){
  if(!home||tr.nopos)return null;// канали назвали лише курс («на Харків»), де ціль зараз, невідомо: «N км від вас» було б вигадкою
  const H=xy(home),P=xy(p);const d=dist(H,P);
  let rel=null,eta=null;
  const path=[P,...tr.route.map(xy)];
  let acc=0,best={d:1e9,c:0};for(let i=1;i<path.length;i++){const a=path[i-1],b=path[i];const vx=b[0]-a[0],vy=b[1]-a[1],L2=vx*vx+vy*vy;let t=L2?((H[0]-a[0])*vx+(H[1]-a[1])*vy)/L2:0;t=Math.max(0,Math.min(1,t));const q=[a[0]+vx*t,a[1]+vy*t];const dd=dist(H,q);if(dd<best.d)best={d:dd,c:acc+Math.sqrt(L2)*t};acc+=Math.sqrt(L2);}
  // ймовірність пройти ≤15 км від дому, з розподілу похибки курсу (бектест; той самий, що й у push.py)
  const pr=tr.hd!=null?pToward(tr.hd_src,angd(tr.hd,brg(P,H)),d):0;
  let maybe=false;
  if(best.d<8){rel='route';eta=best.c/tr.speed*60;}
  else if(tr.hd!=null&&pr>=0.4){rel='heading';eta=d/tr.speed*60;}
  else if(tr.hd!=null&&pr>=0.15&&d<=150&&d/tr.speed*60<=45)maybe=true;// «можлива загроза»: широке попередження, ще не тривога
  if(rel&&(d>150||eta>45)){rel=null;eta=null;}
  if(isBal(tr)||tr.type==='rszv')eta=null;// без відстані й траєкторії пуску зворотного відліку для балістики немає
  const away=tr.hd!=null&&angd(tr.hd,brg(P,H))>100;
  return {d,rel,eta,away,maybe,p:pr,side:SIDE[Math.round((brg(H,P))/45)%8],from:FROM[Math.round((brg(H,P))/45)%8]};
}

/* ---------- кадр ---------- */
let lastLv='',lastFrame=performance.now();
function frame(now){
  {const f=window.NXPERF?NXPERF.fps():30;const tnow=performance.now();if(!f||tnow-(frame.lt||0)<1000/f-2){requestAnimationFrame(frame);return;}frame.lt=tnow;}
  const dt=Math.min(0.2,(now-lastFrame)/1000);
  if(SNAP&&map.getSource('targets')){lastFrame=now;const slow=now-(frame.sd||0)>500;if(slow)frame.sd=now;const fx=[];
    const serverT=Date.now()/1000+offset;
    const feats=[],trails=[],preds=[],threats=[],lpf=[];
    for(const tr of SNAP.tracks){
      if(TAC&&!tacOK(tr,serverT))continue;
      const {p,hd}=posAt(tr,serverT);
      let d=DISP.get(tr.id);
      if(!d||Math.abs(d.p[0]-p[0])+Math.abs(d.p[1]-p[1])>1.2){d={p:[...p],hd:hd??0};DISP.set(tr.id,d);}
      else{const k=Math.min(1,dt*3);d.p[0]+=(p[0]-d.p[0])*k;d.p[1]+=(p[1]-d.p[1])*k;if(hd!=null){let a=hd-d.hd;while(a>180)a-=360;while(a<-180)a+=360;d.hd+=a*Math.min(1,dt*2.5);}}
      const active=tr.status==='active',still=!!(tr.nopos||(tr.pos_est&&!tr.route.length&&!tr.next)),weak0=tr.conf<0.5,weak=weak0||still;// still: місце не назвали або лише оцінка без нового пункту — на мапі стоїть і напівпрозора, щоб не вдавати рух
      const rel=active&&!weak0?homeRel(tr,d.p):null;
      if(rel&&rel.rel)threats.push({tr,rel});
      // кут на ЕКРАНІ: проєктуємо точку і точку на 3 км уздовж курсу, враховує нахил і поворот карти
      const unk=tr.hd==null;let sa=0;
      if(!unk){const P=xy(d.p),r=d.hd*D2R;const A=map.project(d.p),B=map.project(ll([P[0]+Math.sin(r)*3,P[1]+Math.cos(r)*3]));sa=Math.atan2(B.x-A.x,-(B.y-A.y))/D2R;}
      const uk=active?uncKm(tr,((tr.ev&&tr.ev.age)||0)+Math.max(0,serverT-SNAP.now)):0;
      feats.push({type:'Feature',properties:{id:tr.id,type:tr.type,est:!!(tr.pos_est||tr.nopos),hd:d.hd,sa,unk,active,weak,thr:!!(rel&&rel.rel),c:TYPE_COLOR[tr.type],count:tr.count||1,next:(tr.next||'').trim()||undefined,pair:tr.pair||undefined,sk:active?(sel===tr.id?0:1):2,
        u0:uk?uk*1000/(78271.517*Math.cos(d.p[1]*D2R)):undefined},geometry:{type:'Point',coordinates:d.p}});
      const BAL=isBal(tr);
      if(active){const tail=[d.p];let P=xy(d.p),left=Math.max(14,TYPES_KMH(tr.type)*0.09);
        if(!BAL)for(const q of tr.trail.slice().reverse()){const Q=xy([q[0],q[1]]),dd=dist(P,Q);if(dd<0.5)continue;if(dd>=left){const f=left/dd;tail.push(ll([P[0]+(Q[0]-P[0])*f,P[1]+(Q[1]-P[1])*f]));left=0;break;}tail.push([q[0],q[1]]);left-=dd;P=Q;}
        if(left>0&&tr.hd!=null&&!BAL){const r=(d.hd+180)*D2R;tail.push(ll([P[0]+Math.sin(r)*left,P[1]+Math.cos(r)*left]));}
        // краплі хвоста рівномірно вздовж шляху (від цілі назад)
        const dots=[];if(tail.length>1){const X=tail.map(xy);let seg=0,acc=0;const tot=X.slice(1).reduce((s,q,i)=>s+dist(X[i],q),0),step=tot/14;
          for(let k=1;k<=14;k++){let want=k*step;while(seg<X.length-1&&acc+dist(X[seg],X[seg+1])<want){acc+=dist(X[seg],X[seg+1]);seg++;}if(seg>=X.length-1)break;const a=X[seg],b=X[seg+1],f=(want-acc)/(dist(a,b)||1);dots.push(ll([a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f]));}}
        const n=parseInt(TYPE_COLOR[tr.type].slice(1),16);
        fx.push({id:tr.id,est:!!(tr.pos_est||tr.nopos),age:((tr.ev&&tr.ev.age)||0)+Math.max(0,serverT-SNAP.now),spd:tr.speed,p:d.p,sa,hd:d.hd,type:tr.type,col:[(n>>16&255)/255,(n>>8&255)/255,(n&255)/255],weak,thr:!!(rel&&rel.rel),sel:sel===tr.id,sng:(tr.srcs||[]).length<2,tail:dots});}
      const c=TYPE_COLOR[tr.type];
      if(active&&!BAL&&tr.trail&&tr.trail.length){const q=tr.trail[tr.trail.length-1],ag=((tr.ev&&tr.ev.age)||0)+Math.max(0,serverT-SNAP.now);if(dist(xy([q[0],q[1]]),xy(d.p))>1.5)trails.push({type:'Feature',properties:{nm:1,o:Math.max(0.35,1-ag/1800)},geometry:{type:'Point',coordinates:[q[0],q[1]]}});}
      // ціль без названого місця (позиція — оцінка по пункту призначення): слабкий хвіст у бік, звідки вона летить (від фронту/кордону); лише для вибраної й тих, що летять до вас
      if(active&&!BAL&&tr.hd!=null&&(tr.pos_est||tr.nopos)&&!(tr.trail&&tr.trail.length>1)&&(sel===tr.id||(rel&&rel.rel))){const P0=xy(d.p),r0=(d.hd+180)*D2R;
        trails.push({type:'Feature',properties:{c,o:0.55},geometry:{type:'LineString',coordinates:[d.p,ll([P0[0]+Math.sin(r0)*25,P0[1]+Math.cos(r0)*25])]}});}
      // пройдений шлях, крапками за позиціями, які назвали канали; лише для вибраної цілі й тих, що летять до вас (інакше «каша»)
      if(active&&!BAL&&tr.trail&&tr.trail.length){const hi=sel===tr.id||(rel&&rel.rel);trails.push({type:'Feature',properties:{c:hi?c:'#E8ECF4',o:hi?0.95:0.22},geometry:{type:'LineString',coordinates:[...tr.trail.map(t=>[t[0],t[1]]),d.p]}});}
      const nearT=['fpv','fpvf','rszv'].includes(tr.type);// ближні цілі: завжди показуємо лінію до пункту призначення і сам пункт
      if(active&&!BAL&&(sel===tr.id||(rel&&rel.rel)||nearT)&&tr.route.length){const far=!nearT||dist(xy(d.p),xy(tr.route[0]))>3;// ближня ціль уже біля пункту — лінію не малюємо, лише мітку
        if(far)preds.push({type:'Feature',properties:{c},geometry:{type:'LineString',coordinates:nearT?[d.p,tr.route[0]]:[d.p,...tr.route]}});
        if(tr.next)preds.push({type:'Feature',properties:{c,l:tr.next},geometry:{type:'Point',coordinates:tr.route[0]}});}
      if(active&&!BAL&&(sel===tr.id||(rel&&rel.rel))&&tr.lpath&&tr.lpath.length&&!tr.route.length){const L=tr.lpath;lpf.push({type:'Feature',properties:{c},geometry:{type:'LineString',coordinates:[d.p,...L.map(x=>[x[0],x[1]])]}});
        L.forEach(x=>lpf.push({type:'Feature',properties:{c,l:'ймовірно '+x[2]+' · '+Math.round(x[3]*100)+'%'},geometry:{type:'Point',coordinates:[x[0],x[1]]}}));}
    }
    // каша геть: показуємо лише активні цілі; цілі одного типу, що на екрані лягають одна на одну,, один значок ×N
    const shown=[];for(const f of feats.filter(f=>f.properties.active).sort((a,b)=>(b.properties.weak?0:1)-(a.properties.weak?0:1))){
      const P=map.project(f.geometry.coordinates);const near=shown.find(g=>g.properties.type===f.properties.type&&Math.hypot(g._p.x-P.x,g._p.y-P.y)<34);
      if(near&&f.properties.id!==sel){// той самий тип і той самий пункт призначення, значок на значку: майже завжди одна й та сама група, про яку написали різні канали.
        // Сумувати не можна (03.11: «×8 → Варва» від восьми каналів читалось як вісім шахедів), беремо найбільшу названу кількість.
        // Різні пункти призначення: це різні цілі, тоді сума
        if(near.properties.next&&near.properties.next===f.properties.next)near.properties.count=Math.max(near.properties.count,f.properties.count);else near.properties.count+=f.properties.count;near.properties.merged=(near.properties.merged||1)+1;continue;}
      f._p=P;shown.push(f);}
    // різні типи в одній точці (03.11: шахед і «Молнія» біля Прудянки злилися в «гібрид»): розводимо значки віялом на екрані,
    // координати цілей не змінюються, зсув лише візуальний (до ~20 px)
    {const used=new Set();for(const f of shown){if(used.has(f))continue;const grp=shown.filter(g=>!used.has(g)&&Math.hypot(g._p.x-f._p.x,g._p.y-f._p.y)<26);
      if(grp.length<2)continue;const cx=grp.reduce((s,g)=>s+g._p.x,0)/grp.length,cy=grp.reduce((s,g)=>s+g._p.y,0)/grp.length,R=12+3*grp.length;
      grp.forEach((g,i)=>{used.add(g);const a=-Math.PI/2+i*2*Math.PI/grp.length,q=map.unproject([cx+R*Math.cos(a),cy+R*Math.sin(a)]);g.geometry={type:'Point',coordinates:[q.lng,q.lat]};
        const fx0=fx.find(z=>z.id===g.properties.id);if(fx0)fx0.p=[q.lng,q.lat];});}}
    for(const f of shown)delete f._p;// екранна точка (клас Point) не має йти в setData: MapLibre 5.24 падає на серіалізації, і цілі зникають
    feats.length=0;feats.push(...shown);
    const vis=new Set(shown.map(f=>f.properties.id));window.FX=fx.filter(f=>vis.has(f.id));if(TAC&&window.App06)window.FX=[];// тактичний режим: цілі показують лише стандартні символи
    {const top=threats.slice().sort((a,b)=>(a.rel.eta??999)-(b.rel.eta??999))[0];for(const f of window.FX)f.thr=!!(top&&f.id===top.tr.id);}
    window.FXHOME=(home&&!(TAC&&window.App06))?{p:home,state:$('#me').classList.contains('danger')?'danger':$('#me').classList.contains('watch')?'watch':'calm'}:null;
    if(slow)window.FXBEACONS=PREFL().launch?(SNAP.launches||[]).filter(L=>serverT-L.t<3*3600).map(L=>({p:[L.lon,L.lat]})):[];
    if(slow)map.getSource('targets').setData({type:'FeatureCollection',features:feats});
    if(slow&&map.getSource('tac')){const TF=[];
      const A6=TAC?window.App06:null;const RAIL=[];
      if(TAC)for(const f of feats){const tr=SNAP.tracks.find(x=>x.id===f.properties.id);if(!tr)continue;
        const ageS=((tr.ev&&tr.ev.age)||0)+Math.max(0,serverT-SNAP.now),mins=Math.floor(ageS/60),o=ageS>=(((SNAP.counts&&SNAP.counts.live_min)||{})[tr.type]||10)*60?0.3:1,c=f.properties.c,P=f.geometry.coordinates;// те саме правило, що в лічильнику: старша за час життя типу — напівпрозора «тінь», і в лічильник не входить
        TF.push({type:'Feature',properties:{k:'age',l:mins<1?'<1 хв':mins+' хв',o,c},geometry:{type:'Point',coordinates:P}});
        if(A6&&f.properties.active)RAIL.push({id:tr.id,aff:tacAff(tr),type:A6.MAP[tr.type]?tr.type:'unknown',n:f.properties.count,m:mins,hd:null});
        if(A6){const still=tr.nopos||(tr.pos_est&&!tr.route.length&&!tr.next);// напрямок у символі лише коли він відомий
          const key=tacImg({type:A6.MAP[tr.type]?tr.type:'unknown',affiliation:tacAff(tr),hd:(f.properties.unk||tr.hd==null||still)?null:f.properties.sa,count:f.properties.count});
          TF.push({type:'Feature',properties:{k:'sym',img:key,v:(sel===tr.id||map.getZoom()>=6.5)?(A6.MODEL[tr.type]||''):'',o},geometry:{type:'Point',coordinates:P}});
          if(f.properties.active&&o>=1)TF.push({type:'Feature',properties:{k:'hl2'},geometry:{type:'Point',coordinates:P}});// пульсація «огляд ситуації» на старті (шар прозорий, поки не запущена)
          if(sel===tr.id)TF.push({type:'Feature',properties:{k:'sel'},geometry:{type:'Point',coordinates:P}});}
        const q=tr.trail&&tr.trail.length&&tr.trail[tr.trail.length-1];
        if(q&&!isBal(tr)&&dist(xy([q[0],q[1]]),xy(P))>=1.5){TF.push({type:'Feature',properties:{k:'fact',o,c},geometry:{type:'Point',coordinates:[q[0],q[1]]}});
          TF.push({type:'Feature',properties:{k:'ln',o,c},geometry:{type:'LineString',coordinates:[[q[0],q[1]],P]}});}}
      if(TACHL&&Date.now()<TACHL.until)TF.push({type:'Feature',properties:{k:'hl'},geometry:{type:'Point',coordinates:TACHL.p}});
      map.getSource('tac').setData({type:'FeatureCollection',features:TF});
      tacRail(RAIL);
      if(map.getSource('reach'))map.getSource('reach').setData(reachData(serverT));enemyApply();}
    try{if(slow&&map.getSource('flow')){const FL=[],PU=[];const sT=serverT;
      for(const f of feats){const tr=SNAP.tracks.find(x=>x.id===f.properties.id);if(!tr)continue;
        const still=tr.nopos||(tr.pos_est&&!tr.route.length&&!tr.next)||(tr.hd==null&&!tr.route.length);
        if(still){PU.push({type:'Feature',properties:{c:TYPE_COLOR[tr.type]},geometry:f.geometry});continue;}
        const a=f.geometry.coordinates,b=posAt(tr,sT+8*60).p;if(Math.abs(a[0]-b[0])+Math.abs(a[1]-b[1])<1e-4)continue;
        FL.push({type:'Feature',properties:{c:TYPE_COLOR[tr.type]},geometry:{type:'LineString',coordinates:[a,b]}});}
      map.getSource('flow').setData({type:'FeatureCollection',features:FL});map.getSource('pulse').setData({type:'FeatureCollection',features:PU});}
    {const k=Math.floor(now/90)%FLOW_DASH.length;if(k!==frame.fk&&map.getLayer('flow')){frame.fk=k;map.setPaintProperty('flow','line-dasharray',FLOW_DASH[k]);}
     const ph=(now%2400)/2400;if(map.getLayer('pulse')&&now-(frame.pk||0)>60){frame.pk=now;map.setPaintProperty('pulse','circle-radius',8+ph*22);map.setPaintProperty('pulse','circle-stroke-opacity',0.7*(1-ph));}}}catch(e){}// «жива» мапа — лише оздоблення: її помилка не має зупиняти малювання цілей
    if(false){const thr=new Set(threats.map(x=>x.tr.id)),z=map.getZoom(),sz=Math.max(18,Math.min(70,10+z*5));
     window.GLOW=feats.map(f=>{const h=TYPE_COLOR[f.properties.type]||'#ffffff',n=parseInt(h.slice(1),16);const t=thr.has(f.properties.id);
       return {p:f.geometry.coordinates,c:t?[1,0.23,0.27]:[(n>>16&255)/255,(n>>8&255)/255,(n&255)/255],a:f.properties.weak?0.3:0.7,s:t?sz*1.9:sz,ring:t};});}
    if(slow&&map.getSource('chains')){frame.ch=now;const ch=[],ls=new Map();
      for(const L of (SNAP.launches||[])){const w=launchWhat(L);ls.set(L.site,{type:'Feature',properties:{est:false,lid:L.id,l:(isTO(L)?'НОСІЇ В ПОВІТРІ'+(L.count?' · '+cntL(L):''):'ПУСК: '+w.short+(L.count?' ×'+L.count:''))+'\nз '+L.site.replace(/ \(.*\)/,'')+(L.carrier?' ('+L.carrier+')':'')+' · '+fmt(L.t)},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});}
      for(const tr of SNAP.tracks){const L=tr.launch;if(!L||tr.status==='closed')continue;const isSel=sel===tr.id,d=DISP.get(tr.id);if(!d)continue;
        // звʼязок «пуск → ціль» — оцінка SKY, а не факт: лише для вибраної цілі. Віялом до всіх цілей це виглядало як «190 пусків з однієї точки»
        if(!isSel||tr.status!=='active')continue;
        ch.push({type:'Feature',properties:{c:isSel?(L.est?'#FF8A8A':'#FF3B3B'):'#E8ECF4',o:isSel?0.95:0.1,s:isSel},geometry:{type:'LineString',coordinates:[[L.lon,L.lat],[tr.entry[0],tr.entry[1]],...tr.trail.map(t=>[t[0],t[1]]),d.p]}});
        if(!ls.has(L.site))ls.set(L.site,{type:'Feature',properties:{est:true,l:'ймовірно · '+L.site.replace(/ \(.*\)/,'')},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});}
      map.getSource('chains').setData({type:'FeatureCollection',features:ch});map.getSource('lsites').setData({type:'FeatureCollection',features:[...ls.values()]});
}
    T3D.heads=feats.map(f=>({id:f.properties.id,type:f.properties.type,hd:f.properties.hd,active:f.properties.active,weak:f.properties.weak,p:f.geometry.coordinates}));
    if(slow){map.getSource('trails').setData({type:'FeatureCollection',features:trails});
    map.getSource('preds').setData({type:'FeatureCollection',features:preds});if(map.getSource('lpred'))map.getSource('lpred').setData({type:'FeatureCollection',features:lpf});}
    if(slow&&map.getSource('selrep'))map.getSource('selrep').setData(selRep(serverT));
    if(slow&&map.getSource('sel')){const d=sel&&DISP.get(sel);const tr=sel&&SNAP.tracks.find(t=>t.id===sel);map.getSource('sel').setData(d&&tr?{type:'FeatureCollection',features:[{type:'Feature',properties:{c:TYPE_COLOR[tr.type]},geometry:{type:'Point',coordinates:d.p}}]}:EMPTY);}
    if(follow&&sel&&!map.isMoving()){const d=DISP.get(sel);if(d){const c=map.getCenter();const k=0.12;map.jumpTo({center:[c.lng+(d.p[0]-c.lng)*k,c.lat+(d.p[1]-c.lat)*k]});}}
    if(slow)renderBanner(threats);
    if(map.getSource('ticks')&&now-(frame.tk||0)>800){frame.tk=now;const tk=[];const serverT=Date.now()/1000+offset;
      for(const tr of SNAP.tracks){if(tr.status!=='active'||sel!==tr.id||['fpv','fpvf','lancet','molniya'].includes(tr.type))continue;const c=TYPE_COLOR[tr.type];  // 08.11: у короткодальніх жодних «+5 хв»
        let last=map.project(posAt(tr,serverT).p);
        for(const m of [5,10,15]){const q=posAt(tr,serverT+m*60).p,P=map.project(q);if(Math.hypot(P.x-last.x,P.y-last.y)<46)continue;last=P;tk.push({type:'Feature',properties:{c,l:'+'+m+' хв'},geometry:{type:'Point',coordinates:q}});}}
      map.getSource('ticks').setData({type:'FeatureCollection',features:tk});}
    if(now-(frame.me||0)>700){frame.me=now;renderMe(threats);}
    if(sel&&now-(frame.sh||0)>500){frame.sh=now;fillSheet();}
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

function syncLevels(){
  if(!SNAP||!map.getSource('obl'))return;const key=JSON.stringify(SNAP.levels);if(key===lastLv)return;lastLv=key;lastRa='';
  fetchOblNames().then(names=>{if(!map.getSource('obl'))return;names.forEach(n=>{try{map.setFeatureState({source:'obl',id:n},{lvl:SNAP.levels[n]||0});}catch(e){lastLv='';}});});
}
let RA=null,lastRa='';
function inRing(r,x,y){let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const [xi,yi]=r[i],[xj,yj]=r[j];if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/((yj-yi)||1e-12)+xi))c=!c;}return c;}
function raionOf(lon,lat){if(!RA)return -1;for(const r of RA){if(lon<r.bb[0]||lon>r.bb[2]||lat<r.bb[1]||lat>r.bb[3])continue;for(const pl of r.polys)if(inRing(pl[0],lon,lat))return r.i;}return -1;}
fetch('/data/raions.geojson').then(r=>r.json()).then(j=>{RA=j.features.map((f,i)=>{const g=f.geometry;const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;let bb=[180,90,-180,-90];polys.forEach(pl=>pl[0].forEach(([x,y])=>{bb[0]=Math.min(bb[0],x);bb[1]=Math.min(bb[1],y);bb[2]=Math.max(bb[2],x);bb[3]=Math.max(bb[3],y);}));return {i,n:f.properties.n,polys,bb};});});
// Місто з власним статусом (Харків) лежить усередині району, але тривога в районі його не зафарбовує (як в офіційній мапі):
// вирізаємо межі такої громади з району на мапі, щоб жовте не накривало місто, де тривоги немає (04.11)
let CUTK='';
function cutSep(ids){
  if(!window.__RAGJ||!map.getSource('ra')||!ids.length)return;
  if(!HPDATA){loadHP().then(d=>{if(d)cutSep(ids);});return;}
  const key=JSON.stringify(ids);if(key===CUTK)return;
  const inR=(pt,r)=>{let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const [xi,yi]=r[i],[xj,yj]=r[j];if(((yi>pt[1])!==(yj>pt[1]))&&(pt[0]<(xj-xi)*(pt[1]-yi)/(yj-yi)+xi))c=!c;}return c;};
  const g=JSON.parse(JSON.stringify(window.__RAGJ));
  for(const id of ids){
    const h=HPDATA.features[+id];if(!h||h.geometry.type!=='Polygon')continue;
    const ring=h.geometry.coordinates[0],pr=ring[0];
    for(const f of g.features){const G=f.geometry,P=G.type==='Polygon'?[G.coordinates]:G.coordinates;
      for(const pl of P)if(inR(pr,pl[0])&&!pl.slice(1).some(x=>inR(pr,x))&&pl[0].length>ring.length)pl.push(ring);}
  }
  try{map.getSource('ra').setData(g);CUTK=key;lastRa='';}catch(e){}
}
let raSnapSeen=null,raSrcSeen=null;
function syncRaions(){
  if(!SNAP||!RA||!map.getSource('ra'))return;
  // таймер кожні 3 с не перемальовує громади й райони, якщо знімок і джерело не змінились
  {const hs=map.getSource('hrom')||null;if(SNAP===raSnapSeen&&hs===raSrcSeen)return;raSnapSeen=SNAP;raSrcSeen=hs;}const lv={};const up=(i,v)=>{if(i>=0&&(lv[i]||0)<v)lv[i]=v;};
  const O=SNAP.official||{};const rl=O.raion_levels||{};RA.forEach(r=>{if(rl[r.n])up(r.i,rl[r.n]);});
  if(map.getSource('hrom'))map.getSource('hrom').setData({type:'FeatureCollection',features:(O.points||[]).map(([lo,la,n,l,poly])=>({type:'Feature',properties:{l,n,poly:poly||0},geometry:{type:'Point',coordinates:[lo,la]}}))});
  syncHromadas(O.hromadas||{});cutSep(SNAP.sep||O.sep||[]);
  // райони фарбуються лише за офіційними тривогами (alerts.in.ua)
  const key=JSON.stringify(lv);if(key===lastRa)return;lastRa=key;
  RA.forEach(r=>{try{map.setFeatureState({source:'ra',id:r.i},{lvl:lv[r.i]||0});}catch(e){lastRa='';}});
  syncHolo(lv);
}
setInterval(syncRaions,3000);
let OBLF=null;fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>{OBLF=j.features;try{tacOblFill();}catch(e){}lastRa='';syncOutside();});
// поза Україною, притемнено, щоб країна «світилася» на карті (маска готується на сервері)
function syncOutside(){}
function syncHolo(lv){if(!map.getSource('holo')||!RA)return;const F=[];
  RA.forEach(r=>{const l=lv[r.i];if(l)F.push({type:'Feature',properties:{l},geometry:r.polys.length===1?{type:'Polygon',coordinates:r.polys[0]}:{type:'MultiPolygon',coordinates:r.polys}});});
  const L=(SNAP&&SNAP.levels)||{};if(OBLF)OBLF.forEach(f=>{const l=L[f.properties.n];if(l)F.push({type:'Feature',properties:{l},geometry:f.geometry});});
  map.getSource('holo').setData({type:'FeatureCollection',features:F});}
let OBLN=null;function fetchOblNames(){if(OBLN)return Promise.resolve(OBLN);return fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>OBLN=j.features.map(f=>f.properties.n));}
function syncHome(){clearTimeout(window.__wpT);window.__wpT=setTimeout(()=>window.webPushSync&&webPushSync(false),1500);if(map.getSource('home'))map.getSource('home').setData(realHome()?{type:'FeatureCollection',features:[{type:'Feature',properties:{},geometry:{type:'Point',coordinates:realHome()}}]}:EMPTY);}
function syncAvia(){if(!SNAP||!map.getSource('avia'))return;const A=SNAP.avia||[];const P=[],Z=[],L=[];
  A.forEach(a=>{const c=[a.lon,a.lat];const _d=t=>Math.hypot((t[0]-a.lon)*Math.cos(a.lat*Math.PI/180),t[1]-a.lat);const _c=(a.to&&a.to.length?a.to:(SNAP.zones||[]).flatMap(z=>z.places.map(q=>[q[0],q[1]])));const tgt=_c.length?_c.reduce((b,t)=>_d(t)<_d(b)?t:b):[31.5,49];const r=Math.atan2((tgt[0]-a.lon)*Math.cos(a.lat*Math.PI/180),tgt[1]-a.lat)*180/Math.PI;
    P.push({type:'Feature',properties:{ai:A.indexOf(a),r,f:a.fade||0,l:(a.kab?'пуски КАБ':'тактична авіація')+' · '+hm(a.t)+'\n'+a.area},geometry:{type:'Point',coordinates:c}});
    const ring=[];for(let i=0;i<=40;i++){const g=i/40*2*Math.PI,R=38;ring.push([a.lon+R/111/Math.cos(a.lat*Math.PI/180)*Math.sin(g),a.lat+R/111*Math.cos(g)]);}
    Z.push({type:'Feature',properties:{f:a.fade||0},geometry:{type:'Polygon',coordinates:[ring]}});
    (a.to||[]).forEach(t=>L.push({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[c,t]}}));});
  map.getSource('avia').setData({type:'FeatureCollection',features:P});map.getSource('avia-z').setData({type:'FeatureCollection',features:Z});map.getSource('avia-l').setData({type:'FeatureCollection',features:L});}
const hm=t=>new Date(t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
function kabInfo(z){const nm=k=>(SNAP.sources&&SNAP.sources[k]&&SNAP.sources[k].name)||k;const L=z.launch;
  const where=[...new Set(z.places.map(p=>p[2]))].join(', ')+(z.obl?' · '+z.obl+' обл.':'');
  return '<div class="kp"><small>ЗАГРОЗА КАБ</small><h4>'+esc(where)+'</h4>'+
   '<div class="kp-r"><span>Пуски</span><b>'+(L?esc(L.area)+(L.avia_t?' · авіація з '+hm(L.avia_t):''):'район уточнюється')+'</b></div>'+
   '<div class="kp-r"><span>Перша згадка</span><b>'+hm(z.t)+'</b></div>'+
   '<div class="kp-r"><span>Остання</span><b>'+hm(z.last)+(z.n>1?' · повідомлень: '+z.n:'')+'</b></div>'+
   '<div class="kp-r"><span>Зникне</span><b>~'+hm(z.until)+', якщо не буде нових пусків</b></div>'+
   ((z.ev||[]).length?'<div class="kp-ev">'+z.ev.slice(-3).reverse().map(e=>'<div><i>'+hm(e.t)+' · '+esc(nm(e.src))+'</i>'+esc(e.text||'')+'</div>').join('')+'</div>':'')+'</div>';}
function aviaInfo(a){const nm=k=>(SNAP.sources&&SNAP.sources[k]&&SNAP.sources[k].name)||k;
  return '<div class="kp"><small>ВОРОЖА ТАКТИЧНА АВІАЦІЯ</small><h4>'+esc(a.area)+'</h4>'+
   '<div class="kp-r"><span>Що</span><b>'+esc(a.platform)+(a.kab?' · пуски КАБ':'')+'</b></div>'+
   '<div class="kp-r"><span>Напрямок</span><b>'+esc(a.obl)+' обл.</b></div>'+
   (a.targets&&a.targets.length?'<div class="kp-r"><span>КАБ на</span><b>'+esc(a.targets.join(', '))+'</b></div>':'')+
   '<div class="kp-r"><span>Перша згадка</span><b>'+hm(a.first)+'</b></div>'+
   '<div class="kp-r"><span>Остання</span><b>'+hm(a.t)+(a.n>1?' · повідомлень: '+a.n:'')+'</b></div>'+
   '<div class="kp-r"><span>Зникне</span><b>~'+hm(a.until)+', якщо не буде нових згадок</b></div>'+
   '<div class="kp-r"><span>Позиція</span><b>типовий район пусків (оцінка), не точне місце літака</b></div>'+
   ((a.ev||[]).length?'<div class="kp-ev">'+a.ev.slice(-3).reverse().map(e=>'<div><i>'+hm(e.t)+' · '+esc(nm(e.src))+'</i>'+esc(e.text||'')+'</div>').join('')+'</div>':'')+'</div>';}
// що саме пустили: тип з повідомлення → типи цілей, які вже привʼязані до цього пуску → типове для місця (позначено як припущення)
// носії стратегічної авіації в повітрі (stage=takeoff) — не пуск: кількість — борти, ракет ще не повідомлено
const isTO=L=>L&&L.stage==='takeoff';const cntL=L=>L.count?(isTO(L)?L.count+' борт.':'×'+L.count):'';
function launchWhat(L){const N={uav:'БпЛА невизначеного типу',shahed:'шахеди',jet:'реактивні БпЛА',molniya:'«Молнії»',cruise:'крилаті ракети',ballistic:'балістика',kab:'КАБи',geran5:'«Герань-5»',banderol:'«Бандеролі»'};
  if(L.type)return {short:N[L.type]||L.type,full:(N[L.type]||L.type)+' (так написали канали)'};
  const linked=[...new Set((SNAP.tracks||[]).filter(t=>t.launch&&t.launch.id===L.id&&!t.launch.est).map(t=>t.type))];
  if(linked.length)return {short:linked.map(t=>N[t]||t).join(' + '),full:linked.map(t=>N[t]||t).join(' + ')+' (за цілями, що вже летять від цього пуску)'};
  const st=(L.site_types||[]).filter(t=>t!=='kab'||L.site_kind==='аеродром');
  if(st.length===1)return {short:'ймовірно '+(N[st[0]]||st[0]),full:'тип не названо; звідси зазвичай пускають '+(N[st[0]]||st[0])};
  return {short:'тип не названо',full:'тип не названо'+(st.length?'; звідси пускають: '+st.map(t=>N[t]||t).join(', '):'')};}
let kabPop=null;
/* ---------- стратегічна авіація і МіГ-31К: групи мініатюр, шлях, пуски, напрямки (оцінка SKY) ---------- */
const STRAT_PATH={tu95:'M0,-42 L3,-36 L4,-8 L40,2 L40,8 L4,6 L3,26 L14,34 L14,38 L0,35 L-14,38 L-14,34 L-3,26 L-4,6 L-40,8 L-40,2 L-4,-8 L-3,-36 Z',
  tu160:'M0,-44 L3,-34 L5,-14 L38,22 L36,28 L6,14 L4,30 L12,38 L12,42 L0,38 L-12,42 L-12,38 L-4,30 L-6,14 L-36,28 L-38,22 L-5,-14 L-3,-34 Z',
  tu22:'M0,-42 L3,-30 L4,-10 L32,18 L30,24 L5,12 L4,28 L12,36 L12,40 L0,36 L-12,40 L-12,36 L-4,28 L-5,12 L-30,24 L-32,18 L-4,-10 L-3,-30 Z',
  mig31:'M0,-44 L3,-32 L5,-14 L34,10 L34,16 L6,10 L7,30 L16,40 L2,38 L0,34 L-2,38 L-16,40 L-7,30 L-6,10 L-34,16 L-34,10 L-5,-14 L-3,-32 Z'};
const STRAT_TAG={ground:'НА АЕРОДРОМІ',landed:'ПОСАДКА',takeoff:'ЗЛІТ · можливий бойовий',transit:'ВИЛІТ НЕ БОЙОВИЙ\nПЕРЕДИСЛОКАЦІЯ',line:'ВИЛІТ БОЙОВИЙ · на рубежі пуску',launch:'ВИЛІТ БОЙОВИЙ · ПУСК'};
const stratCombat=g=>g.stage==='line'||g.stage==='launch';
const STRAT_STAGE={ground:'на аеродромі',landed:'посадка',takeoff:'зліт',transit:'передислокація (переліт між аеродромами, не бойовий)',line:'на пусковому рубежі',launch:'пуск'};
let STRAT=[];const STRAT_SEEN=new Set();let stratFx=[];let stratRaf=0;
function stratImages(){for(const k in STRAT_PATH){const id='st-'+k;if(map.hasImage(id))continue;const c=document.createElement('canvas');c.width=c.height=192;const x=c.getContext('2d');x.translate(96,96);x.scale(2,2);
  const p=new Path2D(STRAT_PATH[k]);x.shadowColor='#FF8A1F';x.shadowBlur=9;x.fillStyle='#FFB347';x.fill(p);x.shadowBlur=0;x.lineWidth=2.2;x.strokeStyle='#fff';x.stroke(p);
  map.addImage(id,x.getImageData(0,0,192,192),{pixelRatio:6});
  // справжній силует літака (вид згори) замінює запасний контур, щойно завантажився
  const im=new Image();im.onload=()=>{try{const q=document.createElement('canvas');q.width=q.height=192;const g=q.getContext('2d');g.shadowColor='rgba(255,138,31,.85)';g.shadowBlur=10;g.drawImage(im,0,0,192,192);g.shadowBlur=0;g.drawImage(im,0,0,192,192);
    if(map.hasImage(id))map.updateImage(id,g.getImageData(0,0,192,192));}catch(e){}};im.src='/sprites/s-'+k+'.png';}}
function stratAL(l){if(!map.getLayer(l.id))map.addLayer(l);}
function stratEnsure(){if(map.getLayer('strat'))return true;try{return stratBuild();}catch(e){return false;}}
function stratBuild(){stratImages();
  ['strat','strat-l','strat-fx','strat-ring'].forEach(id=>{if(!map.getSource(id))map.addSource(id,{type:'geojson',data:EMPTY});});
  stratAL({id:'strat-dir',type:'line',source:'strat-l',filter:['==',['get','k'],'dir'],paint:{'line-color':'#F5B83D','line-width':1.6,'line-dasharray':[1.4,1.8],'line-opacity':0.85}});
  stratAL({id:'strat-route',type:'line',source:'strat-l',filter:['==',['get','k'],'route'],paint:{'line-color':'#FF8A1F','line-width':1.8,'line-dasharray':[3,2],'line-opacity':0.85}});
  stratAL({id:'strat-rlabel',type:'symbol',source:'strat-l',filter:['==',['get','k'],'rlabel'],layout:{'symbol-placement':'line','text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,-0.9],'symbol-spacing':420},paint:{'text-color':'#FFB347','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  stratAL({id:'strat-rarrow',type:'symbol',source:'strat-l',filter:['==',['get','k'],'rarrow'],layout:{'symbol-placement':'line','text-field':'▶','text-font':['Noto Sans Bold'],'text-size':15,'symbol-spacing':90,'text-keep-upright':false,'text-rotation-alignment':'map','text-allow-overlap':true,'text-ignore-placement':true},paint:{'text-color':'#FF8A1F','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.4}});
  stratAL({id:'strat-rpti',type:'symbol',source:'strat-l',filter:['all',['==',['get','k'],'rpt'],['!=',['get','ic'],null]],layout:{'icon-image':['concat','st-',['get','ic']],'icon-size':['interpolate',['linear'],['zoom'],3,0.8,6,1.1,9,1.5],'icon-rotate':['get','r'],'icon-rotation-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true,'text-field':['get','t'],'text-font':['Noto Sans Bold'],'text-size':12,'text-anchor':'bottom','text-offset':[0,-2.2],'text-allow-overlap':true},paint:{'icon-opacity':1,'text-color':'#FFB347','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  stratAL({id:'strat-rpt',type:'circle',source:'strat-l',filter:['==',['get','k'],'rpt'],paint:{'circle-radius':4,'circle-color':'#0b0f16','circle-stroke-color':'#FF8A1F','circle-stroke-width':2}});
  stratAL({id:'strat-rptl',type:'symbol',source:'strat-l',filter:['==',['get','k'],'rpt'],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-anchor':'top','text-offset':[0,1.9],'text-allow-overlap':true,'text-ignore-placement':true},paint:{'text-color':['coalesce',['get','tc'],'#fff'],'text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  stratAL({id:'strat-trail',type:'line',source:'strat-l',filter:['==',['get','k'],'trail'],layout:{'line-cap':'round'},paint:{'line-color':'#FFB347','line-width':2.6,'line-opacity':0.9}});
  stratAL({id:'strat-ring',type:'circle',source:'strat-ring',paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,14,8,30],'circle-color':'rgba(255,60,60,.12)','circle-stroke-color':'#FF4D4D','circle-stroke-width':1.6,'circle-stroke-opacity':0.9}});
  stratAL({id:'strat-dirt',type:'symbol',source:'strat-l',filter:['all',['==',['get','k'],'dirpt']],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':10.5,'text-anchor':'left','text-offset':[0.6,0],'text-allow-overlap':false},paint:{'text-color':'#F5B83D','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  stratAL({id:'strat',type:'symbol',source:'strat',layout:{'icon-image':['concat','st-',['get','ic']],'icon-size':['interpolate',['linear'],['zoom'],3,0.55,6,0.85,9,1.2],'icon-rotate':['get','r'],'icon-rotation-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true,
    'icon-offset':['get','off'],'text-field':['step',['zoom'],'',2.5,['get','l']],'text-font':['Noto Sans Bold'],'text-size':12,'text-max-width':16,'text-offset':[0,2.4],'text-anchor':'top','text-optional':true},
    paint:{'icon-opacity':['get','o'],'text-color':['coalesce',['get','tc'],'#FFC878'],'text-halo-color':'rgba(0,0,0,.92)','text-halo-width':1.8}});
  stratAL({id:'strat-fxl',type:'line',source:'strat-fx',filter:['==',['geometry-type'],'LineString'],layout:{'line-cap':'round'},paint:{'line-color':'#FFD27A','line-width':['get','w'],'line-opacity':['get','o'],'line-blur':1.2}});
  stratAL({id:'strat-fxp',type:'circle',source:'strat-fx',filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':['get','r'],'circle-color':['get','c'],'circle-opacity':['get','o'],'circle-blur':0.7}});
  if(TAC&&map.getLayer('strat')){const L=(k,v)=>map.setLayoutProperty('strat',k,v);L('icon-image',['get','img']);L('icon-rotate',0);L('icon-offset',[0,0]);L('icon-size',['interpolate',['linear'],['zoom'],3,0.7,7,0.9,10,1.1]);L('text-offset',[0,2.1]);map.setPaintProperty('strat','text-color','#E6EBF2');}
  if(!map._stratClick){map._stratClick=1;map.on('click','strat',e=>{const f=e.features&&e.features[0];if(!f)return;const g=STRAT.find(x=>x.id===f.properties.gid);if(!g)return;
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'330px',className:'kab-pop avia-pop',offset:18}).setLngLat([g.lon,g.lat]).setHTML(stratInfo(g)).addTo(map);
    if(g.path&&g.path.length>1){const a=g.path[0],b=g.path[1];map.fitBounds([[Math.min(a[0],b[0]),Math.min(a[1],b[1])],[Math.max(a[0],b[0]),Math.max(a[1],b[1])]],{padding:{top:150,bottom:Math.min(innerHeight*0.45,380),left:50,right:50},maxZoom:7,duration:900});}});
  map.on('click','strat-rpti',e=>{const f=e.features&&e.features[0];if(!f)return;const g=STRAT.find(x=>x.id===f.properties.gid);if(!g)return;if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'330px',className:'kab-pop avia-pop',offset:18}).setLngLat(f.geometry.coordinates).setHTML(stratInfo(g)).addTo(map);});
  map.on('mouseenter','strat',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','strat',()=>map.getCanvas().style.cursor='');}return true;}
function stratWhere(g){const s=STRAT_STAGE[g.stage]||g.stage;
  if(g.stage==='transit')return 'переліт '+(g.origin||'?')+' → '+(g.dest||'?');
  if(g.stage==='takeoff')return 'зліт'+(g.origin?' з аеродрому «'+g.origin+'»':'');
  if(g.stage==='line')return 'вийшли на пусковий рубіж'+(g.site?' · '+g.site:'');
  if(g.stage==='launch')return 'пуск'+(g.site?' · '+g.site:'');
  return s+(g.site?' «'+g.site+'»':'');}
function stratInfo(g){const nm=k=>(SNAP.sources&&SNAP.sources[k]&&SNAP.sources[k].name)||k;
  const cmb=g.stage==='line'||g.stage==='launch',trn=g.stage==='transit';
  return '<div class="kp"><small>СТРАТЕГІЧНА АВІАЦІЯ</small><h4>'+esc(g.name)+(g.n?' ×'+g.n:'')+'</h4>'+
   '<div class="kp-r"><span>Що</span><b style="color:'+(cmb?'#FF3B3B':'inherit')+'">'+(cmb?'ВИЛІТ БОЙОВИЙ':trn?'ВИЛІТ НЕ БОЙОВИЙ · передислокація':g.stage==='ground'?'На аеродромі'+(g.site?' «'+esc(g.site)+'»':'')+(g.n?' · '+g.n+' борт'+(g.n>1&&g.n<5?'и':g.n>=5?'ів':''):'')+' · про зліт чи пуск не повідомлено':esc(STRAT_TAG[g.stage]||''))+'</b></div>'+
   (g.origin||g.dest?'<div class="kp-r"><span>Куди</span><b>'+esc(g.origin||'?')+' → '+esc(g.dest||'?')+(g.km?' · ~'+g.km+' км':'')+'</b></div>':'')+
   (g.depart?'<div class="kp-r"><span>Коли</span><b>вильот ~'+hm(g.depart)+(g.eta?' · прибуття ~'+hm(g.eta)+' (розрахунок)':'')+'</b></div>':'')+
   '<div class="kp-r"><span>Стан</span><b>'+esc(stratWhere(g))+'</b></div>'+
   '<div class="kp-r"><span>Остання згадка</span><b>'+hm(g.t)+'</b></div>'+
   (g.missiles?'<div class="kp-r"><span>Пуски</span><b>'+g.missiles+' ракет (за повідомленням)</b></div>':'')+
   (g.dirs&&g.dirs.length?'<div class="kp-r"><span>Можливі напрямки</span><b>'+g.dirs.map(d=>esc(d.label)).join(', ')+'</b></div>':'')+
   '<div class="kp-r"><span>Позиція</span><b>'+(g.est?'оцінка за часом і швидкістю, не радар':'за повідомленням каналів')+'</b></div>'+
   (g.dirs&&g.dirs.length?'<div class="kp-r"><span>Напрямки</span><b>оцінка SKY за курсом і дальністю, не прогноз</b></div>':'')+
   ((g.ev||[]).length?'<div class="kp-ev">'+g.ev.slice(-3).reverse().map(e=>'<div><i>'+hm(e.t)+' · '+esc(nm(e.src))+'</i>'+esc(e.text||'')+'</div>').join('')+'</div>':'')+'</div>';}
function stratOffsets(n){const out=[];for(let i=0;i<n;i++){const row=Math.ceil(i/2),side=i%2?-1:1;out.push([i?side*row*24:0,row*30]);}return out;}
function stratRot(g,from){try{if(g.path&&g.path.length>1){const m=ll=>{const x=ll[0],y=Math.log(Math.tan(Math.PI/4+ll[1]*Math.PI/360))*180/Math.PI;return [x,y];},a=m(from||[g.lon,g.lat]),b=m(g.path[1]);if(Math.abs(b[0]-a[0])+Math.abs(b[1]-a[1])>1e-6)return Math.atan2(b[0]-a[0],b[1]-a[1])*180/Math.PI;}}catch(e){}return g.hd||0;}
function syncStrat(){if(!SNAP||!stratEnsure())return;STRAT=SNAP.strat||[];const P=[],L=[],R=[];
  STRAT.forEach(g=>{const act=g.stage==='takeoff'||g.stage==='transit'||g.stage==='line'||g.stage==='launch';const cnt=Math.max(1,Math.min(9,g.n||1));const o=stratOffsets(cnt);
    const ageF=Math.max(0.35,1-Math.max(0,(Date.now()/1000+offset-g.t))/(g.until-g.t0+1)*0.5);
    if(TAC&&window.App06){const A6=window.App06,mk=g.icon&&A6.MAP[g.icon]?g.icon:'unknown',mv=(g.stage==='takeoff'||g.stage==='transit'||g.stage==='line'||g.stage==='launch')&&g.hd!=null;
      const key=tacImg({type:mk,affiliation:A6.affiliationOf({indep:(g.srcs||[]).length}),hd:mv?g.hd:null,count:g.n||null});
      P.push({type:'Feature',properties:{gid:g.id,img:key,o:act?1:0.6*ageF+0.2,l:(g.name||A6.MODEL[mk]||'')+' · '+(STRAT_STAGE[g.stage]||'')+(g.n===null?' · кількість невідома':'')+'\n'+hm(g.t)},geometry:{type:'Point',coordinates:[g.lon,g.lat]}});}
    else o.forEach((off,i)=>P.push({type:'Feature',properties:{gid:g.id,ic:g.icon,tc:stratCombat(g)?'#FF3B3B':undefined,r:stratRot(g),off,o:act?1:0.6*ageF+0.2,l:i===0?(g.name+(g.n>9?' ×'+g.n:'')+'\n'+(STRAT_TAG[g.stage]||STRAT_STAGE[g.stage]||'')+(g.n===null?' · кількість невідома':'')+'\n'+hm(g.t)):''},geometry:{type:'Point',coordinates:[g.lon,g.lat]}}));
    if(g.path&&g.path.length>1){// маршрут перельоту: пройдене — суцільна лінія (trail), попереду — пунктир до аеродрому призначення, з підписом уздовж лінії й назвами кінців
      const rem=g.stage==='transit'?[[g.lon,g.lat],g.path[1]]:g.path,lbl=(g.name||'Літак')+(g.stage==='transit'?' · передислокація, не бойовий виліт':'')+': '+(g.origin||'?')+' → '+(g.dest||'?')+' (розрахунок)';
      L.push({type:'Feature',properties:{k:'route'},geometry:{type:'LineString',coordinates:rem}});
      L.push({type:'Feature',properties:{k:'rlabel',l:lbl},geometry:{type:'LineString',coordinates:rem}});
      const nn=g.n?' ×'+g.n:'';
      L.push({type:'Feature',properties:{k:'rarrow'},geometry:{type:'LineString',coordinates:rem}});
      if(g.origin)L.push({type:'Feature',properties:{k:'rpt',gid:g.id,l:'1 · '+g.origin+' (вильот)\n'+(STRAT_TAG[g.stage]||''),ic:g.icon,tc:stratCombat(g)?'#FF3B3B':undefined,r:stratRot(g,g.path[0]),t:g.n?'×'+g.n:''},geometry:{type:'Point',coordinates:g.path[0]}});
      if(g.dest)L.push({type:'Feature',properties:{k:'rpt',gid:g.id,l:'2 · '+g.dest+' (призначення)\n'+(STRAT_TAG[g.stage]||''),ic:g.icon,tc:stratCombat(g)?'#FF3B3B':undefined,r:stratRot(g,g.path[0]),t:g.n?'×'+g.n:''},geometry:{type:'Point',coordinates:g.path[1]}});}
    if(g.trail&&g.trail.length>1)L.push({type:'Feature',properties:{k:'trail'},geometry:{type:'LineString',coordinates:g.trail}});
    (g.dirs||[]).forEach(d=>{L.push({type:'Feature',properties:{k:'dir'},geometry:{type:'LineString',coordinates:[[g.lon,g.lat],[d.lon,d.lat]]}});
      L.push({type:'Feature',properties:{k:'dirpt',l:d.label+' ~'+d.km+' км'},geometry:{type:'Point',coordinates:[d.lon,d.lat]}});});
    if(g.stage==='line'||g.stage==='launch')R.push({type:'Feature',properties:{},geometry:{type:'Point',coordinates:[g.lon,g.lat]}});
    // пуск: ефект вильоту ракет з мініатюр (раз на пуск, лише свіжий)
    const key=g.id+'|'+(g.launch_t||0);if(g.stage==='launch'&&g.launch_t&&!STRAT_SEEN.has(key)){STRAT_SEEN.add(key);if(Date.now()/1000+offset-g.launch_t<600)stratLaunchFx(g,cnt);}});
  map.getSource('strat').setData({type:'FeatureCollection',features:P});map.getSource('strat-l').setData({type:'FeatureCollection',features:L});map.getSource('strat-ring').setData({type:'FeatureCollection',features:R});}
// ракети виходять із кожного літака групи вздовж курсу (або на першу ймовірну ціль), 4,5 с, з вогняним хвостом
function stratLaunchFx(g,cnt){if(TAC)return;const hd=(g.dirs&&g.dirs[0])?Math.atan2((g.dirs[0].lon-g.lon)*Math.cos(g.lat*Math.PI/180),g.dirs[0].lat-g.lat):(g.hd||0)*Math.PI/180;
  const per=Math.min(3,Math.max(1,Math.round((g.missiles||cnt*2)/cnt)));const t0=performance.now();
  const sp=Math.PI/180*0.9,sign=[0,-1,1];
  for(let i=0;i<cnt;i++)for(let j=0;j<per;j++)stratFx.push({lon:g.lon+(i%2?-1:1)*Math.ceil(i/2)*0.06*Math.cos(hd),lat:g.lat,h:hd+(per>1?sign[j%3]*sp:0),t0:t0+i*90+j*140,life:4500,v:0.0016});
  if(!stratRaf)stratRaf=requestAnimationFrame(stratTick);}
function stratTick(){stratRaf=0;if(!map.getSource('strat-fx')){stratFx=[];return;}const now=performance.now(),F=[];stratFx=stratFx.filter(m=>now-m.t0<m.life+200);
  for(const m of stratFx){const a=now-m.t0;if(a<0)continue;const d=Math.max(0,a)*m.v*0.05,k=a/m.life;const dx=Math.sin(m.h),dy=Math.cos(m.h),cl=Math.cos(m.lat*Math.PI/180)||1;
    const lon=m.lon+dx*d/cl,lat=m.lat+dy*d,o=Math.max(0,1-k*k);
    F.push({type:'Feature',properties:{r:5+4*(1-k),c:a<400?'#FFFFFF':'#FF9A2E',o},geometry:{type:'Point',coordinates:[lon,lat]}});
    const tl=Math.min(d,0.5);F.push({type:'Feature',properties:{w:2.4*(1-k)+0.6,o:o*0.8},geometry:{type:'LineString',coordinates:[[lon-dx*tl/cl,lat-dy*tl],[lon,lat]]}});}
  map.getSource('strat-fx').setData({type:'FeatureCollection',features:F});if(stratFx.length)stratRaf=requestAnimationFrame(stratTick);}

function syncZones(){syncAvia();try{syncStrat();}catch(e){console.warn(e);}if(!SNAP||!map.getSource('zones'))return;map.getSource('zones').setData({type:'FeatureCollection',features:SNAP.zones.flatMap((z,zi)=>z.places.map(([lo,la])=>({type:'Feature',properties:{zi,r:(z.launch&&z.launch.lat!=null)?Math.atan2((lo-z.launch.lon)*Math.cos(la*Math.PI/180),la-z.launch.lat)*180/Math.PI:180},geometry:{type:'Point',coordinates:[lo,la]}})))});}

/* ---------- лічильники, статус ---------- */
const CNTI={};
const CNT_LBL={uav:'Невизн.',lancet:'«ланцети»',shahed:'шахеди',jet:'реактивні',cruise:'крилаті',ballistic:'балістика',molniya:'«молнії»',kab:'КАБи',geran5:'Герань-5',banderol:'бандеролі',rszv:'РСЗВ',fpv:'FPV',fpvf:'FPV-оптоволокно',recon:'розвідники'};
// натиск на лічильник, показати всі цілі цього типу
function focusType(t){const nowS=Date.now()/1000+offset;const LM=(SNAP.counts&&SNAP.counts.live_min)||{};const fr=x=>(((x.ev&&x.ev.age)||0)+Math.max(0,nowS-SNAP.now))<(LM[x.type]||10)*60;const all=SNAP.tracks.filter(x=>x.status==='active'&&x.type===t);const ps=all.map(x=>(DISP.get(x.id)||{p:[x.lon,x.lat]}).p);if(!all.length)return;
  const b=ps.reduce((a,p)=>a.extend(p),new maplibregl.LngLatBounds(ps[0],ps[0]));map.fitBounds(b,{padding:{top:140,bottom:180,left:60,right:60},maxZoom:9,duration:900});toast((TYPE_NAME[t]||t)+': '+ps.length);
  // підсвітка на 3.5 с: цілі цього типу пульсують кільцями, решта тьмяніє; лічильник виділено
  window.FXHL={type:t,t0:performance.now(),until:performance.now()+3500};map.triggerRepaint();
  document.querySelectorAll('#counters .cnt').forEach(c=>c.classList.toggle('hl-off',c.dataset.t!==t));clearTimeout(focusType.t);
  focusType.t=setTimeout(()=>{document.querySelectorAll('#counters .cnt').forEach(c=>c.classList.remove('hl-off'));map.triggerRepaint();},3500);}
function renderCounters(){
  // 04.11: лічильник рахує ТРЕКИ, а не суму ×N (85 «одиниць» при 48 треках збивало з пантелику); ×N лишається на значках.
  // Цілі, про які не писали 10+ хв, у лічильник не входять (на мапі вони напівпрозорі)
  const nowS=Date.now()/1000+offset;const LM=(SNAP.counts&&SNAP.counts.live_min)||{};const fresh=t=>(((t.ev&&t.ev.age)||0)+Math.max(0,nowS-SNAP.now))<(LM[t.type]||10)*60;// той самий час життя за типом, що й на мапі й в аналітиці (app/count.py)
  const act=SNAP.tracks.filter(t=>t.status==='active');const by={};act.forEach(t=>by[t.type]=(by[t.type]||0)+1);
  // компроміс: велике число — оцінка кількості одиниць (як на мапі: той самий тип і пункт призначення = одна група, береться найбільша названа кількість, різні пункти додаються); дрібно — скільки це груп/цілей
  const UN={};{const g={};act.forEach(t=>{const k=t.type+'|'+((t.next||'').trim()||t.id);g[k]=Math.max(g[k]||0,t.count||1);});for(const k in g){const ty=k.split('|')[0];UN[ty]=(UN[ty]||0)+g[k];}}
  const order=['uav','shahed','jet','geran5','cruise','banderol','ballistic','rszv','molniya','recon','lancet','fpv','fpvf'];
  $('#counters').innerHTML='';
  // кожен тип цілі = окремий блок; тип, якого ще немає у списку, сам отримує свій блок у кінці ряду (КАБи показуються зонами, не лічильником)
  const types=order.filter(t=>by[t]).concat(Object.keys(by).filter(t=>!order.includes(t)&&t!=='kab').sort());
  types.forEach(t=>{const d=document.createElement('div');d.className='cnt';d.dataset.t=t;d.title=TYPE_NAME[t]||t;if(TAC&&window.App06){const sv=document.createElement('span');sv.className='cs';try{sv.innerHTML=window.App06.svg({type:window.App06.MAP[t]?t:'unknown',affiliation:'hostile',hd:null,size:26});}catch(e){}d.appendChild(sv);}else{const c=(CNTI[t]&&CNTI[t]._sprite?CNTI[t]:(CNTI[t]=drawTarget(TYPE_COLOR[t]?t:'uav',28)));const cc=document.createElement('canvas');cc.width=c.width;cc.height=c.height;cc.getContext('2d').drawImage(c,0,0);d.appendChild(cc);}const w=document.createElement('div');w.className='cw';const b=document.createElement('b');b.textContent=by[t];if(renderCounters.prev&&renderCounters.prev[t]!==by[t])b.className='pop';
    const l=document.createElement('small');l.textContent=(CNT_LBL[t]||TYPE_NAME[t]||t);w.appendChild(b);w.appendChild(l);d.appendChild(w);d.style.setProperty('--tc',TYPE_COLOR[t]||'#B9C2D0');d.onclick=()=>focusType(t);$('#counters').appendChild(d);});
  renderCounters.prev=Object.fromEntries(Object.keys(by).map(k=>[k,by[k]]));
  if(!act.length){const d=document.createElement('div');d.className='cnt';d.innerHTML='<b style="font-size:16px">Цілей не видно</b>';$('#counters').appendChild(d);}
}
function renderAsOf(){
  // для людей: лише «наживо» і час; технічні деталі, у стрічці
  const el=$('#asof');const age=(Date.now()-recvAt)/1000;
  if(!SNAP){el.className='asof';el.innerHTML='<i class="live-dot wait"></i>Підключення…';return;}
  if(REPLAY){el.className='asof stale';el.innerHTML='<i class="live-dot"></i>Машина часу · '+fmt(REPLAY.t)+' · ✕';el.style.cursor='pointer';return;}
  if(age>30){el.className='asof stale';el.innerHTML='<i class="live-dot"></i>Немає звʼязку '+Math.round(age)+' с, це не відбій';return;}
  const h=SNAP.health,ok=h.telegram||h.replay;
  el.className='asof'+(ok?'':' stale');
  el.innerHTML='<i class="live-dot'+(ok?'':' wait')+'"></i>'+(h.replay?'Демо':ok?'Наживо':'Дані затримуються')+' · '+fmt(SNAP.now);
}
setInterval(()=>SNAP&&renderAsOf(),1000);
let SHELTER=+(localStorage.getItem('shelter')||3);if($('#me-sh'))$('#me-sh').textContent=SHELTER;
if($('#me-set'))$('#me-set').onclick=()=>{const v=[1,2,3,5,7,10];SHELTER=v[(v.indexOf(SHELTER)+1)%v.length];localStorage.setItem('shelter',SHELTER);$('#me-sh').textContent=SHELTER;toast('До укриття: '+SHELTER+' хв');};
const MEI={};
function homeObl(){if(!home||!window.__OBLGJ)return null;if(homeObl.k===home.join())return homeObl.v;
  const inRing=(pt,r)=>{let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const [xi,yi]=r[i],[xj,yj]=r[j];if(((yi>pt[1])!==(yj>pt[1]))&&(pt[0]<(xj-xi)*(pt[1]-yi)/(yj-yi)+xi))c=!c;}return c;};
  const find=g=>{const f=g&&g.features.find(f=>{const G=f.geometry;const P=G.type==='Polygon'?[G.coordinates]:G.coordinates;return P.some(poly=>inRing(home,poly[0]));});return f?f.properties.n:null;};
  homeObl.k=home.join();homeObl.v=find(window.__OBLGJ);homeObl.r=find(window.__RAGJ);return homeObl.v;}
// офіційний статус для дому: уся область → район дому → «у частині області» (громади) → немає
function homeOfficial(ob){const O=SNAP.official||{};const ra=homeObl.r;
  // офіційне зведення застаріло (джерело не відповідає): чесно кажемо, а не показуємо старий стан як поточний
  const age=O.updated?(Date.now()/1000+offset-O.updated)/60:999;const st=age>3?' · дані тривог '+(age>120?'недоступні':Math.round(age)+' хв тому'):'';
  if((SNAP.levels||{})[ob])return {on:1,t:'тривога в усій області'+st};
  // 04.11: місто з власним офіційним статусом (м. Харків): для дому в ньому статус району не діє — лише статус міста
  const hh=homeHrom(),sep=hh!=null&&(O.sep||[]).includes(hh);
  if(sep){const H0=O.hromadas||{};if(H0[hh]||H0[String(hh)])return {on:1,t:'тривога у вашій громаді'+st};
    if(ra&&(O.raion_levels||{})[ra])return {on:2,t:'тривога в районі, у вашій громаді тривоги немає'+st};}
  if(ra&&(O.raion_levels||{})[ra])return {on:1,t:'тривога у вашому районі'+st};
  // громада дому (м. Харків має власну тривогу, окремо від району): 03.11 карта показувала «тривога: м. Харків», а панель «у частині області»
  const H=O.hromadas||{};if(HPDATA&&home)for(const id in H){const f=HPDATA.features[+id];if(H[id]&&f&&geomIn(f.geometry,home[0],home[1]))return {on:1,t:'тривога у вашій громаді'+st};}
  if(!HPDATA&&Object.keys(H).length)loadHP();
  if((O.alert_obl||[]).includes(ob))return {on:2,t:'тривога в частині області'+st};
  return {on:0,t:'тривоги немає'+st};}
/* ---------- Режим балістичної загрози (03.11) ----------
   Вмикається повідомленням про балістику, де названо область дому (або регіональним каналом цієї області).
   Не стверджує, де ракета: показує територію, яку назвали, вік повідомлення й першоджерело.
   Вимикається відбоєм балістики від каналів або офіційним відбоєм для дому; мовчання джерел режим не вимикає
   (страховка: 40 хв без жодного нового повідомлення про балістику для області). */
const OBL_GEN={'Вінницька':'Вінниччина','Волинська':'Волинь','Дніпропетровська':'Дніпропетровщина','Донецька':'Донеччина','Житомирська':'Житомирщина','Закарпатська':'Закарпаття','Запорізька':'Запоріжжя','Івано-Франківська':'Прикарпаття','Київська':'Київщина','Київ':'Київ','Кіровоградська':'Кіровоградщина','Луганська':'Луганщина','Львівська':'Львівщина','Миколаївська':'Миколаївщина','Одеська':'Одещина','Полтавська':'Полтавщина','Рівненська':'Рівненщина','Сумська':'Сумщина','Тернопільська':'Тернопільщина','Харківська':'Харківщина','Херсонська':'Херсонщина','Хмельницька':'Хмельниччина','Черкаська':'Черкащина','Чернівецька':'Буковина','Чернігівська':'Чернігівщина'};
let BALM=null;
function balMode(ob,OF){if(!ob||!SNAP||!SNAP.bal)return null;const now=Date.now()/1000+offset;const cov=e=>e.obl.includes('*')||e.obl.includes(ob)||(ob==='Київ'&&e.obl.includes('Київська'));
  // МіГ-31К/І (k:'mig'): окремий етап «носій у повітрі» для всієї України; його відбій закриває лише його
  const ev=SNAP.bal.slice().sort((a,b)=>a.t-b.t);let items=[];
  for(const e of ev){if(e.close){if(e.k==='mig')items=items.filter(x=>x.k!=='mig');else if(!e.obl.length||cov(e))items=items.filter(x=>x.k==='mig');continue;}
    if(cov(e))items.push(e);}
  if(!items.length)return null;const start=items[0],last=items[items.length-1];
  if(now-last.t>40*60)return null;
  // офіційний відбій для дому після початку режиму (повідомлення старше 90 с)
  if(OF&&OF.on===0&&SNAP.official&&SNAP.official.ok&&now-last.t>90)return null;
  return {start,last,items:items.slice(-4).reverse(),obl:ob,names:last.obl.includes('*')?[]:last.obl,mig:items.every(e=>e.k==='mig'),bw:(()=>{const t=new Set(items.map(e=>e.ty||'ballistic'));return t.size===1&&t.has('banderol')?'ban':t.has('banderol')?'mix':'bal';})()};}
function showBalRegion(){if(!BALM||!window.__OBLGJ)return;const fs=window.__OBLGJ.features.filter(f=>BALM.names.includes(f.properties.n)||f.properties.n===BALM.obl);if(!fs.length)return;
  let b=[180,90,-180,-90];const walk=c=>{if(typeof c[0]==='number'){b=[Math.min(b[0],c[0]),Math.min(b[1],c[1]),Math.max(b[2],c[0]),Math.max(b[3],c[1])];}else c.forEach(walk);};fs.forEach(f=>walk(f.geometry.coordinates));
  map.fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:{top:120,bottom:260,left:30,right:30},duration:800});}
function syncBalLayers(){if(!map.getLayer('bal-dim'))return;const on=!!BALM;const names=on?Array.from(new Set([BALM.obl,...BALM.names])):[];
  map.setLayoutProperty('bal-dim','visibility',on?'visible':'none');map.setLayoutProperty('bal-hl','visibility',on?'visible':'none');
  if(on){const key=names.join('|');if(syncBalLayers.k!==key){syncBalLayers.k=key;map.setFilter('bal-dim',['!',['in',['get','n'],['literal',names]]]);map.setFilter('bal-hl',['in',['get','n'],['literal',names]]);}}}
/* ---------- поділитись зведенням (04.11): картка «область, час, джерела», що при відкритті показує свій вік ---------- */
{const sb=$('#me-share');if(sb)sb.onclick=async e=>{e.stopPropagation();if(!home){toast('Спершу позначте своє місце ⌂');return;}
  const obl=window.OBLPOLY?window.OBLPOLY(home[0],home[1]):null;if(!obl){toast('Не вдалося визначити область');return;}
  try{const r=await(await fetch('/api/brief',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({obl})})).json();
    if(!r.ok)throw 0;const url=location.origin+r.url,title=obl+' область · NAVRYX SKY';
    if(navigator.share){try{await navigator.share({title,text:'Обстановка: '+obl+' область',url});}catch(_){}}
    else{try{await navigator.clipboard.writeText(url);toast('Посилання скопійовано');}catch(_){prompt('Посилання на зведення',url);}}}
  catch(_){toast('Не вдалося створити зведення');}};}
/* ---------- свіжість і збої на першому екрані (04.11): вік даних по вашій області й чесна позначка, коли джерела мовчать ---------- */
function renderFresh(){const el=$('#me-fresh');if(!el)return;const F=SNAP&&SNAP.fresh;if(!F||!home||REPLAY){el.hidden=true;return;}
  const now=liveNow(),ago=s=>{const m=Math.round((now-s)/60);return m<1?'щойно':m<60?m+' хв тому':Math.floor(m/60)+' год '+(m%60)+' хв тому';};
  const myO=window.OBLPOLY?window.OBLPOLY(home[0],home[1]):null,lo=myO&&F.obl?F.obl[myO]:0;
  const alertMine=!!(myO&&SNAP.levels&&SNAP.levels[myO]);const warn=[];
  if(!F.alerts_ok||now-F.alerts>180)warn.push('Офіційні тривоги не оновлюються'+(F.alerts?' '+ago(F.alerts).replace(' тому',''):'')+'. Перевіряйте застосунок «Повітряна тривога».');
  if(F.channels&&F.live/F.channels<0.3)warn.push('Більшість джерел зараз не оновлюється: картина може бути неповною.');
  let t;if(warn.length){el.className='me-fresh bad';t='⚠ '+warn.join(' ');}
  else{el.className='me-fresh';t='Дані оновлено '+ago(Math.max(F.any||0,F.alerts||0))+(myO?' · '+(lo?'по вашій області останнє повідомлення '+ago(lo):'по вашій області даних про цілі за останні години немає'):'');
    if(alertMine&&(!lo||now-lo>1200)){el.className='me-fresh mid';t+='. Тривога триває: тиша в джерелах не означає безпеку.';}}
  el.textContent=t;el.hidden=false;}
/* ---------- ціль зовсім поряд (04.11): мапа сама наближається так, щоб у кадрі були і ціль, і дім ----------
   ≤10 км від дому або ~≤5 хв до вас за названим маршрутом; не частіше разу на ціль за 10 хв і не всупереч людині
   (якщо вона щойно рухала мапу, стежить за ціллю чи грає машина часу) */
let AF_LAST={},AF_USER=0;
map.on('movestart',e=>{if(e.originalEvent)AF_USER=Date.now();});
function autoFrame(close,first){
  if(!home||REPLAY||follow||document.hidden||Date.now()-AF_USER<60000||!$('#sheet').hidden)return;
  let c=null;const fc=close&&close[0];
  if(fc&&fc.d<=10&&!fc.tr.pos_est)c={tr:fc.tr};
  else if(first&&first.r.eta!=null&&first.r.eta<=5&&first.r.rel==='route')c={tr:first.tr};
  if(!c)return;const id=c.tr.id,now=Date.now();if(AF_LAST[id]&&now-AF_LAST[id]<600000)return;AF_LAST[id]=now;
  const d=DISP.get(id);if(!d)return;const p=d.p;
  const b=[[Math.min(p[0],home[0]),Math.min(p[1],home[1])],[Math.max(p[0],home[0]),Math.max(p[1],home[1])]];
  const me=$('#me'),bot=(me&&!me.hidden?me.offsetHeight:0)+110;
  map.fitBounds(b,{padding:{top:130,bottom:Math.min(innerHeight*0.55,bot),left:50,right:50},maxZoom:12.5,duration:1400});}
function renderMe(threats){
  const box=$('#me');if(!home){box.className='me'+(box.classList.contains('open')?' open':'');$('#me-word').textContent='Що летить до мене?';$('#me-sub').innerHTML='Покажу, що летить саме до вас.<button class="cta" id="me-cta">Визначити моє місце</button>';const cta=$('#me-cta');if(cta)cta.onclick=()=>$('#b-locate').click();$('#me-list').innerHTML='';return;}
  const isStale=!SNAP||(Date.now()-recvAt)/1000>(document.hidden?75:30);
  const near=SNAP.tracks.filter(t=>t.status==='active'&&t.conf>=0.5).map(t=>{const d=DISP.get(t.id);return d?{tr:t,r:homeRel(t,d.p)}:null;}).filter(x=>x&&x.r&&x.r.d<120).sort((a,b)=>(a.r.eta??999)-(b.r.eta??999)||a.r.d-b.r.d);
  const thr=near.filter(x=>x.r.rel);const first=thr[0];
  // перший рядок, завжди офіційний статус області дому; відсутність позначки на мапі ≠ персональний відбій (аудит 02.11)
  const ob=homeObl();const OF=ob?homeOfficial(ob):{on:0,t:''};const lvl=OF.on;
  const offL=ob?'<div class="me-off '+(OF.on===1?'on':OF.on===2?'part':'')+'"><i></i>'+esc(OF.t)+'</div>':'';
  // що відомо моніторам: давність останнього повідомлення поруч (≤60 км), непідтверджені цілі теж рахуємо
  const tg=!SNAP.health||SNAP.health.telegram||SNAP.health.replay;
  let cls=lvl?'me watch':'me',word='Цілей у ваш бік немає',sub=offL;
  if(!tg){cls='me watch';word='Дані неповні';sub=offL+'Канали моніторів зараз не надходять.';}
  const mb=near.filter(x=>!x.r.rel&&x.r.maybe).sort((a,b)=>b.r.p-a.r.p)[0];
  // «може наблизитися» лише в межах 40 км, як і push (калібрування 03.11: показаний відсоток завищений ~10 разів, тому без чисел)
  if(!first&&mb&&mb.r.d<=40){cls='me watch';word='Ціль неподалік';sub=offL+esc(TYPE_NAME[mb.tr.type])+' · '+Math.round(mb.r.d)+' км '+mb.r.from+' · може наблизитися';}
  // ціль поруч — загроза незалежно від курсу (03.11: дві цілі за 3–6 км від дому, а панель писала «Цілей у ваш бік немає»)
  const HX=xy(home);const close=SNAP.tracks.filter(t=>t.status==='active'&&!t.nopos).map(t=>{const d=DISP.get(t.id);return d?{tr:t,d:dist(HX,xy(d.p)),side:FROM[Math.round(brg(HX,xy(d.p))/45)%8]}:null;}).filter(x=>x&&x.d<=15).sort((a,b)=>a.d-b.d);
  autoFrame(close,first);
  if(!first&&close.length){const c0=close[0],n=close.reduce((a,x)=>a+(x.tr.count||1),0);cls=c0.d<=8?'me danger':'me watch';word=n>1?'Цілі поруч: '+n:'Ціль поруч';
    sub=offL+esc(TYPE_NAME[c0.tr.type])+' · '+Math.max(1,Math.round(c0.d))+' км '+c0.side+(c0.tr.next?' · курс → '+esc(c0.tr.next):c0.tr.hd==null?' · курс невідомий':'')+(c0.tr.conf<0.5?' · ще не підтверджено':'')+(close.length>1?' · ще '+(close.length-1)+' в межах 15 км':'');}
  if(isStale){cls='me watch';word='Невідомо';sub=offL+'Немає звʼязку з сервером. Це <b>не відбій</b>.';}
  else if(first){const e=first.r.eta||0,byRoute=first.r.rel==='route';
    cls=e<=5&&byRoute?'me danger':'me watch';word=byRoute?(e<=5?'Летить на вас':'Маршрут поруч'):'Можливо у ваш бік';
    sub=offL+esc(TYPE_NAME[first.tr.type])+' · '+Math.round(first.r.d)+' км '+first.r.from+(byRoute?(first.r.eta!=null?' · ~'+Math.max(1,Math.round(e))+' хв':''):' · напрямок за оцінкою, може наблизитися');}
  BALM=(!isStale)?balMode(ob,OF):null;syncBalLayers();
  if(BALM){const now=Date.now()/1000+offset,L=BALM.last,ag=Math.max(0,Math.round(now-L.t));const nm=k=>esc(SNAP.sources[k]?.name||k);
    cls='me danger bal';word=BALM.mig?'МіГ-31К у повітрі · загроза «Кинджала»':(BALM.bw==='ban'?'Загроза бандеролей':BALM.bw==='mix'?'Загроза балістики й бандеролей':'Балістична загроза')+' · '+(OBL_GEN[BALM.obl]||BALM.obl);
    sub=offL+'<div class="bal-age">Повідомлення отримано '+(ag<60?ag+' с':Math.round(ag/60)+' хв')+' тому · '+nm(L.src)+(SNAP.sources[L.src]?.official?' (офіційне)':'')+'</div>'+
      '<div class="bal-go">Перейдіть в укриття</div>'+
      '<ol class="bal-log">'+BALM.items.map(e=>'<li><span>'+fmt(e.t)+'</span><b>'+nm(e.src)+'</b> '+esc(e.k==='mig'?(e.txt||'МіГ-31К').slice(0,70):e.pl.length?e.pl.join(', '):e.obl.map(o=>OBL_GEN[o]||o).slice(0,4).join(', ')+(e.obl.length>4?' +'+(e.obl.length-4):''))+(e.link?' <a href="'+esc(e.link)+'" target=_blank rel=noopener>↗</a>':'')+'</li>').join('')+'</ol>'+
      (BALM.mig?'<small class="bal-note">Зліт носія ще не пуск: на нього Повітряні сили зазвичай оголошують тривогу по всій Україні. Кількість бортів не дорівнює кількості ракет</small>':'<small class="bal-note">Це вік повідомлення, а не час до удару. Де ракета, канали не знають</small>')+
      (BALM.mig?'':'<button class="bal-btn" id="bal-show">Показати регіон загрози</button>');}
  {const was=box.classList.contains('bal');if(!BALM)box.classList.remove('fold');// нова загроза завжди показується повністю, потім сама згортається
    if(BALM&&!was){box.classList.remove('fold');clearTimeout(window.__foldT);window.__foldT=setTimeout(()=>{if($('#me').classList.contains('bal'))meFold(true);},15000);}}
  box.className=cls+(box.classList.contains('open')?' open':'')+(box.classList.contains('fold')?' fold':'');$('#me-word').textContent=word;box.classList.toggle('off-on',OF.on===1);box.classList.toggle('off-part',OF.on===2);{const fb=$('#me-fold');if(fb){fb.hidden=!BALM;fb.setAttribute('aria-label',box.classList.contains('fold')?'Розгорнути':'Згорнути');}}
  // великі хвилини, лише коли маршрут названо каналами (обґрунтована оцінка), а не з напрямку
  if(first&&!isStale&&!BALM&&first.r.eta!=null&&first.r.rel==='route'){const eta=Math.max(1,Math.round(first.r.eta)),k=Math.max(0.04,Math.min(1,eta/30));const C=2*Math.PI*44;
    sub=offL+'<div class="big"><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" class="trk"/><circle cx="50" cy="50" r="44" class="arc" style="stroke-dasharray:'+(C*k)+' '+C+'"/></svg><b>'+eta+'</b><i>хв</i></div>'+
      '<div class="big-t"><b>'+esc(TYPE_NAME[first.tr.type])+(first.tr.count>1?' ×'+first.tr.count:'')+'</b> · ~'+eta+' хв до вас<br><span>'+Math.round(first.r.d)+' км '+first.r.from+(first.tr.next?' · курс → '+esc(first.tr.next):'')+' · за повідомленнями каналів</span></div>';}
  $('#me-sub').innerHTML=sub;renderFresh();{const bs=$('#bal-show');if(bs)bs.onclick=e=>{e.stopPropagation();showBalRegion();};}
  $('#me-list').innerHTML='';
  const nearIds=new Set(near.map(x=>x.tr.id));const closeAsNear=close.filter(x=>!nearIds.has(x.tr.id)).map(x=>({tr:x.tr,r:{d:x.d,from:x.side,eta:null,rel:null,away:false,maybe:false,p:0,near:true}}));
  (thr.length?thr:closeAsNear.concat(near)).slice(0,3).forEach(x=>{const t=x.tr,r=x.r;const li=document.createElement('li');
    const c=(MEI[t.type]&&MEI[t.type]._sprite?MEI[t.type]:(MEI[t.type]=drawTarget(t.type,22)));const cv=document.createElement('canvas');cv.width=c.width;cv.height=c.height;cv.getContext('2d').drawImage(c,0,0);
    const eta=r.eta!=null?Math.max(1,Math.round(r.eta)):null;
    li.innerHTML='<div class="me-row"><span class="n">'+esc(TYPE_NAME[t.type])+(t.count>1?' ×'+t.count:'')+' · '+Math.round(r.d)+' км '+r.from+'</span><span class="t '+(eta?(eta<=5&&r.rel==='route'?'go':'eta'):r.near?'near':r.away?'away':r.maybe?'maybe':'')+'">'+(eta?'~'+eta+' хв':r.near?(t.next?'курс → '+esc(t.next):'поруч'):(r.away?'віддаляється':t.hd==null?'курс невідомий':r.maybe?'можливо у ваш бік · '+Math.round(r.p*100)+'%':'летить повз'))+'</span></div>'+
      (eta?'<div class="me-act '+(eta<=5&&r.rel==='route'?'go':'ok')+'">'+(r.rel==='route'?'маршрут проходить поруч':'напрямок за оцінкою, може наблизитися')+'</div>':'');
    li.querySelector('.me-row').prepend(cv);li.onclick=()=>openSheet(t.id);$('#me-list').appendChild(li);});
}
function renderBanner(threats){
  const b=$('#banner');if(!threats.length){b.hidden=true;return;}
  threats.sort((a,b)=>(a.rel.eta??999)-(b.rel.eta??999));const t=threats[0];
  b.hidden=false;b.innerHTML=esc(TYPE_NAME[t.tr.type])+(t.tr.count>1?' ×'+t.tr.count:'')+' · '+(t.rel.rel==='route'?'маршрут проходить біля дому':'може наблизитися до вашого району')+(t.rel.eta!=null?' · ~'+Math.max(1,Math.round(t.rel.eta))+' хв':'')+'<small>'+Math.round(t.rel.d)+' км '+t.rel.from+(threats.length>1?' · ще '+(threats.length-1):'')+'</small>';
  b.onclick=()=>openSheet(t.tr.id);
  // кінематографічний переліт: нова загроза дому, камера плавно показує і дім, і ціль (якщо користувач не крутить карту)
  renderBanner.seen=renderBanner.seen||new Set();
  if(!renderBanner.seen.has(t.tr.id)){renderBanner.seen.add(t.tr.id);
    note({k:'home:'+t.tr.id,lvl:'red',ic:'⚠️',title:TYPE_NAME[t.tr.type]+(t.tr.count>1?' ×'+t.tr.count:'')+', '+(t.rel.rel==='route'?'маршрут біля вашого дому':'курс на ваш район'),sub:Math.round(t.rel.d)+' км '+t.rel.from+(t.rel.eta!=null?' · ~'+Math.max(1,Math.round(t.rel.eta))+' хв':''),go:()=>openSheet(t.tr.id)});const d=DISP.get(t.tr.id);
    if(d&&home&&introDone&&Date.now()-(window.__introAt||0)>9000&&Date.now()-(window.__touch||0)>20000){const b2=new maplibregl.LngLatBounds(home,home).extend(d.p);
      const cam=map.cameraForBounds(b2,{padding:{top:140,bottom:160,left:80,right:380}});if(cam)map.flyTo({...cam,zoom:Math.min(cam.zoom,10),pitch:tilt?55:20,bearing:0,curve:1.5,speed:0.7,essential:true});}}
}
['mousedown','touchstart','wheel'].forEach(ev=>document.getElementById('map').addEventListener(ev,()=>window.__touch=Date.now(),{passive:true}));

/* ---------- картка цілі ---------- */
// навчений прогноз траєкторії: куди такі цілі з цього місця летіли раніше + власна точність прогнозу
function lpHtml(tr){const L=tr.lpath||[];if(!L.length)return '';const A=(SNAP.pred_acc||{})[tr.type];
  return '<h4>Ймовірно далі <small>· навчено на попередніх перельотах'+(A?' · точність '+Math.round(A.acc*100)+'% з '+A.n:'')+'</small></h4><ol class="lp">'+L.map(x=>'<li><b>'+Math.round(x[3]*100)+'%</b> '+esc(x[2])+'</li>').join('')+'</ol>';}
function openSheet(id){if(XRAY){sel=id;const d=DISP.get(id);if(d)map.easeTo({center:d.p,zoom:Math.max(map.getZoom(),9),duration:700});xrPanel().dataset.k='';syncXray();return;}if(follow&&id!==sel)stopFollow();sel=id;$('#sh-follow').classList.toggle('on',follow);$('#sh-follow').textContent=follow?'Зупинити':'Стежити';$('#sheet').hidden=false;fillSheet(true);const d=DISP.get(id);if(d)map.flyTo({center:d.p,zoom:Math.max(map.getZoom(),8.5),curve:1.3,speed:1.1,essential:true});}
/* докази цілі (список публікацій), за запитом, кеш 15 с; у знімку їх більше немає (були >50% трафіку) */
const EVC=new Map();function evItems(id,cb){const c=EVC.get(id);const now=Date.now();if(c&&now-c.t<15000)return c.items;
  if(c&&c.pending)return c.items||null;EVC.set(id,{t:c?c.t:0,items:c?c.items:null,pending:true});
  fetch('/api/track/'+encodeURIComponent(id),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(j=>{EVC.set(id,{t:Date.now(),items:j?j.items:[],contra:j?j.contra:[]});if(cb)cb();}).catch(()=>EVC.set(id,{t:Date.now()-10000,items:c?c.items:[]}));
  return c?c.items:null;}
function fillSheet(first){
  const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);if(!tr){$('#sheet').hidden=true;sel=null;return;}
  if(first||!fillSheet.icon||fillSheet.icon!==tr.type){const c=drawTarget(tr.type,40);$('#sh-icon').innerHTML='';$('#sh-icon').appendChild(c);fillSheet.icon=tr.type;}
  $('#sh-name').textContent=TYPE_NAME[tr.type]+(tr.count>1?' ×'+tr.count:'');
  const BAL=isBal(tr);
  $('#sh-course').innerHTML=tr.status!=='active'?(tr.status==='lost'?'Втрачено':'Більше не фіксується'):BAL?(tr.next?'Загроза: <b>'+esc(tr.next)+'</b>':'Загроза, місце не назване'):(tr.next?'Курс → <b>'+esc(tr.next)+'</b>':tr.hd!=null?'Ймовірно '+SIDE[Math.round(tr.hd/45)%8]+' <small>(оцінка SKY)</small>':'Курс невідомий');
  const d=DISP.get(tr.id);const r=d&&homeRel(tr,d.p);const nowT=Date.now()/1000+offset;const mago=t=>Math.max(0,Math.round((nowT-t)/60));
  // 1) для вас: відстань і що ціль робить відносно дому, одним рядком
  $('#sh-dist').textContent=r?Math.round(r.d)+' км '+r.side:'';
  $('#sh-eta').textContent=!r?'':BAL?'· до згаданої території':r.eta!=null?'· ≈ '+Math.max(1,Math.round(r.eta))+' хв до вас':r.away?'· віддаляється':tr.hd==null?'· курс невідомий':'· летить повз';
  $('#sh-dist').closest('div').hidden=!r;
  // 2) де зараз: останній пункт від каналів і як давно; далі лише оцінка
  {let h;const at=tr.at;
   if(tr.nopos)h='<b class=warn>Невідомо</b>, канали назвали лише курс'+(tr.next?' на '+esc(tr.next):'');
   else if(at)h='<b>'+esc(at[0])+'</b>, останнє підтвердження о '+fmt(at[1])+' ('+mago(at[1])+' хв тому)'+(mago(at[1])>=5?'<br><small>далі на мапі, оцінка SKY за курсом і швидкістю</small>':'');
   else h=tr.pos_est?'оцінка SKY за курсом':'назвали канали';
   // можливості моделі поруч зі свіжістю; «скільки залишилося» не рахуємо: час запуску невідомий
   const END={uav:'не встановлено: тип не названо',shahed:'≈5 год 30 хв – 14 год (розрахунок за дальністю)',jet:'не встановлено: модель не названа',geran5:'до 2 год',banderol:'≈1 год на 500 км (розрахунок)',recon:'від 2 год до 16 год, залежно від моделі',molniya:'не встановлено',lancet:'до 30 хв («Ланцет-1») або до 40 хв («Ланцет-3»); версію канали зазвичай не називають'}[tr.type];
   if(END)h+='<br><small>Модель може бути в повітрі: '+END+'. Це не відлік і не відбій</small>';
   if(tr.ai)h+='<br><b class=warn>✦ Розпізнано ШІ.</b> <small>Правила SKY це повідомлення не розібрали, а кілька мовних моделей погодились, що це ціль, і її місця перевірено довідником. Перевірте першоджерело нижче</small>';
   if(tr.pair==='lancet')h+='<br><b class=warn>Канал попереджає про можливий Ланцет.</b> <small>ZALA чи Орлан часто працюють у парі з Ланцетом і наводять його, але сам Ланцет поруч ніхто не підтвердив</small>';
   if(BAL){const lt=tr.last||tr.first,nm=tr.next||(at&&at[0]);
     h=(nm?'Згадано: <b>'+esc(nm)+'</b>':'Місце не назване')+' о '+fmt(lt)+' ('+mago(lt)+' хв тому)'+(mago(lt)>=3?'<br><b class=warn>Оновлень немає</b> · це не відбій':'')+
       '<br><small>Це територія з повідомлення, а не координати ракети. Траєкторію й час до удару SKY не домальовує: канали не дають ні положення, ні висоти, ні часу виявлення</small>';}
   if(tr.fkm>25&&tr.status==='active')h+='<br><small>≈'+tr.fkm+' км від фронту: радіо-FPV так далеко не дістає, тож це носій «Молнія» або FPV на оптоволокні</small>';
   if(TAC&&tr.last){const D=new Date(tr.last*1000),z=n=>String(n).padStart(2,'0'),M=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];h+='<br><small>DTG '+z(D.getUTCDate())+z(D.getUTCHours())+z(D.getUTCMinutes())+'Z'+M[D.getUTCMonth()]+String(D.getUTCFullYear()).slice(2)+'</small>';}// група «дата-час» останнього повідомлення, лише в тактичному режимі
   $('#sh-now').innerHTML=h;{const hd=$('#sh-now').closest('div').querySelector('span');if(hd)hd.textContent=BAL?'Що повідомили':'Де зараз';}}
  // 2б) куди летить: напрямок, звідки SKY його знає і наскільки такий напрямок справджувався (жива самоперевірка)
  {const PA=SNAP.pred_acc||{};const HA=PA['hd:'+tr.type],LA=PA[tr.type];let h='';
   const SRC={fused:'злиття кількох джерел з вагами за їхньою точністю',channels:'канали назвали пункт',course:'канал назвав напрямок',learned:'навчені маршрути попередніх перельотів',movement:'рух між названими позиціями'}[tr.hd_src]||'';
   if(tr.status!=='active')h='Не відстежується: '+(tr.status==='lost'?'нових повідомлень немає':'канали написали «збито / не фіксується»');
   else if(tr.hd==null&&!tr.next)h='<b class=warn>Напрямок невідомий</b><br><small>Канали не назвали пункт, а навчених маршрутів звідси замало. Стрілку не домальовуємо</small>';
   else{h='<div class="dir-h">'+(tr.hd!=null?'<span class="dir-arrow" style="transform:rotate('+Math.round(tr.hd)+'deg)">↑</span><span><b>'+SIDE[Math.round(tr.hd/45)%8]+'</b>':'<span>')+(tr.next?(tr.hd!=null?' · ':'')+'на <b>'+esc(tr.next)+'</b>':'')+'</span></div>';
     if(SRC)h+='<small>Звідки відомо: '+SRC+'</small>';
     if(HA)h+='<br><small>Наскільки справджується: напрямок цього типу цілей збігався з наступною позицією (±45°) у '+Math.round(HA.acc*100)+'% з '+HA.n+' перевірок</small>';
     const L=tr.lpath||[];if(!(tr.route_names&&tr.route_names.length)&&L.length)h+='<br><small>Ймовірно далі: '+L.slice(0,3).map(x=>esc(x[2])+' '+Math.round(x[3]*100)+'%').join(', ')+(LA?' · такий прогноз справджувався у '+Math.round(LA.acc*100)+'% з '+LA.n+(LA.naive!=null?' (просто «тим самим курсом»: '+Math.round(LA.naive*100)+'%)':''):'')+'</small>';
     h+='<br><small>Ціль може змінити курс будь-якої миті</small>';}
   if(BAL)h='<small>Для балістики напрямок не прогнозуємо. Показуємо лише, що написали канали, і першоджерело нижче</small>';
   const dz=$('#sh-dir');if(dz){dz.innerHTML=h;dz.closest('div').hidden=BAL;}}// старий index.html з кешу може не мати цього блоку: решта картки все одно заповнюється
  // 3) звідки: перша фіксація, потім імовірне місце пуску
  {const L=tr.launch,en=tr.entry;let h='';
   if(en&&en[2])h='Вперше: <b>'+esc(en[2])+'</b> о '+fmt(en[3])+' ('+mago(en[3])+' хв тому)';
   else h='Вперше: '+fmt(tr.first)+' ('+mago(tr.first)+' хв тому)';
   if(L)h+='<br>Пуск: '+(L.est?'ймовірно ':'')+'<b>'+esc(L.site)+'</b>'+(L.carrier?' · '+esc(L.carrier):'')+(L.t?' · '+fmt(L.t):'')+(L.est?' <small>(оцінка за курсом'+(L.p>=0.4?' і статистикою':'')+')</small>':' <small>('+(L.srcs||[]).map(s=>esc(SNAP.sources[s]?.name||s)).join(', ')+(L.link?' · <a href="'+esc(L.link)+'" target="_blank" rel="noopener">пост ↗</a>':'')+')</small>');
   else if(tr.from)h+='<br>З боку: '+esc(tr.from);
   $('#sh-from').innerHTML=h;}
  // 4) хто повідомив: незалежні джерела поіменно, тип, як написали
  {const E=tr.ev||{};const P=(E.prim&&E.prim.length?E.prim:tr.srcs)||[];const ind=P.length;const cp=Math.max(0,(E.pubs||0)-ind);
   $('#sh-conf').innerHTML=(ind>=2?'<b class=ok>'+ind+' незалежних джерел</b>':'<b class=warn>Одне джерело, ще не підтверджено</b>')+': '+P.map(s=>esc(SNAP.sources[s]?.name||s)).join(', ')+
     (cp?'<br><small>ще '+cp+' повторів/копій, не рахуються як підтвердження</small>':'')+'<br><small>Тип, як написали канали'+(tr.likely?' (ймовірно)':'')+'</small>';}
  const serverT=Date.now()/1000+offset;const pos=DISP.get(tr.id);
  if(!BAL&&tr.route_names&&tr.route_names.length&&tr.route&&tr.route.length&&pos){let acc=0,prev=xy(pos.p);const items=tr.route.slice(0,tr.route_names.length).map((p,i)=>{const q=xy(p);acc+=dist(prev,q);prev=q;return '<li><b>~'+Math.max(1,Math.round(acc/tr.speed*60))+' хв</b> '+esc(tr.route_names[i])+'</li>';});
    if(home&&r&&r.eta!=null)items.push('<li class="home"><b>~'+Math.max(1,Math.round(r.eta))+' хв</b> ваш дім</li>');
    const why=tr.pred==='learned'?' <small>· вивчено з історії'+(tr.pred_p?' ('+Math.round(tr.pred_p*100)+'%)':'')+'</small>':tr.pred==='channels'?' <small>· за каналами</small>':'';
    $('#sh-route').innerHTML='<h4>Прогноз маршруту'+why+'</h4><ol>'+items.join('')+'</ol>'+(tr.pos_est?'<p class="est">Точне місце не названо, позицію оцінено'+(tr.pred==='learned-origin'?' за типовими маршрутами':' по пункту призначення')+'</p>':'');}else $('#sh-route').innerHTML='';
  // «Чому я це показую»: першоджерело, копії, суперечності, давність, що змінило відображення
  {const E=Object.assign({items:[],prim:[],pubs:0,contra:[],age:0},tr.ev||{});const got=(tr.ev&&tr.ev.items)?tr.ev.items:(REPLAY?null:evItems(tr.id,()=>{if(sel===tr.id)fillSheet();}));// машина часу: лише те, що було відомо на той момент
   E.items=got||[];const nm=k=>esc(SNAP.sources[k]?.name||k);const ind=E.prim.length;
   const head=E.pubs+' '+(E.pubs===1?'публікація':E.pubs<5?'публікації':'публікацій')+' · '+ind+' '+(ind===1?'першоджерело':ind<5?'першоджерела':'першоджерел')+' · '+(ind>=2?'<b class=ok>незалежне підтвердження є</b>':'<b class=warn>незалежного підтвердження немає</b>');
   const age=E.age;const ageTxt=age<120?'щойно':age<3600?Math.round(age/60)+' хв тому':'понад годину тому';
   // дві різні певності (04.11): чи ціль справді є — і наскільки точно відомо, де вона зараз
   const qm=tr.pos_lvl==='невідоме'?'<b class=warn>невідоме</b>: канали назвали лише курс чи район':tr.pos_km!=null?'<b class='+(tr.pos_lvl==='точне'?'ok':tr.pos_lvl==='приблизне'?'mid':'warn')+'>'+esc(tr.pos_lvl)+'</b>, ±'+tr.pos_km+' км'+(tr.fix_age!=null?' · назване '+(tr.fix_age<120?'щойно':Math.round(tr.fix_age/60)+' хв тому'):''):'';
   const qi=tr.id_lvl?'<b class='+(tr.id_lvl==='висока'?'ok':tr.id_lvl==='середня'?'mid':'warn')+'>'+esc(tr.id_lvl)+'</b> · '+(tr.n_indep||0)+' '+((tr.n_indep||0)===1?'незалежне джерело':'незалежних джерел'):'';
   const qb=(qi||qm)?'<div class=q2>'+(qi?'<div><span>Що ціль є</span><em>'+qi+'</em></div>':'')+(qm?'<div><span>Де вона зараз</span><em>'+qm+'</em></div>':'')+'</div>':'';
   let h='<h4>Чому я це показую</h4>'+qb+'<p class=ev-head>'+head+'</p><p class=ev-age>'+(tr.pos_lvl==='невідоме'?'Місце цієї цілі канали не називали; на мапі показано оцінку за курсом. Останнє повідомлення: '+ageTxt:'Остання фіксація місця: '+(tr.fix_age!=null?(tr.fix_age<120?'щойно':tr.fix_age<3600?Math.round(tr.fix_age/60)+' хв тому':'понад годину тому'):ageTxt))+(tr.pos_lvl!=='невідоме'&&(tr.fix_age??age)>120&&tr.type!=='ballistic'?'. Далі положення розраховане: на мапі біла точка з часом показує, де ціль бачили востаннє, пунктир веде до оцінки. Типова похибка оцінки за журналом ≈15–20 км через 10 хв і ≈30 км через 20 хв':'')+'</p>';
   if(E.contra.length)h+='<div class=ev-contra><b>Версії розходяться:</b>'+E.contra.map(v=>'<div>→ '+esc(v.dest||'?')+' <small>('+v.srcs.map(nm).join(', ')+')</small></div>').join('')+'</div>';
   if(!got)h+='<div class=note>Завантажую публікації…</div>';
   h+='<ol class=ev-list>'+E.items.slice().sort((a,b)=>b.t-a.t).map(it=>{const tag=it.copy?(it.copy===it.src?'<i class=cp>повтор</i>':'<i class=cp>копія '+nm(it.copy)+'</i>'):(it.why==='нова ціль'?'<i class=nw>першоджерело</i>':it.why==='змінило позицію'?'<i class=mv>змінило позицію</i>':it.why==='змінило курс'?'<i class=cr>змінило курс</i>':'<i class=cf>підтвердження</i>');
     const dr=SNAP.sources&&SNAP.sources[it.src]&&SNAP.sources[it.src].dir;const dt=dr&&it.dest?'<i class=cp title="Як часто напрямок від цього каналу справджувався (≤30°), перевірено '+dr.n+' разів">курс ✓'+Math.round(dr.acc*100)+'%</i>':'';
     return '<li class="'+(it.copy?'copy':'')+'"><div class=ev-m><span>'+fmt(it.t)+'</span><b>'+nm(it.src)+'</b>'+dt+tag+(it.link?'<a href="'+esc(it.link)+'" target=_blank rel=noopener>пост ↗</a>':'')+'</div>'+(it.text?'<q>'+esc(it.text)+'</q>':'')+'</li>';}).join('')+'</ol>';
   $('#sh-proof').innerHTML=h;}
  // тактичний режим: окремо «що повідомили» (факт з каналів) і «що оцінив SKY» (розрахунок), дотик підсвічує місце на мапі
  {const box=$('#sh-split');if(box){box.hidden=!TAC||tr.status!=='active';if(TAC&&tr.status==='active'){
    const nm=k=>esc(SNAP.sources[k]?.name||k),E=tr.ev||{},P=((E.prim&&E.prim.length?E.prim:tr.srcs)||[]),pos=DISP.get(tr.id),q=tr.trail&&tr.trail.length?tr.trail[tr.trail.length-1]:null;
    const lt=(q&&q[2])||(tr.at&&tr.at[1])||tr.last,mins=lt?Math.max(0,Math.round((serverT-lt)/60)):null,ago=mins==null?'':mins<1?'щойно':mins+' хв тому';
    const items=(E.items||EVC.get(tr.id)?.items||[]).slice().sort((a,b)=>b.t-a.t),last=items.find(i=>!i.copy)||items[0];
    const place=tr.nopos?'місце не назване, лише курс'+(tr.next?' на '+esc(tr.next):''):tr.at?esc(tr.at[0]):q?'точка за повідомленнями':'місце не назване';
    const fact='<div class="sp-c fact"'+(q&&!tr.nopos?' data-ll="'+q[0]+','+q[1]+'"':'')+'><h5>Що повідомили</h5><p><b>'+place+'</b></p>'+(lt?'<p>'+fmt(lt)+' · '+ago+'</p>':'')+(q&&window.MGRS&&!tr.nopos?'<p class="sp-m">MGRS '+MGRS.toMGRS(q[1],q[0],2)+'</p>':'')+(P.length?'<p>'+P.map(nm).join(', ')+'</p>':'')+(last&&last.text?'<q>'+esc(last.text.slice(0,140))+'</q>':'')+'</div>';
    const km=pos&&q?Math.round(dist(xy([q[0],q[1]]),xy(pos.p))):null;
    const est='<div class="sp-c est"'+(pos?' data-ll="'+pos.p[0]+','+pos.p[1]+'"':'')+'><h5>Що оцінив SKY</h5><p><b>'+(tr.pos_est||tr.nopos||(km!=null&&km>=2)?'позиція за курсом і швидкістю':'місце збігається з повідомленням')+'</b></p>'+(km!=null&&km>=2?'<p>≈ '+km+' км від названого місця</p>':'')+
      (tr.hd!=null?'<p>напрямок: '+SIDE[Math.round(tr.hd/45)%8]+(tr.next?' · на '+esc(tr.next):'')+'</p>':tr.next?'<p>на '+esc(tr.next)+'</p>':'<p>напрямок невідомий</p>')+(tr.pos_km!=null?'<p>точність: ±'+tr.pos_km+' км</p>':'')+(pos&&window.MGRS?'<p class="sp-m">MGRS ≈ '+MGRS.toMGRS(pos.p[1],pos.p[0],MGRS.digitsFor(tr.pos_km))+'</p>':'')+'<p class="sp-n">Це розрахунок, а не повідомлення</p></div>';
    box.innerHTML=fact+est;}}}
  const link=tr.links[tr.links.length-1];const a=$('#sh-post');if(link){a.href=link;a.hidden=false;}else a.hidden=true;
}
if($('#sh-split'))$('#sh-split').onclick=e=>{const c=e.target.closest('.sp-c');if(!c||!c.dataset.ll)return;const p=c.dataset.ll.split(',').map(Number);TACHL={p,until:Date.now()+6000};map.easeTo({center:p,zoom:Math.max(map.getZoom(),8.5),duration:600});};
$('#sh-close').onclick=()=>{$('#sheet').hidden=true;if(!follow)sel=null;};
// «Стежити за ціллю»: камера веде ціль, картка ховається, зверху, компактна плашка з живими даними і «Зупинити»
let followPrev=null,followSayT=0,followThr=false;
// 04.11 власник: супровід цілі голосом: куди летить, змінила курс, продовжує рух. Лише з даних треку, не частіше раз на 20 с.
const HD8=['на північ','на північний схід','на схід','на південний схід','на південь','на південний захід','на захід','на північний захід'];
function followSay(tr,r,kind,force){try{const S=window.NXSound;if(!S||!S.speakOnly)return;const m=S.get().mode;if(m!=='voice'&&m!=='both')return;
  if(!r||!r.rel)return;// голос лише коли ціль явно загрожує вам (курс/маршрут до дому), інакше мовчимо
  const now=Date.now();if(!force&&now-followSayT<20000)return;followSayT=now;
  const n=TYPE_NAME[tr.type]||'Ціль';
  const where=tr.next?'курс на '+tr.next:(tr.hd!=null?HD8[Math.round((((tr.hd%360)+360)%360)/45)%8]:'');
  const head=kind==='start'||kind==='threat'?'Увага. '+n+', загроза вам':kind==='turn'?n+' змінює курс':n+' продовжує рух';const wh=kind==='turn'&&tr.next?'на '+tr.next:where;
  const dist=r?'. '+Math.round(r.d)+' км '+(r.from||'від вас'):'';
  S.speakOnly(head+(wh?(kind==='turn'?' ':', ')+wh:'')+dist);}catch(e){}}
function startFollow(){if(!sel)return;follow=true;const d=DISP.get(sel);$('#sheet').hidden=true;
  if(d)map.flyTo({center:d.p,zoom:Math.max(map.getZoom(),9.2),pitch:tilt?50:0,duration:1400,essential:true});
  const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);followPrev=tr?{last:tr.last,next:tr.next}:null;followThr=false;renderFollow();toast('Стежу за ціллю. Голосом попереджу, якщо вона загрожуватиме вам');}
function stopFollow(msg){if(!follow)return;follow=false;$('#follow-pill').hidden=true;if(msg)toast(msg);}
function renderFollow(){const el=$('#follow-pill');if(!follow||!sel){el.hidden=true;return;}
  const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);if(!tr||tr.status!=='active'){stopFollow('Ціль більше не фіксується, стеження зупинено');return;}
  const d=DISP.get(sel);const r=d&&homeRel(tr,d.p);
  let ev='',sayK='';if(followPrev&&tr.last!==followPrev.last){ev='нова фіксація '+fmt(tr.last);sayK='go';el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}
  if(followPrev&&tr.next!==followPrev.next&&tr.next){ev='змінила курс → '+tr.next;sayK='turn';}
  const thrNow=!!(r&&r.rel);if(thrNow&&!followThr)sayK='threat';followThr=thrNow;
  if(sayK)followSay(tr,r,sayK,sayK==='turn'||sayK==='threat');followPrev={last:tr.last,next:tr.next,ev:ev||followPrev.ev};
  el.innerHTML='<span class="fp-dot" style="background:'+TYPE_COLOR[tr.type]+'"></span><div class="fp-t"><b>'+esc(TYPE_NAME[tr.type])+(tr.count>1?' ×'+tr.count:'')+(tr.next?' → '+esc(tr.next):'')+'</b><span>'+
    (r?Math.round(r.d)+' км '+r.side+' від вас'+(r.eta!=null?' · ~'+Math.max(1,Math.round(r.eta))+' хв до вас':''):'')+(followPrev.ev?' · '+esc(followPrev.ev):'')+' · фіксація '+fmt(tr.last)+'</span></div><button id="fp-card">Картка</button><button id="fp-stop">Зупинити</button>';
  el.hidden=false;try{const ao=$('#asof').getBoundingClientRect(),cn=$('#counters').getBoundingClientRect();el.style.top=(Math.max(ao.bottom,cn.bottom)+8)+'px';}catch(_){}// під лічильниками й плашкою «Наживо», не поверх них
  $('#fp-stop').onclick=e=>{e.stopPropagation();stopFollow('Стеження зупинено');};$('#fp-card').onclick=e=>{e.stopPropagation();$('#sheet').hidden=false;fillSheet(true);};}
/* «Чому тут?», рентген саме цієї цілі; «Карта на той момент», машина часу на першу публікацію про ціль */
if($('#sh-why'))$('#sh-why').onclick=()=>{if(!sel)return;
  // картка закриває мапу, ховаємо її (ціль лишається вибраною), вмикаємо рентген лише цієї цілі й летимо до неї
  $('#sheet').hidden=true;xrPanel().dataset.k='';if(!XRAY)setXray(true);else syncXray();const d=DISP.get(sel);if(d)map.flyTo({center:d.p,zoom:Math.max(map.getZoom(),9.5),duration:900,essential:true,padding:{bottom:Math.round(innerHeight*0.4)}});};
if($('#sh-then'))$('#sh-then').onclick=async()=>{const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);if(!tr)return;const t0=Math.max(tr.first||tr.last,liveNow()-2*3600);
  try{if(!HISTF.length){const j=await fetch('/api/history').then(r=>r.json());HISTF=j.frames||[];}}catch(e){}
  if(!HISTF.length)return toast('Історія ще збирається');let i=HISTF.findIndex(f=>f.t>=t0);if(i<0)i=HISTF.length-1;
  const id=tr.id;$('#sheet').hidden=true;$('#timebar').hidden=false;const r=$('#tb-range');r.max=HISTF.length-1;showFrame(i);play(true);
  const ft=(HISTF[i].tracks||[]).find(x=>x.id===id);if(ft){map.flyTo({center:[ft.lon,ft.lat],zoom:Math.max(map.getZoom(),9),duration:900});}
  toast('Програю з '+fmt(HISTF[i].t)+' до зараз'+(ft?', ціль у центрі':'')+'. «Наживо», вийти');};
$('#sh-follow').onclick=()=>{if(follow)stopFollow('Стеження зупинено');else startFollow();$('#sh-follow').classList.toggle('on',follow);$('#sh-follow').textContent=follow?'Зупинити':'Стежити';};
map.on('dragstart',e=>{if(follow&&e.originalEvent)stopFollow('Ви зсунули карту, стеження зупинено');});
setInterval(()=>{if(follow)renderFollow();},1000);

/* ---------- стрічка ---------- */
function renderFeed(){
  const kindTxt={launch:'Пуск',filtered:'Повідомлення про роботу ППО або влучання приховано фільтром безпеки.',close:'Ціль більше не фіксується',zone:'Загроза КАБ',info:'Без географічної привʼязки'};
  {const h=SNAP.health||{},c=h.channels||{};$('#dr-tech').textContent=(c.channels?'Канали: '+c.live+'/'+c.channels+(c.all_every?' · повний обхід '+c.all_every+' с':''):'')+(SNAP.official&&SNAP.official.source?' · тривоги: '+SNAP.official.source:'')+(h.version?'':' · стара версія сервера');}
  const LS=(SNAP.launches||[]).slice().reverse();
  const lh=LS.length?'<li class="launches"><div class="m"><span>Пуски за 6 год</span></div>'+LS.map(L=>'<div>'+fmt(L.t)+' · <b>'+esc(L.site)+'</b>'+(isTO(L)?' · носії в повітрі, пуску ще не повідомлено':(L.type?' · '+esc(TYPE_NAME[L.type]||L.type):''))+(L.count?' · '+cntL(L):'')+(L.carrier?' · '+esc(L.carrier):'')+(L.tracks?' · цілей звідти: '+L.tracks:'')+'</div>').join('')+'</li>':'';
  $('#feed').innerHTML=lh+SNAP.log.slice().reverse().filter(r=>r.kind!=='filtered').map(r=>{// повідомлення про ППО/влучання у стрічку не потрапляють взагалі (навіть заглушкою)
    const src=SNAP.sources[r.src]?.name||r.src;
    let txt=kindTxt[r.kind]||'';if(r.kind==='note')txt='⚠ Активність FPV · '+(r.text||'');if(r.kind==='track'||r.kind==='zone'){const tg=r.places.filter(p=>p.r==='t').map(p=>p.n),pos=r.places.find(p=>p.r==='p'),fr=r.places.find(p=>p.r==='f');txt=(TYPE_NAME[r.type]||'Ціль')+(r.count?' ×'+r.count:'')+(fr?' · з боку '+fr.n:'')+(pos?' · в районі '+pos.n:'')+(tg.length?(r.kind==='zone'?' · загроза для: ':' · курсом на ')+tg.slice(0,6).join(', '):'');}
    return '<li><div class="m"><span>'+fmt(r.t)+'</span><span>'+esc(src)+'</span>'+(r.track?'<span>→ '+esc(r.track)+'</span>':'')+(r.link?'<a href="'+esc(r.link)+'" target="_blank" rel="noopener">пост ↗</a>':'')+'</div><div class="'+(r.kind==='filtered'?'f':'')+'">'+esc(txt)+'</div></li>';}).join('')||'<li>Повідомлень ще немає.</li>';
}

/* ---------- кнопки ---------- */
// дім: змінити або видалити (з Налаштувань і дотиком до значка на мапі)
function delHome(){if(FOLHOME)homeSaved=null;if(!home)return;try{localStorage.setItem('home_prev',JSON.stringify(home));}catch(x){}home=null;try{localStorage.removeItem('home');localStorage.removeItem('wp_home');}catch(x){}
  syncHome();homeRow();try{renderMe([]);}catch(x){}toast('Дім видалено. Сповіщення про загрози для дому вимкнено');}
function realHome(){return FOLHOME?homeSaved:home;}
function homeRow(){const home=realHome();const l=$('#st-home-l');if(!l)return;l.textContent=home?'Дім: '+(homeObl()?homeObl()+' обл. · ':'')+home[1].toFixed(3)+', '+home[0].toFixed(3):'Дім не позначено';
  $('#st-home-set').textContent=home?'Змінити':'Позначити';$('#st-home-del').hidden=!home;}
if($('#st-home-set')){$('#st-home-set').onclick=()=>{if(!$('#settings').hidden)$('#st-close').click();armHome();};$('#st-home-del').onclick=()=>{if(confirmDel())delHome();};setTimeout(homeRow,1500);}
function confirmDel(){const b=$('#st-home-del');if(b.dataset.ask){delete b.dataset.ask;b.textContent='Видалити';return true;}b.dataset.ask='1';b.textContent='Точно видалити?';setTimeout(()=>{delete b.dataset.ask;b.textContent='Видалити';},4000);return false;}
map.on('click','home',e=>{const home=realHome();if(!home)return;const pp=new maplibregl.Popup({closeButton:false,offset:22,className:'home-pop'}).setLngLat(home)
  .setHTML('<div style="display:flex;gap:6px"><button class="pill" id="hp-move">Перемістити</button><button class="pill" id="hp-del">Видалити</button></div>').addTo(map);
  setTimeout(()=>{const m=document.getElementById('hp-move'),d=document.getElementById('hp-del');if(m)m.onclick=()=>{pp.remove();armHome();};if(d)d.onclick=()=>{pp.remove();delHome();};},0);});
$('#b-home').onclick=()=>{if(setHomeMode){disarmHome();toast('Скасовано');return;}if(home){map.flyTo({center:home,zoom:Math.max(map.getZoom(),9)});toast('Торкніться значка «Дім», щоб перемістити або видалити');return;}armHome();};
// довге натискання на «Дім» прибрано: на телефоні воно спрацьовувало випадково й наступний дотик переносив дім
$('#b-locate').onclick=()=>{if(!navigator.geolocation)return toast('Геолокація недоступна');navigator.geolocation.getCurrentPosition(p=>{const c=[p.coords.longitude,p.coords.latitude];map.flyTo({center:c,zoom:10});if(!home){home=c;localStorage.setItem('home',JSON.stringify(home));syncHome();toast('Дім = ваше місце');}},()=>toast('Не вдалося визначити місце'),{enableHighAccuracy:true,timeout:8000});};
$('#b-layers').onclick=()=>{if(TAC){PREF.tacSat=base!=='sat';savePref();setBase(PREF.tacSat?'sat':wantBase(effTheme()));toast(PREF.tacSat?'Супутник':'Схема');return;}
  const nx={night:'sat',sat:'map',map:'night'}[base]||'night';try{const p=JSON.parse(localStorage.getItem('pref')||'{}');p.base=nx;localStorage.setItem('pref',JSON.stringify(p));}catch(e){}setBase(nx);toast({night:'Ніч',sat:'Супутник',map:'Карта'}[nx]);};
function flat3d(on){// значок завжди «дивиться» на екран (як у 2D), без перспективних спотворень; у 3D лише коротша тінь
  if(map.getLayer('tg-sh')){map.setPaintProperty('tg-sh','icon-translate',on?[8,12]:[14,22]);map.setPaintProperty('tg-sh','icon-opacity',on?0.6:0.9);}}
function set3d(on,anim){tilt=on;flat3d(on);localStorage.setItem('t3d',on?'1':'0');$('#b-3d').classList.toggle('on',on);if(anim!=='keep')map.easeTo({pitch:on?55:0,bearing:0,duration:anim?700:0});}
$('#b-3d').onclick=()=>set3d(!tilt,true);
document.querySelectorAll('.tools [data-b]').forEach(b=>b.onclick=()=>{const t=document.getElementById(b.dataset.b);if(!t)return;const keep=b.dataset.b==='b-3d'||b.dataset.b==='b-layers';if(!keep)$('#settings').hidden=true;t.click();});
$('#b-daily').onclick=()=>{location.href='/daily.html';};
if($('#b-an'))$('#b-an').onclick=()=>{location.href='/analysis.html';};
$('#b-feed').onclick=()=>{$('#drawer').hidden=false;renderFeed();};
$('#dr-close').onclick=()=>$('#drawer').hidden=true;

/* ---------- живий потік ---------- */
// 08.11: ціль збито/вибухнула — на її місці коротка анімація вибуху, значок зникає (сервер віддає s.fx)
const BOOMED=new Set();
function showBooms(s){for(const b of (s.fx||[])){if(BOOMED.has(b.id+':'+b.t))continue;BOOMED.add(b.id+':'+b.t);if(Date.now()/1000-b.t>40)continue;
  try{const el=document.createElement('div');el.className='boom';el.innerHTML='<i></i><i></i><b>💥</b>';
    new maplibregl.Marker({element:el,pointerEvents:'none'}).setLngLat([b.lon,b.lat]).addTo(map);setTimeout(()=>{try{el.remove();}catch(e){}},2200);}catch(e){}}}
function onSnap(s){window.__snapOK=true;LIVE=s;if(REPLAY)return;SNAP=s;try{showBooms(s);}catch(e){}if(!introDone&&map.isStyleLoaded&&map.isStyleLoaded())setTimeout(()=>introFly(false),0);try{notesCheck(s);}catch(e){console.warn(e);}recvAt=Date.now();offset=s.now-Date.now()/1000;renderCounters();renderAsOf();syncLevels();syncZones();syncRaions();renderForecast();if(!$('#drawer').hidden)renderFeed();}
let LIVE=null,REPLAY=null;
// «зараз» за сервером, не залежить від того, на який кадр машини часу перемкнуто offset
const liveNow=()=>LIVE&&LIVE.now?LIVE.now+(REPLAY?0:Math.max(0,(Date.now()-recvAt)/1000)):Date.now()/1000;
/* ---------- прогноз ---------- */
function renderForecast(){const el=$('#fc');if(!el)return;el.innerHTML='';el.hidden=true;return;if(!SNAP||!SNAP.forecast||!SNAP.forecast.oblasts){el.innerHTML='';return;}const O=SNAP.forecast.oblasts;
  let mine=null;if(home&&window.OBLPOLY){mine=window.OBLPOLY(home[0],home[1]);}
  const rows=Object.entries(O).filter(([n,v])=>v.p60>=0.1).slice(0,4);if(mine&&O[mine]&&!rows.some(r=>r[0]===mine))rows.unshift([mine,O[mine]]);
  if(!rows.length){el.innerHTML=SNAP.tracks.some(t=>t.status==='active')?'':'<h4>Прогноз на годину</h4><p class="fc-calm">Нових загроз на найближчу годину не видно</p>';return;}
  el.innerHTML='<h4>Прогноз на годину <small>імовірність · ≈ скільки цілей</small></h4>'+rows.map(([n,v])=>{const p=Math.round(v.p60*100);const lv=p>=60?'hi':p>=30?'mid':'lo';
    return '<div class="fc-row'+(n===mine?' mine':'')+'"><span>'+esc(n)+(n===mine?' · ви тут':'')+'</span><i class="'+lv+'" style="width:'+Math.max(4,p)+'%"></i><b>'+p+'%'+(v.n60>=1?'<small title="очікувана кількість цілей за годину"> ≈'+Math.round(v.n60)+'</small>':'')+'</b></div>';}).join('');}
fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>{const P=j.features.map(f=>({n:f.properties.n,polys:f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates}));
  window.OBLPOLY=(lo,la)=>{for(const o of P)for(const pl of o.polys)if(inRing(pl[0],lo,la))return o.n;return null;};});
/* ---------- машина часу ---------- */
let HISTF=[],tbTimer=null;
$('#b-time').onclick=()=>{fetch('/api/history').then(r=>r.json()).then(j=>{HISTF=j.frames||[];if(!HISTF.length)return toast('Історія ще збирається, кадр щохвилини');
  $('#timebar').hidden=false;const r=$('#tb-range');r.max=HISTF.length-1;const t30=liveNow()-1800;let i0=HISTF.findIndex(f=>f.t>=t30);if(i0<0)i0=HISTF.length-1;showFrame(i0);play(true);toast('Програю останні 30 хв до зараз. ❚❚, пауза, −5/+5, крок, «Наживо», вийти');});};
function showFrame(i){const f=HISTF[i];if(!f)return;document.body.classList.add('replay');$('#tb-range').value=i;$('#tb-time').textContent=new Date(f.t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  REPLAY=f;SNAP=Object.assign({},LIVE||{},{now:f.t,levels:f.levels,official:Object.assign({},(LIVE&&LIVE.official)||{},{raion_levels:f.raions,points:[]}),
    tracks:f.tracks.map(t=>Object.assign({status:'active',speed:0,route:[],trail:[],route_names:[],srcs:(t.ev&&t.ev.prim)||[],links:[],first:f.t,last:f.t,ts:f.t,entry:[t.lon,t.lat,'',f.t],ev:{pubs:0,prim:[],items:[],contra:[],age:0}},t)),launches:[],zones:[],ru:[]});
  $('#tb-time').title='Що було відомо на цей момент';if(XRAY)syncXray();
  // докази кадру (хто й що писав ДО цього моменту), догружаємо лише для кадру, на якому зупинились
  clearTimeout(showFrame.ft);if(!f.full)showFrame.ft=setTimeout(()=>{if(REPLAY!==f)return;fetch('/api/history/frame?t='+f.t).then(r=>r.json()).then(g=>{if(!g||!g.tracks)return;g.full=1;HISTF[i]=g;if(REPLAY===f)showFrame(i);if(sel)fillSheet();}).catch(()=>{});},tbTimer?1500:250);
  offset=f.t-Date.now()/1000;recvAt=Date.now();DISP.clear();renderCounters();renderAsOf();syncLevels();syncRaions();}
function play(on){clearInterval(tbTimer);tbTimer=null;$('#tb-play').textContent=on?'❚❚':'▶';if(!on)return;tbTimer=setInterval(()=>{const r=$('#tb-range');const i=+r.value+1;if(i>=HISTF.length){play(false);return;}showFrame(i);},250);}
const tbStep=k=>{play(false);const r=$('#tb-range');const i=Math.max(0,Math.min(HISTF.length-1,+r.value+k));showFrame(i);};
if($('#tb-back'))$('#tb-back').onclick=()=>tbStep(-5);if($('#tb-fwd'))$('#tb-fwd').onclick=()=>tbStep(5);
$('#tb-play').onclick=()=>play(!tbTimer||$('#tb-play').textContent==='▶');
if($('#asof'))$('#asof').addEventListener('click',()=>{if(REPLAY)$('#tb-live').click();});
$('#tb-range').oninput=e=>{play(false);showFrame(+e.target.value);};
$('#tb-live').onclick=()=>{play(false);REPLAY=null;document.body.classList.remove('replay');setTimeout(renderAsOf,50);$('#timebar').hidden=true;DISP.clear();lastLv='';lastRa='';if(LIVE)onSnap(LIVE);};
/* ---------- «Що змінилося, поки мене не було?» ---------- */
function seenNow(){try{localStorage.setItem('seen',String(Math.round(Date.now()/1000+offset)));}catch(e){}}
setInterval(()=>{if(!document.hidden&&!REPLAY)seenNow();},30000);
document.addEventListener('visibilitychange',()=>{if(document.hidden)seenNow();else setTimeout(showChanges,1500);});
async function showChanges(force){
  if(!home||REPLAY)return;let seen=0;try{seen=+localStorage.getItem('seen')||0;}catch(e){}
  const nowS=Date.now()/1000+offset;if(!seen||(!force&&nowS-seen<180))return;
  const away=Math.round((nowS-seen)/60);seen=Math.max(seen,nowS-3600);// давніше за годину, не «що змінилось», а історія: показуємо лише останню годину
  const ob=homeObl();const q='lon='+home[0].toFixed(2)+'&lat='+home[1].toFixed(2)+'&since='+Math.round(seen)+(ob?'&obl='+encodeURIComponent(ob):'')+(homeObl.r?'&raion='+encodeURIComponent(homeObl.r):'');
  let j;try{j=await fetch('/api/changes?'+q,{cache:'no-store'}).then(r=>r.json());}catch(e){return;}seenNow();
  const min=Math.max(1,Math.round((nowS-seen)/60));const span=away>60?'за останню годину':'за '+min+' хв, поки вас не було';const place=ob?esc(ob)+' обл.'+(homeObl.r?' · '+esc(homeObl.r)+' р-н':''):'Ваше місце';
  let el=$('#chg');if(!el){el=document.createElement('div');el.id='chg';document.body.appendChild(el);}
  if(!j.total){el.hidden=true;toast('Біля вашого місця '+span.replace('за ','за ')+' змін не було');return;}
  const IC={official:'🔔',new:'＋',course:'↻',closer:'↘',away:'↗',lost:'?',closed:'✕'};
  el.hidden=false;el.innerHTML='<div class="chg-h"><b>'+place+'</b><span> · зміни '+span+'</span><button class="chg-x" aria-label="Закрити">✕</button></div>'+
    (()=>{const OF=ob?homeOfficial(ob):{on:j.official_now,t:j.official_now?'тривога':'тривоги немає'};return '<div class="me-off '+(OF.on===1?'on':OF.on===2?'part':'')+'"><i></i>Зараз: '+esc(OF.t)+'</div>';})()+
    '<ul>'+j.events.slice(0,6).map(e=>'<li class="k-'+e.k+'"><i>'+(IC[e.k]||'•')+'</i><span>'+esc(e.text)+' <small>'+fmt(e.t)+'</small></span></li>').join('')+'</ul>'+
    (j.total>6?'<div class="chg-more">ще '+(j.total-6)+'</div>':'')+
    (j.events.some(e=>e.from||e.to)?'<button class="pill chg-go">Показати '+(j.events.filter(e=>e.from||e.to).length)+' змін на карті →</button>':'');
  el.querySelector('.chg-x').onclick=()=>{el.hidden=true;clearChg();};
  const go=el.querySelector('.chg-go');if(go)go.onclick=()=>{clearTimeout(showChanges.t);el.hidden=true;playChanges(j.events);};
  // 07.11: на старті — згорнутий рядок (не закриває екран), висить 4 с і зникає; дотик розгортає і лишає
  el.classList.add('min');el.insertAdjacentHTML('afterbegin','<div class="chg-sum">'+j.total+' змін біля вас, поки вас не було · торкніться</div>');
  clearTimeout(showChanges.t);showChanges.t=setTimeout(()=>{if(!el.hidden){el.hidden=true;clearChg();}},4000);
  el.onclick=ev=>{if(el.classList.contains('min')&&!ev.target.closest('.chg-x')){el.classList.remove('min');clearTimeout(showChanges.t);
    showChanges.t=setTimeout(()=>{if(!el.hidden){el.hidden=true;clearChg();}},15000);}};}
function clearChg(){if(map.getSource('chg'))map.getSource('chg').setData({type:'FeatureCollection',features:[]});}
function playChanges(evs){
  if(!map.getSource('chg')){map.addSource('chg',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
    map.addLayer({id:'chg-l',type:'line',source:'chg',filter:['==',['get','g'],'l'],paint:{'line-color':['get','c'],'line-width':3,'line-dasharray':[1.5,1],'line-opacity':0.9}});
    map.addLayer({id:'chg-old',type:'circle',source:'chg',filter:['==',['get','g'],'old'],paint:{'circle-radius':6,'circle-color':'rgba(0,0,0,0)','circle-stroke-width':2,'circle-stroke-color':['get','c'],'circle-stroke-opacity':0.6}});
    map.addLayer({id:'chg-new',type:'circle',source:'chg',filter:['==',['get','g'],'new'],paint:{'circle-radius':7,'circle-color':['get','c'],'circle-stroke-width':2,'circle-stroke-color':'#fff'}});
    map.addLayer({id:'chg-t',type:'symbol',source:'chg',filter:['==',['get','g'],'new'],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,1.4],'text-anchor':'top','text-allow-overlap':false},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});}
  const C={new:'#FFB020',course:'#5AA9FF',closer:'#FF5A5A',away:'#7CD992',lost:'#9AA4B8',closed:'#9AA4B8'};const F=[];const pts=[home];
  const L={new:'нова',course:'курс уточнено',closer:'наблизилась',away:'віддаляється',lost:'втрачено',closed:'закрито'};
  for(const e of evs){if(!(e.from||e.to))continue;const c=C[e.k]||'#fff';
    if(e.from){F.push({type:'Feature',properties:{g:'old',c},geometry:{type:'Point',coordinates:e.from}});pts.push(e.from);}
    if(e.from&&e.to)F.push({type:'Feature',properties:{g:'l',c},geometry:{type:'LineString',coordinates:[e.from,e.to]}});
    if(e.to){F.push({type:'Feature',properties:{g:'new',c,l:L[e.k]+' · '+fmt(e.t)},geometry:{type:'Point',coordinates:e.to}});pts.push(e.to);}
    else F.push({type:'Feature',properties:{g:'new',c,l:L[e.k]+' · '+fmt(e.t)},geometry:{type:'Point',coordinates:e.from}});}
  map.getSource('chg').setData({type:'FeatureCollection',features:F});
  const b=pts.reduce((b,p)=>[[Math.min(b[0][0],p[0]),Math.min(b[0][1],p[1])],[Math.max(b[1][0],p[0]),Math.max(b[1][1],p[1])]],[[180,90],[-180,-90]]);
  map.fitBounds(b,{padding:{top:90,bottom:200,left:40,right:40},maxZoom:10,duration:1200});
  clearTimeout(playChanges.t);playChanges.t=setTimeout(clearChg,45000);toast('Кружечок, де було, крапка, де зараз');}
setTimeout(()=>showChanges(),6000);
/* ---------- телефон: панель стану згорнута, тап, розгорнути ---------- */
// 05.11: червона картка загрози закривала весь екран. Згортається кнопкою ▾, дотиком по картці, змахом униз; сама згортається за 15 с без дотиків.
// У згорнутій лишаються смуга тривоги, назва загрози й «Перейдіть в укриття».
const meFold=on=>{const b=$('#me'),fb=$('#me-fold');clearTimeout(window.__foldT);b.classList.toggle('fold',on);if(fb)fb.setAttribute('aria-label',on?'Розгорнути':'Згорнути');};
{const fb=$('#me-fold');if(fb)fb.onclick=e=>{e.stopPropagation();meFold(!$('#me').classList.contains('fold'));};}
$('#me').addEventListener('click',e=>{const b=$('#me');if(e.target.closest('li a,button,a'))return;
  if(b.classList.contains('bal')){if(Date.now()-(window.__meSw||0)<400)return;meFold(!b.classList.contains('fold'));return;}
  if(innerWidth>640||e.target.closest('li'))return;b.classList.toggle('open');});
{let y0=null,x0=0;const b=$('#me');b.addEventListener('touchstart',e=>{y0=e.touches[0].clientY;x0=e.touches[0].clientX;clearTimeout(window.__foldT);},{passive:true});
  b.addEventListener('touchend',e=>{if(y0==null)return;const t=e.changedTouches[0],dy=t.clientY-y0,dx=t.clientX-x0;y0=null;if(Math.abs(dy)<28||Math.abs(dy)<Math.abs(dx)*1.5)return;
    if(b.scrollTop>0&&dy<0)return;window.__meSw=Date.now();if(b.classList.contains('bal'))meFold(dy>0);else if(innerWidth<=640)b.classList.toggle('open',dy<0);},{passive:true});}
/* ---------- віджет для Windows ---------- */
if(new URLSearchParams(location.search).has('mini'))document.body.classList.add('mini');
async function openWidget(){
  if(!('documentPictureInPicture' in window)){window.open(location.origin+'/?mini=1','tryvoga-mini','width=400,height=300');return;}
  const pip=await documentPictureInPicture.requestWindow({width:400,height:300});
  [...document.styleSheets].forEach(ss=>{try{const st=document.createElement('style');st.textContent=[...ss.cssRules].map(r=>r.cssText).join('\n');pip.document.head.appendChild(st);}catch(e){const l=document.createElement('link');l.rel='stylesheet';l.href=ss.href;pip.document.head.appendChild(l);}});
  pip.document.documentElement.dataset.theme=document.documentElement.dataset.theme;pip.document.body.className='mini pip';
  const upd=()=>{pip.document.body.innerHTML=$('#me').outerHTML;const m=pip.document.querySelector('#me');if(m)m.onclick=()=>window.focus();};
  upd();const h=setInterval(upd,1000);pip.addEventListener('pagehide',()=>clearInterval(h));}
window.__openWidget=openWidget;
/* ---------- «Рентген неба» ---------- */
let XRAY=false;
function setXray(on){XRAY=on;document.body.classList.toggle('xray',on);if($('#b-xray'))$('#b-xray').classList.toggle('on',on);const lg=$('#xr-legend');if(lg)lg.hidden=true;
  for(const id of ['xr-dim','xr-edge','xr-edge2','xr-node','xr-t'])if(map.getLayer(id))map.setLayoutProperty(id,'visibility',on?'visible':'none');
  for(const id of ['holo','holo-top','ra-glow'])if(map.getLayer(id))map.setLayoutProperty(id,'visibility',on?'none':'visible');
  const pn=xrPanel();pn.hidden=!on;if(on&&!sel)pn.innerHTML='<div class="xp-h"><b>Де ціль?</b><button class="xp-x">Готово</button></div><p class="xp-n">Торкніться будь-яку ціль на мапі, покажу по кроках, хто й коли про неї написав і що з цього SKY вирахував сам.</p>';
  if(on&&sel)xrMsg('Завантажую повідомлення про ціль…');
  if(on&&!sel)pn.querySelector('.xp-x').onclick=()=>setXray(false);
  syncXray();}
function xrPanel(){let p=$('#xr-panel');if(!p){p=document.createElement('div');p.id='xr-panel';p.hidden=true;document.body.appendChild(p);}return p;}
// окремої кнопки «Рентген» більше немає: пояснення відкривається лише з картки цілі («Чому SKY показує її тут?»)
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&XRAY)setXray(false);});
map.on('styledata',()=>{if(XRAY&&map.getLayer('xr-dim')&&map.getLayoutProperty('xr-dim','visibility')!=='visible')setXray(true);});
// панель рентгену ніколи не лишається порожньою: заголовок, пояснення стану і «Готово»
function xrMsg(t){const pn=xrPanel();pn.dataset.k='';pn.hidden=false;pn.innerHTML='<div class="xp-h"><b>Де ціль?</b><button class="xp-x">Готово</button></div><p class="xp-n">'+t+'</p>';pn.querySelector('.xp-x').onclick=()=>setXray(false);}
function syncXray(){if(!XRAY)return;
  if(!SNAP||!map.getSource('xr')){xrMsg('Завантажую дані…');return;}
  try{syncXray0();}catch(e){xrMsg('Не вдалося показати пояснення. Закрийте й торкніться ціль ще раз.');}}
function syncXray0(){
  const tr=sel&&SNAP.tracks.find(t=>t.id===sel);const F=[];
  if(!tr){map.getSource('xr').setData({type:'FeatureCollection',features:F});
    if(sel){if(xrPanel().dataset.k!=='gone')xrMsg('Цієї цілі вже немає в даних: канали перестали про неї писати або її обʼєднано з іншою. Торкніться іншу ціль.');xrPanel().dataset.k='gone';}
    else if(!xrPanel().innerHTML.trim())xrMsg('Торкніться будь-яку ціль на мапі, покажу по кроках, хто й коли про неї написав.');
    return;}
  const nm=k=>SNAP.sources[k]?.name||k;const d=DISP.get(tr.id);
  const items=((tr.ev&&tr.ev.items)||(REPLAY?null:evItems(tr.id,syncXray))||[]).slice().sort((a,b)=>a.t-b.t);
  const prim=items.filter(i=>!i.copy),copies=items.filter(i=>i.copy);
  // кроки на мапі, лише місця, які назвали канали (і оцінені SKY з їхніх слів); номер = порядок у списку нижче
  let n=0;const path=[];const rows=[];
  for(const it of prim){const cp=copies.filter(c=>c.copy===it.src&&Math.abs(c.t-it.t)<600).map(c=>nm(c.src));
    let num=null;
    if(it.p&&it.pt!=='dest'){n++;num=n;F.push({type:'Feature',properties:{k:'step',l:String(n)},geometry:{type:'Point',coordinates:it.p}});path.push(it.p);}
    else if(it.p&&it.pt==='dest'&&path.length){F.push({type:'Feature',properties:{k:'destl'},geometry:{type:'LineString',coordinates:[path[path.length-1],it.p]}});
      F.push({type:'Feature',properties:{k:'dest',l:'→ '+(it.dest||'')},geometry:{type:'Point',coordinates:it.p}});}
    const what=it.pt==='pos'?'назвав, де ціль':it.pt==='est'?'назвав напрямок, SKY оцінив місце':it.dest?'назвав курс → '+esc(it.dest):'підтвердив';
    rows.push('<li>'+(num?'<i class="xp-num">'+num+'</i>':'<i class="xp-num o">·</i>')+'<div><div class="xp-m"><b>'+fmt(it.t)+' · '+esc(nm(it.src))+'</b>, '+what+(it.link?' <a href="'+esc(it.link)+'" target=_blank rel=noopener>пост ↗</a>':'')+'</div>'+
      (it.text?'<q>'+esc(it.text.length>120?it.text.slice(0,118)+'…':it.text)+'</q>':'')+(cp.length?'<div class="xp-c">повторили (копії, не нове підтвердження): '+esc(cp.join(', '))+'</div>':'')+'</div></li>');}
  for(let k=1;k<path.length;k++)F.push({type:'Feature',properties:{k:'path'},geometry:{type:'LineString',coordinates:[path[k-1],path[k]]}});
  let nowRow='';
  if(d){F.push({type:'Feature',properties:{k:'now',l:'зараз · оцінка SKY'},geometry:{type:'Point',coordinates:d.p}});
    if(path.length)F.push({type:'Feature',properties:{k:'nowl'},geometry:{type:'LineString',coordinates:[path[path.length-1],d.p]}});
    const age=Math.max(0,Math.round(((tr.ev&&tr.ev.age)||0)/60+(Date.now()/1000+offset-SNAP.now)/60));
    const km=path.length?Math.round(dist(xy(path[path.length-1]),xy(d.p))):0;
    nowRow='<li class="now"><i class="xp-num p">●</i><div><div class="xp-m"><b>Зараз</b>, оцінка SKY, не повідомлення</div><div class="xp-c">Останнє місце від каналів, '+age+' хв тому; відтоді ціль «просунута» на ~'+km+' км '+(tr.next?'в бік '+esc(tr.next):tr.hd!=null?'тим самим курсом':'курс невідомий, тому стоїть на місці')+'.</div></div></li>';}
  const E=tr.ev||{};const ind=(E.prim||[]).length;
  const contra=(E.contra||[]).length>1?'<div class="xp-w">⚠ Канали розходяться в курсі: '+E.contra.map(v=>'→ '+esc(v.dest||'?')+' ('+v.srcs.map(x=>esc(nm(x))).join(', ')+')').join('; ')+'</div>':'';
  map.getSource('xr').setData({type:'FeatureCollection',features:F});
  const pn=xrPanel();const key=tr.id+'|'+items.length+'|'+Math.floor(Date.now()/60000);if(pn.dataset.k===key&&!pn.hidden)return;pn.dataset.k=key;pn.hidden=false;
  pn.innerHTML='<div class="xp-h"><b>'+esc(TYPE_NAME[tr.type]||'Ціль')+': де ціль?</b><button class="xp-x">Готово</button></div>'+
    '<p class="xp-n">'+(E.pubs||items.length)+' повідомл. · '+ind+' '+(ind===1?'незалежне джерело':'незалежних джерела')+(ind<2?', <b>ще не підтверджено другим джерелом</b>':'')+(ind?': '+(E.prim||[]).map(x=>esc(nm(x))).join(', '):'')+'</p>'+contra+
    (items.length?'<ol class="xp-l">'+rows.join('')+nowRow+'</ol>':'<p class="xp-n">Завантажую повідомлення…</p>');
  pn.querySelector('.xp-x').onclick=()=>{const id=sel;setXray(false);if(id){sel=id;$('#sheet').hidden=false;fillSheet(true);}};}
setInterval(syncXray,1000);
/* ---------- небо в камері ---------- */
$('#b-ar').onclick=()=>{location.href='ar.html';};
let ws,backoff=1000;
function connect(){
  const proto=location.protocol==='https:'?'wss':'ws';ws=new WebSocket(proto+'://'+location.host+'/ws');
  ws.onmessage=e=>{backoff=1000;const s=JSON.parse(e.data);if(LIVE){if(!s.sources)s.sources=LIVE.sources;if(!s.log)s.log=LIVE.log;}s.sources=s.sources||{};s.log=s.log||[];onSnap(s);};ws.onopen=()=>{if(document.hidden)ws.send('hidden');};
  ws.onclose=()=>{setTimeout(connect,backoff);backoff=Math.min(backoff*2,15000);};
  ws.onerror=()=>ws.close();
}
connect();
setInterval(()=>{if(ws&&ws.readyState===1)ws.send('ping');},20000);
// фонова вкладка / згорнутий застосунок: сервер шле рідше (економія трафіку й батареї); повернення, одразу свіжий стан
document.addEventListener('visibilitychange',()=>{if(ws&&ws.readyState===1)ws.send(document.hidden?'hidden':'visible');});

/* ---------- налаштування, теми, шари ---------- */
const PREF=Object.assign({theme:'night',base:null,sound:false,ru:true,launch:true,zones:true,wm:true},(()=>{try{return JSON.parse(localStorage.getItem('pref')||'{}');}catch(e){return {};}})());
// темна тема за замовчуванням (02.11): збережене раніше «Авто» переводимо в «Ніч» один раз; свідомий вибір після цього не чіпаємо
if(!PREF.darkV2){if(PREF.theme==='auto')PREF.theme='night';PREF.darkV2=1;try{localStorage.setItem('pref',JSON.stringify(PREF));}catch(e){}}
const savePref=()=>{try{localStorage.setItem('pref',JSON.stringify(PREF));}catch(e){}};
function sunNight(){const p=home||[31.5,49];const d=new Date();const doy=Math.floor((d-new Date(d.getFullYear(),0,0))/864e5);
  const decl=23.44*Math.sin(2*Math.PI*(284+doy)/365)*D2R,lat=p[1]*D2R;const h0=Math.acos(Math.max(-1,Math.min(1,(Math.sin(-0.83*D2R)-Math.sin(lat)*Math.sin(decl))/(Math.cos(lat)*Math.cos(decl)))))/D2R;
  const noonUTC=12-p[0]/15;const rise=noonUTC-h0/15,set=noonUTC+h0/15;const u=d.getUTCHours()+d.getUTCMinutes()/60;return !(u>rise&&u<set);}
function effTheme(){return PREF.theme==='auto'?(sunNight()?'night':'day'):PREF.theme;}
function applyTheme(force){const th=effTheme();document.documentElement.dataset.theme=th;window.FXDAY=th==='day';
  const want=wantBase(th);if(force||want!==base)setBase(want);
  $('#st-theme-note').textContent=PREF.theme==='auto'?('Зараз: '+(th==='night'?'ніч':'день')+', перемикається само за сходом і заходом сонця над вашим домом.'):'';syncSettingsUI();}
function syncSettingsUI(){document.querySelectorAll('.seg[data-pref]').forEach(g=>{const k=g.dataset.pref;const v=k==='mode'?(TAC?'tac':'norm'):k==='base'?base:k==='shelter'?String(SHELTER):PREF[k];g.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v===String(v)));});
  $('#st-3d').checked=tilt;$('#st-sys').checked=!!PREF.sys&&'Notification' in window&&Notification.permission==='granted';$('#st-ru').checked=!!PREF.ru;$('#st-launch').checked=!!PREF.launch;$('#st-zones').checked=!!PREF.zones;$('#st-wm').checked=PREF.wm!==false;document.body.classList.toggle('wm',PREF.wm!==false);}
function applyLayers(){const vis=(ids,on)=>ids.forEach(i=>{if(map.getLayer(i))map.setLayoutProperty(i,'visibility',on?'visible':'none');});
  vis(['ru-glow','ru-dot','ru-t','hits'],PREF.ru);vis(['chains','lsites','lsites-t'],PREF.launch);vis(['zones','zones-t','avia','avia-z','avia-zl','avia-l'],PREF.zones);
  if(TAC)vis(['holo','holo-top','ra-glow'],false);
  if(TAC)vis(['tg-n','strat-ring','strat-fxl','strat-fxp'],false);
  vis(['enemy-sym','enemy-hot'],TAC?TACF.enemy:true);vis(['reach-f','reach-l','reach-t'],TAC&&TACF.reach);vis(['meas-l','meas-p','meas-t'],TAC);
  if(TAC&&!TACF.alerts)vis(['hp-f','hp-l','hrom','hrom-t'],false);}
map.on('styledata',()=>{if(map.getLayer('ru-glow'))applyLayers();});
function syncRu(){if(!SNAP||!map.getSource('ru'))return;map.getSource('ru').setData(EMPTY);return;// заяви МО РФ «скільки збили над регіоном» прибрано з мапи: застарілі зведення без місця й часу удару нічого не дають людині

  // останнє зведення МО РФ: на карті, лише точки регіонів (з кількістю, якщо названа) і ОДИН підсумковий підпис
  const ev=(SNAP.ru||[]).slice().sort((a,b)=>b.t-a.t)[0];if(!ev){map.getSource('ru').setData(EMPTY);return;}
  const PER=p=>!p?'':/ноч/.test(p)?'за ніч':/дня/.test(p)?'за день':/суток/.test(p)?'за добу':'';
  const F=ev.regions.map(r=>({type:'Feature',properties:{c:r.cnt?Math.min(12,r.cnt/3):3,l:'Наші БпЛА над '+r.n+(r.cnt?' · ×'+r.cnt:'')+'\n'+PER(ev.period)+(PER(ev.period)?' до ':'')+fmt(ev.t)+' · заява МО РФ',n:r.n,cnt:r.cnt||0},geometry:{type:'Point',coordinates:[r.lon,r.lat]}}));
  const lo=ev.regions.reduce((s,r)=>s+r.lon,0)/ev.regions.length,la=ev.regions.reduce((s,r)=>s+r.lat,0)/ev.regions.length;
  F.push({type:'Feature',properties:{c:0,sum:true,l:'Наші дрони над РФ '+PER(ev.period)+': '+ev.total+' «збитих» за МО РФ · '+ev.regions.length+' рег. · '+fmt(ev.t)},geometry:{type:'Point',coordinates:[lo+1.5,la+0.6]}});
  map.getSource('ru').setData({type:'FeatureCollection',features:F});}
setInterval(syncRu,5000);
let HITS=[];
function syncHits(){if(!SNAP||!map.getSource('hits'))return;
  const nowS=Date.now()/1000+offset,t24=nowS-86400;// лише свіжі (за добу), вчорашні влучання не про сьогоднішню ніч
  const seen=new Map();// одна подія = один вогник: ключ — пост, місце й об'єкт (два уражені об'єкти в одному місті дають два вогники)
  for(const h of (SNAP.hits||[]).filter(h=>h.t>=t24).sort((a,b)=>b.t-a.t)){const k=(h.link||h.t)+'|'+h.place+'|'+h.what;if(!seen.has(k))seen.set(k,h);}
  HITS=[...seen.values()];
  // кілька подій в одній точці: розводимо віялом (~2 км), щоб кожен вогник було видно й можна було торкнутись
  const grp={};HITS.forEach((h,i)=>{const g=h.lat.toFixed(2)+','+h.lon.toFixed(2);(grp[g]=grp[g]||[]).push(i);});
  const pos=HITS.map(h=>[h.lon,h.lat]);for(const g in grp){const ix=grp[g];if(ix.length<2)continue;ix.forEach((i,n)=>{const a=-Math.PI/2+n*2*Math.PI/ix.length,r=0.022;pos[i]=[HITS[i].lon+r*Math.cos(a)/Math.cos(HITS[i].lat*Math.PI/180),HITS[i].lat+r*Math.sin(a)];});}
  const hm=t=>new Date(t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  map.getSource('hits').setData({type:'FeatureCollection',features:HITS.map((h,hi)=>({type:'Feature',properties:{hi,wb:!!h.wb,fresh:(nowS-h.t)<10800,l:(h.wb?'🔥 ':'')+h.what+'\n'+h.place+' · '+hm(h.t),link:h.link},geometry:{type:'Point',coordinates:pos[hi]}}))});}
setInterval(syncHits,10000);
$('#b-set').onclick=()=>{$('#settings').hidden=false;syncSettingsUI();loadLan();
  const h=SNAP&&SNAP.health||{},c=h.channels||{};if(c.channels)$('#st-tech').textContent='SKY збирає повідомлення '+c.channels+' моніторингових каналів (зараз оновлюються '+(c.live||0)+') і офіційні тривоги, звіряє їх між собою й показує, наскільки підтверджена кожна ціль і наскільки точно відоме її місце. Роботу ППО та влучання в Україні не показуємо.';
  {const dl=$('#fb-dlg'),msg=$('#fb-msg');$('#st-fb-open')&&($('#st-fb-open').onclick=()=>{msg.textContent='';dl.showModal?dl.showModal():dl.setAttribute('open','')});$('#fb-close')&&($('#fb-close').onclick=()=>dl.close?dl.close():dl.removeAttribute('open'));
    $('#fb-send')&&($('#fb-send').onclick=async()=>{const t=$('#fb-text').value.trim();if(t.length<3){msg.textContent='Напишіть хоча б кілька слів.';return}msg.textContent='Надсилаю…';try{const r=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t,contact:$('#fb-contact').value,v:(($('#st-ver')||{}).textContent||'').slice(0,40)})});let j={};try{j=await r.json()}catch(e){msg.textContent='Помилка сервера '+r.status+'. Спробуйте пізніше.';return}if(j.ok){msg.textContent='Дякуємо! Повідомлення надіслано.';$('#fb-text').value='';setTimeout(()=>dl.close&&dl.close(),1500)}else msg.textContent=j.why==='rate'?'Зачекайте хвилину й спробуйте ще.':'Не вдалося надіслати.'}catch(e){msg.textContent='Немає зв’язку. Спробуйте пізніше.'}})}
  const so=$('#st-online');if(so){const upd=async()=>{try{const j=await (await fetch('/api/online',{cache:'no-store'})).json();if(typeof j.online==='number'){so.hidden=false;so.textContent='Зараз онлайн: '+j.online;}}catch(e){}};upd();setInterval(upd,30000);}
  const sv=$('#st-ver');if(sv){const show=b=>{const AV = 499,dd=Math.max(0,Math.floor((Date.now()-Date.UTC(2026,10,1))/864e5)),bb=b?(Math.floor(b/100)+'.'+String(b%100).padStart(2,'0')):'';sv.textContent='Версія '+Math.floor(dd/7)+'.'+(dd%7)+(bb?' · збірка '+bb:'');};show(window.__SKYBUILD);if(!window.__SKYBUILD)fetch('/sw.js').then(r=>r.text()).then(t=>{const m=t.match(/tryvoga-v(\d+)/);window.__SKYBUILD=m?m[1]:'';show(window.__SKYBUILD);}).catch(()=>{});}};
$('#st-close').onclick=()=>$('#settings').hidden=true;
if($('#st-widget'))$('#st-widget').onclick=()=>window.__openWidget&&window.__openWidget();
if($('#st-widget-sec'))$('#st-widget-sec').hidden=new URLSearchParams(location.search).get('app')==='widget'||!/Windows NT/.test(navigator.userAgent);// лише на комп'ютерах з Windows
document.querySelectorAll('.seg[data-pref]').forEach(g=>g.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const k=g.dataset.pref,v=b.dataset.v;
  if(k==='mode'){setTac(v==='tac');}
  else if(k==='theme'){PREF.theme=v;PREF.base=null;savePref();applyTheme(true);}
  else if(k==='base'){PREF.base=v;if(TAC){PREF.tacSat=v==='sat';}savePref();if(!TAC)setBase(v);else if(v==='sat'||PREF.tacSat===false)setBase(wantBase(effTheme()));setTimeout(syncSettingsUI,50);}
  else if(k==='shelter'){SHELTER=+v;localStorage.setItem('shelter',SHELTER);if($('#me-sh'))$('#me-sh').textContent=SHELTER;syncSettingsUI();}}));
$('#st-3d').onchange=e=>set3d(e.target.checked,true);
(function(){const S=window.NXSound;if(!S)return;const g=S.get();
  const segs={'snd-mode':'mode','snd-tone':'tone','snd-voice':'voice'};
  Object.entries(segs).forEach(([id,k])=>{const box=document.getElementById(id);if(!box)return;box.querySelectorAll('button').forEach(b=>{b.classList.toggle('on',b.dataset.v===g[k]);b.onclick=()=>{S.set(k,b.dataset.v);box.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));if(k==='voice'){S.speakOnly('Привіт. Так звучить голос '+b.textContent+'.');}else if(k==='tone'||b.dataset.v!=='off')S.test();};});});
  const vol=document.getElementById('snd-vol');if(vol){vol.value=Math.round(g.vol*100);vol.oninput=()=>S.set('vol',vol.value/100);}
  const tb=document.getElementById('snd-test');if(tb)tb.onclick=()=>S.test();
  const vh=document.getElementById('snd-voice-hint');if(vh)setTimeout(()=>{fetch('/api/tts/status').then(r=>r.json()).then(t=>{vh.textContent=t.neural?'Природний нейромережевий голос, українська з правильними наголосами; Лада й Тетяна жіночі, Микита й Олекса чоловічі':t.ready?'Голоси Лада, Тетяна, Микита, Олекса, українська озвучка сервера':'Готую українську озвучку на сервері (перший раз кілька хвилин); поки, голос пристрою';}).catch(()=>{});},1200);})();
$('#st-sys').onchange=async e=>{if(e.target.checked&&'Notification' in window&&Notification.permission!=='granted'){const r=await Notification.requestPermission();if(r!=='granted'){e.target.checked=false;toast('Браузер не дозволив сповіщення');}}PREF.sys=e.target.checked;savePref();webPushSync(true);};
/* ---------- Web Push: сповіщення від сервера навіть із закритим сайтом ---------- */
function b64u(s){const p='='.repeat((4-s.length%4)%4);const b=atob((s+p).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(b,c=>c.charCodeAt(0));}
async function webPushSync(loud){const H0=realHome();
  if(!('serviceWorker' in navigator)||!('PushManager' in window)){wpStatus(null,/iPhone|iPad/.test(navigator.userAgent)?'відкрийте SKY з іконки на початковому екрані («Поділитися» → «На початковий екран»)':'цей браузер не підтримує');if(loud&&PREF.sys)toast(/iPhone|iPad/.test(navigator.userAgent)?'На iPhone: «Поділитися → На початковий екран», потім відкрийте звідти':'Цей браузер не підтримує сповіщення із закритим сайтом');return;}
  try{// якщо служба сповіщень не запустилась, ready чекає вічно: обмежуємо 8 с і кажемо про це
    const reg=await Promise.race([navigator.serviceWorker.ready,new Promise((_,j)=>setTimeout(()=>j(new Error('служба сповіщень не запустилась. Закрийте SKY свайпом і відкрийте з іконки ще раз')),8000))]);let sub=await reg.pushManager.getSubscription();
    if(!PREF.sys||!H0||Notification.permission!=='granted'){
      if(sub){fetch('/api/webpush/unsubscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:sub.endpoint})}).catch(()=>{});await sub.unsubscribe();try{localStorage.removeItem('wp_home');}catch(e){}}
      if(loud&&PREF.sys&&!H0)toast('Позначте своє місце, тоді сервер стежитиме за загрозами для нього');
      wpStatus(null,!H0?'не позначено дім':Notification.permission==='denied'?'телефон заборонив: Налаштування iPhone → Сповіщення → NAVRYX SKY':!PREF.sys?'вимкнено':'немає дозволу');return;}
    if(!sub){const {key}=await fetch('/api/webpush/key').then(r=>r.json());sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64u(key)});}
    // обрані області й громади (явно, не автоматична «область дому») — сервер шле по них зведення навіть із закритим застосунком
    const MZ=myZones(),zones=!MZ.auto&&((MZ.obl&&MZ.obl.length)||(MZ.hrom&&MZ.hrom.length))?{obl:MZ.obl||[],hrom:(MZ.hrom||[]).map(h=>h.id)}:null;// область дому «автоматично» не шлемо: зведення по всій області засмічує// без явного вибору — область дому
    const hk=H0.map(v=>v.toFixed(2)).join(',')+'|'+sub.endpoint.slice(-24)+'|'+(PREF.pre!==false)+'|'+JSON.stringify(zones);let prev=null;try{prev=localStorage.getItem('wp_home');}catch(e){}
    if(prev!==hk||loud){const r=await fetch('/api/webpush/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sub:sub.toJSON(),lon:+H0[0].toFixed(2),lat:+H0[1].toFixed(2),pre:PREF.pre!==false,zones})});
      if(r.ok){try{localStorage.setItem('wp_home',hk);}catch(e){}if(loud)toast('Сповіщення на заблокований екран увімкнено');}}
    wpStatus(sub);
  }catch(e){wpStatus(null,'помилка: '+(e&&e.message||e));if(loud)toast('Не вдалося увімкнути сповіщення: '+(e&&e.message||e));}}
// стан підписки й кнопка «Надіслати тестове»: щоб перевірити, що сповіщення справді доходять на цей телефон
function wpStatus(sub,why){const row=$('#st-wp-row');if(!row)return;row.hidden=false;const st=$('#st-wp-st'),bt=$('#st-wp-test');
  window.__wpOK=!!sub;
  if(!sub){st.textContent='✗ Сповіщення на цей пристрій не надходять: '+(why||'не увімкнено');bt.textContent='Увімкнути';bt.onclick=()=>pushEnable();return;}
  bt.textContent='Надіслати тестове';
  st.textContent='✓ Цей пристрій отримує сповіщення про загрози для вашого дому';
  $('#st-wp-test').onclick=async()=>{const r=await fetch('/api/webpush/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:sub.endpoint})}).catch(()=>null);
    const j=r?await r.json().catch(()=>({})):{};toast(r&&r.ok?'Надіслано. Заблокуйте екран: сповіщення має прийти за кілька секунд':'Не вдалося: '+(j.why||'немає звʼязку'));};}
if($('#st-pre')){$('#st-pre').checked=PREF.pre!==false;$('#st-pre').onchange=e=>{PREF.pre=e.target.checked;savePref();webPushSync(false);};}
window.webPushSync=webPushSync;setTimeout(()=>webPushSync(false),4000);
/* одне натискання замість трьох кроків: картка «Увімкнути сповіщення» (iPhone дозволяє вмикати лише дотиком користувача) */
function pushCard(){if(document.getElementById('push-card'))return;
  const ios=/iPhone|iPad/.test(navigator.userAgent),standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
  const can='serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window;
  // не частіше за раз на 3 дні, максимум 3 рази; лічильник росте лише від натискання кнопки (автозникнення відмовою не вважається)
  const DAY=864e5,GAP=3*DAY,MAX=3;let n=0,last=0;
  try{n=+localStorage.getItem('push_card_n')||0;last=+localStorage.getItem('push_card_t')||0;
    if(!n&&(localStorage.getItem('push_card_once')||localStorage.getItem('push_card_x'))){n=1;last=+localStorage.getItem('push_card_once')||Date.now();}}catch(e){return;}
  if(n>=MAX||(last&&Date.now()-last<GAP))return;
  if(can&&Notification.permission==='granted'&&PREF.sys!==false&&window.__wpOK!==false)return;// push уже увімкнено
  if(can&&Notification.permission==='denied')return;
  let txt,btn;
  if(!can&&ios&&!standalone){txt='Щоб SKY попереджав навіть із закритим телефоном: «Поділитися» → «На початковий екран», і відкрийте SKY звідти.';btn=null;}
  else if(can){txt=H0?'Попереджати про загрози для вашого дому й області навіть із закритим застосунком?':'Позначте свій дім, і SKY попереджатиме про загрози для нього навіть із закритим застосунком.';btn=H0?'Увімкнути сповіщення':'Позначити дім';}
  else return;
  let alarm=false;try{const ho=homeObl();alarm=!!(ho&&typeof SNAP!=='undefined'&&SNAP&&SNAP.levels&&SNAP.levels[ho]);}catch(e){}// 12.11: лише область користувача — десь в Україні тривога є майже завжди
  const el=document.createElement('div');el.id='push-card';el.className='push-card'+(alarm?' compact':'');
  el.innerHTML=alarm?'<span>🔔 Триває тривога. '+esc(btn?'Увімкніть сповіщення, щоб не пропустити наступну.':txt)+'</span><div>'+(btn?'<button class="pill primary" id="pc-on">'+btn+'</button>':'')+'<button class="pill" id="pc-x">Пізніше</button></div>'
    :'<b>🔔 Сповіщення</b><span>'+esc(txt)+'</span><div>'+(btn?'<button class="pill primary" id="pc-on">'+btn+'</button>':'')+'<button class="pill" id="pc-x">Пізніше</button></div>';
  document.body.appendChild(el);
  const mark=()=>{try{localStorage.setItem('push_card_n',String(n+1));localStorage.setItem('push_card_t',String(Date.now()));}catch(e){}};
  // автозникнення (поза тривогою) нічого не запамʼятовує, картка зʼявиться знову згідно з графіком
  if(!alarm)setTimeout(()=>{if(el.isConnected)el.remove();},25000);
  $('#pc-x').onclick=()=>{mark();el.remove();toast('Увімкнути можна будь-коли: Налаштування → Сповіщення');};
  const on=$('#pc-on');if(on)on.onclick=async()=>{mark();el.remove();if(!H0){armHome();return;}await pushEnable();};}
async function pushEnable(){
  {
    if(!H0){toast('Спершу позначте свій дім');armHome();return;}
    const r=await Notification.requestPermission();if(r!=='granted'){toast('Телефон не дозволив сповіщення. Увімкніть їх у налаштуваннях телефону для SKY');return;}
    PREF.sys=true;savePref();if($('#st-sys'))$('#st-sys').checked=true;await webPushSync(true);
    // одразу перевіряємо доставку: тестове сповіщення
    try{const reg=await navigator.serviceWorker.ready;const sub=await reg.pushManager.getSubscription();
      if(sub)fetch('/api/webpush/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:sub.endpoint})});}catch(e){}
    toast('Готово. Зараз прийде тестове сповіщення');};}
/* підказка встановлення для iPhone: у Facebook/Instagram спершу «Відкрити в Safari», потім «Поділитися» → «На початковий екран»; без цього пуші на iPhone неможливі */
function installHint(){if(document.getElementById('inst-hint'))return;
  const ua=navigator.userAgent,ios=/iPhone|iPad/.test(ua),andr=/Android/.test(ua)&&!window.Capacitor;if((!ios&&!andr)||matchMedia('(display-mode: standalone)').matches||navigator.standalone)return;
  const inapp=/FBAN|FBAV|Instagram|Messenger|Line\/|Telegram/i.test(ua);let n=0,last=0;
  try{n=+localStorage.getItem('inst_n')||0;last=+localStorage.getItem('inst_t')||0;}catch(e){return;}
  if(n>=4||(last&&Date.now()-last<864e5))return;
  const steps=inapp?['Натисніть <b>⋯</b> (або іконку компаса) → <b>«Відкрити в Safari»</b>','У Safari: <b>«Поділитися» ⬆︎ → «На початковий екран»</b>']:['Натисніть <b>«Поділитися»</b> ⬆︎ внизу екрана','Оберіть <b>«На початковий екран»</b> → «Додати»'];
  const el=document.createElement('div');el.id='inst-hint';el.className='inst-hint';
  if(andr)el.innerHTML='<b>📲 Застосунок SKY для Android</b><span>Відкривається одним дотиком, надійніше отримує сповіщення про тривогу.</span><ol><li>Натисніть «Завантажити» (APK, 7 МБ)</li><li>Відкрийте файл і дозвольте встановлення з цього джерела</li></ol><div><a class="pill primary" id="ih-ok" href="/download/sky.apk" download>Завантажити APK</a><button class="pill" id="ih-x">Пізніше</button></div>';
  else el.innerHTML='<b>📲 Встановіть SKY на iPhone</b><span>Так він відкривається одним дотиком і єдиний може присилати сповіщення про тривогу при закритому екрані.</span><ol><li>'+steps[0]+'</li><li>'+steps[1]+'</li></ol><div><button class="pill primary" id="ih-ok">Зрозуміло</button><button class="pill" id="ih-x">Пізніше</button></div>';
  document.body.appendChild(el);
  const done=()=>{try{localStorage.setItem('inst_n',String(n+1));localStorage.setItem('inst_t',String(Date.now()));}catch(e){}el.remove();};
  $('#ih-ok').onclick=done;$('#ih-x').onclick=done;}
setTimeout(()=>{try{installHint();}catch(e){}},9000);
setTimeout(pushCard,6000);setInterval(()=>{try{pushCard();}catch(e){}},60000);// під час тривоги з'являється компактний банер
// облік встановлень: запуск з іконки (встановлений застосунок) і подія встановлення; без cookies, сервер не зберігає IP
try{if(matchMedia('(display-mode: standalone)').matches||navigator.standalone)fetch('/api/visits/app?k=app',{method:'POST'}).catch(()=>{});
  addEventListener('appinstalled',()=>fetch('/api/visits/app?k=install',{method:'POST'}).catch(()=>{}));}catch(e){}
$('#st-ru').onchange=e=>{PREF.ru=e.target.checked;savePref();applyLayers();};
$('#st-launch').onchange=e=>{PREF.launch=e.target.checked;savePref();applyLayers();};
$('#st-zones').onchange=e=>{PREF.zones=e.target.checked;savePref();applyLayers();};
$('#st-wm').onchange=e=>{PREF.wm=e.target.checked;savePref();syncSettingsUI();};
$('#st-geo').onclick=()=>{$('#b-locate').click();};
$('#st-pick').onclick=()=>{$('#settings').hidden=true;armHome();};
$('#st-clear').onclick=()=>{if(FOLHOME)homeSaved=null;H0=null;localStorage.removeItem('H0');syncHome();toast('Дім прибрано');};
let lanDone=false;function loadLan(){if(!$('#st-qr'))return;fetch('/api/lan').then(r=>r.json()).then(j=>{lanDone=true;const urls=j.urls||[];const host=location.hostname;
  const sec=(j.secure||[]).sort((a,b)=>(/\/\/192\.168\./.test(b)-/\/\/192\.168\./.test(a)));const best=sec[0]||((host!=='localhost'&&host!=='127.0.0.1')?location.origin:(urls[0]||location.origin));
  $('#st-urls').innerHTML=[...sec,...(urls.length?urls:[location.origin])].map(u=>'<code>'+esc(u)+'</code>').join('');
  try{$('#st-qr').innerHTML='';new QRCode($('#st-qr'),{text:best,width:132,height:132,colorDark:'#0B0F17',colorLight:'#ffffff'});}catch(e){$('#st-qr').textContent=best;}}).catch(()=>{});}
let actx=null;function beep(){try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();const o=actx.createOscillator(),g=actx.createGain();o.type='sine';o.frequency.value=880;o.connect(g);g.connect(actx.destination);
  const t=actx.currentTime;g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(0.3,t+0.02);g.gain.exponentialRampToValueAtTime(0.0001,t+0.5);o.start(t);o.stop(t+0.55);
  const o2=actx.createOscillator();o2.frequency.value=660;o2.connect(g);o2.start(t+0.6);o2.stop(t+1.1);g.gain.setValueAtTime(0.3,t+0.6);g.gain.exponentialRampToValueAtTime(0.0001,t+1.1);}catch(e){}}
// 08.11: голос читав заголовок картки як є («×2 · ~10 хв до «X» → Y»). Тепер: окрема коротка фраза n.say або очищений текст без значків і службових символів
const NUMW=['','одна','дві','три','чотири','п’ять','шість','сім','вісім','дев’ять','десять'];
function sayClean(t){return String(t||'').replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu,'').replace(/×\s*(\d+)/g,(m,n)=>'. '+(NUMW[+n]||n)+(+n<5?' цілі. ':' цілей. ')).replace(/~\s*/g,'приблизно ').replace(/→/g,'курс на ').replace(/[«»]/g,'').replace(/\s*[·|]\s*/g,'. ').replace(/(?:\s+о)?\s+\d{1,2}:\d{2}/g,'').replace(/(?<![а-яіїєґ])хв(?![а-яіїєґ])/g,'хвилин').replace(/(?<![а-яіїєґ])км(?![а-яіїєґ])/g,'кілометрів').replace(/\s+/g,' ').replace(/\.\s*\./g,'.').trim();}
window.__beep=(txt)=>{txt=sayClean(txt);if(window.NXSound)NXSound.alert(txt);else if(PREF.sound)beep();};
setInterval(()=>{if(PREF.theme==='auto'&&effTheme()!==document.documentElement.dataset.theme)applyTheme(true);},60000);
applyTheme(false);document.body.classList.toggle('tac',TAC);tacScaleBars();enemyLoad();if(TAC){loadApp06();}tacBarSync();
fetch('/api/state').then(r=>r.json()).then(onSnap).catch(()=>{});

/* ---------- важливі сповіщення: з'являються на головному екрані й лишаються, доки їх не закрити ---------- */
const NOTE_CLR={red:'#FF4D57',orange:'#FF9F2E',green:'#2FE38A',blue:'#5AA2FF',violet:'#C77DFF'};
const NSEEN=new Set();let NBASE=false,NHOMELV=null;
function note(n){
  if(NSEEN.has(n.k))return;NSEEN.add(n.k);
  const box=$('#notes');if(!box)return;
  const el=document.createElement('div');el.className='note-c';el.style.setProperty('--nc',NOTE_CLR[n.lvl]||NOTE_CLR.orange);
  const tm=new Date((n.t||Date.now()/1000)*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  // картка: силует цілі в кольоровому колі рівня, заголовок, деталі «чіпами» (місце · напрямок · джерела)
  const parts=String(n.sub||'').split(' · ').filter(Boolean);
  el.innerHTML='<span class="ni'+(n.type?' ni-t':'')+'">'+(n.type?'':(n.ic||'🔔'))+'</span><div class="nb"><b>'+esc(String(n.title).replace(/^(🔴|🟠|🟡|🟢)\s*/u,''))+'</b>'+
    (parts.length?'<div class="nch">'+parts.map((x,i)=>'<span'+(i===0?' class="lead"':'')+'>'+esc(x)+'</span>').join('')+'</div>':'')+'</div><time>'+tm+'</time><button class="nx" aria-label="Закрити">✕</button>';
  if(n.type){const im=new Image();im.alt='';im.width=im.height=32;im.style.objectFit='contain';im.onerror=()=>{try{im.replaceWith(drawTarget(n.type,22));}catch(e){}};im.src='sprites/t-'+n.type+'.png?v=ref17';el.querySelector('.ni').appendChild(im);}
  const close=()=>{if(el.classList.contains('out'))return;el.classList.add('out');setTimeout(()=>{el.remove();notesAll();},600);};
  // зникає сама за 3 с плавно; якщо застосунок у фоні, відлік починається, коли користувач його відкрив
  const arm=()=>{if(document.hidden){document.addEventListener('visibilitychange',function v(){if(!document.hidden){document.removeEventListener('visibilitychange',v);setTimeout(close,3000);}});}else setTimeout(close,3000);};arm();
  el.querySelector('.nx').onclick=e=>{e.stopPropagation();close();};
  el.onclick=()=>{if(n.go)n.go();};
  box.insertBefore(el,box.querySelector('.note-c'));
  // на екрані щонайбільше 5, найстаріші прибираються самі
  const cs=box.querySelectorAll('.note-c');for(let i=5;i<cs.length;i++)cs[i].remove();
  notesAll();
  if(n.lvl==='red'||n.lvl==='orange'){window.__beep&&window.__beep(n.say||((n.title||'')+(n.sub?'. '+n.sub:'')));if(navigator.vibrate)try{navigator.vibrate([120,60,120]);}catch(e){}}
  if(PREF.sys&&document.hidden&&'Notification' in window&&Notification.permission==='granted'){
    try{const sn=new Notification(n.title,{body:n.sub||'',tag:n.k,icon:'brand/icon-192.png',renotify:false});sn.onclick=()=>{window.focus();n.go&&n.go();sn.close();};}catch(e){}}
}
// картки сповіщень завжди нижче верхньої панелі з лічильниками (вона може переноситися у два рядки)
function notesPos(){const tp=document.querySelector('header.top'),nb=$('#notes');if(!tp||!nb)return;const b=tp.getBoundingClientRect().bottom;if(b>0)nb.style.top=(b+8)+'px';}
addEventListener('resize',notesPos);setInterval(notesPos,2000);
function notesAll(){const box=$('#notes');let a=box.querySelector('.all');const n=box.querySelectorAll('.note-c').length;
  if(n>=2&&!a){a=document.createElement('button');a.className='all';a.textContent='Закрити всі';a.onclick=()=>{box.innerHTML='';};box.prepend(a);}
  if(n<2&&a)a.remove();}
function flyP(p,z){map.flyTo({center:p,zoom:Math.max(map.getZoom(),z||7),essential:true});}
const TNAME_PL={uav:'БпЛА невизначеного типу',lancet:'«Ланцети»',shahed:'Шахеди',jet:'Реактивні шахеди',molniya:'«Молнії»',cruise:'Крилаті ракети',ballistic:'Балістика',kab:'КАБи',geran5:'«Герань-5»',banderol:'«Бандеролі»',rszv:'РСЗВ',fpv:'FPV-дрони',fpvf:'FPV на оптоволокні',recon:'Дрони-розвідники'};
/* ---------- мої громади й області для сповіщень ---------- */
const NZLV=new Map();
function myZones(){const Z=PREF.nz||{obl:[],hrom:[]};if(!Z.obl.length&&!Z.hrom.length&&home&&window.OBLPOLY){const o=window.OBLPOLY(home[0],home[1]);if(o)return {obl:[o],hrom:[],auto:true};}return Z;}
function ringIn(r,x,y){let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const a=r[i],b=r[j];if(((a[1]>y)!==(b[1]>y))&&(x<(b[0]-a[0])*(y-a[1])/((b[1]-a[1])||1e-12)+a[0]))c=!c;}return c;}
// громада дому (індекс у hromadas.geojson); null, доки межі не завантажені
function homeHrom(){if(!HPDATA||!home){if(!HPDATA&&home)loadHP();return null;}if(homeHrom.k===home.join())return homeHrom.v;
  homeHrom.k=home.join();const i=HPDATA.features.findIndex(f=>geomIn(f.geometry,home[0],home[1]));homeHrom.v=i<0?null:(HPDATA.features[i].id!=null?HPDATA.features[i].id:i);return homeHrom.v;}
function geomIn(g,x,y){const P=g.type==='Polygon'?[g.coordinates]:g.coordinates;return P.some(p=>ringIn(p[0],x,y));}
function zoneOf(p){const Z=myZones();if(Z.obl.length&&window.OBLPOLY){const o=window.OBLPOLY(p[0],p[1]);if(o&&Z.obl.includes(o))return o+' обл.';}
  if(Z.hrom.length&&HPDATA){for(const h of Z.hrom){const f=HPDATA.features[h.id];if(f&&geomIn(f.geometry,p[0],p[1]))return h.n;}}return null;}
function loadHP(){if(HPDATA||HPLOADING)return Promise.resolve(HPDATA);HPLOADING=true;return fetch('/data/hromadas.geojson').then(r=>r.json()).then(d=>{HPDATA=d;if(map.getSource('hp'))map.getSource('hp').setData(d);HPPREV={};return d;}).catch(()=>{HPLOADING=false;});}
function renderZones(){clearTimeout(renderZones.t);renderZones.t=setTimeout(()=>window.webPushSync&&webPushSync(false),1200);const ul=$('#st-zones-list');if(!ul)return;const Z=myZones();ul.innerHTML='';
  if(Z.auto)ul.innerHTML='<li><span style="opacity:.75;font-weight:500">Зараз: '+esc(Z.obl[0])+' обл. (за домом). Додайте свої громади або області:</span></li>';
  else if(!Z.obl.length&&!Z.hrom.length)ul.innerHTML='<li><span style="opacity:.75;font-weight:500">Не обрано, сповіщення лише про пуски й про загрози біля дому/моїх місць</span></li>';
  if(!Z.auto){Z.obl.forEach(o=>{const li=document.createElement('li');li.innerHTML='<span>🗺 '+esc(o)+' обл.</span><button>✕</button>';li.querySelector('button').onclick=()=>{Z.obl=Z.obl.filter(x=>x!==o);PREF.nz=Z;savePref();renderZones();};ul.appendChild(li);});
    Z.hrom.forEach(h=>{const li=document.createElement('li');li.innerHTML='<span>📍 '+esc(h.n)+' громада <small style="opacity:.6">'+esc(h.o)+' обл.</small></span><button>✕</button>';li.querySelector('button').onclick=()=>{Z.hrom=Z.hrom.filter(x=>x.id!==h.id);PREF.nz=Z;savePref();renderZones();};ul.appendChild(li);});}}
{const inp=$('#st-zone-in'),dl=$('#st-zone-dl'),add=$('#st-zone-add');
  const fill=()=>loadHP().then(d=>{if(!dl||dl.childElementCount)return;const opts=[];(OBLF||[]).forEach(f=>opts.push(f.properties.n+' обл.'));if(d)d.features.forEach(f=>opts.push(f.properties.n+' громада ('+f.properties.r+' р-н, '+f.properties.o+' обл.)'));dl.innerHTML=opts.map(o=>'<option value="'+esc(o)+'">').join('');});
  if(inp){inp.addEventListener('focus',fill);
    const doAdd=()=>{const v=inp.value.trim();if(!v)return;const Z=myZones().auto?{obl:[],hrom:[]}:(PREF.nz||{obl:[],hrom:[]});
      let m=v.match(/^(.+?) обл\.$/);if(m&&(OBLF||[]).some(f=>f.properties.n===m[1])){if(!Z.obl.includes(m[1]))Z.obl.push(m[1]);}
      else{m=v.match(/^(.+?) громада \((.+?) р-н, (.+?) обл\.\)$/);const f=m&&HPDATA&&HPDATA.features.find(x=>x.properties.n===m[1]&&x.properties.r===m[2]&&x.properties.o===m[3]);
        if(!f){toast('Оберіть зі списку підказок');return;}if(!Z.hrom.some(h=>h.id===f.id))Z.hrom.push({id:f.id,n:f.properties.n,o:f.properties.o});}
      PREF.nz=Z;savePref();inp.value='';renderZones();NZLV.clear();toast('Додано');};
    add.onclick=doAdd;inp.addEventListener('keydown',e=>{if(e.key==='Enter')doAdd();});}
  const cl=$('#st-nlaunch'),ca=$('#st-nall');if(cl){cl.checked=PREF.nLaunch!==false;cl.onchange=()=>{PREF.nLaunch=cl.checked;savePref();};}
  if(ca){ca.checked=!!PREF.nAll;ca.onchange=()=>{PREF.nAll=ca.checked;savePref();};}
  setTimeout(renderZones,1500);if((PREF.nz||{}).hrom&&PREF.nz.hrom.length)loadHP();}
function notesCheck(s){
  const first=!NBASE;NBASE=true;const now=s.now||Date.now()/1000;
  // 1) пуски, за налаштуванням (типово так: пуск стосується всієї країни)
  for(const L of (s.launches||[])){const k='L:'+L.site+':'+Math.round((L.t||0)/60)+(isTO(L)?':to':'');if(first||now-(L.t||now)>1200||PREF.nLaunch===false){NSEEN.add(k);continue;}
    note({k,say:isTO(L)?'Носії в повітрі. '+L.site+'.':(L.type?'З району '+L.site+' запустили: '+(TNAME_PL[L.type]||TYPE_NAME[L.type]).toLowerCase()+'.':'З району '+L.site+' щось запустили.'),t:L.t,lvl:'red',ic:'🚀',title:(isTO(L)?'Носії в повітрі: ':'Пуск: ')+L.site,sub:[isTO(L)?'про пуски ракет ще не повідомлено':L.type?(TNAME_PL[L.type]||TYPE_NAME[L.type]):'',cntL(L),L.carrier||''].filter(Boolean).join(' · ')||'деталі уточнюються',go:()=>flyP([L.lon,L.lat],6)});}
  // 2) нові цілі, лише ті, що в моїх громадах/областях або летять туди протягом 30 хв (або всі, якщо так обрано)
  const serverT=Date.now()/1000+offset;
  for(const t of (s.tracks||[])){if(t.status!=='active')continue;const k='T:'+t.id;
    if(first||(t.conf||0)<0.5){NSEEN.add(k);continue;}
    if(NSEEN.has(k))continue;
    const fast=['ballistic','cruise','jet'].includes(t.type);
    let z=null;const p0=(DISP.get(t.id)||{p:[t.lon,t.lat]}).p;z=zoneOf(p0);let eta=0;
    if(!z){for(let m=5;m<=30;m+=5){const q=posAt(t,serverT+m*60).p;z=zoneOf(q);if(z){eta=m;break;}}}
    if(!z&&!(PREF.nAll&&fast))continue;   // не моя зона, мовчимо
    if(window.__wpOK){NSEEN.add(k);continue;}// push увімкнено: про цілі попереджає телефон (екран блокування), у застосунку не дублюємо
    const _nm=(TYPE_NAME[t.type]||'Ціль'),_cnt=t.count>1?(', '+(NUMW[t.count]||t.count)+(t.count<5?' цілі':' цілей')):'';
    const _say=_nm+_cnt+'. '+(t.next?'Курс на '+t.next+'. ':(t.hd!=null?'Летить '+SIDE[Math.round(t.hd/45)%8]+'. ':''))+(z?(eta?'Приблизно через '+eta+' хвилин буде біля '+z+'.':'Уже в зоні '+z+'. Укриття.'):'');
    note({k,say:_say,type:t.type,lvl:z?(eta?'orange':'red'):(t.type==='jet'?'orange':'red'),ic:t.type==='ballistic'?'🔺':t.type==='cruise'?'✈️':t.type==='jet'?'🔥':'⚠️',
      title:(z?(eta?'🟠 ':'🔴 '):'')+(TYPE_NAME[t.type]||'Ціль')+(t.count>1?' ×'+t.count:'')+(z?(eta?' · ~'+eta+' хв до «'+z+'»':' · у межах «'+z+'»'):'')+(t.next?' → '+t.next:''),
      sub:[t.at?'останнє місце: '+t.at[0]+' о '+fmt(t.at[1]):'',
           t.hd!=null?(t.next?'':'ймовірно ')+SIDE[Math.round(t.hd/45)%8]:'',
           !z&&t.launch&&t.launch.site&&!t.launch.est?'запуск: '+t.launch.site:''].filter(Boolean).join(' · '),go:()=>openSheet(t.id)});}
  // 3) тривога / відбій у моїх областях і громадах
  const Z=myZones();
  for(const o of Z.obl){const lv=(s.levels||{})[o]||0,pv=NZLV.get('o:'+o);
    if(pv!==undefined&&!first){if(!pv&&lv)note({k:'A:'+o+':'+Math.round(now),lvl:'red',ic:'🔴',say:'Повітряна тривога. '+o+' область.',title:'Повітряна тривога: '+o+' обл.',sub:'офіційна тривога'});
      else if(pv&&!lv)note({k:'O:'+o+':'+Math.round(now),lvl:'green',ic:'🟢',say:'Відбій. '+o+' область.',title:'Відбій тривоги: '+o+' обл.',sub:'У межах окремих громад тривога може ще тривати'});}
    NZLV.set('o:'+o,lv);}
  const HL=((s.official||{}).hromadas)||{};
  for(const h of Z.hrom){const lv=HL[h.id]||((s.levels||{})[h.o]?1:0),pv=NZLV.get('h:'+h.id);
    if(pv!==undefined&&!first){if(!pv&&lv)note({k:'AH:'+h.id+':'+Math.round(now),lvl:'red',ic:'🔴',say:'Тривога. '+h.n+' громада.',title:'Тривога: '+h.n+' громада',sub:h.o+' обл.'});
      else if(pv&&!lv)note({k:'OH:'+h.id+':'+Math.round(now),lvl:'green',ic:'🟢',say:'Відбій. '+h.n+' громада.',title:'Відбій: '+h.n+' громада',sub:h.o+' обл.'});}
    NZLV.set('h:'+h.id,lv);}
  // 0) мапа доби о 09:00
  if(s.daily){let seen=null;try{seen=localStorage.getItem('dailySeen');}catch(e){}
    if(seen!==s.daily){try{localStorage.setItem('dailySeen',s.daily);}catch(e){}
      note({k:'D:'+s.daily,lvl:'violet',ic:'🗺️',title:'Мапа доби готова',sub:'Маршрути, пуски й вибухи за добу до 09:00, натисніть, щоб відкрити',go:()=>{location.href='/daily.html?d='+s.daily;}});}}
  // 4) що вразили наші (офіційно)
  for(const h of (s.hits||[])){const k='H:'+(h.link||'')+':'+h.place+':'+h.what;if(first){NSEEN.add(k);continue;}
    note({k,t:h.t,lvl:'blue',ic:'🎯',title:'Уражено: '+h.what+' · '+h.place,sub:'Генштаб ЗСУ',go:()=>flyP([h.lon,h.lat],7)});}
}

window.__note=note;

/* ---------- «Стеж за мною»: загрози в радіусі R від поточного місця пристрою ---------- */
const FOL={watch:null,pos:null,acc:null,fired:new Map()};
// 04.11 власник: у режимі «стежити за мною» прив'язка до дому вимкнена, усе рахується лише від геопозиції (home тимчасово = позиція)
function folHome(){if(!PREF.follow||!FOL.pos)return;const fresh=!FOLHOME;if(fresh){homeSaved=home;FOLHOME=true;}
  const far=!home||fresh||dist(xy(home),xy(FOL.pos))>1;home=FOL.pos.slice();}
function folHomeOff(){if(!FOLHOME)return;FOLHOME=false;home=homeSaved||null;homeSaved=null;}
function ringGeo(c,km){const P=xy(c),pts=[];for(let i=0;i<=64;i++){const a=i/64*2*Math.PI;pts.push(ll([P[0]+Math.sin(a)*km,P[1]+Math.cos(a)*km]));}return {type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[pts]}};}
function syncMe(){if(!map.getSource('mepos'))return;map.getSource('mepos').setData(PREF.follow&&FOL.pos?{type:'FeatureCollection',features:[ringGeo(FOL.pos,PREF.radius||10),{type:'Feature',properties:{},geometry:{type:'Point',coordinates:FOL.pos}}]}:EMPTY);}
function followOn(){
  if(!navigator.geolocation){toast('Геолокація недоступна');return false;}
  if(FOL.watch!=null)return true;
  FOL.watch=navigator.geolocation.watchPosition(p=>{const first=!FOL.pos;FOL.pos=[p.coords.longitude,p.coords.latitude];FOL.acc=p.coords.accuracy;syncMe();folHome();
      if(first){toast('Стежу за вами · радіус '+(PREF.radius||10)+' км');map.flyTo({center:FOL.pos,zoom:Math.max(map.getZoom(),9.5)});}},
    e=>{toast(e.code===1?'Доступ до геолокації заборонено в браузері':'Не вдалося визначити місце');},{enableHighAccuracy:true,maximumAge:20000,timeout:20000});
  if('Notification' in window&&Notification.permission==='default')Notification.requestPermission().then(r=>{if(r==='granted'){PREF.sys=true;savePref();}});
  return true;}
function followOff(){if(FOL.watch!=null)navigator.geolocation.clearWatch(FOL.watch);FOL.watch=null;FOL.pos=null;FOL.fired.clear();folHomeOff();syncMe();}
/* ---------- «Мої місця»: власні точки з назвами (дача, робота, батьки…) ---------- */
let PLACES=[];try{PLACES=JSON.parse(localStorage.getItem('places')||'[]');}catch(e){PLACES=[];}
const savePlaces=()=>{try{localStorage.setItem('places',JSON.stringify(PLACES));}catch(e){}syncPlaces();renderPlaces();};
function syncPlaces(){if(map.getSource('myplaces'))map.getSource('myplaces').setData({type:'FeatureCollection',features:PLACES.map(p=>({type:'Feature',properties:{n:p.name},geometry:{type:'Point',coordinates:[p.lon,p.lat]}}))});}
function renderPlaces(){const ul=$('#st-places');if(!ul)return;ul.innerHTML=PLACES.length?'':'<li><span style="font-weight:500;opacity:.7">Ще немає жодного місця</span></li>';
  PLACES.forEach(p=>{const li=document.createElement('li');li.innerHTML='<span>📍 '+esc(p.name)+'</span><button data-a="ren">Назва</button><button data-a="del">✕</button>';
    li.querySelector('span').onclick=()=>{$('#settings').hidden=true;map.flyTo({center:[p.lon,p.lat],zoom:Math.max(map.getZoom(),10)});};
    li.querySelector('[data-a=ren]').onclick=()=>askName(p.name,n=>{p.name=n;savePlaces();});
    li.querySelector('[data-a=del]').onclick=()=>{PLACES=PLACES.filter(x=>x!==p);savePlaces();toast('Видалено');};ul.appendChild(li);});}
function askName(def,cb){const box=$('#pl-ask'),inp=$('#pl-name');box.hidden=false;inp.value=def||'';setTimeout(()=>inp.focus(),50);
  const done=ok=>{box.hidden=true;$('#pl-ok').onclick=$('#pl-cancel').onclick=inp.onkeydown=null;if(ok&&inp.value.trim())cb(inp.value.trim().slice(0,40));};
  $('#pl-ok').onclick=()=>done(true);$('#pl-cancel').onclick=()=>done(false);inp.onkeydown=e=>{if(e.key==='Enter')done(true);if(e.key==='Escape')done(false);};}
let addPlaceMode=false;
function addPlaceAt(lon,lat){askName('',n=>{PLACES.push({id:Date.now(),name:n,lon:+lon.toFixed(5),lat:+lat.toFixed(5)});savePlaces();toast('📍 «'+n+'» додано, стежу за загрозами поруч');});}
map.on('click',e=>{if(!addPlaceMode)return;addPlaceMode=false;map.getCanvas().style.cursor='';addPlaceAt(e.lngLat.lng,e.lngLat.lat);});
if($('#st-place-add'))$('#st-place-add').onclick=()=>{$('#settings').hidden=true;addPlaceMode=true;map.getCanvas().style.cursor='crosshair';toast('Торкніться карти, де це місце');};
if($('#st-place-here'))$('#st-place-here').onclick=()=>{if(FOL.pos)return addPlaceAt(FOL.pos[0],FOL.pos[1]);if(!navigator.geolocation)return toast('Геолокація недоступна');
  navigator.geolocation.getCurrentPosition(p=>addPlaceAt(p.coords.longitude,p.coords.latitude),()=>toast('Не вдалося визначити місце'),{enableHighAccuracy:true,timeout:10000});};
renderPlaces();

// перевірка загроз: поточне місце (якщо «Стеж за мною») + усі «Мої місця»
setInterval(()=>{
  if(!SNAP||REPLAY)return;
  const pts=[];if(PREF.follow&&FOL.pos)pts.push({k:'me',label:'від вас',pos:FOL.pos});
  PLACES.forEach(p=>pts.push({k:'p'+p.id,label:'від «'+p.name+'»',pos:[p.lon,p.lat]}));
  if(!pts.length)return;
  const R=PREF.radius||10,serverT=Date.now()/1000+offset,now=Date.now();
  for(const tr of SNAP.tracks){
    if(tr.status!=='active'||tr.conf<0.5)continue;
    const d0=DISP.get(tr.id);const p0=d0?d0.p:[tr.lon,tr.lat];
    const fut=[];for(let m=1;m<=15;m++)fut.push(posAt(tr,serverT+m*60).p);
    for(const W of pts){
      const P=xy(W.pos),d=dist(P,xy(p0));let eta=null;
      if(d>R){for(let m=0;m<fut.length;m++)if(dist(P,xy(fut[m]))<=R){eta=m+1;break;}}
      const key=W.k+':'+tr.id,inside=d<=R;
      if(!inside&&eta==null){const f=FOL.fired.get(key);if(f&&now-f.t>5*60000)FOL.fired.delete(key);continue;}
      const f=FOL.fired.get(key),level=inside?2:1;
      if(f&&f.level>=level&&now-f.t<10*60000)continue;   // повтор не частіше ніж раз на 10 хв або коли ціль ще ближче
      FOL.fired.set(key,{t:now,level});
      const side=FROM[Math.round(brg(P,xy(p0))/45)%8];
      note({k:'F:'+key+':'+level+':'+Math.floor(now/600000),lvl:'red',ic:inside?'🚨':'⚠️',
        title:(TYPE_NAME[tr.type]||'Ціль')+(tr.count>1?' ×'+tr.count:'')+(inside?', '+Math.max(1,Math.round(d))+' км '+W.label:', за ~'+eta+' хв у '+R+' км '+W.label),
        sub:Math.round(d)+' км '+side+(tr.next?' · курс → '+tr.next:''),go:()=>openSheet(tr.id)});
      if(W.k==='me'&&navigator.vibrate)try{navigator.vibrate(inside?[300,120,300,120,300]:[200,100,200]);}catch(e){}
    }
  }
},3000);
{const cb=$('#st-follow'),seg=$('#st-radius');
  const md=$('#st-mode'),mh=$('#st-mode-hint');
  const modeUi=()=>{if(md)md.querySelectorAll('button').forEach(b=>b.classList.toggle('on',(b.dataset.m==='me')===!!PREF.follow));
    if(mh)mh.textContent=PREF.follow?'Усі відстані й попередження рахуються лише від вашої геопозиції, дім не враховується.':'Відстані й попередження рахуються від позначеного дому.';};
  if(cb){cb.checked=!!PREF.follow;cb.onchange=()=>{PREF.follow=cb.checked;savePref();if(PREF.follow){if(!followOn()){PREF.follow=false;cb.checked=false;savePref();}}else followOff();modeUi();};}
  if(md){md.onclick=e=>{const b=e.target.closest('button');if(!b||!cb)return;const want=b.dataset.m==='me';if(cb.checked!==want){cb.checked=want;cb.onchange();}};}
  modeUi();
  if(seg){const upd=()=>seg.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.v===(PREF.radius||10)));upd();
    seg.onclick=e=>{const b=e.target.closest('button');if(!b)return;PREF.radius=+b.dataset.v;savePref();upd();syncMe();FOL.fired.clear();toast('Радіус '+PREF.radius+' км');};}
  if(PREF.follow)followOn();}
/* ---------- ШІ: «Що зараз відбувається?» для області дому (03.11) ---------- */
fetch('/api/llm').then(r=>r.json()).then(st=>{if(!st||!st.enabled)return;const box=$('#ai-box');if(!box)return;$('#ai-ask').hidden=false;
  const aiHide=()=>{const a=$('#ai-ans');a.hidden=true;a.innerHTML='';clearTimeout(aiHide.t);};
  $('#ai-ans').onclick=e=>{e.stopPropagation();if(e.target.closest('.ai-x'))aiHide();};
  $('#ai-ask').onclick=async e=>{e.stopPropagation();const a=$('#ai-ans');if(!a.hidden){aiHide();return;}// друге торкання — сховати
    const ob=homeObl();a.hidden=false;clearTimeout(aiHide.t);aiHide.t=setTimeout(aiHide,90000);// саме зникає за 1,5 хв
    if(!ob){a.innerHTML='Спершу позначте дім кнопкою ⌂';return;}
    a.innerHTML='<small>Аналізую дані SKY…</small>';
    try{const r=await (await fetch('/api/ask?obl='+encodeURIComponent(ob))).json();
      a.innerHTML='<button class=ai-x aria-label="Закрити">✕</button>'+esc(r.text||'Немає відповіді')+'<small class=ai-note>'+esc(r.note||'Оцінка ШІ за даними SKY')+(r.t?' · '+fmt(r.t):'')+'</small>';}
    catch(x){a.innerHTML='Не вдалося отримати відповідь';}};}).catch(()=>{});
})();

/* 12.11: закриття свайпом. Бічні панелі (налаштування, арсенал, стрічка) — вправо; нижня картка цілі й картки-підказки — вниз.
   Свайп ігнорується, якщо палець почав рух на прокручуваному списку, що ще не доскролений до краю, на повзунку або у стрічці з горизонтальним скролом. */
(function(){
  function scrollableAncestor(t,root,axis){for(let n=t;n&&n!==root;n=n.parentElement){if(!n||n.nodeType!==1)break;const cs=getComputedStyle(n);
      if(axis==='y'&&/(auto|scroll)/.test(cs.overflowY)&&n.scrollHeight>n.clientHeight+2&&n.scrollTop>0)return true;
      if(axis==='x'&&/(auto|scroll)/.test(cs.overflowX)&&n.scrollWidth>n.clientWidth+2)return true;
      if(n.tagName==='INPUT'&&n.type==='range')return true;}return false;}
  function swipeClose(el,dir,closeFn){
    if(!el||el._swc)return;el._swc=1;let x0=0,y0=0,t0=0,mode=0,dx=0,dy=0;// mode: 0 очікування, 1 тягнемо, -1 ігноруємо
    const horiz=dir==='right';el.style.touchAction=horiz?'pan-y':'pan-x pan-y';
    el.addEventListener('touchstart',e=>{if(e.touches.length!==1){mode=-1;return;}const t=e.touches[0];x0=t.clientX;y0=t.clientY;t0=Date.now();dx=dy=0;
      mode=(horiz?scrollableAncestor(e.target,el,'x'):scrollableAncestor(e.target,el,'y')||(el.scrollTop>0))?-1:0;},{passive:true});
    el.addEventListener('touchmove',e=>{if(mode<0)return;const t=e.touches[0];dx=t.clientX-x0;dy=t.clientY-y0;
      if(mode===0){if(Math.abs(dx)<10&&Math.abs(dy)<10)return;
        const ok=horiz?(dx>0&&Math.abs(dx)>Math.abs(dy)*1.4):(dy>0&&Math.abs(dy)>Math.abs(dx)*1.4);
        if(!ok){mode=-1;return;}mode=1;el.style.animation='none';el.style.transition='none';}
      if(mode===1){if(e.cancelable)e.preventDefault();const d=Math.max(0,horiz?dx:dy);el.style.transform=horiz?'translateX('+d+'px)':'translateY('+d+'px)';}},{passive:false});
    const end=()=>{if(mode!==1){mode=0;return;}mode=0;const d=Math.max(0,horiz?dx:dy),v=d/Math.max(1,Date.now()-t0),W=horiz?el.offsetWidth:el.offsetHeight;
      el.style.transition='transform .22s ease-out';
      if(d>Math.min(110,W*0.3)||(v>0.5&&d>40)){el.style.transform=horiz?'translateX(110%)':'translateY(110%)';
        setTimeout(()=>{try{closeFn();}catch(_){}el.style.transition='';el.style.transform='';el.style.animation='';},200);}
      else{el.style.transform='';setTimeout(()=>{el.style.transition='';el.style.animation='';},230);}};
    el.addEventListener('touchend',end,{passive:true});el.addEventListener('touchcancel',end,{passive:true});}
  // нижня картка цілі: короткий свайп вниз — ЗГОРНУТИ (лишається смужка із заголовком), довгий або різкий — ЗАКРИТИ; свайп угору по смужці — розгорнути.
  // Ловимо жест і за ручку зверху (touch-action:none, працює завжди), і за вміст, коли він прокручений до верху.
  function sheetSwipe(el){
    if(!el||el._swc)return;el._swc=1;
    const grab=document.createElement('div');grab.className='sh-grab';el.insertBefore(grab,el.firstChild);
    let y0=0,x0=0,t0=0,mode=0,dy=0,fromGrab=false;
    const peeked=()=>el.classList.contains('peek');
    const unpeek=()=>{el.classList.remove('peek');};
    new MutationObserver(()=>{if(el.hidden)unpeek();}).observe(el,{attributes:true,attributeFilter:['hidden']});
    el.addEventListener('click',e=>{if(peeked()&&!e.target.closest('button,a'))unpeek();});
    el.addEventListener('touchstart',e=>{if(e.touches.length!==1){mode=-1;return;}const t=e.touches[0];y0=t.clientY;x0=t.clientX;t0=Date.now();dy=0;
      fromGrab=!!e.target.closest('.sh-grab');
      mode=(fromGrab||peeked())?0:((el.scrollTop>0||scrollableAncestor(e.target,el,'y')||scrollableAncestor(e.target,el,'x'))?-1:0);},{passive:true});
    el.addEventListener('touchmove',e=>{if(mode<0)return;const t=e.touches[0];dy=t.clientY-y0;const dx=t.clientX-x0;
      if(mode===0){if(Math.abs(dy)<5&&Math.abs(dx)<5)return;
        const ok=(fromGrab||peeked())?Math.abs(dy)>Math.abs(dx):(dy>0&&dy>Math.abs(dx)*1.2);
        if(!ok){mode=-1;return;}mode=1;el.style.animation='none';el.style.transition='none';}
      if(e.cancelable)e.preventDefault();el.style.transform='translateY('+Math.max(0,dy)+'px)';},{passive:false});
    const end=()=>{if(mode!==1){mode=0;return;}mode=0;const v=dy/Math.max(1,Date.now()-t0),H=el.offsetHeight;
      el.style.transition='transform .22s ease-out';
      const reset=()=>{el.style.transition='';el.style.transform='';el.style.animation='';};
      if(peeked()){
        if(dy<-40){unpeek();el.style.transform='';setTimeout(reset,230);}
        else if(dy>90){el.style.transform='translateY(110%)';setTimeout(()=>{const b=document.getElementById('sh-close');if(b)b.click();reset();},200);}
        else{el.style.transform='';setTimeout(reset,230);}
        return;}
      if(dy>Math.max(230,H*0.55)||(v>0.9&&dy>110)){el.style.transform='translateY(110%)';setTimeout(()=>{const b=document.getElementById('sh-close');if(b)b.click();reset();},200);}
      else if(dy>60){el.classList.add('peek');el.style.transform='';setTimeout(reset,230);}
      else{el.style.transform='';setTimeout(reset,230);}};
    el.addEventListener('touchend',end,{passive:true});el.addEventListener('touchcancel',end,{passive:true});}
  window.swipeClose=swipeClose;
  const btn=id=>()=>{const b=document.getElementById(id);if(b)b.click();};
  function wire(){
    swipeClose(document.getElementById('settings'),'right',btn('st-close'));
    swipeClose(document.getElementById('arsenal'),'right',btn('ars-close'));
    swipeClose(document.getElementById('drawer'),'right',btn('dr-close'));
    sheetSwipe(document.getElementById('sheet'));
  }
  wire();
  // картки, що створюються на льоту (підказка встановлення, картка сповіщень): свайп вниз = «Пізніше»
  new MutationObserver(()=>{for(const [id,b] of [['inst-hint','ih-x'],['push-card','pc-x']]){const el=document.getElementById(id);if(el&&!el._swc)swipeClose(el,'down',()=>{const x=document.getElementById(b);if(x)x.click();else el.remove();});}}).observe(document.body,{childList:true});
})();
