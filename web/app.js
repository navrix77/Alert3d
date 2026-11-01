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

let SNAP=null,recvAt=0,offset=0,sel=null,follow=false,home=null,setHomeMode=false,tilt=localStorage.getItem('t3d')!=='0',base=localStorage.getItem('base2')||'night';
try{home=JSON.parse(localStorage.getItem('home')||'null');}catch(e){}
const DISP=new Map();
const PREFL=()=>{try{return Object.assign({launch:true},JSON.parse(localStorage.getItem('pref')||'{}'));}catch(e){return {launch:true};}};
const TYPES_KMH=t=>({shahed:170,jet:450,molniya:120,cruise:800,ballistic:2000,kab:600})[t]||200;

/* ---------- карта ---------- */
const ESRI='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
let CFG={vectorStyle:'https://tiles.openfreemap.org/styles/liberty'};
const INTRO=!sessionStorage.getItem('intro');
const map=new maplibregl.Map({container:'map',style:{version:8,sources:{},layers:[{id:'bg',type:'background',paint:{'background-color':'#03050A'}}]},center:INTRO?[27,46]:[32.2,48.4],zoom:INTRO?3.1:5.6,pitch:INTRO?0:(tilt?50:0),bearing:INTRO?0:(tilt?-14:0),attributionControl:{compact:true},maxPitch:65});window.tryvogaMap=map;
async function styleFor(kind){
  const vec=await fetch(CFG.vectorStyle).then(r=>r.json());
  // підписи українською: name:uk → name (OSM) замість латиниці
  const UK=['coalesce',['get','name:uk'],['get','name']];
  vec.layers.forEach(l=>{if(l.type==='symbol'&&l.layout&&l.layout['text-field']&&JSON.stringify(l.layout['text-field']).includes('name'))l.layout['text-field']=UK;});
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
      {id:'esri',type:'raster',source:'esri',paint:NIGHT?{'raster-saturation':-0.55,'raster-brightness-max':['interpolate',['linear'],['zoom'],6,0.18,9,0.42,12,0.6],'raster-contrast':0.15,'raster-opacity':['interpolate',['linear'],['zoom'],5,0.6,8,1]}:{'raster-saturation':-0.25,'raster-brightness-max':0.82}},
      ...(NIGHT?[{id:'lights',type:'raster',source:'lights',maxzoom:10,paint:{'raster-opacity':['interpolate',['linear'],['zoom'],6.5,0.95,9,0],'raster-saturation':-0.1,'raster-contrast':0.25,'raster-resampling':'linear'}}]:[]),...keep]};
  if(NIGHT){out.sources.lights={type:'raster',tiles:['https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png'],tileSize:256,maxzoom:8,attribution:'NASA Black Marble'};}
  out.sky={'sky-color':'#04060C','horizon-color':'#1B2A4A','fog-color':'#04060C','sky-horizon-blend':0.7,'horizon-fog-blend':0.85,'fog-ground-blend':0.35,'atmosphere-blend':['interpolate',['linear'],['zoom'],0,1,5,0.75,8,0.2]};
  if(vec.sprite)out.sprite=vec.sprite;return out;
}
async function setBase(kind){base=kind;localStorage.setItem('base2',kind);map.setStyle(await styleFor(kind),{diff:false});}

