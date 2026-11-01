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
const FROM=['з півночі','з північного сходу','зі сходу','з південного сходу','з півдня','з південного заходу','з заходу','з північного заходу'];
const toast=m=>{const t=$('#toast');t.textContent=m;t.hidden=false;clearTimeout(toast.h);toast.h=setTimeout(()=>t.hidden=true,2600);};

let SNAP=null,recvAt=0,offset=0,sel=null,follow=false,home=null,setHomeMode=false,tilt=false,base=localStorage.getItem('base')||'sat';
try{home=JSON.parse(localStorage.getItem('home')||'null');}catch(e){}
const DISP=new Map();

/* ---------- карта ---------- */
const ESRI='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
let CFG={vectorStyle:'https://tiles.openfreemap.org/styles/liberty'};
const map=new maplibregl.Map({container:'map',style:{version:8,sources:{},layers:[{id:'bg',type:'background',paint:{'background-color':'#0B0F17'}}]},center:[33.5,48.6],zoom:5.2,attributionControl:{compact:true},maxPitch:65});window.tryvogaMap=map;
async function styleFor(kind){
  const vec=await fetch(CFG.vectorStyle).then(r=>r.json());
  // підписи українською: name:uk → name (OSM) замість латиниці
  const UK=['coalesce',['get','name:uk'],['get','name']];
  vec.layers.forEach(l=>{if(l.type==='symbol'&&l.layout&&l.layout['text-field']&&JSON.stringify(l.layout['text-field']).includes('name'))l.layout['text-field']=UK;});
  if(kind==='map')return vec;
  // супутник + підписи й дороги з векторної карти
  const keep=vec.layers.filter(l=>l.type==='symbol'||/boundary|road_(trunk|motorway|primary)|highway/.test(l.id)).map(l=>{
    const L=JSON.parse(JSON.stringify(l));
    if(L.type==='symbol'&&L.paint){L.paint['text-color']='#FFFFFF';L.paint['text-halo-color']='rgba(0,0,0,.85)';L.paint['text-halo-width']=1.6;}
    if(L.type==='line'&&L.paint){L.paint['line-opacity']=0.55;}
    return L;});
  const out={version:8,glyphs:vec.glyphs,sources:{...vec.sources,esri:{type:'raster',tiles:[ESRI],tileSize:256,maxzoom:19,attribution:'© Esri, Maxar, Earthstar Geographics'}},
    layers:[{id:'esri',type:'raster',source:'esri',paint:{'raster-saturation':-0.25,'raster-brightness-max':0.82}},...keep]};
  if(vec.sprite)out.sprite=vec.sprite;return out;
}
async function setBase(kind){base=kind;localStorage.setItem('base',kind);map.setStyle(await styleFor(kind),{diff:false});}

