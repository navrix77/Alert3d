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

let SNAP=null,recvAt=0,offset=0,sel=null,follow=false,home=null,setHomeMode=false,tilt=localStorage.getItem('t3d')!=='0',base=localStorage.getItem('base')||'sat';
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
  // реалістичні спрайти цілей (вид згори, ніс на північ) + тіні
  for(const t of Object.keys(TYPE_COLOR))for(const v of ['','-d','-sh']){const id='t-'+t+v;if(map.hasImage(id))continue;
    map.loadImage('sprites/t-'+t+v+'.png').then(r=>{if(!map.hasImage(id))map.addImage(id,r.data,{pixelRatio:2});}).catch(()=>{const c=drawTarget(t,44,{dim:v==='-d'});if(!map.hasImage(id))map.addImage(id,c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});});}
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
  map.addSource('ticks',{type:'geojson',data:EMPTY});
  ['zones','trails','preds','targets','home','chains','lsites'].forEach(id=>map.addSource(id,{type:'geojson',data:EMPTY}));
  map.addLayer({id:'obl-fill',type:'fill',source:'obl',paint:{'fill-color':['match',LV,2,'#C8102E',1,'#E8B300','#000'],'fill-opacity':['match',LV,2,0.2,1,0.22,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-fill',type:'fill',source:'ra',paint:{'fill-color':['match',LV,2,'#B3122E',1,'#E0A800','#000'],'fill-opacity':['match',LV,2,0.38,1,0.2,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-line',type:'line',source:'ra',minzoom:5.5,paint:{'line-color':'#fff','line-opacity':['interpolate',['linear'],['zoom'],5.5,0.25,9,0.55],'line-width':['interpolate',['linear'],['zoom'],6,0.5,10,1.2]}});
  map.addLayer({id:'obl-line',type:'line',source:'obl',paint:{'line-color':'#fff','line-width':['interpolate',['linear'],['zoom'],4,1,9,2.2],'line-opacity':0.9}});
  map.addLayer({id:'zones',type:'circle',source:'zones',paint:{'circle-pitch-alignment':'map','circle-radius':['interpolate',['exponential',2],['zoom'],5,4,9,60,12,480],'circle-color':'#FF7A2E','circle-opacity':0.18,'circle-stroke-color':'#FF7A2E','circle-stroke-width':1.2,'circle-stroke-opacity':0.7}});
  map.addLayer({id:'chains',type:'line',source:'chains',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':['case',['get','s'],2.6,1.4],'line-dasharray':[2,1.6],'line-opacity':['get','o']}});
  map.addLayer({id:'lsites',type:'circle',source:'lsites',paint:{'circle-radius':['case',['get','est'],5,7],'circle-color':['case',['get','est'],'rgba(255,77,77,0.25)','#FF3B3B'],'circle-stroke-color':'#fff','circle-stroke-width':['case',['get','est'],1.2,2],'circle-pitch-alignment':'map'}});
  map.addLayer({id:'lsites-t',type:'symbol',source:'lsites',layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,1.25],'text-anchor':'top','text-allow-overlap':true},paint:{'text-color':'#FFB3B3','text-halo-color':'#0B0F17','text-halo-width':2}});
  map.addLayer({id:'trails',type:'line',source:'trails',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':3,'line-dasharray':[0.1,2.2],'line-opacity':['get','o']}});
  map.addLayer({id:'sel-ring',type:'circle',source:'sel',paint:{'circle-pitch-alignment':'map','circle-radius':28,'circle-color':'rgba(0,0,0,0)','circle-stroke-color':['get','c'],'circle-stroke-width':2.5}});
  map.addLayer({id:'ticks-c',type:'circle',source:'ticks',paint:{'circle-radius':4,'circle-color':['get','c'],'circle-stroke-color':'#0B0F17','circle-stroke-width':2,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'ticks-t',type:'symbol',source:'ticks',layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,-1.1],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  map.addLayer({id:'preds',type:'line',source:'preds',layout:{'line-cap':'round'},paint:{'line-color':['get','c'],'line-width':2,'line-dasharray':[1.5,2],'line-opacity':0.9}});
  map.addLayer({id:'home',type:'symbol',source:'home',layout:{'icon-image':'home','icon-size':1,'icon-allow-overlap':true,'text-field':'Дім','text-font':['Noto Sans Bold'],'text-size':13,'text-offset':[0,1.7],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'tg-course',type:'symbol',source:'targets',filter:['all',['has','next'],['==',['get','active'],true]],layout:{'text-field':['concat','→ ',['get','next']],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[3,7,3,7],'text-anchor':'left','text-offset':[1.9,0.9],'icon-allow-overlap':false,'text-allow-overlap':false,'text-optional':false,'symbol-sort-key':['get','sk']},paint:{'text-color':'#fff'}});
  const TGS=['interpolate',['linear'],['zoom'],4,0.55,7,0.85,9,1.15,12,1.55];
  try{if(window.GlowLayer&&!map.getLayer('glow'))map.addLayer(window.GlowLayer);}catch(e){console.warn('glow',e);}
  map.addLayer({id:'ra-glow',type:'line',source:'ra',paint:{'line-color':'#FF3B4E','line-width':['interpolate',['linear'],['zoom'],5,2,9,5],'line-blur':['interpolate',['linear'],['zoom'],5,2,9,5],'line-opacity':['case',['==',LV,2],0.5,0]}});
  map.addLayer({id:'tg-sh',type:'symbol',source:'targets',filter:['==',['get','active'],true],layout:{'icon-image':['concat','t-',['get','type'],'-sh'],'icon-rotate':['get','sa'],'icon-rotation-alignment':'viewport','icon-pitch-alignment':'viewport','icon-allow-overlap':true,'icon-ignore-placement':true,'icon-size':TGS},paint:{'icon-opacity':0.9,'icon-translate':[14,22],'icon-translate-anchor':'viewport'}});
  map.addLayer({id:'tg',type:'symbol',source:'targets',layout:{'icon-image':['concat','t-',['get','type'],['case',['get','active'],'','-d']],'icon-rotate':['get','sa'],'icon-rotation-alignment':'viewport','icon-pitch-alignment':'viewport','icon-allow-overlap':true,'icon-ignore-placement':true,'icon-size':TGS,'symbol-sort-key':['get','sk']},paint:{'icon-opacity':['case',['get','weak'],0.6,1]}});
  map.addLayer({id:'tg-n',type:'symbol',source:'targets',filter:['>',['get','count'],1],layout:{'text-field':['concat','×',['to-string',['get','count']]],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[2,6,2,6],'text-offset':[1.3,-1.2],'text-allow-overlap':true,'icon-allow-overlap':true},paint:{'text-color':'#fff'}});
  map.addLayer({id:'tg-unk',type:'symbol',source:'targets',filter:['all',['get','unk'],['get','active']],layout:{'text-field':'курс ?','text-font':['Noto Sans Bold'],'text-size':11,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[2,6,2,6],'text-offset':[0,2.2],'text-allow-overlap':true,'icon-allow-overlap':true},paint:{'text-color':'#F5B83D'}});
  map.on('click','tg',e=>{const f=e.features[0];openSheet(f.properties.id);});
  map.on('mouseenter','tg',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','tg',()=>map.getCanvas().style.cursor='');
  lastLv='';lastRa='';syncHome();
  if(tilt)set3d(true,false);
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
      // кут на ЕКРАНІ: проєктуємо точку і точку на 3 км уздовж курсу — враховує нахил і поворот карти
      const unk=tr.hd==null;let sa=0;
      if(!unk){const P=xy(d.p),r=d.hd*D2R;const A=map.project(d.p),B=map.project(ll([P[0]+Math.sin(r)*3,P[1]+Math.cos(r)*3]));sa=Math.atan2(B.x-A.x,-(B.y-A.y))/D2R;}
      feats.push({type:'Feature',properties:{id:tr.id,type:tr.type,hd:d.hd,sa,unk,active,weak,count:tr.count||1,next:tr.next||undefined,sk:active?(sel===tr.id?0:1):2},geometry:{type:'Point',coordinates:d.p}});
      const c=TYPE_COLOR[tr.type];
      if(active)trails.push({type:'Feature',properties:{c,o:0.95},geometry:{type:'LineString',coordinates:[...tr.trail.slice(-3).map(t=>[t[0],t[1]]),d.p]}});
      if(active&&(sel===tr.id||(rel&&rel.rel))&&tr.route.length)preds.push({type:'Feature',properties:{c},geometry:{type:'LineString',coordinates:[d.p,...tr.route]}});
    }
    // каша геть: показуємо лише активні цілі; цілі одного типу, що на екрані лягають одна на одну, — один значок ×N
    const shown=[];for(const f of feats.filter(f=>f.properties.active).sort((a,b)=>(b.properties.weak?0:1)-(a.properties.weak?0:1))){
      const P=map.project(f.geometry.coordinates);const near=shown.find(g=>g.properties.type===f.properties.type&&Math.hypot(g._p.x-P.x,g._p.y-P.y)<34);
      if(near&&f.properties.id!==sel){near.properties.count+=f.properties.count;near.properties.merged=(near.properties.merged||1)+1;continue;}
      f._p=P;shown.push(f);}
    feats.length=0;feats.push(...shown);
    map.getSource('targets').setData({type:'FeatureCollection',features:feats});
    {const thr=new Set(threats.map(x=>x.tr.id)),z=map.getZoom(),sz=Math.max(18,Math.min(70,10+z*5));
     window.GLOW=feats.map(f=>{const h=TYPE_COLOR[f.properties.type]||'#ffffff',n=parseInt(h.slice(1),16);const t=thr.has(f.properties.id);
       return {p:f.geometry.coordinates,c:t?[1,0.23,0.27]:[(n>>16&255)/255,(n>>8&255)/255,(n&255)/255],a:f.properties.weak?0.3:0.7,s:t?sz*1.9:sz,ring:t};});}
    if(map.getLayer('ra-glow')&&now-(frame.rg||0)>90){frame.rg=now;const k=0.25+0.45*(0.5+0.5*Math.sin(now/520));map.setPaintProperty('ra-glow','line-opacity',['case',['==',['coalesce',['feature-state','lvl'],0],2],k,0]);}
    if(map.getSource('chains')&&now-(frame.ch||0)>500){frame.ch=now;const ch=[],ls=new Map();
      for(const L of (SNAP.launches||[]))ls.set(L.site,{type:'Feature',properties:{est:false,l:'ПУСК · '+L.site.replace(/ \(.*\)/,'')+' '+fmt(L.t)+(L.count?' ×'+L.count:'')},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});
      for(const tr of SNAP.tracks){const L=tr.launch;if(!L||tr.status==='closed')continue;const isSel=sel===tr.id,d=DISP.get(tr.id);if(!d)continue;
        if(L.est&&!isSel)continue;
        ch.push({type:'Feature',properties:{c:L.est?'#FF8A8A':'#FF3B3B',o:isSel?0.95:(L.est?0.3:0.38),s:isSel},geometry:{type:'LineString',coordinates:[[L.lon,L.lat],[tr.entry[0],tr.entry[1]],...tr.trail.map(t=>[t[0],t[1]]),d.p]}});
        if(!ls.has(L.site))ls.set(L.site,{type:'Feature',properties:{est:true,l:'ймовірно · '+L.site.replace(/ \(.*\)/,'')},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});}
      map.getSource('chains').setData({type:'FeatureCollection',features:ch});map.getSource('lsites').setData({type:'FeatureCollection',features:[...ls.values()]});}
    T3D.heads=feats.map(f=>({id:f.properties.id,type:f.properties.type,hd:f.properties.hd,active:f.properties.active,weak:f.properties.weak,p:f.geometry.coordinates}));
    map.getSource('trails').setData({type:'FeatureCollection',features:trails});
    map.getSource('preds').setData({type:'FeatureCollection',features:preds});
    if(map.getSource('sel')){const d=sel&&DISP.get(sel);const tr=sel&&SNAP.tracks.find(t=>t.id===sel);map.getSource('sel').setData(d&&tr?{type:'FeatureCollection',features:[{type:'Feature',properties:{c:TYPE_COLOR[tr.type]},geometry:{type:'Point',coordinates:d.p}}]}:EMPTY);}
    if(follow&&sel){const d=DISP.get(sel);if(d)map.easeTo({center:d.p,duration:0});}
    renderBanner(threats);
    if(map.getSource('ticks')&&now-(frame.tk||0)>800){frame.tk=now;const tk=[];const serverT=Date.now()/1000+offset;
      for(const tr of SNAP.tracks){if(tr.status!=='active'||!(sel===tr.id||threats.some(x=>x.tr.id===tr.id)))continue;const c=TYPE_COLOR[tr.type];
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
  if(!SNAP||!map.getSource('obl'))return;const key=JSON.stringify(SNAP.levels);if(key===lastLv)return;lastLv=key;
  fetchOblNames().then(names=>{if(!map.getSource('obl'))return;names.forEach(n=>{try{map.setFeatureState({source:'obl',id:n},{lvl:SNAP.levels[n]||0});}catch(e){lastLv='';}});});
}
let RA=null,lastRa='';
function inRing(r,x,y){let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const [xi,yi]=r[i],[xj,yj]=r[j];if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/((yj-yi)||1e-12)+xi))c=!c;}return c;}
function raionOf(lon,lat){if(!RA)return -1;for(const r of RA){if(lon<r.bb[0]||lon>r.bb[2]||lat<r.bb[1]||lat>r.bb[3])continue;for(const pl of r.polys)if(inRing(pl[0],lon,lat))return r.i;}return -1;}
fetch('/data/raions.geojson').then(r=>r.json()).then(j=>{RA=j.features.map((f,i)=>{const g=f.geometry;const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;let bb=[180,90,-180,-90];polys.forEach(pl=>pl[0].forEach(([x,y])=>{bb[0]=Math.min(bb[0],x);bb[1]=Math.min(bb[1],y);bb[2]=Math.max(bb[2],x);bb[3]=Math.max(bb[3],y);}));return {i,n:f.properties.n,polys,bb};});});
function syncRaions(){
  if(!SNAP||!RA||!map.getSource('ra'))return;const lv={};const up=(i,v)=>{if(i>=0&&(lv[i]||0)<v)lv[i]=v;};
  const O=SNAP.official||{};const rl=O.raion_levels||{};RA.forEach(r=>{if(rl[r.n])up(r.i,rl[r.n]);});(O.points||[]).forEach(([lo,la,_n,l])=>up(raionOf(lo,la),l));
  // райони фарбуються лише за офіційними тривогами (alerts.in.ua)
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
  order.filter(t=>by[t]).forEach(t=>{const d=document.createElement('div');d.className='cnt';d.title=TYPE_NAME[t];const c=CNTI[t]||(CNTI[t]=drawTarget(t,28));const cc=document.createElement('canvas');cc.width=c.width;cc.height=c.height;cc.getContext('2d').drawImage(c,0,0);d.appendChild(cc);const b=document.createElement('b');b.textContent=by[t];if(renderCounters.prev&&renderCounters.prev[t]!==by[t])b.className='pop';d.appendChild(b);$('#counters').appendChild(d);});
  renderCounters.prev=by;
  if(!act.length){const d=document.createElement('div');d.className='cnt';d.innerHTML='<b style="font-size:16px">Цілей не видно</b>';$('#counters').appendChild(d);}
}
function renderAsOf(){
  // для людей: лише «наживо» і час; технічні деталі — у стрічці
  const el=$('#asof');const age=(Date.now()-recvAt)/1000;
  if(!SNAP){el.className='asof';el.innerHTML='<i class="live-dot wait"></i>Підключення…';return;}
  if(age>20){el.className='asof stale';el.innerHTML='<i class="live-dot"></i>Немає звʼязку '+Math.round(age)+' с — це не відбій';return;}
  const h=SNAP.health,ok=h.telegram||h.replay;
  el.className='asof'+(ok?'':' stale');
  el.innerHTML='<i class="live-dot'+(ok?'':' wait')+'"></i>'+(h.replay?'Демо':ok?'Наживо':'Дані затримуються')+' · '+fmt(SNAP.now);
}
setInterval(()=>SNAP&&renderAsOf(),1000);
let SHELTER=+(localStorage.getItem('shelter')||3);$('#me-sh').textContent=SHELTER;
$('#me-set').onclick=()=>{const v=[1,2,3,5,7,10];SHELTER=v[(v.indexOf(SHELTER)+1)%v.length];localStorage.setItem('shelter',SHELTER);$('#me-sh').textContent=SHELTER;toast('До укриття: '+SHELTER+' хв');};
const MEI={};
function renderMe(threats){
  const box=$('#me');if(!home){box.className='me';$('#me-word').textContent='Мій дім';$('#me-sub').innerHTML='Позначте дім кнопкою ⌂ унизу — тут буде особистий таймер: що летить до вас і коли йти в укриття.';$('#me-list').innerHTML='';return;}
  const isStale=!SNAP||(Date.now()-recvAt)/1000>20;
  const near=SNAP.tracks.filter(t=>t.status==='active'&&t.conf>=0.5).map(t=>{const d=DISP.get(t.id);return d?{tr:t,r:homeRel(t,d.p)}:null;}).filter(x=>x&&x.r&&x.r.d<120).sort((a,b)=>(a.r.eta??999)-(b.r.eta??999)||a.r.d-b.r.d);
  const thr=near.filter(x=>x.r.rel);const first=thr[0];
  let cls='me',word='Спокійно',sub='Підтверджених цілей у бік дому немає. Найближча: '+(near[0]?Math.round(near[0].r.d)+' км '+near[0].r.from:'далі 120 км')+'.';
  if(isStale){cls='me watch';word='Невідомо';sub='Немає звʼязку з джерелами. Це <b>не відбій</b>.';}
  else if(first){const m=Math.max(0,(first.r.eta||0)-SHELTER);cls=m<=3?'me danger':'me watch';word=m<=0?'В укриття зараз':m<=3?'Виходь в укриття':'Увага';
    sub=(m<=0?'Ціль прибуде раніше, ніж ви дійдете до укриття. Правило двох стін.':'Маєте <b>~'+Math.floor(m)+' хв</b>, щоб зібратися, потім '+SHELTER+' хв до укриття.');}
  box.className=cls;$('#me-word').textContent=word;$('#me-sub').innerHTML=sub;
  $('#me-list').innerHTML='';
  (thr.length?thr:near).slice(0,3).forEach(x=>{const t=x.tr,r=x.r;const li=document.createElement('li');
    const c=MEI[t.type]||(MEI[t.type]=drawTarget(t.type,22));const cv=document.createElement('canvas');cv.width=c.width;cv.height=c.height;cv.getContext('2d').drawImage(c,0,0);
    const eta=r.eta!=null?Math.max(1,Math.round(r.eta)):null;const span=Math.max(eta||0,SHELTER)+3;
    li.innerHTML='<div class="me-row"><span class="n">'+esc(TYPE_NAME[t.type])+(t.count>1?' ×'+t.count:'')+' · '+Math.round(r.d)+' км '+r.from+'</span><span class="t">'+(eta?'~'+eta+' хв':'—')+'</span></div>'+
      (eta?'<div class="me-bar"><i class="sh" style="width:'+(SHELTER/span*100)+'%"></i><i class="tg" style="left:'+(eta*0.8/span*100)+'%;width:'+Math.max(3,eta*0.5/span*100)+'%"></i></div><div class="me-act '+(eta-SHELTER<=3?'go':'ok')+'">'+(r.rel==='route'?'маршрут проходить біля дому':'курс у ваш бік')+'</div>':'');
    li.querySelector('.me-row').prepend(cv);li.onclick=()=>openSheet(t.id);$('#me-list').appendChild(li);});
}
function renderBanner(threats){
  const b=$('#banner');if(!threats.length){b.hidden=true;return;}
  threats.sort((a,b)=>(a.rel.eta??999)-(b.rel.eta??999));const t=threats[0];
  b.hidden=false;b.innerHTML=esc(TYPE_NAME[t.tr.type])+(t.tr.count>1?' ×'+t.tr.count:'')+' · '+(t.rel.rel==='route'?'маршрут проходить біля дому':'курс на твій район')+(t.rel.eta!=null?' · ~'+Math.max(1,Math.round(t.rel.eta))+' хв':'')+'<small>'+Math.round(t.rel.d)+' км '+t.rel.from+(threats.length>1?' · ще '+(threats.length-1):'')+'</small>';
  b.onclick=()=>openSheet(t.tr.id);
  // кінематографічний переліт: нова загроза дому — камера плавно показує і дім, і ціль (якщо користувач не крутить карту)
  renderBanner.seen=renderBanner.seen||new Set();
  if(!renderBanner.seen.has(t.tr.id)){renderBanner.seen.add(t.tr.id);const d=DISP.get(t.tr.id);
    if(d&&home&&Date.now()-(window.__touch||0)>20000){const b2=new maplibregl.LngLatBounds(home,home).extend(d.p);
      const cam=map.cameraForBounds(b2,{padding:{top:140,bottom:160,left:80,right:380}});if(cam)map.flyTo({...cam,zoom:Math.min(cam.zoom,10),pitch:tilt?55:20,bearing:tilt?-18:0,curve:1.5,speed:0.7,essential:true});}}
}
['mousedown','touchstart','wheel'].forEach(ev=>document.getElementById('map').addEventListener(ev,()=>window.__touch=Date.now(),{passive:true}));

/* ---------- картка цілі ---------- */
function openSheet(id){sel=id;follow=false;$('#sh-follow').classList.remove('on');$('#sh-follow').textContent='Стежити за ціллю';$('#sheet').hidden=false;fillSheet(true);const d=DISP.get(id);if(d)map.flyTo({center:d.p,zoom:Math.max(map.getZoom(),8.5),curve:1.3,speed:1.1,essential:true});}
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
  {const L=tr.launch,en=tr.entry;let h='';
   if(L)h=(L.est?'ймовірно ':'')+'<b>'+esc(L.site)+'</b>'+(L.carrier?' · '+esc(L.carrier):'')+(L.t?' · пуск '+fmt(L.t):'')+(L.est?' <small>(оцінка за курсом'+(L.p>=0.4?' і статистикою':'')+')</small>':' <small>('+(L.srcs||[]).map(s=>esc(SNAP.sources[s]?.name||s)).join(', ')+(L.link?' · <a href="'+esc(L.link)+'" target="_blank" rel="noopener">пост ↗</a>':'')+')</small>');
   else h=tr.from?'з боку '+esc(tr.from):'канали не вказали';
   if(en)h+='<br><small>перша фіксація: '+esc(en[2])+' · '+fmt(en[3])+'</small>';
   $('#sh-from').innerHTML=h;}
  $('#sh-conf').textContent=Math.round(tr.conf*100)+'%'+(tr.conf<0.5?' · непідтверджено':'');
  const serverT=Date.now()/1000+offset;const pos=DISP.get(tr.id);
  if(tr.route_names&&tr.route_names.length&&tr.route&&tr.route.length&&pos){let acc=0,prev=xy(pos.p);const items=tr.route.slice(0,tr.route_names.length).map((p,i)=>{const q=xy(p);acc+=dist(prev,q);prev=q;return '<li><b>~'+Math.max(1,Math.round(acc/tr.speed*60))+' хв</b> '+esc(tr.route_names[i])+'</li>';});
    if(home&&r&&r.eta!=null)items.push('<li class="home"><b>~'+Math.max(1,Math.round(r.eta))+' хв</b> ваш дім</li>');
    const why=tr.pred==='learned'?' <small>· вивчено з історії'+(tr.pred_p?' ('+Math.round(tr.pred_p*100)+'%)':'')+'</small>':tr.pred==='channels'?' <small>· за каналами</small>':'';
    $('#sh-route').innerHTML='<h4>Прогноз маршруту'+why+'</h4><ol>'+items.join('')+'</ol>'+(tr.pos_est?'<p class="est">Точне місце не названо — позицію оцінено'+(tr.pred==='learned-origin'?' за типовими маршрутами':' по пункту призначення')+'</p>':'');}else $('#sh-route').innerHTML='';
  const n=tr.srcs.length;$('#sh-proof').innerHTML='<h4>Підтвердження: '+n+' '+(n===1?'канал':n<5?'канали':'каналів')+(n>=2?' · незалежно':' · лише одне джерело')+'</h4><div class="bar">'+[0,1,2,3].map(i=>'<i class="'+(i<n?'on':'')+'"></i>').join('')+'</div><ul>'+tr.srcs.map(s=>{const L=tr.links.filter(l=>SNAP.sources[s]&&l.includes('/'+(SNAP.sources[s].url||'').split('/').pop()+'/')).pop();return '<li><span>'+esc(SNAP.sources[s]?.name||s)+'</span>'+(L?'<a href="'+esc(L)+'" target="_blank" rel="noopener">пост ↗</a>':'')+'</li>';}).join('')+'</ul>';
  const link=tr.links[tr.links.length-1];const a=$('#sh-post');if(link){a.href=link;a.hidden=false;}else a.hidden=true;
}
$('#sh-close').onclick=()=>{sel=null;follow=false;$('#sheet').hidden=true;};
$('#sh-follow').onclick=()=>{follow=!follow;$('#sh-follow').classList.toggle('on',follow);$('#sh-follow').textContent=follow?'Стежу · зупинити':'Стежити за ціллю';};

/* ---------- стрічка ---------- */
function renderFeed(){
  const kindTxt={launch:'Пуск',filtered:'Повідомлення про роботу ППО або влучання приховано фільтром безпеки.',close:'Ціль більше не фіксується',zone:'Загроза КАБ',info:'Без географічної привʼязки'};
  {const h=SNAP.health||{},c=h.channels||{};$('#dr-tech').textContent=(c.channels?'Канали: '+c.live+'/'+c.channels+(c.all_every?' · повний обхід '+c.all_every+' с':''):'')+(SNAP.official&&SNAP.official.source?' · тривоги: '+SNAP.official.source:'')+(h.version?'':' · стара версія сервера');}
  const LS=(SNAP.launches||[]).slice().reverse();
  const lh=LS.length?'<li class="launches"><div class="m"><span>Пуски за 6 год</span></div>'+LS.map(L=>'<div>'+fmt(L.t)+' · <b>'+esc(L.site)+'</b>'+(L.type?' · '+esc(TYPE_NAME[L.type]||L.type):'')+(L.count?' ×'+L.count:'')+(L.carrier?' · '+esc(L.carrier):'')+(L.tracks?' · цілей звідти: '+L.tracks:'')+'</div>').join('')+'</li>':'';
  $('#feed').innerHTML=lh+SNAP.log.slice().reverse().map(r=>{const src=SNAP.sources[r.src]?.name||r.src;
    let txt=kindTxt[r.kind]||'';if(r.kind==='track'||r.kind==='zone'){const tg=r.places.filter(p=>p.r==='t').map(p=>p.n),pos=r.places.find(p=>p.r==='p'),fr=r.places.find(p=>p.r==='f');txt=(TYPE_NAME[r.type]||'Ціль')+(r.count?' ×'+r.count:'')+(fr?' · з боку '+fr.n:'')+(pos?' · в районі '+pos.n:'')+(tg.length?(r.kind==='zone'?' · загроза для: ':' · курсом на ')+tg.slice(0,6).join(', '):'');}
    return '<li><div class="m"><span>'+fmt(r.t)+'</span><span>'+esc(src)+'</span>'+(r.track?'<span>→ '+esc(r.track)+'</span>':'')+(r.link?'<a href="'+esc(r.link)+'" target="_blank" rel="noopener">пост ↗</a>':'')+'</div><div class="'+(r.kind==='filtered'?'f':'')+'">'+esc(txt)+'</div></li>';}).join('')||'<li>Повідомлень ще немає.</li>';
}

/* ---------- кнопки ---------- */
$('#b-home').onclick=()=>{if(home&&!setHomeMode){map.flyTo({center:home,zoom:Math.max(map.getZoom(),9)});toast('Довге натискання — змінити дім');return;}setHomeMode=!setHomeMode;$('#b-home').classList.toggle('on',setHomeMode);toast(setHomeMode?'Торкніться карти, щоб позначити дім':'Скасовано');};
let pressT;$('#b-home').addEventListener('pointerdown',()=>{pressT=setTimeout(()=>{setHomeMode=true;$('#b-home').classList.add('on');toast('Торкніться карти, щоб позначити дім');},650);});$('#b-home').addEventListener('pointerup',()=>clearTimeout(pressT));
$('#b-locate').onclick=()=>{if(!navigator.geolocation)return toast('Геолокація недоступна');navigator.geolocation.getCurrentPosition(p=>{const c=[p.coords.longitude,p.coords.latitude];map.flyTo({center:c,zoom:10});if(!home){home=c;localStorage.setItem('home',JSON.stringify(home));syncHome();toast('Дім = ваше місце');}},()=>toast('Не вдалося визначити місце'),{enableHighAccuracy:true,timeout:8000});};
$('#b-layers').onclick=()=>{setBase(base==='sat'?'map':'sat');toast(base==='sat'?'Супутник':'Карта');};
function flat3d(on){// значок завжди «дивиться» на екран (як у 2D) — без перспективних спотворень; у 3D лише коротша тінь
  if(map.getLayer('tg-sh')){map.setPaintProperty('tg-sh','icon-translate',on?[8,12]:[14,22]);map.setPaintProperty('tg-sh','icon-opacity',on?0.6:0.9);}}
function set3d(on,anim){tilt=on;flat3d(on);localStorage.setItem('t3d',on?'1':'0');$('#b-3d').classList.toggle('on',on);if(map.getSource('obl')){on?T3D.enable(map):T3D.disable(map);}map.easeTo({pitch:on?60:0,bearing:on?-18:0,duration:anim?700:0});}
$('#b-3d').onclick=()=>set3d(!tilt,true);
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