function addImages(){
  // реалістичні спрайти цілей (вид згори, ніс на північ) + тіні
  for(const t of Object.keys(TYPE_COLOR))for(const v of ['','-d','-sh']){const id='t-'+t+v;if(map.hasImage(id))continue;
    map.loadImage('sprites/t-'+t+v+'.png').then(r=>{if(!map.hasImage(id))map.addImage(id,r.data,{pixelRatio:2});}).catch(()=>{const c=drawTarget(t,44,{dim:v==='-d'});if(!map.hasImage(id))map.addImage(id,c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});});}
  if(!map.hasImage('home')){const c=drawHome(40);map.addImage('home',c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});}
  if(!map.hasImage('chip')){const s=48,c=document.createElement('canvas');c.width=c.height=s;const x=c.getContext('2d');x.fillStyle='rgba(12,15,22,.88)';x.beginPath();x.roundRect(2,2,s-4,s-4,14);x.fill();map.addImage('chip',x.getImageData(0,0,s,s),{pixelRatio:2,stretchX:[[14,34]],stretchY:[[14,34]],content:[10,8,38,40]});}
}
const EMPTY={type:'FeatureCollection',features:[]};
function addRelief(){
  // об'єм: рельєф (висоти Terrarium/AWS) + тіньовий відмив + 3D-будівлі в містах
  try{
    if(!map.getSource('dem-hs'))map.addSource('dem-hs',{type:'raster-dem',tiles:['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],encoding:'terrarium',tileSize:256,maxzoom:12,attribution:'Рельєф: Mapzen/AWS Terrain'});
    const firstSym=(map.getStyle().layers.find(l=>l.type==='symbol')||{}).id;
    const night=base!=='map'&&document.documentElement.dataset.theme!=='day';
    if(!map.getLayer('hillshade'))map.addLayer({id:'hillshade',type:'hillshade',source:'dem-hs',paint:{'hillshade-exaggeration':night?0.55:0.4,'hillshade-shadow-color':night?'#000000':'#3a3328','hillshade-highlight-color':night?'rgba(150,170,210,.35)':'#ffffff','hillshade-accent-color':night?'#05070c':'#5a4a36','hillshade-illumination-direction':315}},firstSym);
    const vs=Object.keys(map.getStyle().sources).find(k=>map.getStyle().sources[k].type==='vector');
    if(vs&&!map.getLayer('bld3d'))map.addLayer({id:'bld3d',type:'fill-extrusion',source:vs,'source-layer':'building',minzoom:12.5,
      paint:{'fill-extrusion-color':night?'#1b2333':'#d9d4cc','fill-extrusion-height':['coalesce',['get','render_height'],['get','height'],8],'fill-extrusion-base':['coalesce',['get','render_min_height'],0],
        'fill-extrusion-opacity':['interpolate',['linear'],['zoom'],12.5,0,13.5,night?0.75:0.85],'fill-extrusion-vertical-gradient':true}},firstSym);
  }catch(e){console.warn('relief',e);}
}
function addOverlays(){
  addRelief();
  const st=map.getStyle();if(!st||!st.glyphs||map.getSource('obl'))return;
  addImages();
  const LV=['coalesce',['feature-state','lvl'],0];
  map.addSource('obl',{type:'geojson',data:'/data/oblasts.geojson',promoteId:'n'});
  map.addSource('ra',{type:'geojson',data:'/data/raions.geojson',generateId:true});
  map.addSource('occ',{type:'geojson',data:'/data/occupied.geojson'});
  if(!map.hasImage('hatch')){const c=document.createElement('canvas');c.width=c.height=16;const x=c.getContext('2d');x.strokeStyle='rgba(20,0,6,.55)';x.lineWidth=3;x.beginPath();x.moveTo(-4,20);x.lineTo(20,-4);x.moveTo(-4,4);x.lineTo(4,-4);x.moveTo(12,20);x.lineTo(20,12);x.stroke();map.addImage('hatch',x.getImageData(0,0,16,16),{pixelRatio:2});}
  map.addSource('sel',{type:'geojson',data:EMPTY});
  map.addSource('ticks',{type:'geojson',data:EMPTY});
  map.addSource('holo',{type:'geojson',data:EMPTY});map.addSource('hrom',{type:'geojson',data:EMPTY});map.addSource('comets',{type:'geojson',data:EMPTY,lineMetrics:true});
  ['zones','trails','preds','targets','home','chains','lsites'].forEach(id=>map.addSource(id,{type:'geojson',data:EMPTY}));
  map.addLayer({id:'obl-fill',type:'fill',source:'obl',paint:{'fill-color':['match',LV,2,'#C8102E',1,'#E8B300','#000'],'fill-opacity':['match',LV,2,0.1,1,0.1,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-fill',type:'fill',source:'ra',paint:{'fill-color':['match',LV,2,'#B3122E',1,'#E0A800','#000'],'fill-opacity':['match',LV,2,0.16,1,0.1,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-line',type:'line',source:'ra',minzoom:5.5,paint:{'line-color':'#fff','line-opacity':['interpolate',['linear'],['zoom'],5.5,0.25,9,0.55],'line-width':['interpolate',['linear'],['zoom'],6,0.5,10,1.2]}});
  map.addLayer({id:'occ-fill',type:'fill',source:'occ',paint:{'fill-color':['match',['get','k'],'occupied','#2A0710','#3A3A3A'],'fill-opacity':['match',['get','k'],'occupied',0.62,0.35]}});
  map.addLayer({id:'occ-hatch',type:'fill',source:'occ',filter:['==',['get','k'],'occupied'],paint:{'fill-pattern':'hatch','fill-opacity':0.8}});
  map.addLayer({id:'occ-line',type:'line',source:'occ',filter:['==',['get','k'],'occupied'],paint:{'line-color':'#E0405A','line-width':['interpolate',['linear'],['zoom'],5,1,9,2.2],'line-opacity':0.85}});
  map.addLayer({id:'obl-line',type:'line',source:'obl',paint:{'line-color':'#fff','line-width':['interpolate',['linear'],['zoom'],4,1,9,2.2],'line-opacity':0.9}});
  map.addSource('ru',{type:'geojson',data:EMPTY});map.addSource('hits',{type:'geojson',data:EMPTY});
  if(!map.hasImage('hit')){const c=document.createElement('canvas');c.width=c.height=40;const x=c.getContext('2d');x.translate(20,20);
    x.fillStyle='rgba(255,213,0,.25)';x.beginPath();x.arc(0,0,18,0,7);x.fill();x.strokeStyle='#FFD500';x.lineWidth=2.5;x.beginPath();x.arc(0,0,11,0,7);x.stroke();
    x.beginPath();for(const a of [0,90,180,270]){const r=a*Math.PI/180;x.moveTo(Math.sin(r)*6,-Math.cos(r)*6);x.lineTo(Math.sin(r)*17,-Math.cos(r)*17);}x.stroke();x.fillStyle='#2F7BFF';x.beginPath();x.arc(0,0,4,0,7);x.fill();
    x.setTransform(1,0,0,1,0,0);map.addImage('hit',x.getImageData(0,0,40,40),{pixelRatio:2});}
  map.addLayer({id:'ru-glow',type:'circle',source:'ru',minzoom:3,filter:['!',['has','sum']],paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,['+',10,['*',2,['coalesce',['get','c'],3]]],8,['+',30,['*',4,['coalesce',['get','c'],3]]]],'circle-color':'#2F7BFF','circle-blur':1,'circle-opacity':0.22,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'ru-dot',type:'circle',source:'ru',filter:['!',['has','sum']],paint:{'circle-radius':3.5,'circle-color':'#FFD500','circle-stroke-color':'#2F7BFF','circle-stroke-width':2,'circle-opacity':0.85}});
  map.addLayer({id:'ru-t',type:'symbol',source:'ru',layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':['case',['has','sum'],12,10.5],'text-max-width':16,'text-offset':['case',['has','sum'],['literal',[0,0]],['literal',[0,1.1]]],'text-anchor':['case',['has','sum'],'center','top'],'text-allow-overlap':false},paint:{'text-color':'rgba(255,227,107,.8)','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'hits',type:'symbol',source:'hits',layout:{'icon-image':'hit','icon-size':1,'icon-allow-overlap':true,'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,1.5],'text-anchor':'top','text-max-width':14,'text-optional':true},paint:{'text-color':'#FFE36B','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  map.addSource('xr',{type:'geojson',data:EMPTY});
  map.addLayer({id:'xr-dim',type:'background',layout:{visibility:'none'},paint:{'background-color':'#02040A','background-opacity':0.62}});
  map.addLayer({id:'xr-edge',type:'line',source:'xr',filter:['all',['==',['geometry-type'],'LineString'],['==',['get','k'],'confirm']],layout:{visibility:'none','line-cap':'round'},paint:{'line-color':['match',['get','k'],'confirm','#34C759','copy','#8892A6','assume','#B48CFF','contra','#F5B83D','#fff'],'line-width':['match',['get','k'],'confirm',2.5,1.6],'line-opacity':0.9}});map.addLayer({id:'xr-edge2',type:'line',source:'xr',filter:['all',['==',['geometry-type'],'LineString'],['!=',['get','k'],'confirm']],layout:{visibility:'none','line-cap':'round'},paint:{'line-dasharray':[1.5,2],'line-color':['match',['get','k'],'confirm','#34C759','copy','#8892A6','assume','#B48CFF','contra','#F5B83D','#fff'],'line-width':['match',['get','k'],'confirm',2.5,1.6],'line-opacity':0.9}});
  map.addLayer({id:'xr-node',type:'circle',source:'xr',filter:['==',['geometry-type'],'Point'],layout:{visibility:'none'},paint:{'circle-radius':['match',['get','k'],'prim',7,'copy',4.5,'now',6,5],'circle-color':['match',['get','k'],'prim','#34C759','copy','#8892A6','dest','rgba(0,0,0,0)','now','rgba(180,140,255,.25)','#B48CFF'],'circle-stroke-color':['match',['get','k'],'prim','#C8FFD6','copy','#C9D2E3','dest','#F5B83D','now','#B48CFF','#E3D4FF'],'circle-stroke-width':['match',['get','k'],'dest',2,'now',2,1.5]}});
  map.addLayer({id:'xr-t',type:'symbol',source:'xr',filter:['all',['==',['geometry-type'],'Point'],['has','l']],minzoom:6.5,layout:{visibility:'none','text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':10.5,'text-offset':[0,1.2],'text-anchor':'top','text-allow-overlap':false,'text-max-width':12},paint:{'text-color':['match',['get','k'],'prim','#B8FFCB','copy','#AEB6C6','dest','#FFD27A','#D9C8FF'],'text-halo-color':'#000','text-halo-width':1.5}});
  map.addLayer({id:'zones',type:'circle',source:'zones',paint:{'circle-pitch-alignment':'map','circle-radius':['interpolate',['exponential',2],['zoom'],5,4,9,60,12,480],'circle-color':'#FF7A2E','circle-opacity':0.18,'circle-stroke-color':'#FF7A2E','circle-stroke-width':1.2,'circle-stroke-opacity':0.7}});
  map.addLayer({id:'chains',type:'line',source:'chains',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':['case',['get','s'],2.6,1.4],'line-dasharray':[2,1.6],'line-opacity':['get','o']}});
  map.addLayer({id:'lsites',type:'circle',source:'lsites',paint:{'circle-radius':['case',['get','est'],5,7],'circle-color':['case',['get','est'],'rgba(255,77,77,0.25)','#FF3B3B'],'circle-stroke-color':'#fff','circle-stroke-width':['case',['get','est'],1.2,2],'circle-pitch-alignment':'map'}});
  map.addLayer({id:'lsites-t',type:'symbol',source:'lsites',layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,1.25],'text-anchor':'top','text-allow-overlap':true},paint:{'text-color':'#FFB3B3','text-halo-color':'#0B0F17','text-halo-width':2}});
  map.addLayer({id:'trails',type:'line',source:'trails',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':3,'line-dasharray':[0.1,2.2],'line-opacity':['get','o']}});
  map.addLayer({id:'ticks-c',type:'circle',source:'ticks',paint:{'circle-radius':4,'circle-color':['get','c'],'circle-stroke-color':'#0B0F17','circle-stroke-width':2,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'ticks-t',type:'symbol',source:'ticks',layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,-1.1],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  map.addLayer({id:'preds',type:'line',source:'preds',layout:{'line-cap':'round'},paint:{'line-color':['get','c'],'line-width':2,'line-dasharray':[1.5,2],'line-opacity':0.9}});
  map.addLayer({id:'home',type:'symbol',source:'home',layout:{'icon-image':'home','icon-size':1,'icon-allow-overlap':true,'text-field':'Дім','text-font':['Noto Sans Bold'],'text-size':13,'text-offset':[0,1.7],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'tg-course',type:'symbol',source:'targets',filter:['all',['has','next'],['==',['get','active'],true],['any',['get','thr'],['==',['get','sk'],0],['>=',['zoom'],7]]],layout:{'text-field':['concat',['case',['>',['get','count'],1],['concat','×',['to-string',['get','count']],'  '],''],'→ ',['get','next']],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[3,7,3,7],'text-anchor':'top','text-offset':['interpolate',['linear'],['zoom'],2,['literal',[0,1.30]],5,['literal',[0,1.68]],7,['literal',[0,2.04]],9.5,['literal',[0,2.48]]],'icon-allow-overlap':false,'text-allow-overlap':false,'text-optional':false,'symbol-sort-key':['get','sk']},paint:{'text-color':'#fff'}});
  const TGS=['interpolate',['linear'],['zoom'],4,0.55,7,0.85,9,1.15,12,1.55];
  // голограма тривоги: об'єми над районами (червоні вищі), «дихають»
  const firstLbl=(map.getStyle().layers.find(l=>l.type==='symbol')||{}).id;
  map.addLayer({id:'holo',type:'fill-extrusion',source:'holo',paint:{'fill-extrusion-color':['match',['get','l'],2,'#FF2D3D','#FFB020'],'fill-extrusion-height':['match',['get','l'],2,12000,4500],'fill-extrusion-base':0,'fill-extrusion-opacity':0.26,'fill-extrusion-vertical-gradient':true}},firstLbl);
  // громади з тривогою — справжні межі громади (КАТОТТГ + OSM), а не коло
  if(!map.getSource('hp'))map.addSource('hp',{type:'geojson',data:HPDATA||EMPTY,attribution:'Межі громад: КАТОТТГ, © OpenStreetMap (ODbL)'});HPPREV={};lastRa='';
  map.addLayer({id:'hp-f',type:'fill',source:'hp',paint:{'fill-color':['match',['coalesce',['feature-state','l'],0],2,'#FF2D3D','#FFB020'],'fill-opacity':['match',['coalesce',['feature-state','l'],0],0,0,0.34]}},firstLbl);
  map.addLayer({id:'hp-l',type:'line',source:'hp',paint:{'line-color':['match',['coalesce',['feature-state','l'],0],2,'#FF7A84','#FFD27A'],'line-width':1.6,'line-opacity':['match',['coalesce',['feature-state','l'],0],0,0,0.95]}},firstLbl);
  map.addLayer({id:'hrom',type:'circle',source:'hrom',filter:['!=',['get','poly'],1],paint:{'circle-radius':['interpolate',['exponential',2],['zoom'],5,3,8,22,11,170],'circle-color':['match',['get','l'],2,'#FF2D3D','#FFB020'],'circle-opacity':0.32,'circle-stroke-color':['match',['get','l'],2,'#FF6B76','#FFD27A'],'circle-stroke-width':1.2,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'hrom-t',type:'symbol',source:'hrom',minzoom:8,layout:{'text-field':['concat','тривога: ',['get','n']],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,1.4]},paint:{'text-color':'#FFD0D4','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.4}});
  map.addLayer({id:'holo-top',type:'line',source:'holo',paint:{'line-color':['match',['get','l'],2,'#FF6B76','#FFD27A'],'line-width':1.2,'line-opacity':0.8}},firstLbl);
  map.addLayer({id:'ra-glow',type:'line',source:'ra',paint:{'line-color':'#FF3B4E','line-width':['interpolate',['linear'],['zoom'],5,2,9,5],'line-blur':['interpolate',['linear'],['zoom'],5,2,9,5],'line-opacity':['case',['==',LV,2],0.5,0]}});
  map.addLayer({id:'tg-hit',type:'circle',source:'targets',filter:['==',['get','active'],true],paint:{'circle-radius':22,'circle-opacity':0,'circle-stroke-opacity':0}});
  try{if(window.FxLayer&&!map.getLayer('fx'))map.addLayer(window.FxLayer);}catch(e){console.warn('fx',e);}
  map.addLayer({id:'tg-n',type:'symbol',source:'targets',filter:['all',['>',['get','count'],1],['!',['has','next']]],layout:{'text-field':['concat','×',['to-string',['get','count']]],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[2,6,2,6],'text-anchor':'top','text-offset':['interpolate',['linear'],['zoom'],2,['literal',[0,1.30]],5,['literal',[0,1.68]],7,['literal',[0,2.04]],9.5,['literal',[0,2.48]]],'text-allow-overlap':true,'icon-allow-overlap':true},paint:{'text-color':'#fff'}});
  if(map.getLayer('tg-course'))map.moveLayer('tg-course');
  map.on('click','tg-hit',e=>{const f=e.features[0];openSheet(f.properties.id);});
  map.on('mouseenter','tg-hit',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','tg-hit',()=>map.getCanvas().style.cursor='');
  lastLv='';lastRa='';syncHome();
  if(tilt)set3d(true,'keep');
  if(!map._scaleAdded){map.addControl(new maplibregl.ScaleControl({unit:'metric',maxWidth:110}),'bottom-left');map._scaleAdded=true;}
}
map.on('style.load',addOverlays);
// кінематографічне інтро: з космосу — на Україну вночі, поки збираються дані
let introDone=false;function introFly(skip){if(introDone)return;introDone=true;sessionStorage.setItem('intro','1');const el=$('#intro');
  const cam={center:home||[32.2,48.4],zoom:home?7.6:5.6,pitch:52,bearing:-14};
  if(skip||!INTRO){if(el)el.remove();if(INTRO)map.jumpTo(cam);return;}
  setTimeout(()=>el&&el.classList.add('out'),1900);setTimeout(()=>el&&el.remove(),3200);
  map.flyTo({...cam,duration:5600,curve:1.65,essential:true});window.__introAt=Date.now();tilt=true;}
map.once('idle',()=>setTimeout(()=>introFly(false),INTRO?700:0));
setTimeout(()=>introFly(false),6000);
{const el=$('#intro');if(el){if(!INTRO)el.remove();else el.onclick=()=>introFly(true);}}map.on('styledata',()=>{if(map.isStyleLoaded()&&!map.getSource('obl'))addOverlays();if(map.getSource('obl')&&!lastLv)syncLevels();});
map.on('click',e=>{if(!setHomeMode)return;const f=map.queryRenderedFeatures(e.point,{layers:['tg-hit']});if(f.length)return;home=[e.lngLat.lng,e.lngLat.lat];localStorage.setItem('home',JSON.stringify(home));setHomeMode=false;$('#b-home').classList.remove('on');syncHome();toast('Дім збережено');});
fetch('/api/config').then(r=>r.json()).then(c=>{CFG={...CFG,...c};}).catch(()=>{}).finally(()=>setBase(base==='__init'?'night':base));

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
function posAt(tr,serverT){
  if(tr.status!=='active')return {p:[tr.lon,tr.lat],hd:tr.hd};
  let km=tr.speed*Math.max(0,serverT-tr.ts)/3600;
  const SHOW={shahed:25,molniya:20,jet:6,cruise:2,ballistic:1}[tr.type]??25;// хв: ціль рухається курсом, доки не прийде нове повідомлення (зона «де може бути» росте)
  const cap=Math.max(0,tr.speed*SHOW/60-tr.speed*Math.max(0,tr.ts-tr.last)/3600);
  if(!tr.route.length)km=Math.min(km,cap);
  const pts=[xy([tr.lon,tr.lat]),...tr.route.map(xy)];
  if(pts.length===1){if(tr.hd==null)return {p:[tr.lon,tr.lat],hd:tr.hd};const r=tr.hd*D2R;return {p:ll([pts[0][0]+Math.sin(r)*km,pts[0][1]+Math.cos(r)*km]),hd:tr.hd};}
  let acc=0;for(let i=1;i<pts.length;i++){const d=dist(pts[i-1],pts[i]);if(acc+d>=km){const f=(km-acc)/(d||1);const q=[pts[i-1][0]+(pts[i][0]-pts[i-1][0])*f,pts[i-1][1]+(pts[i][1]-pts[i-1][1])*f];return {p:ll(q),hd:brg(pts[i-1],pts[i])};}acc+=d;}
  // пункт пройдено — далі тим самим курсом
  const n=pts.length,h=brg(pts[n-2],pts[n-1]),r=h*D2R,ex=Math.min(km-acc,cap);
  return {p:ll([pts[n-1][0]+Math.sin(r)*ex,pts[n-1][1]+Math.cos(r)*ex]),hd:h};
}
function homeRel(tr,p){
  if(!home)return null;const H=xy(home),P=xy(p);const d=dist(H,P);
  let rel=null,eta=null;
  const path=[P,...tr.route.map(xy)];
  let acc=0,best={d:1e9,c:0};for(let i=1;i<path.length;i++){const a=path[i-1],b=path[i];const vx=b[0]-a[0],vy=b[1]-a[1],L2=vx*vx+vy*vy;let t=L2?((H[0]-a[0])*vx+(H[1]-a[1])*vy)/L2:0;t=Math.max(0,Math.min(1,t));const q=[a[0]+vx*t,a[1]+vy*t];const dd=dist(H,q);if(dd<best.d)best={d:dd,c:acc+Math.sqrt(L2)*t};acc+=Math.sqrt(L2);}
  if(best.d<8){rel='route';eta=best.c/tr.speed*60;}
  else if(tr.hd!=null&&angd(tr.hd,brg(P,H))<20){rel='heading';eta=d/tr.speed*60;}
  if(rel&&(d>150||eta>45)){rel=null;eta=null;}
  return {d,rel,eta,from:FROM[Math.round((brg(H,P))/45)%8]};
}

/* ---------- кадр ---------- */
let lastLv='',lastFrame=performance.now();
function frame(now){
  const dt=Math.min(0.2,(now-lastFrame)/1000);
  if(SNAP&&map.getSource('targets')){lastFrame=now;const slow=now-(frame.sd||0)>500;if(slow)frame.sd=now;const fx=[];
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
      feats.push({type:'Feature',properties:{id:tr.id,type:tr.type,hd:d.hd,sa,unk,active,weak,thr:!!(rel&&rel.rel),c:TYPE_COLOR[tr.type],count:tr.count||1,next:tr.next||undefined,sk:active?(sel===tr.id?0:1):2},geometry:{type:'Point',coordinates:d.p}});
      if(active){const tail=[d.p];let P=xy(d.p),left=Math.max(14,TYPES_KMH(tr.type)*0.09);
        for(const q of tr.trail.slice().reverse()){const Q=xy([q[0],q[1]]),dd=dist(P,Q);if(dd<0.5)continue;if(dd>=left){const f=left/dd;tail.push(ll([P[0]+(Q[0]-P[0])*f,P[1]+(Q[1]-P[1])*f]));left=0;break;}tail.push([q[0],q[1]]);left-=dd;P=Q;}
        if(left>0&&tr.hd!=null){const r=(d.hd+180)*D2R;tail.push(ll([P[0]+Math.sin(r)*left,P[1]+Math.cos(r)*left]));}
        // краплі хвоста рівномірно вздовж шляху (від цілі назад)
        const dots=[];if(tail.length>1){const X=tail.map(xy);let seg=0,acc=0;const tot=X.slice(1).reduce((s,q,i)=>s+dist(X[i],q),0),step=tot/14;
          for(let k=1;k<=14;k++){let want=k*step;while(seg<X.length-1&&acc+dist(X[seg],X[seg+1])<want){acc+=dist(X[seg],X[seg+1]);seg++;}if(seg>=X.length-1)break;const a=X[seg],b=X[seg+1],f=(want-acc)/(dist(a,b)||1);dots.push(ll([a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f]));}}
        const n=parseInt(TYPE_COLOR[tr.type].slice(1),16);
        fx.push({id:tr.id,age:((tr.ev&&tr.ev.age)||0)+Math.max(0,serverT-SNAP.now),spd:tr.speed,p:d.p,sa,hd:d.hd,type:tr.type,col:[(n>>16&255)/255,(n>>8&255)/255,(n&255)/255],weak,thr:!!(rel&&rel.rel),sel:sel===tr.id,tail:dots});}
      const c=TYPE_COLOR[tr.type];
      if(false)trails.push({type:'Feature',properties:{c,o:0.95},geometry:{type:'LineString',coordinates:[...tr.trail.slice(-3).map(t=>[t[0],t[1]]),d.p]}});
      if(active&&(sel===tr.id||(rel&&rel.rel))&&tr.route.length)preds.push({type:'Feature',properties:{c},geometry:{type:'LineString',coordinates:[d.p,...tr.route]}});
    }
    // каша геть: показуємо лише активні цілі; цілі одного типу, що на екрані лягають одна на одну, — один значок ×N
    const shown=[];for(const f of feats.filter(f=>f.properties.active).sort((a,b)=>(b.properties.weak?0:1)-(a.properties.weak?0:1))){
      const P=map.project(f.geometry.coordinates);const near=shown.find(g=>g.properties.type===f.properties.type&&Math.hypot(g._p.x-P.x,g._p.y-P.y)<34);
      if(near&&f.properties.id!==sel){near.properties.count+=f.properties.count;near.properties.merged=(near.properties.merged||1)+1;continue;}
      f._p=P;shown.push(f);}
    feats.length=0;feats.push(...shown);
    const vis=new Set(shown.map(f=>f.properties.id));window.FX=fx.filter(f=>vis.has(f.id));
    {const top=threats.slice().sort((a,b)=>(a.rel.eta??999)-(b.rel.eta??999))[0];for(const f of window.FX)f.thr=!!(top&&f.id===top.tr.id);}
    window.FXHOME=home?{p:home,state:$('#me').classList.contains('danger')?'danger':$('#me').classList.contains('watch')?'watch':'calm'}:null;
    if(slow)window.FXBEACONS=PREFL().launch?(SNAP.launches||[]).filter(L=>serverT-L.t<3*3600).map(L=>({p:[L.lon,L.lat]})):[];
    if(slow)map.getSource('targets').setData({type:'FeatureCollection',features:feats});
    if(false){const thr=new Set(threats.map(x=>x.tr.id)),z=map.getZoom(),sz=Math.max(18,Math.min(70,10+z*5));
     window.GLOW=feats.map(f=>{const h=TYPE_COLOR[f.properties.type]||'#ffffff',n=parseInt(h.slice(1),16);const t=thr.has(f.properties.id);
       return {p:f.geometry.coordinates,c:t?[1,0.23,0.27]:[(n>>16&255)/255,(n>>8&255)/255,(n&255)/255],a:f.properties.weak?0.3:0.7,s:t?sz*1.9:sz,ring:t};});}
    if(slow&&map.getSource('chains')){frame.ch=now;const ch=[],ls=new Map();
      for(const L of (SNAP.launches||[]))ls.set(L.site,{type:'Feature',properties:{est:false,l:'ПУСК по Україні: '+(L.type?({shahed:'Шахеди',jet:'Реактивні БпЛА',molniya:'«Молнії»',cruise:'Крилаті ракети',ballistic:'Балістика',kab:'КАБи'})[L.type]||'':'')+(L.count?' ×'+L.count:'')+'\nз '+L.site.replace(/ \(.*\)/,'')+(L.carrier?' ('+L.carrier+')':'')+' · '+fmt(L.t)},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});
      for(const tr of SNAP.tracks){const L=tr.launch;if(!L||tr.status==='closed')continue;const isSel=sel===tr.id,d=DISP.get(tr.id);if(!d)continue;
        if(L.est&&!isSel)continue;
        ch.push({type:'Feature',properties:{c:L.est?'#FF8A8A':'#FF3B3B',o:isSel?0.95:(L.est?0.3:0.38),s:isSel},geometry:{type:'LineString',coordinates:[[L.lon,L.lat],[tr.entry[0],tr.entry[1]],...tr.trail.map(t=>[t[0],t[1]]),d.p]}});
        if(!ls.has(L.site))ls.set(L.site,{type:'Feature',properties:{est:true,l:'ймовірно · '+L.site.replace(/ \(.*\)/,'')},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});}
      map.getSource('chains').setData({type:'FeatureCollection',features:ch});map.getSource('lsites').setData({type:'FeatureCollection',features:[...ls.values()]});}
    T3D.heads=feats.map(f=>({id:f.properties.id,type:f.properties.type,hd:f.properties.hd,active:f.properties.active,weak:f.properties.weak,p:f.geometry.coordinates}));
    if(slow){map.getSource('trails').setData({type:'FeatureCollection',features:trails});
    map.getSource('preds').setData({type:'FeatureCollection',features:preds});}
    if(slow&&map.getSource('sel')){const d=sel&&DISP.get(sel);const tr=sel&&SNAP.tracks.find(t=>t.id===sel);map.getSource('sel').setData(d&&tr?{type:'FeatureCollection',features:[{type:'Feature',properties:{c:TYPE_COLOR[tr.type]},geometry:{type:'Point',coordinates:d.p}}]}:EMPTY);}
    if(follow&&sel){const d=DISP.get(sel);if(d)map.easeTo({center:d.p,duration:0});}
    if(slow)renderBanner(threats);
    if(map.getSource('ticks')&&now-(frame.tk||0)>800){frame.tk=now;const tk=[];const serverT=Date.now()/1000+offset;
      for(const tr of SNAP.tracks){if(tr.status!=='active'||sel!==tr.id)continue;const c=TYPE_COLOR[tr.type];
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
function syncRaions(){
  if(!SNAP||!RA||!map.getSource('ra'))return;const lv={};const up=(i,v)=>{if(i>=0&&(lv[i]||0)<v)lv[i]=v;};
  const O=SNAP.official||{};const rl=O.raion_levels||{};RA.forEach(r=>{if(rl[r.n])up(r.i,rl[r.n]);});
  if(map.getSource('hrom'))map.getSource('hrom').setData({type:'FeatureCollection',features:(O.points||[]).map(([lo,la,n,l,poly])=>({type:'Feature',properties:{l,n,poly:poly||0},geometry:{type:'Point',coordinates:[lo,la]}}))});
  syncHromadas(O.hromadas||{});
  // райони фарбуються лише за офіційними тривогами (alerts.in.ua)
  const key=JSON.stringify(lv);if(key===lastRa)return;lastRa=key;
  RA.forEach(r=>{try{map.setFeatureState({source:'ra',id:r.i},{lvl:lv[r.i]||0});}catch(e){lastRa='';}});
  syncHolo(lv);
}
setInterval(syncRaions,3000);
let OBLF=null;fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>{OBLF=j.features;lastRa='';});
function syncHolo(lv){if(!map.getSource('holo')||!RA)return;const F=[];
  RA.forEach(r=>{const l=lv[r.i];if(l)F.push({type:'Feature',properties:{l},geometry:r.polys.length===1?{type:'Polygon',coordinates:r.polys[0]}:{type:'MultiPolygon',coordinates:r.polys}});});
  const L=(SNAP&&SNAP.levels)||{};if(OBLF)OBLF.forEach(f=>{const l=L[f.properties.n];if(l)F.push({type:'Feature',properties:{l},geometry:f.geometry});});
  map.getSource('holo').setData({type:'FeatureCollection',features:F});}
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
  const box=$('#me');if(!home){box.className='me';$('#me-word').textContent='Що летить до мене?';$('#me-sub').innerHTML='Покажу, що летить саме до вас і скільки хвилин є до укриття.<button class="cta" id="me-cta">Визначити моє місце</button>';const cta=$('#me-cta');if(cta)cta.onclick=()=>$('#b-locate').click();$('#me-list').innerHTML='';return;}
  const isStale=!SNAP||(Date.now()-recvAt)/1000>20;
  const near=SNAP.tracks.filter(t=>t.status==='active'&&t.conf>=0.5).map(t=>{const d=DISP.get(t.id);return d?{tr:t,r:homeRel(t,d.p)}:null;}).filter(x=>x&&x.r&&x.r.d<120).sort((a,b)=>(a.r.eta??999)-(b.r.eta??999)||a.r.d-b.r.d);
  const thr=near.filter(x=>x.r.rel);const first=thr[0];
  let cls='me',word='Над вами чисто',sub='Підтверджених цілей у бік дому немає. Найближча: '+(near[0]?Math.round(near[0].r.d)+' км '+near[0].r.from:'далі 120 км')+'.';
  if(isStale){cls='me watch';word='Невідомо';sub='Немає звʼязку з джерелами. Це <b>не відбій</b>.';}
  else if(first){const m=Math.max(0,(first.r.eta||0)-SHELTER);cls=m<=3?'me danger':'me watch';word=m<=0?'В укриття зараз':m<=3?'Виходь в укриття':'Увага';
    sub=(m<=0?'Ціль прибуде раніше, ніж ви дійдете до укриття. Правило двох стін.':'Маєте <b>~'+Math.floor(m)+' хв</b>, щоб зібратися, потім '+SHELTER+' хв до укриття.');}
  box.className=cls;$('#me-word').textContent=word;
  // ГОЛОВНЕ: скільки хвилин саме у вас — великим числом з кільцем
  if(first&&!isStale&&first.r.eta!=null){const eta=Math.max(1,Math.round(first.r.eta)),k=Math.max(0.04,Math.min(1,eta/30));const C=2*Math.PI*44;
    sub='<div class="big"><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" class="trk"/><circle cx="50" cy="50" r="44" class="arc" style="stroke-dasharray:'+(C*k)+' '+C+'"/></svg><b>'+eta+'</b><i>хв</i></div>'+
      '<div class="big-t"><b>'+esc(TYPE_NAME[first.tr.type])+(first.tr.count>1?' ×'+first.tr.count:'')+'</b> над вашим домом приблизно через '+eta+' хв<br><span>'+Math.round(first.r.d)+' км '+first.r.from+(first.tr.next?' · курс → '+esc(first.tr.next):'')+'</span></div>'+
      '<p class="big-a">'+(eta-SHELTER<=0?'Ідіть в укриття зараз. Якщо не встигаєте — правило двох стін.':'Маєте ~'+Math.floor(eta-SHELTER)+' хв, щоб зібратися; '+SHELTER+' хв — дорога до укриття.')+'</p>';}
  $('#me-sub').innerHTML=sub;
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
  if(!renderBanner.seen.has(t.tr.id)){renderBanner.seen.add(t.tr.id);window.__beep&&window.__beep();
    note({k:'home:'+t.tr.id,lvl:'red',ic:'⚠️',title:TYPE_NAME[t.tr.type]+(t.tr.count>1?' ×'+t.tr.count:'')+' — '+(t.rel.rel==='route'?'маршрут біля вашого дому':'курс на ваш район'),sub:Math.round(t.rel.d)+' км '+t.rel.from+(t.rel.eta!=null?' · ~'+Math.max(1,Math.round(t.rel.eta))+' хв':''),go:()=>openSheet(t.tr.id)});const d=DISP.get(t.tr.id);
    if(d&&home&&introDone&&Date.now()-(window.__introAt||0)>9000&&Date.now()-(window.__touch||0)>20000){const b2=new maplibregl.LngLatBounds(home,home).extend(d.p);
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
  // «Чому я це показую»: першоджерело, копії, суперечності, давність, що змінило відображення
  {const E=tr.ev||{items:[],prim:[],pubs:0,contra:[],age:0};const nm=k=>esc(SNAP.sources[k]?.name||k);const ind=E.prim.length;
   const head=E.pubs+' '+(E.pubs===1?'публікація':E.pubs<5?'публікації':'публікацій')+' · '+ind+' '+(ind===1?'першоджерело':ind<5?'першоджерела':'першоджерел')+' · '+(ind>=2?'<b class=ok>незалежне підтвердження є</b>':'<b class=warn>незалежного підтвердження немає</b>');
   const age=E.age;const ageTxt=age<120?'щойно':age<3600?Math.round(age/60)+' хв тому':'понад годину тому';
   let h='<h4>Чому я це показую</h4><p class=ev-head>'+head+'</p><p class=ev-age>Остання фіксація місця: '+ageTxt+(age>300?' — позиція далі лише оцінка, зона невизначеності росте':'')+'</p>';
   if(E.contra.length)h+='<div class=ev-contra><b>Версії розходяться:</b>'+E.contra.map(v=>'<div>→ '+esc(v.dest||'?')+' <small>('+v.srcs.map(nm).join(', ')+')</small></div>').join('')+'</div>';
   h+='<ol class=ev-list>'+E.items.slice().sort((a,b)=>b.t-a.t).map(it=>{const tag=it.copy?(it.copy===it.src?'<i class=cp>повтор</i>':'<i class=cp>копія '+nm(it.copy)+'</i>'):(it.why==='нова ціль'?'<i class=nw>першоджерело</i>':it.why==='змінило позицію'?'<i class=mv>змінило позицію</i>':it.why==='змінило курс'?'<i class=cr>змінило курс</i>':'<i class=cf>підтвердження</i>');
     return '<li class="'+(it.copy?'copy':'')+'"><div class=ev-m><span>'+fmt(it.t)+'</span><b>'+nm(it.src)+'</b>'+tag+(it.link?'<a href="'+esc(it.link)+'" target=_blank rel=noopener>пост ↗</a>':'')+'</div>'+(it.text?'<q>'+esc(it.text)+'</q>':'')+'</li>';}).join('')+'</ol>';
   $('#sh-proof').innerHTML=h;}
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
$('#b-layers').onclick=()=>{const nx={night:'sat',sat:'map',map:'night'}[base]||'night';try{const p=JSON.parse(localStorage.getItem('pref')||'{}');p.base=nx;localStorage.setItem('pref',JSON.stringify(p));}catch(e){}setBase(nx);toast({night:'Ніч',sat:'Супутник',map:'Карта'}[nx]);};
function flat3d(on){// значок завжди «дивиться» на екран (як у 2D) — без перспективних спотворень; у 3D лише коротша тінь
  if(map.getLayer('tg-sh')){map.setPaintProperty('tg-sh','icon-translate',on?[8,12]:[14,22]);map.setPaintProperty('tg-sh','icon-opacity',on?0.6:0.9);}}
function set3d(on,anim){tilt=on;flat3d(on);localStorage.setItem('t3d',on?'1':'0');$('#b-3d').classList.toggle('on',on);if(anim!=='keep')map.easeTo({pitch:on?55:0,bearing:on?-14:0,duration:anim?700:0});}
$('#b-3d').onclick=()=>set3d(!tilt,true);
$('#b-daily').onclick=()=>{location.href='/daily.html';};
$('#b-feed').onclick=()=>{$('#drawer').hidden=false;renderFeed();};
$('#dr-close').onclick=()=>$('#drawer').hidden=true;

/* ---------- живий потік ---------- */
function onSnap(s){LIVE=s;if(REPLAY)return;SNAP=s;try{notesCheck(s);}catch(e){console.warn(e);}recvAt=Date.now();offset=s.now-Date.now()/1000;renderCounters();renderAsOf();syncLevels();syncZones();syncRaions();renderForecast();if(!$('#drawer').hidden)renderFeed();}
let LIVE=null,REPLAY=null;
/* ---------- прогноз ---------- */
function renderForecast(){const el=$('#fc');if(!el)return;if(!SNAP||!SNAP.forecast||!SNAP.forecast.oblasts){el.innerHTML='';return;}const O=SNAP.forecast.oblasts;
  let mine=null;if(home&&window.OBLPOLY){mine=window.OBLPOLY(home[0],home[1]);}
  const rows=Object.entries(O).filter(([n,v])=>v.p60>=0.1).slice(0,4);if(mine&&O[mine]&&!rows.some(r=>r[0]===mine))rows.unshift([mine,O[mine]]);
  if(!rows.length){el.innerHTML=SNAP.tracks.some(t=>t.status==='active')?'':'<h4>Прогноз на годину</h4><p class="fc-calm">Нових загроз на найближчу годину не видно</p>';return;}
  el.innerHTML='<h4>Прогноз на годину <small>за курсами цілей і пусками</small></h4>'+rows.map(([n,v])=>{const p=Math.round(v.p60*100);const lv=p>=60?'hi':p>=30?'mid':'lo';
    return '<div class="fc-row'+(n===mine?' mine':'')+'"><span>'+esc(n)+(n===mine?' · ви тут':'')+'</span><i class="'+lv+'" style="width:'+Math.max(4,p)+'%"></i><b>'+p+'%</b></div>';}).join('');}
fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>{const P=j.features.map(f=>({n:f.properties.n,polys:f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates}));
  window.OBLPOLY=(lo,la)=>{for(const o of P)for(const pl of o.polys)if(inRing(pl[0],lo,la))return o.n;return null;};});
/* ---------- машина часу ---------- */
let HISTF=[],tbTimer=null;
$('#b-time').onclick=()=>{fetch('/api/history').then(r=>r.json()).then(j=>{HISTF=j.frames||[];if(!HISTF.length)return toast('Історія ще збирається — кадр щохвилини');
  $('#timebar').hidden=false;const r=$('#tb-range');r.max=HISTF.length-1;r.value=0;showFrame(0);play(true);});};
function showFrame(i){const f=HISTF[i];if(!f)return;$('#tb-range').value=i;$('#tb-time').textContent=new Date(f.t*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  REPLAY=f;SNAP=Object.assign({},LIVE||{},{now:f.t,levels:f.levels,official:Object.assign({},(LIVE&&LIVE.official)||{},{raion_levels:f.raions,points:[]}),
    tracks:f.tracks.map(t=>Object.assign({status:'active',speed:0,route:[],trail:[],route_names:[],srcs:(t.ev&&t.ev.prim)||[],links:[],first:f.t,last:f.t,ts:f.t,entry:[t.lon,t.lat,'',f.t],ev:{pubs:0,prim:[],items:[],contra:[],age:0}},t)),launches:[],zones:[],ru:[]});
  $('#tb-time').title='Що було відомо на цей момент';if(XRAY)syncXray();
  offset=f.t-Date.now()/1000;recvAt=Date.now();DISP.clear();renderCounters();syncLevels();syncRaions();}
function play(on){clearInterval(tbTimer);$('#tb-play').textContent=on?'❚❚':'▶';if(!on)return;tbTimer=setInterval(()=>{const r=$('#tb-range');const i=+r.value+1;if(i>=HISTF.length){play(false);return;}showFrame(i);},140);}
$('#tb-play').onclick=()=>play(!tbTimer||$('#tb-play').textContent==='▶');
$('#tb-range').oninput=e=>{play(false);showFrame(+e.target.value);};
$('#tb-live').onclick=()=>{play(false);REPLAY=null;$('#timebar').hidden=true;DISP.clear();lastLv='';lastRa='';if(LIVE)onSnap(LIVE);};
/* ---------- телефон: панель стану згорнута, тап — розгорнути ---------- */
$('#me').addEventListener('click',e=>{if(innerWidth>640||e.target.closest('li,button'))return;$('#me').classList.toggle('open');});
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
function setXray(on){XRAY=on;document.body.classList.toggle('xray',on);$('#b-xray').classList.toggle('on',on);$('#xr-legend').hidden=!on;
  for(const id of ['xr-dim','xr-edge','xr-edge2','xr-node','xr-t'])if(map.getLayer(id))map.setLayoutProperty(id,'visibility',on?'visible':'none');
  for(const id of ['holo','holo-top','ra-glow'])if(map.getLayer(id))map.setLayoutProperty(id,'visibility',on?'none':'visible');
  syncXray();toast(on?'Рентген неба: повідомлення → підтвердження → припущення':'Звичайна карта');}
$('#b-xray').onclick=()=>setXray(!XRAY);
map.on('styledata',()=>{if(XRAY&&map.getLayer('xr-dim')&&map.getLayoutProperty('xr-dim','visibility')!=='visible')setXray(true);});
function syncXray(){if(!XRAY||!SNAP||!map.getSource('xr'))return;const F=[],nm=k=>SNAP.sources[k]?.name||k;
  for(const tr of SNAP.tracks){if(tr.status!=='active'||!tr.ev)continue;if(sel&&tr.id!==sel&&SNAP.tracks.length>12)continue;
    const d=DISP.get(tr.id);const items=tr.ev.items.filter(i=>i.p);let lastReal=null,prevPrim=null;const primAt={};
    items.forEach((it,ix)=>{let p=it.p;if(it.copy&&primAt[it.copy]){const a=ix*1.3;p=[primAt[it.copy][0]+Math.cos(a)*0.035,primAt[it.copy][1]+Math.sin(a)*0.024];
        F.push({type:'Feature',properties:{k:'copy'},geometry:{type:'LineString',coordinates:[primAt[it.copy],p]}});}
      const k=it.copy?'copy':(it.pt==='dest'?'dest':(it.pt==='est'?'est':'prim'));
      F.push({type:'Feature',properties:{k:it.copy?'copy':k==='dest'?'dest':k==='est'?'est':'prim',l:nm(it.src)+' · '+fmt(it.t)+(it.copy?' (копія)':k==='dest'?' → '+(it.dest||''):'')},geometry:{type:'Point',coordinates:p}});
      if(!it.copy){if(prevPrim&&(prevPrim[0]!==p[0]||prevPrim[1]!==p[1]))F.push({type:'Feature',properties:{k:'confirm'},geometry:{type:'LineString',coordinates:[prevPrim,p]}});prevPrim=p;primAt[it.src]=primAt[it.src]||p;if(k==='prim')lastReal=p;}});
    if(d){F.push({type:'Feature',properties:{k:'now',l:'зараз (оцінка)'},geometry:{type:'Point',coordinates:d.p}});
      const from=lastReal||prevPrim;if(from)F.push({type:'Feature',properties:{k:'assume'},geometry:{type:'LineString',coordinates:[from,d.p]}});
      if(tr.route&&tr.route.length)F.push({type:'Feature',properties:{k:'assume'},geometry:{type:'LineString',coordinates:[d.p,...tr.route.slice(0,3)]}});
      for(const v of (tr.ev.contra||[])){const r=v.b*D2R,P=xy(d.p);F.push({type:'Feature',properties:{k:'contra'},geometry:{type:'LineString',coordinates:[d.p,ll([P[0]+Math.sin(r)*25,P[1]+Math.cos(r)*25])]}});}}}
  map.getSource('xr').setData({type:'FeatureCollection',features:F});}
setInterval(syncXray,1000);
/* ---------- небо в камері ---------- */
$('#b-ar').onclick=()=>{location.href='ar.html';};
let ws,backoff=1000;
function connect(){
  const proto=location.protocol==='https:'?'wss':'ws';ws=new WebSocket(proto+'://'+location.host+'/ws');
  ws.onmessage=e=>{backoff=1000;onSnap(JSON.parse(e.data));};
  ws.onclose=()=>{setTimeout(connect,backoff);backoff=Math.min(backoff*2,15000);};
  ws.onerror=()=>ws.close();
}
connect();
setInterval(()=>{if(ws&&ws.readyState===1)ws.send('ping');},20000);

/* ---------- налаштування, теми, шари ---------- */
const PREF=Object.assign({theme:'auto',base:null,sound:false,ru:true,launch:true,zones:true},(()=>{try{return JSON.parse(localStorage.getItem('pref')||'{}');}catch(e){return {};}})());
const savePref=()=>{try{localStorage.setItem('pref',JSON.stringify(PREF));}catch(e){}};
function sunNight(){const p=home||[31.5,49];const d=new Date();const doy=Math.floor((d-new Date(d.getFullYear(),0,0))/864e5);
  const decl=23.44*Math.sin(2*Math.PI*(284+doy)/365)*D2R,lat=p[1]*D2R;const h0=Math.acos(Math.max(-1,Math.min(1,(Math.sin(-0.83*D2R)-Math.sin(lat)*Math.sin(decl))/(Math.cos(lat)*Math.cos(decl)))))/D2R;
  const noonUTC=12-p[0]/15;const rise=noonUTC-h0/15,set=noonUTC+h0/15;const u=d.getUTCHours()+d.getUTCMinutes()/60;return !(u>rise&&u<set);}
function effTheme(){return PREF.theme==='auto'?(sunNight()?'night':'day'):PREF.theme;}
function applyTheme(force){const th=effTheme();document.documentElement.dataset.theme=th;window.FXDAY=th==='day';
  const want=PREF.base||(th==='night'?'night':'map');if(force||want!==base)setBase(want);
  $('#st-theme-note').textContent=PREF.theme==='auto'?('Зараз: '+(th==='night'?'ніч':'день')+' — перемикається само за сходом і заходом сонця над вашим домом.'):'';syncSettingsUI();}
function syncSettingsUI(){document.querySelectorAll('.seg[data-pref]').forEach(g=>{const k=g.dataset.pref;const v=k==='base'?base:k==='shelter'?String(SHELTER):PREF[k];g.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v===String(v)));});
  $('#st-3d').checked=tilt;$('#st-sound').checked=!!PREF.sound;$('#st-sys').checked=!!PREF.sys&&'Notification' in window&&Notification.permission==='granted';$('#st-ru').checked=!!PREF.ru;$('#st-launch').checked=!!PREF.launch;$('#st-zones').checked=!!PREF.zones;}
function applyLayers(){const vis=(ids,on)=>ids.forEach(i=>{if(map.getLayer(i))map.setLayoutProperty(i,'visibility',on?'visible':'none');});
  vis(['ru-glow','ru-dot','ru-t','hits'],PREF.ru);vis(['chains','lsites','lsites-t'],PREF.launch);vis(['zones'],PREF.zones);}
map.on('styledata',()=>{if(map.getLayer('ru-glow'))applyLayers();});
function syncRu(){if(!SNAP||!map.getSource('ru'))return;
  // останнє зведення МО РФ: на карті — лише точки регіонів (з кількістю, якщо названа) і ОДИН підсумковий підпис
  const ev=(SNAP.ru||[]).slice().sort((a,b)=>b.t-a.t)[0];if(!ev){map.getSource('ru').setData(EMPTY);return;}
  const PER=p=>!p?'':/ноч/.test(p)?'за ніч':/дня/.test(p)?'за день':/суток/.test(p)?'за добу':'';
  const F=ev.regions.map(r=>({type:'Feature',properties:{c:r.cnt?Math.min(12,r.cnt/3):3,l:r.cnt?'×'+r.cnt:''},geometry:{type:'Point',coordinates:[r.lon,r.lat]}}));
  const lo=ev.regions.reduce((s,r)=>s+r.lon,0)/ev.regions.length,la=ev.regions.reduce((s,r)=>s+r.lat,0)/ev.regions.length;
  F.push({type:'Feature',properties:{c:0,sum:true,l:'Наші дрони над РФ '+PER(ev.period)+': '+ev.total+' «збитих» за МО РФ · '+ev.regions.length+' рег. · '+fmt(ev.t)},geometry:{type:'Point',coordinates:[lo+1.5,la+0.6]}});
  map.getSource('ru').setData({type:'FeatureCollection',features:F});}
setInterval(syncRu,5000);
function syncHits(){if(!SNAP||!map.getSource('hits'))return;const seen=new Map();
  for(const h of (SNAP.hits||[]).slice().sort((a,b)=>b.t-a.t)){const k=h.place+'|'+h.what;if(!seen.has(k))seen.set(k,h);}
  map.getSource('hits').setData({type:'FeatureCollection',features:[...seen.values()].map(h=>({type:'Feature',properties:{l:'Уражено: '+h.what+'\n'+h.place+' · '+new Date(h.t*1000).toLocaleDateString('uk-UA',{day:'2-digit',month:'2-digit'}),link:h.link},geometry:{type:'Point',coordinates:[h.lon,h.lat]}}))});}
setInterval(syncHits,10000);
$('#b-set').onclick=()=>{$('#settings').hidden=false;syncSettingsUI();loadLan();
  const h=SNAP&&SNAP.health||{},c=h.channels||{};$('#st-tech').textContent='Джерела: '+(c.channels||'—')+' Telegram-каналів моніторингу (наживо '+(c.live||0)+'), офіційні тривоги й фіксації цілей alerts.in.ua (Повітряні сили / War Monitor), заяви МО РФ — для шару «куди летіли наші дрони». Роботу ППО й влучання в Україні не показуємо.';};
$('#st-close').onclick=()=>$('#settings').hidden=true;
$('#st-widget').onclick=()=>window.__openWidget&&window.__openWidget();
document.querySelectorAll('.seg[data-pref]').forEach(g=>g.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const k=g.dataset.pref,v=b.dataset.v;
  if(k==='theme'){PREF.theme=v;PREF.base=null;savePref();applyTheme(true);}
  else if(k==='base'){PREF.base=v;savePref();setBase(v);setTimeout(syncSettingsUI,50);}
  else if(k==='shelter'){SHELTER=+v;localStorage.setItem('shelter',SHELTER);$('#me-sh').textContent=SHELTER;syncSettingsUI();}}));
$('#st-3d').onchange=e=>set3d(e.target.checked,true);
$('#st-sound').onchange=e=>{PREF.sound=e.target.checked;savePref();if(PREF.sound)beep();};
$('#st-sys').onchange=async e=>{if(e.target.checked&&'Notification' in window&&Notification.permission!=='granted'){const r=await Notification.requestPermission();if(r!=='granted'){e.target.checked=false;toast('Браузер не дозволив сповіщення');}}PREF.sys=e.target.checked;savePref();};
$('#st-ru').onchange=e=>{PREF.ru=e.target.checked;savePref();applyLayers();};
$('#st-launch').onchange=e=>{PREF.launch=e.target.checked;savePref();applyLayers();};
$('#st-zones').onchange=e=>{PREF.zones=e.target.checked;savePref();applyLayers();};
$('#st-geo').onclick=()=>{$('#b-locate').click();};
$('#st-pick').onclick=()=>{$('#settings').hidden=true;setHomeMode=true;$('#b-home').classList.add('on');toast('Торкніться карти, щоб позначити дім');};
$('#st-clear').onclick=()=>{home=null;localStorage.removeItem('home');syncHome();toast('Дім прибрано');};
let lanDone=false;function loadLan(){fetch('/api/lan').then(r=>r.json()).then(j=>{lanDone=true;const urls=j.urls||[];const host=location.hostname;
  const sec=(j.secure||[]).sort((a,b)=>(/\/\/192\.168\./.test(b)-/\/\/192\.168\./.test(a)));const best=sec[0]||((host!=='localhost'&&host!=='127.0.0.1')?location.origin:(urls[0]||location.origin));
  $('#st-urls').innerHTML=[...sec,...(urls.length?urls:[location.origin])].map(u=>'<code>'+esc(u)+'</code>').join('');
  try{$('#st-qr').innerHTML='';new QRCode($('#st-qr'),{text:best,width:132,height:132,colorDark:'#0B0F17',colorLight:'#ffffff'});}catch(e){$('#st-qr').textContent=best;}}).catch(()=>{});}
let actx=null;function beep(){try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();const o=actx.createOscillator(),g=actx.createGain();o.type='sine';o.frequency.value=880;o.connect(g);g.connect(actx.destination);
  const t=actx.currentTime;g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(0.3,t+0.02);g.gain.exponentialRampToValueAtTime(0.0001,t+0.5);o.start(t);o.stop(t+0.55);
  const o2=actx.createOscillator();o2.frequency.value=660;o2.connect(g);o2.start(t+0.6);o2.stop(t+1.1);g.gain.setValueAtTime(0.3,t+0.6);g.gain.exponentialRampToValueAtTime(0.0001,t+1.1);}catch(e){}}
window.__beep=()=>{if(PREF.sound)beep();};
setInterval(()=>{if(PREF.theme==='auto'&&effTheme()!==document.documentElement.dataset.theme)applyTheme(true);},60000);
applyTheme(false);
fetch('/api/state').then(r=>r.json()).then(onSnap).catch(()=>{});

/* ---------- важливі сповіщення: з'являються на головному екрані й лишаються, доки їх не закрити ---------- */
const NOTE_CLR={red:'#FF4D57',orange:'#FF9F2E',green:'#2FE38A',blue:'#5AA2FF',violet:'#C77DFF'};
const NSEEN=new Set();let NBASE=false,NHOMELV=null;
function note(n){
  if(NSEEN.has(n.k))return;NSEEN.add(n.k);
  const box=$('#notes');if(!box)return;
  const el=document.createElement('div');el.className='note-c';el.style.setProperty('--nc',NOTE_CLR[n.lvl]||NOTE_CLR.orange);
  const tm=new Date((n.t||Date.now()/1000)*1000).toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  el.innerHTML='<span class="ni">'+(n.ic||'🔔')+'</span><div><b>'+esc(n.title)+'</b>'+(n.sub?'<small>'+esc(n.sub)+'</small>':'')+'</div><time>'+tm+'</time><button class="nx" aria-label="Закрити">✕</button>';
  const close=()=>{el.classList.add('out');setTimeout(()=>{el.remove();notesAll();},300);};
  el.querySelector('.nx').onclick=e=>{e.stopPropagation();close();};
  el.onclick=()=>{if(n.go)n.go();};
  box.insertBefore(el,box.querySelector('.note-c'));
  // на екрані щонайбільше 5 — найстаріші прибираються самі
  const cs=box.querySelectorAll('.note-c');for(let i=5;i<cs.length;i++)cs[i].remove();
  notesAll();
  if(n.lvl==='red'||n.lvl==='orange'){window.__beep&&window.__beep();if(navigator.vibrate)try{navigator.vibrate([120,60,120]);}catch(e){}}
  if(PREF.sys&&document.hidden&&'Notification' in window&&Notification.permission==='granted'){
    try{const sn=new Notification(n.title,{body:n.sub||'',tag:n.k,icon:'icons/icon.svg',renotify:false});sn.onclick=()=>{window.focus();n.go&&n.go();sn.close();};}catch(e){}}
}
function notesAll(){const box=$('#notes');let a=box.querySelector('.all');const n=box.querySelectorAll('.note-c').length;
  if(n>=2&&!a){a=document.createElement('button');a.className='all';a.textContent='Закрити всі';a.onclick=()=>{box.innerHTML='';};box.prepend(a);}
  if(n<2&&a)a.remove();}
function flyP(p,z){map.flyTo({center:p,zoom:Math.max(map.getZoom(),z||7),essential:true});}
const TNAME_PL={shahed:'Шахеди',jet:'Реактивні шахеди',molniya:'«Молнії»',cruise:'Крилаті ракети',ballistic:'Балістика',kab:'КАБи'};
function notesCheck(s){
  const first=!NBASE;NBASE=true;const now=s.now||Date.now()/1000;
  // 1) пуски
  for(const L of (s.launches||[])){const k='L:'+L.site+':'+Math.round((L.t||0)/60);if(first||now-(L.t||now)>1200){NSEEN.add(k);continue;}
    note({k,t:L.t,lvl:'red',ic:'🚀',title:'Пуск: '+L.site,sub:[L.type?(TNAME_PL[L.type]||TYPE_NAME[L.type]):'',L.count?'×'+L.count:'',L.carrier||''].filter(Boolean).join(' · ')||'деталі уточнюються',go:()=>flyP([L.lon,L.lat],6)});}
  // 2) нова швидка/небезпечна ціль: балістика, крилаті, «Молнії», реактивні
  for(const t of (s.tracks||[])){if(t.status!=='active'||!['ballistic','cruise','jet'].includes(t.type))continue;const k='T:'+t.id;
    if(first||(t.conf||0)<0.5){NSEEN.add(k);continue;}
    note({k,lvl:t.type==='jet'?'orange':'red',ic:t.type==='ballistic'?'🔺':t.type==='cruise'?'✈️':'🔥',title:(TYPE_NAME[t.type]||'Ціль')+(t.count>1?' ×'+t.count:'')+(t.next?' → '+t.next:''),sub:'Нова ціль'+(t.launch&&t.launch.site&&!t.launch.est?' · запуск: '+t.launch.site:''),go:()=>openSheet(t.id)});}
  // 3) тривога / відбій у моїй області
  if(home&&window.OBLPOLY){const mine=window.OBLPOLY(home[0],home[1]);if(mine){const lv=(s.levels||{})[mine]||0;
    if(NHOMELV!==null&&!first){if(!NHOMELV&&lv)note({k:'A:'+mine+':'+Math.round(now),lvl:'red',ic:'🔴',title:'Повітряна тривога: '+mine+' обл.',sub:'Пройдіть в укриття',go:()=>flyP(home,8)});
      else if(NHOMELV&&!lv)note({k:'O:'+mine+':'+Math.round(now),lvl:'green',ic:'🟢',title:'Відбій тривоги: '+mine+' обл.',sub:'У межах окремих громад тривога може ще тривати',go:()=>flyP(home,8)});}
    NHOMELV=lv;}}
  // 0) мапа доби о 09:00
  if(s.daily){let seen=null;try{seen=localStorage.getItem('dailySeen');}catch(e){}
    if(seen!==s.daily){try{localStorage.setItem('dailySeen',s.daily);}catch(e){}
      note({k:'D:'+s.daily,lvl:'violet',ic:'🗺️',title:'Мапа доби готова',sub:'Маршрути, пуски й вибухи за добу до 09:00 — натисніть, щоб відкрити',go:()=>{location.href='/daily.html?d='+s.daily;}});}}
  // 4) що вразили наші (офіційно)
  for(const h of (s.hits||[])){const k='H:'+(h.link||'')+':'+h.place+':'+h.what;if(first){NSEEN.add(k);continue;}
    note({k,t:h.t,lvl:'blue',ic:'🎯',title:'Уражено: '+h.what+' · '+h.place,sub:'Генштаб ЗСУ',go:()=>flyP([h.lon,h.lat],7)});}
}

window.__note=note;
})();