function addImages(){
  for(const t of Object.keys(TYPE_COLOR)){for(const d of [0,1]){const id='t-'+t+(d?'-d':'');if(map.hasImage(id))continue;const c=drawTarget(t,44,{dim:!!d});map.addImage(id,c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});}}
  if(!map.hasImage('home')){const c=drawHome(40);map.addImage('home',c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});}
  if(!map.hasImage('chip')){const s=48,c=document.createElement('canvas');c.width=c.height=s;const x=c.getContext('2d');x.fillStyle='rgba(12,15,22,.88)';x.beginPath();x.roundRect(2,2,s-4,s-4,14);x.fill();map.addImage('chip',x.getImageData(0,0,s,s),{pixelRatio:2,stretchX:[[14,34]],stretchY:[[14,34]],content:[10,8,38,40]});}
}
const EMPTY={type:'FeatureCollection',features:[]};
function addOverlays(){
  const st=map.getStyle();if(!st||!st.glyphs||map.getSource('obl'))return;
  addImages();
  const LV=['coalesce',['feature-state','lvl'],0];
  map.addSource('obl',{type:'geojson',data:'/data/oblasts.geojson',promoteId:'n'});
  map.addSource('ra',{type:'geojson',data:'/data/raions.geojson',generateId:true});
  map.addSource('sel',{type:'geojson',data:EMPTY});
  ['zones','trails','preds','targets','home'].forEach(id=>map.addSource(id,{type:'geojson',data:EMPTY}));
  map.addLayer({id:'obl-fill',type:'fill',source:'obl',paint:{'fill-color':['match',LV,2,'#C8102E',1,'#E8B300','#000'],'fill-opacity':['match',LV,2,0.2,1,0.22,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-fill',type:'fill',source:'ra',paint:{'fill-color':['match',LV,2,'#B3122E',1,'#E0A800','#000'],'fill-opacity':['match',LV,2,0.38,1,0.2,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-line',type:'line',source:'ra',minzoom:5.5,paint:{'line-color':'#fff','line-opacity':['interpolate',['linear'],['zoom'],5.5,0.25,9,0.55],'line-width':['interpolate',['linear'],['zoom'],6,0.5,10,1.2]}});
  map.addLayer({id:'obl-line',type:'line',source:'obl',paint:{'line-color':'#fff','line-width':['interpolate',['linear'],['zoom'],4,1,9,2.2],'line-opacity':0.9}});
  map.addLayer({id:'zones',type:'circle',source:'zones',paint:{'circle-radius':['interpolate',['exponential',2],['zoom'],5,4,9,60,12,480],'circle-color':'#FF7A2E','circle-opacity':0.18,'circle-stroke-color':'#FF7A2E','circle-stroke-width':1.2,'circle-stroke-opacity':0.7}});
  map.addLayer({id:'trails',type:'line',source:'trails',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':3,'line-dasharray':[0.1,2.2],'line-opacity':['get','o']}});
  map.addLayer({id:'sel-ring',type:'circle',source:'sel',paint:{'circle-radius':28,'circle-color':'rgba(0,0,0,0)','circle-stroke-color':['get','c'],'circle-stroke-width':2.5}});
  map.addLayer({id:'preds',type:'line',source:'preds',layout:{'line-cap':'round'},paint:{'line-color':['get','c'],'line-width':2,'line-dasharray':[1.5,2],'line-opacity':0.9}});
  map.addLayer({id:'home',type:'symbol',source:'home',layout:{'icon-image':'home','icon-size':1,'icon-allow-overlap':true,'text-field':'Дім','text-font':['Noto Sans Bold'],'text-size':13,'text-offset':[0,1.7],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'tg-course',type:'symbol',source:'targets',filter:['all',['has','next'],['==',['get','active'],true]],layout:{'text-field':['concat','→ ',['get','next']],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[3,7,3,7],'text-anchor':'left','text-offset':[1.9,0.9],'icon-allow-overlap':false,'text-optional':false},paint:{'text-color':'#fff'}});
  map.addLayer({id:'tg',type:'symbol',source:'targets',layout:{'icon-image':['concat','t-',['get','type'],['case',['get','active'],'','-d']],'icon-rotate':['get','hd'],'icon-rotation-alignment':'map','icon-pitch-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true,'icon-size':['interpolate',['linear'],['zoom'],4,0.62,8,0.95,12,1.25],'symbol-sort-key':['get','sk']},paint:{'icon-opacity':['case',['get','weak'],0.6,1]}});
  map.addLayer({id:'tg-n',type:'symbol',source:'targets',filter:['>',['get','count'],1],layout:{'text-field':['concat','×',['to-string',['get','count']]],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[2,6,2,6],'text-offset':[1.3,-1.2],'text-allow-overlap':true,'icon-allow-overlap':true},paint:{'text-color':'#fff'}});
  map.on('click','tg',e=>{const f=e.features[0];openSheet(f.properties.id);});
  map.on('mouseenter','tg',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','tg',()=>map.getCanvas().style.cursor='');
  lastLv='';lastRa='';syncHome();
  if(!map._scaleAdded){map.addControl(new maplibregl.ScaleControl({unit:'metric',maxWidth:110}),'bottom-left');map._scaleAdded=true;}
}
map.on('style.load',addOverlays);map.on('styledata',()=>{if(map.isStyleLoaded()&&!map.getSource('obl'))addOverlays();if(map.getSource('obl')&&!lastLv)syncLevels();});
map.on('click',e=>{if(!setHomeMode)return;const f=map.queryRenderedFeatures(e.point,{layers:['tg']});if(f.length)return;home=[e.lngLat.lng,e.lngLat.lat];localStorage.setItem('home',JSON.stringify(home));setHomeMode=false;$('#b-home').classList.remove('on');syncHome();toast('Дім збережено');});
fetch('/api/config').then(r=>r.json()).then(c=>{CFG={...CFG,...c};}).catch(()=>{}).finally(()=>setBase(base));

/* ---------- позиція цілі в момент часу ---------- */
function posAt(tr,serverT){
  if(tr.status!=='active')return {p:[tr.lon,tr.lat],hd:tr.hd};
  const km=tr.speed*Math.max(0,serverT-tr.ts)/3600;
  const pts=[xy([tr.lon,tr.lat]),...tr.route.map(xy)];
  if(pts.length===1){if(tr.hd==null)return {p:[tr.lon,tr.lat],hd:tr.hd};const r=tr.hd*D2R;return {p:ll([pts[0][0]+Math.sin(r)*km,pts[0][1]+Math.cos(r)*km]),hd:tr.hd};}
  let acc=0;for(let i=1;i<pts.length;i++){const d=dist(pts[i-1],pts[i]);if(acc+d>=km){const f=(km-acc)/(d||1);const q=[pts[i-1][0]+(pts[i][0]-pts[i-1][0])*f,pts[i-1][1]+(pts[i][1]-pts[i-1][1])*f];return {p:ll(q),hd:brg(pts[i-1],pts[i])};}acc+=d;}
  return {p:ll(pts[pts.length-1]),hd:tr.hd};
}
function homeRel(tr,p){
  if(!home)return null;const H=xy(home),P=xy(p);const d=dist(H,P);
  let rel=null,eta=null;
  const path=[P,...tr.route.map(xy)];
  let acc=0,best={d:1e9,c:0};for(let i=1;i<path.length;i++){const a=path[i-1],b=path[i];const vx=b[0]-a[0],vy=b[1]-a[1],L2=vx*vx+vy*vy;let t=L2?((H[0]-a[0])*vx+(H[1]-a[1])*vy)/L2:0;t=Math.max(0,Math.min(1,t));const q=[a[0]+vx*t,a[1]+vy*t];const dd=dist(H,q);if(dd<best.d)best={d:dd,c:acc+Math.sqrt(L2)*t};acc+=Math.sqrt(L2);}
  if(best.d<8){rel='route';eta=best.c/tr.speed*60;}
  else if(tr.hd!=null&&angd(tr.hd,brg(P,H))<20){rel='heading';eta=d/tr.speed*60;}
  return {d,rel,eta,from:FROM[Math.round((brg(H,P))/45)%8]};
}

/* ---------- кадр ---------- */
let lastLv='',lastFrame=performance.now();
function frame(now){
  const dt=Math.min(0.2,(now-lastFrame)/1000);lastFrame=now;
  if(SNAP&&map.getSource('targets')){
    const serverT=Date.now()/1000+offset;
    const feats=[],trails=[],preds=[],threats=[];
    for(const tr of SNAP.tracks){
      const {p,hd}=posAt(tr,serverT);
      let d=DISP.get(tr.id);
      if(!d||Math.abs(d.p[0]-p[0])+Math.abs(d.p[1]-p[1])>1.2){d={p:[...p],hd:hd??0};DISP.set(tr.id,d);}
      else{const k=Math.min(1,dt*3);d.p[0]+=(p[0]-d.p[0])*k;d.p[1]+=(p[1]-d.p[1])*k;if(hd!=null){let a=hd-d.hd;while(a>180)a-=360;while(a<-180)a+=360;d.hd+=a*Math.min(1,dt*2.5);}}
      const active=tr.status==='active',weak=tr.conf<0.5;
      const rel=active&&!weak?homeRel(tr,d.p):null;
      if(rel&&rel.rel)threats.push({tr,rel});
      feats.push({type:'Feature',properties:{id:tr.id,type:tr.type,hd:d.hd,active,weak,count:tr.count||1,next:tr.next||undefined,sk:active?(sel===tr.id?0:1):2},geometry:{type:'Point',coordinates:d.p}});
      const c=TYPE_COLOR[tr.type];
      trails.push({type:'Feature',properties:{c,o:active?0.95:0.35},geometry:{type:'LineString',coordinates:[...tr.trail.slice(-3).map(t=>[t[0],t[1]]),d.p]}});
      if(active&&(sel===tr.id||(rel&&rel.rel))&&tr.route.length)preds.push({type:'Feature',properties:{c},geometry:{type:'LineString',coordinates:[d.p,...tr.route]}});
    }
    map.getSource('targets').setData({type:'FeatureCollection',features:feats});
    map.getSource('trails').setData({type:'FeatureCollection',features:trails});
    map.getSource('preds').setData({type:'FeatureCollection',features:preds});
    if(map.getSource('sel')){const d=sel&&DISP.get(sel);const tr=sel&&SNAP.tracks.find(t=>t.id===sel);map.getSource('sel').setData(d&&tr?{type:'FeatureCollection',features:[{type:'Feature',properties:{c:TYPE_COLOR[tr.type]},geometry:{type:'Point',coordinates:d.p}}]}:EMPTY);}
    if(follow&&sel){const d=DISP.get(sel);if(d)map.easeTo({center:d.p,duration:0});}
    renderBanner(threats);
    if(sel&&now-(frame.sh||0)>500){frame.sh=now;fillSheet();}
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

function syncLevels(){
  if(!SNAP||!map.getSource('obl'))return;const key=JSON.stringify(SNAP.levels);if(key===lastLv)return;lastLv=key;
  fetchOblNames().then(names=>{if(!map.getSource('obl'))return;names.forEach(n=>{try{map.setFeatureState({source:'obl',id:n},{lvl:SNAP.levels[n]||0});}catch(e){lastLv='';}});});
}
let RA=null,lastRa='';
function inRing(r,x,y){let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const [xi,yi]=r[i],[xj,yj]=r[j];if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/((yj-yi)||1e-12)+xi))c=!c;}return c;}
function raionOf(lon,lat){if(!RA)return -1;for(const r of RA){if(lon<r.bb[0]||lon>r.bb[2]||lat<r.bb[1]||lat>r.bb[3])continue;for(const pl of r.polys)if(inRing(pl[0],lon,lat))return r.i;}return -1;}
fetch('/data/raions.geojson').then(r=>r.json()).then(j=>{RA=j.features.map((f,i)=>{const g=f.geometry;const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;let bb=[180,90,-180,-90];polys.forEach(pl=>pl[0].forEach(([x,y])=>{bb[0]=Math.min(bb[0],x);bb[1]=Math.min(bb[1],y);bb[2]=Math.max(bb[2],x);bb[3]=Math.max(bb[3],y);}));return {i,n:f.properties.n,polys,bb};});});
function syncRaions(){
  if(!SNAP||!RA||!map.getSource('ra'))return;const lv={};const up=(i,v)=>{if(i>=0&&(lv[i]||0)<v)lv[i]=v;};
  const off=new Set((SNAP.official&&SNAP.official.raions)||[]);RA.forEach(r=>{if(off.has(r.n))up(r.i,2);});
  const serverT=Date.now()/1000+offset;
  for(const tr of SNAP.tracks){if(tr.status!=='active'||tr.conf<0.5)continue;const {p}=posAt(tr,serverT);up(raionOf(p[0],p[1]),2);
    for(let m=2;m<=15;m+=2){const q=posAt(tr,serverT+m*60).p;up(raionOf(q[0],q[1]),1);}}
  SNAP.zones.forEach(z=>z.places.forEach(([lo,la])=>up(raionOf(lo,la),2)));
  const key=JSON.stringify(lv);if(key===lastRa)return;lastRa=key;
  RA.forEach(r=>{try{map.setFeatureState({source:'ra',id:r.i},{lvl:lv[r.i]||0});}catch(e){lastRa='';}});
}
setInterval(syncRaions,3000);
let OBLN=null;function fetchOblNames(){if(OBLN)return Promise.resolve(OBLN);return fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>OBLN=j.features.map(f=>f.properties.n));}
function syncHome(){if(map.getSource('home'))map.getSource('home').setData(home?{type:'FeatureCollection',features:[{type:'Feature',properties:{},geometry:{type:'Point',coordinates:home}}]}:EMPTY);}
function syncZones(){if(!SNAP||!map.getSource('zones'))return;map.getSource('zones').setData({type:'FeatureCollection',features:SNAP.zones.flatMap(z=>z.places.map(([lo,la])=>({type:'Feature',properties:{},geometry:{type:'Point',coordinates:[lo,la]}})))});}

/* ---------- лічильники, статус ---------- */
const CNTI={};
function renderCounters(){
  const act=SNAP.tracks.filter(t=>t.status==='active');const by={};act.forEach(t=>by[t.type]=(by[t.type]||0)+(t.count||1));
  const order=['shahed','jet','cruise','ballistic','molniya'];
  $('#counters').innerHTML='';
  order.filter(t=>by[t]).forEach(t=>{const d=document.createElement('div');d.className='cnt';d.title=TYPE_NAME[t];const c=CNTI[t]||(CNTI[t]=drawTarget(t,28));const cc=document.createElement('canvas');cc.width=c.width;cc.height=c.height;cc.getContext('2d').drawImage(c,0,0);d.appendChild(cc);const b=document.createElement('b');b.textContent=by[t];d.appendChild(b);$('#counters').appendChild(d);});
  if(!act.length){const d=document.createElement('div');d.className='cnt';d.innerHTML='<b style="font-size:16px">Цілей не видно</b>';$('#counters').appendChild(d);}
}
function renderAsOf(){
  const el=$('#asof');const age=(Date.now()-recvAt)/1000;
  if(!SNAP||age>20){el.className='asof stale';el.innerHTML=SNAP?'Немає звʼязку <b>'+Math.round(age)+' с</b> · це не відбій':'зʼєднання…';return;}
  const h=SNAP.health;el.className='asof'+((!h.telegram&&!h.replay)?' stale':'');
  el.innerHTML='станом на <b>'+fmtS(SNAP.now)+'</b>'+(h.replay?' · демо: записана ніч 29→30.10':(!h.telegram?' · Telegram не підключено':''))+(!h.alerts?' · рівні областей лише за трекером':'');
}
setInterval(()=>SNAP&&renderAsOf(),1000);
function renderBanner(threats){
  const b=$('#banner');if(!threats.length){b.hidden=true;return;}
  threats.sort((a,b)=>(a.rel.eta??999)-(b.rel.eta??999));const t=threats[0];
  b.hidden=false;b.innerHTML=esc(TYPE_NAME[t.tr.type])+(t.tr.count>1?' ×'+t.tr.count:'')+' · '+(t.rel.rel==='route'?'маршрут проходить біля дому':'курс на твій район')+(t.rel.eta!=null?' · ~'+Math.max(1,Math.round(t.rel.eta))+' хв':'')+'<small>'+Math.round(t.rel.d)+' км '+t.rel.from+(threats.length>1?' · ще '+(threats.length-1):'')+'</small>';
  b.onclick=()=>openSheet(t.tr.id);
}

/* ---------- картка цілі ---------- */
function openSheet(id){sel=id;follow=false;$('#sh-follow').classList.remove('on');$('#sh-follow').textContent='Стежити за ціллю';$('#sheet').hidden=false;fillSheet(true);const d=DISP.get(id);if(d)map.easeTo({center:d.p,zoom:Math.max(map.getZoom(),8.5),duration:600});}
function fillSheet(first){
  const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);if(!tr){$('#sheet').hidden=true;sel=null;return;}
  if(first||!fillSheet.icon||fillSheet.icon!==tr.type){const c=drawTarget(tr.type,40);$('#sh-icon').innerHTML='';$('#sh-icon').appendChild(c);fillSheet.icon=tr.type;}
  $('#sh-name').textContent=TYPE_NAME[tr.type]+(tr.count>1?' ×'+tr.count:'');
  $('#sh-course').innerHTML=tr.status!=='active'?(tr.status==='lost'?'Втрачено':'Більше не фіксується'):(tr.next?'Курс → <b>'+esc(tr.next)+'</b>':'Курс уточнюється');
  const d=DISP.get(tr.id);const r=d&&homeRel(tr,d.p);
  $('#sh-dist').textContent=!home?'вкажіть дім':r?Math.round(r.d)+' км '+r.from:'—';
  $('#sh-eta').textContent=!home?'—':(r&&r.eta!=null?'~'+Math.max(1,Math.round(r.eta))+' хв':'не в бік дому');
  const ago=Math.round((Date.now()/1000+offset-tr.first)/60);
  $('#sh-first').textContent=fmt(tr.first)+' · '+ago+' хв тому';
  $('#sh-src').textContent=tr.srcs.map(s=>SNAP.sources[s]?.name||s).join(', ')+(tr.srcs.length>1?'':'');
  $('#sh-from').textContent=tr.from||'канали не вказали';
  $('#sh-conf').textContent=Math.round(tr.conf*100)+'%'+(tr.conf<0.5?' · непідтверджено':'');
  const link=tr.links[tr.links.length-1];const a=$('#sh-post');if(link){a.href=link;a.hidden=false;}else a.hidden=true;
}
$('#sh-close').onclick=()=>{sel=null;follow=false;$('#sheet').hidden=true;};
$('#sh-follow').onclick=()=>{follow=!follow;$('#sh-follow').classList.toggle('on',follow);$('#sh-follow').textContent=follow?'Стежу · зупинити':'Стежити за ціллю';};

/* ---------- стрічка ---------- */
function renderFeed(){
  const kindTxt={filtered:'Повідомлення про роботу ППО або влучання приховано фільтром безпеки.',close:'Ціль більше не фіксується',zone:'Загроза КАБ',info:'Без географічної привʼязки'};
  $('#feed').innerHTML=SNAP.log.slice().reverse().map(r=>{const src=SNAP.sources[r.src]?.name||r.src;
    let txt=kindTxt[r.kind]||'';if(r.kind==='track'||r.kind==='zone'){const tg=r.places.filter(p=>p.r==='t').map(p=>p.n),pos=r.places.find(p=>p.r==='p'),fr=r.places.find(p=>p.r==='f');txt=(TYPE_NAME[r.type]||'Ціль')+(r.count?' ×'+r.count:'')+(fr?' · з боку '+fr.n:'')+(pos?' · в районі '+pos.n:'')+(tg.length?(r.kind==='zone'?' · загроза для: ':' · курсом на ')+tg.slice(0,6).join(', '):'');}
    return '<li><div class="m"><span>'+fmt(r.t)+'</span><span>'+esc(src)+'</span>'+(r.track?'<span>→ '+esc(r.track)+'</span>':'')+(r.link?'<a href="'+esc(r.link)+'" target="_blank" rel="noopener">пост ↗</a>':'')+'</div><div class="'+(r.kind==='filtered'?'f':'')+'">'+esc(txt)+'</div></li>';}).join('')||'<li>Повідомлень ще немає.</li>';
}

/* ---------- кнопки ---------- */
$('#b-home').onclick=()=>{if(home&&!setHomeMode){map.flyTo({center:home,zoom:Math.max(map.getZoom(),9)});toast('Довге натискання — змінити дім');return;}setHomeMode=!setHomeMode;$('#b-home').classList.toggle('on',setHomeMode);toast(setHomeMode?'Торкніться карти, щоб позначити дім':'Скасовано');};
let pressT;$('#b-home').addEventListener('pointerdown',()=>{pressT=setTimeout(()=>{setHomeMode=true;$('#b-home').classList.add('on');toast('Торкніться карти, щоб позначити дім');},650);});$('#b-home').addEventListener('pointerup',()=>clearTimeout(pressT));
$('#b-locate').onclick=()=>{if(!navigator.geolocation)return toast('Геолокація недоступна');navigator.geolocation.getCurrentPosition(p=>{const c=[p.coords.longitude,p.coords.latitude];map.flyTo({center:c,zoom:10});if(!home){home=c;localStorage.setItem('home',JSON.stringify(home));syncHome();toast('Дім = ваше місце');}},()=>toast('Не вдалося визначити місце'),{enableHighAccuracy:true,timeout:8000});};
$('#b-layers').onclick=()=>{setBase(base==='sat'?'map':'sat');toast(base==='sat'?'Супутник':'Карта');};
$('#b-3d').onclick=()=>{tilt=!tilt;$('#b-3d').classList.toggle('on',tilt);map.easeTo({pitch:tilt?55:0,bearing:tilt?-15:0,duration:600});};
$('#b-feed').onclick=()=>{$('#drawer').hidden=false;renderFeed();};
$('#dr-close').onclick=()=>$('#drawer').hidden=true;

/* ---------- живий потік ---------- */
function onSnap(s){SNAP=s;recvAt=Date.now();offset=s.now-Date.now()/1000;renderCounters();renderAsOf();syncLevels();syncZones();syncRaions();if(!$('#drawer').hidden)renderFeed();}
let ws,backoff=1000;
function connect(){
  const proto=location.protocol==='https:'?'wss':'ws';ws=new WebSocket(proto+'://'+location.host+'/ws');
  ws.onmessage=e=>{backoff=1000;onSnap(JSON.parse(e.data));};
  ws.onclose=()=>{setTimeout(connect,backoff);backoff=Math.min(backoff*2,15000);};
  ws.onerror=()=>ws.close();
}
connect();
setInterval(()=>{if(ws&&ws.readyState===1)ws.send('ping');},20000);
fetch('/api/state').then(r=>r.json()).then(onSnap).catch(()=>{});
})();
