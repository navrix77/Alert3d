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

let SNAP=null,recvAt=0,offset=0,sel=null,follow=false,home=null,setHomeMode=false,tilt=(()=>{try{if(!localStorage.getItem('mapv2')){localStorage.setItem('mapv2','1');localStorage.setItem('t3d','0');}}catch(e){}return localStorage.getItem('t3d')==='1';})(),base=(()=>{try{if(localStorage.getItem('base2')==='navryx'){localStorage.setItem('base2','night');const p=JSON.parse(localStorage.getItem('pref')||'{}');if(p.base==='navryx'){delete p.base;localStorage.setItem('pref',JSON.stringify(p));}}}catch(e){}return localStorage.getItem('base2')||'night';})();
function applySaver(){const on=window.NXPERF&&NXPERF.saver;['hillshade','bld3d'].forEach(id=>{if(map.getLayer(id))map.setLayoutProperty(id,'visibility',on?'none':'visible');});const c=$('#st-saver');if(c){c.checked=!!(window.NXPERF&&localStorage.getItem('saver')==='1');c.onchange=e=>NXPERF.setSaver(e.target.checked);}}
document.addEventListener('nxsaver',()=>{try{applySaver();}catch(e){}});
function syncReal3d(){applySaver();const r=$('#st-real3d-row');if(r)r.hidden=!(CFG&&CFG.gtilesKey);const c=$('#st-real3d');if(c){c.checked=!!(window.Real3D&&Real3D.active());c.onchange=async e=>{if(e.target.checked){const ok=await Real3D.on();if(!ok){e.target.checked=false;toast('3D-моделі зараз недоступні');}}else Real3D.off();};}}
window.NX={snap:()=>SNAP,focusType:t=>focusType(t),toast:m=>toast(m)};
try{home=JSON.parse(localStorage.getItem('home')||'null');}catch(e){}
const DISP=new Map();
const PREFL=()=>{try{return Object.assign({launch:true},JSON.parse(localStorage.getItem('pref')||'{}'));}catch(e){return {launch:true};}};
const TYPES_KMH=t=>({shahed:170,jet:450,molniya:120,cruise:800,ballistic:2000,kab:600})[t]||200;

/* ---------- карта ---------- */
const ESRI='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
let CFG={vectorStyle:'https://tiles.openfreemap.org/styles/liberty'};
const INTRO=!sessionStorage.getItem('intro');
const map=new maplibregl.Map({container:'map',pixelRatio:Math.min(window.devicePixelRatio||1,2),fadeDuration:150,maxTileCacheSize:200,style:{version:8,sources:{},layers:[{id:'bg',type:'background',paint:{'background-color':'#03050A'}}]},center:INTRO?[31.4,48.6]:[32.2,48.4],zoom:INTRO?(innerWidth<640?3.2:4.1):5.6,pitch:INTRO?0:(tilt?50:0),bearing:INTRO?0:(tilt?-14:0),attributionControl:{compact:true},maxPitch:65,minZoom:2.8,maxBounds:[[8,36],[56,62]]});window.tryvogaMap=map;
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
      {id:'esri',type:'raster',source:'esri',paint:NIGHT?{'raster-saturation':-0.15,'raster-brightness-max':['interpolate',['linear'],['zoom'],4,0.62,7,0.6,10,0.62,13,0.7],'raster-brightness-min':0.02,'raster-contrast':0.08,'raster-opacity':1}:{'raster-saturation':-0.1,'raster-brightness-max':0.9}},
      ...(NIGHT?[{id:'lights',type:'raster',source:'lights',maxzoom:10,paint:{'raster-opacity':['interpolate',['linear'],['zoom'],4,0.22,7,0.15,9,0],'raster-saturation':-0.1,'raster-contrast':0.25,'raster-resampling':'linear'}}]:[]),...keep]};
  if(NIGHT){out.sources.lights={type:'raster',tiles:['https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png'],tileSize:256,maxzoom:8,attribution:'NASA Black Marble'};}
  out.sky={'sky-color':'#04060C','horizon-color':'#1B2A4A','fog-color':'#04060C','sky-horizon-blend':0.7,'horizon-fog-blend':0.85,'fog-ground-blend':0.35,'atmosphere-blend':['interpolate',['linear'],['zoom'],0,1,5,0.75,8,0.2]};
  if(vec.sprite)out.sprite=vec.sprite;return out;
}
async function setBase(kind){base=kind;localStorage.setItem('base2',kind);map.setStyle(await styleFor(kind),{diff:false});}

function addImages(){
  // реалістичні спрайти цілей (вид згори, ніс на північ) + тіні
  for(const t of Object.keys(TYPE_COLOR))for(const v of ['','-d','-sh']){const id='t-'+t+v;if(map.hasImage(id))continue;
    map.loadImage('sprites/t-'+t+v+'.png?v=ref2').then(r=>{if(!map.hasImage(id))map.addImage(id,r.data,{pixelRatio:2});}).catch(()=>{const c=drawTarget(t,44,{dim:v==='-d'});if(!map.hasImage(id))map.addImage(id,c.getContext('2d').getImageData(0,0,c.width,c.height),{pixelRatio:2});});}
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
// Детально — лише Україна: дрібні підписи, дороги й будівлі за кордоном не малюємо (великі міста та країни лишаються)
let UAGEO=null;
function uaDetail(){
  const go=()=>{const st=map.getStyle();if(!st)return;const vs=Object.keys(st.sources).filter(k=>st.sources[k].type==='vector');
    const IN=['within',UAGEO];const KEEP=/country|continent|state|ocean|sea|water_name|marine/;
    st.layers.forEach(l=>{if(!vs.includes(l.source)||l._ua||KEEP.test(l.id))return;
      if(l.type!=='symbol'&&l.type!=='line'&&l.type!=='fill-extrusion')return;
      if(l.type==='fill-extrusion'){return;}  // будівлі — лише на великих масштабах, де й так Україна
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
  map.addSource('occ',{type:'geojson',data:'/data/occupied.geojson'});
  if(!map.hasImage('hatch')){const c=document.createElement('canvas');c.width=c.height=16;const x=c.getContext('2d');x.strokeStyle='rgba(20,0,6,.55)';x.lineWidth=3;x.beginPath();x.moveTo(-4,20);x.lineTo(20,-4);x.moveTo(-4,4);x.lineTo(4,-4);x.moveTo(12,20);x.lineTo(20,12);x.stroke();map.addImage('hatch',x.getImageData(0,0,16,16),{pixelRatio:2});}
  map.addSource('sel',{type:'geojson',data:EMPTY});map.addSource('mepos',{type:'geojson',data:EMPTY});map.addSource('lpred',{type:'geojson',data:EMPTY});map.addSource('myplaces',{type:'geojson',data:EMPTY});
  map.addSource('ticks',{type:'geojson',data:EMPTY});
  map.addSource('holo',{type:'geojson',data:EMPTY});map.addSource('hrom',{type:'geojson',data:EMPTY});map.addSource('comets',{type:'geojson',data:EMPTY,lineMetrics:true});
  ['zones','trails','preds','targets','home','chains','lsites'].forEach(id=>map.addSource(id,{type:'geojson',data:EMPTY}));
  map.addLayer({id:'obl-fill',type:'fill',source:'obl',paint:{'fill-color':['match',LV,2,'#C8102E',1,'#E8B300','#000'],'fill-opacity':['match',LV,2,0.1,1,0.1,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-fill',type:'fill',source:'ra',paint:{'fill-color':['match',LV,2,'#B3122E',1,'#E0A800','#000'],'fill-opacity':['match',LV,2,0.16,1,0.1,0],'fill-opacity-transition':{duration:500}}});
  map.addLayer({id:'ra-line',type:'line',source:'ra',minzoom:5.5,paint:{'line-color':['match',LV,2,'#FF6B7D',1,'#FFC940','#fff'],'line-opacity':['match',LV,0,['interpolate',['linear'],['zoom'],5.5,0.2,9,0.5],0.9],'line-width':['match',LV,0,['interpolate',['linear'],['zoom'],6,0.5,10,1.2],['interpolate',['linear'],['zoom'],6,1.2,10,2.2]]}});
  map.addLayer({id:'occ-fill',type:'fill',source:'occ',paint:{'fill-color':['match',['get','k'],'occupied','#2A0710','#3A3A3A'],'fill-opacity':['match',['get','k'],'occupied',0.5,0.3]}});
  map.addLayer({id:'occ-hatch',type:'fill',source:'occ',filter:['==',['get','k'],'occupied'],paint:{'fill-pattern':'hatch','fill-opacity':0.45}});
  map.addLayer({id:'occ-line',type:'line',source:'occ',filter:['==',['get','k'],'occupied'],paint:{'line-color':'#B24A5C','line-width':['interpolate',['linear'],['zoom'],5,1,9,2],'line-opacity':0.7}});
  map.addSource('outside',{type:'geojson',data:'/data/outside.geojson',tolerance:0.2,buffer:256});
  // напис навскіс, напівпрозоро — над територією РФ (у площині карти)
  map.addSource('rf-mark',{type:'geojson',data:{type:'FeatureCollection',features:[[39.2,53.6],[44.5,50.4],[36.2,56.9],[46.5,55.4]].map(c=>({type:'Feature',properties:{},geometry:{type:'Point',coordinates:c}}))}});map.addLayer({id:'outside',type:'fill',source:'outside',paint:{'fill-color':'#02040a','fill-opacity':['interpolate',['linear'],['zoom'],4,0.55,8,0.6]}});
  map.addLayer({id:'rf-mark',type:'symbol',source:'rf-mark',maxzoom:7.5,layout:{'text-field':'ДЕРЖАВА-ТЕРОРИСТ','text-font':['Noto Sans Bold'],
    'text-size':['interpolate',['exponential',1.6],['zoom'],3,13,5,26,7,46],'text-letter-spacing':0.18,'text-max-width':40,'text-rotate':-22,'text-rotation-alignment':'map','text-pitch-alignment':'map',
    'text-allow-overlap':true,'text-ignore-placement':true},paint:{'text-color':'rgba(255,90,90,0.22)','text-halo-color':'rgba(0,0,0,0.15)','text-halo-width':1}});
  map.addSource('by-mark',{type:'geojson',data:{type:'FeatureCollection',features:[[27.6,53.4],[29.4,52.2]].map(c=>({type:'Feature',properties:{},geometry:{type:'Point',coordinates:c}}))}});
  map.addLayer({id:'by-mark',type:'symbol',source:'by-mark',maxzoom:7.5,layout:{'text-field':'ПОСІПАКИ ТЕРОРИСТІВ','text-font':['Noto Sans Bold'],
    'text-size':['interpolate',['exponential',1.6],['zoom'],3,9,5,18,7,32],'text-letter-spacing':0.16,'text-max-width':40,'text-rotate':-18,'text-rotation-alignment':'map','text-pitch-alignment':'map',
    'text-allow-overlap':true,'text-ignore-placement':true},paint:{'text-color':'rgba(255,150,90,0.2)','text-halo-color':'rgba(0,0,0,0.15)','text-halo-width':1}});syncOutside();
  map.addLayer({id:'obl-line',type:'line',source:'obl',paint:{'line-color':'#fff','line-width':['interpolate',['linear'],['zoom'],4,1,9,2.2],'line-opacity':0.9}});
  // «пам'ятні місця»: крейсер «Москва» на дні та Кримський міст
  if(!map.hasImage('moskva')){const c=document.createElement('canvas');c.width=120;c.height=60;const x=c.getContext('2d');
    x.translate(60,34);x.rotate(-0.38);x.fillStyle='rgba(150,170,190,.85)';x.strokeStyle='rgba(255,255,255,.7)';x.lineWidth=1.5;
    x.beginPath();x.moveTo(-44,0);x.lineTo(40,0);x.lineTo(48,-6);x.lineTo(-38,-6);x.closePath();x.fill();x.stroke();
    x.fillRect(-18,-14,22,8);x.fillRect(-6,-22,6,8);x.fillRect(10,-11,12,5);
    x.rotate(0.38);x.strokeStyle='rgba(120,200,255,.55)';x.lineWidth=2;for(let k=0;k<3;k++){x.beginPath();x.moveTo(-52+k*6,10+k*6);x.quadraticCurveTo(-30+k*6,4+k*6,-8,10+k*6);x.quadraticCurveTo(14,16+k*6,36-k*6,10+k*6);x.stroke();}
    map.addImage('moskva',x.getImageData(0,0,120,60),{pixelRatio:2});}
  map.addSource('memo',{type:'geojson',data:{type:'FeatureCollection',features:[
    {type:'Feature',properties:{i:'moskva',l:'крейсер «Москва»\nна дні з 14.04.2022'},geometry:{type:'Point',coordinates:[30.93,45.17]}},
    {type:'Feature',properties:{i:'',l:'Кримський міст\nЗАЧЕКАЙ ЩЕ ТРОХИ'},geometry:{type:'Point',coordinates:[36.51,45.31]}}]}});
  map.addLayer({id:'memo-br',type:'line',source:{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[[36.44,45.25],[36.52,45.30],[36.60,45.36]]}}},paint:{'line-color':'rgba(255,90,90,.55)','line-width':2.5,'line-dasharray':[1,1]}});
  map.addLayer({id:'memo',type:'symbol',source:'memo',minzoom:4.6,layout:{'icon-image':['get','i'],'icon-size':['interpolate',['linear'],['zoom'],5,0.8,8,1.25],'icon-allow-overlap':true,'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':['interpolate',['linear'],['zoom'],5,9.5,8,12],'text-letter-spacing':0.08,'text-offset':[0,1.3],'text-anchor':'top','text-rotate':-8,'text-optional':true,'text-max-width':20},paint:{'text-color':'rgba(255,215,140,.75)','text-halo-color':'rgba(0,0,0,.8)','text-halo-width':1.3,'icon-opacity':0.85}});
  map.addSource('ru',{type:'geojson',data:EMPTY});map.addSource('hits',{type:'geojson',data:EMPTY});
  // приліт по РФ — живе багаття: анімоване полум'я (оновлюється ~12 разів/с, лише коли карта й так перемальовується)
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
  map.addLayer({id:'ru-glow',type:'circle',source:'ru',minzoom:3,filter:['!',['has','sum']],paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,['+',10,['*',2,['coalesce',['get','c'],3]]],8,['+',30,['*',4,['coalesce',['get','c'],3]]]],'circle-color':'#2F7BFF','circle-blur':1,'circle-opacity':0.22,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'ru-dot',type:'circle',source:'ru',filter:['!',['has','sum']],paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,1.8,7,3.5],'circle-color':'#FFD500','circle-stroke-color':'#2F7BFF','circle-stroke-width':['interpolate',['linear'],['zoom'],4,1,7,2],'circle-opacity':0.85}});
  map.addLayer({id:'ru-t',type:'symbol',source:'ru',minzoom:6.5,filter:['!',['has','sum']],layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':['case',['has','sum'],12,10.5],'text-max-width':16,'text-offset':['case',['has','sum'],['literal',[0,0]],['literal',[0,1.1]]],'text-anchor':['case',['has','sum'],'center','top'],'text-allow-overlap':false},paint:{'text-color':'rgba(255,227,107,.8)','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'hits',type:'symbol',source:'hits',layout:{'icon-image':'hit','icon-size':['interpolate',['linear'],['zoom'],4,0.9,7,1.5,10,2],'icon-allow-overlap':true,'text-field':['step',['zoom'],'',6.5,['get','l']],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,1.5],'text-anchor':'top','text-max-width':14,'text-optional':true},paint:{'text-color':'#FFE36B','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  map.addSource('xr',{type:'geojson',data:EMPTY});
  map.addLayer({id:'xr-dim',type:'background',layout:{visibility:'none'},paint:{'background-color':'#02040A','background-opacity':0.62}});
  map.addLayer({id:'xr-edge',type:'line',source:'xr',filter:['all',['==',['geometry-type'],'LineString'],['==',['get','k'],'confirm']],layout:{visibility:'none','line-cap':'round'},paint:{'line-color':['match',['get','k'],'confirm','#34C759','copy','#8892A6','assume','#B48CFF','contra','#F5B83D','#fff'],'line-width':['match',['get','k'],'confirm',2.5,1.6],'line-opacity':0.9}});map.addLayer({id:'xr-edge2',type:'line',source:'xr',filter:['all',['==',['geometry-type'],'LineString'],['!=',['get','k'],'confirm']],layout:{visibility:'none','line-cap':'round'},paint:{'line-dasharray':[1.5,2],'line-color':['match',['get','k'],'confirm','#34C759','copy','#8892A6','assume','#B48CFF','contra','#F5B83D','#fff'],'line-width':['match',['get','k'],'confirm',2.5,1.6],'line-opacity':0.9}});
  map.addLayer({id:'xr-node',type:'circle',source:'xr',filter:['==',['geometry-type'],'Point'],layout:{visibility:'none'},paint:{'circle-radius':['match',['get','k'],'prim',7,'copy',4.5,'now',6,5],'circle-color':['match',['get','k'],'prim','#34C759','copy','#8892A6','dest','rgba(0,0,0,0)','now','rgba(180,140,255,.25)','#B48CFF'],'circle-stroke-color':['match',['get','k'],'prim','#C8FFD6','copy','#C9D2E3','dest','#F5B83D','now','#B48CFF','#E3D4FF'],'circle-stroke-width':['match',['get','k'],'dest',2,'now',2,1.5]}});
  map.addLayer({id:'xr-t',type:'symbol',source:'xr',filter:['all',['==',['geometry-type'],'Point'],['has','l']],minzoom:6.5,layout:{visibility:'none','text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':10.5,'text-offset':[0,1.2],'text-anchor':'top','text-allow-overlap':false,'text-max-width':12},paint:{'text-color':['match',['get','k'],'prim','#B8FFCB','copy','#AEB6C6','dest','#FFD27A','#D9C8FF'],'text-halo-color':'#000','text-halo-width':1.5}});
  map.addLayer({id:'zones',type:'circle',source:'zones',paint:{'circle-radius':['interpolate',['linear'],['zoom'],5,5,9,13,12,18],'circle-color':TYPE_COLOR.kab,'circle-opacity':0.16,'circle-stroke-color':TYPE_COLOR.kab,'circle-stroke-width':1.6,'circle-stroke-opacity':0.9,'circle-blur':0.1}});
  // загроза КАБ: маленький значок авіабомби над пунктом і підпис — замість великих помаранчевих кіл
  if(!map.hasImage('kab-mini')){const im=new Image();im.onload=()=>{if(!map.hasImage('kab-mini'))map.addImage('kab-mini',im,{pixelRatio:4});};im.src='sprites/t-kab.png?v=ref1';}
  map.addLayer({id:'zones-t',type:'symbol',source:'zones',layout:{'icon-image':'kab-mini','icon-size':['interpolate',['linear'],['zoom'],5,0.5,9,0.9],'icon-allow-overlap':true,'text-field':['step',['zoom'],'',7,'загроза КАБ'],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,1.6],'text-anchor':'top','text-optional':true},paint:{'text-color':TYPE_COLOR.kab,'text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.4}});
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
     '<div class="kp-r"><span>Прильоти</span><b>багаття на мапі — за Генштабом ЗСУ та ASTRA</b></div>'+
     (ev.link?'<div class="kp-ev"><a href="'+esc(ev.link)+'" target="_blank" rel="noopener" style="color:inherit">допис-першоджерело ↗</a></div>':'')+'</div>').addTo(map);});
  map.on('click','lsites',e=>{const f=e.features&&e.features[0];if(!f||!SNAP||!f.properties.lid)return;const L=(SNAP.launches||[]).find(x=>x.id===f.properties.lid);if(!L)return;const w=launchWhat(L);const nm=k=>(SNAP.sources&&SNAP.sources[k]&&SNAP.sources[k].name)||k;
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'320px',className:'kab-pop avia-pop',offset:12}).setLngLat(f.geometry.coordinates).setHTML(
     '<div class="kp"><small>ПУСК ПО УКРАЇНІ</small><h4>'+esc(L.site)+'</h4>'+
     '<div class="kp-r"><span>Що</span><b>'+esc(w.full)+'</b></div>'+
     (L.count?'<div class="kp-r"><span>Кількість</span><b>'+L.count+'</b></div>':'')+(L.carrier?'<div class="kp-r"><span>Носій</span><b>'+esc(L.carrier)+'</b></div>':'')+
     '<div class="kp-r"><span>Коли</span><b>'+fmt(L.t)+'</b></div>'+'<div class="kp-r"><span>Цілей привʼязано</span><b>'+(L.tracks||0)+'</b></div>'+
     ((L.ev||[]).length?'<div class="kp-ev">'+L.ev.slice(-3).reverse().map(e=>'<div><i>'+fmt(e.t)+' · '+esc(nm(e.src))+'</i>'+esc(e.text||'')+'</div>').join('')+'</div>':'')+'</div>').addTo(map);});
  map.on('mouseenter','lsites',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','lsites',()=>map.getCanvas().style.cursor='');
  map.on('click','hits',e=>{const f=e.features&&e.features[0];if(!f)return;const h=HITS[f.properties.hi];if(!h)return;
    if(kabPop)kabPop.remove();kabPop=new maplibregl.Popup({closeButton:true,maxWidth:'300px',className:'kab-pop ru-pop',offset:12}).setLngLat(f.geometry.coordinates).setHTML(
     '<div class="kp"><small>'+(h.src==='ASTRA'?'ПРИЛІТ НАШИХ ДРОНІВ':'УРАЖЕНО СИЛАМИ ОБОРОНИ')+'</small><h4>'+esc(h.place)+'</h4>'+
     '<div class="kp-r"><span>Що</span><b>'+esc(h.what)+'</b></div>'+
     '<div class="kp-r"><span>Коли</span><b>'+new Date(h.t*1000).toLocaleString('uk-UA',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+'</b></div>'+
     '<div class="kp-r"><span>Джерело</span><b>'+esc(h.src||'Генштаб ЗСУ')+'</b></div>'+
     '<div class="kp-ev"><div>'+esc(h.detail||'')+'</div>'+(h.link?'<a href="'+esc(h.link)+'" target="_blank" rel="noopener" style="color:inherit">першоджерело ↗</a>':'')+'</div></div>').addTo(map);});
  map.on('mouseenter','hits',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','hits',()=>map.getCanvas().style.cursor='');
  map.on('mouseenter','ru-dot',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','ru-dot',()=>map.getCanvas().style.cursor='');
  map.on('mouseenter','zones-t',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','zones-t',()=>map.getCanvas().style.cursor='');}
  map.addLayer({id:'chains',type:'line',source:'chains',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':['case',['get','s'],2.6,1.4],'line-dasharray':[2,1.6],'line-opacity':['get','o']}});
  map.addLayer({id:'lsites',type:'circle',source:'lsites',paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,['case',['get','est'],3,4],7,['case',['get','est'],5,7]],'circle-color':['case',['get','est'],'rgba(255,77,77,0.25)','#FF3B3B'],'circle-stroke-color':'#fff','circle-stroke-width':['case',['get','est'],1.2,2],'circle-pitch-alignment':'map'}});
  map.addLayer({id:'lsites-t',type:'symbol',source:'lsites',minzoom:6.2,layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11,'text-max-width':14,'text-offset':[0,1.1],'text-anchor':'top','text-allow-overlap':false,'text-optional':true},paint:{'text-color':'#FFB3B3','text-halo-color':'#0B0F17','text-halo-width':2}});
  map.addLayer({id:'trails',type:'line',source:'trails',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['get','c'],'line-width':3,'line-dasharray':[0.1,2.2],'line-opacity':['get','o']}});
  map.addLayer({id:'ticks-c',type:'circle',source:'ticks',paint:{'circle-radius':4,'circle-color':['get','c'],'circle-stroke-color':'#0B0F17','circle-stroke-width':2,'circle-pitch-alignment':'map'}});
  map.addLayer({id:'ticks-t',type:'symbol',source:'ticks',layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,-1.1],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.9)','text-halo-width':1.6}});
  map.addLayer({id:'preds',type:'line',source:'preds',layout:{'line-cap':'round'},paint:{'line-color':['get','c'],'line-width':2,'line-dasharray':[1.5,2],'line-opacity':0.9}});
  map.addLayer({id:'home',type:'symbol',source:'home',layout:{'icon-image':'home','icon-size':1,'icon-allow-overlap':true,'text-field':'Дім','text-font':['Noto Sans Bold'],'text-size':13,'text-offset':[0,1.7],'text-allow-overlap':true},paint:{'text-color':'#fff','text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.6}});
  map.addLayer({id:'tg-course',type:'symbol',source:'targets',filter:['all',['has','next'],['==',['get','active'],true],['any',['get','thr'],['==',['get','sk'],0],['>=',['zoom'],7]]],layout:{'text-field':['concat',['case',['>',['get','count'],1],['concat','×',['to-string',['get','count']],'  '],''],'→ ',['get','next']],'text-font':['Noto Sans Bold'],'text-size':13,'icon-image':'chip','icon-text-fit':'both','icon-text-fit-padding':[3,7,3,7],'text-variable-anchor':['left','right','bottom','top'],'text-radial-offset':['interpolate',['linear'],['zoom'],2,1.9,5,2.3,7,2.8,9.5,3.4,12,3.8],'text-justify':'auto','icon-allow-overlap':false,'text-allow-overlap':false,'text-optional':false,'symbol-sort-key':['get','sk']},paint:{'text-color':'#fff'}});
  const TGS=['interpolate',['linear'],['zoom'],4,0.55,7,0.85,9,1.15,12,1.55];
  // голограма тривоги: об'єми над районами (червоні вищі), «дихають»
  const firstLbl=(map.getStyle().layers.find(l=>l.type==='symbol')||{}).id;
  map.addLayer({id:'holo',type:'fill-extrusion',source:'holo',maxzoom:8.5,paint:{'fill-extrusion-color':['match',['get','l'],2,'#FF2D3D','#FFB020'],'fill-extrusion-height':['interpolate',['linear'],['zoom'],5,['match',['get','l'],2,12000,4500],7.5,['match',['get','l'],2,1500,600],8.5,0],'fill-extrusion-base':0,'fill-extrusion-opacity':0.26,'fill-extrusion-vertical-gradient':true}},firstLbl);
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
  map.addLayer({id:'lpred',type:'line',source:'lpred',filter:['==',['geometry-type'],'LineString'],layout:{'line-cap':'round'},paint:{'line-color':['get','c'],'line-width':2,'line-dasharray':[0.6,2.2],'line-opacity':0.75}});
  map.addLayer({id:'lpred-t',type:'symbol',source:'lpred',filter:['==',['geometry-type'],'Point'],minzoom:6,layout:{'text-field':['get','l'],'text-font':['Noto Sans Bold'],'text-size':11,'text-offset':[0,-1],'text-allow-overlap':false},paint:{'text-color':['get','c'],'text-halo-color':'rgba(0,0,0,.85)','text-halo-width':1.4,'text-opacity':0.9}});
  map.addLayer({id:'me-ring',type:'fill',source:'mepos',filter:['==',['geometry-type'],'Polygon'],paint:{'fill-color':'#3B9BFF','fill-opacity':0.07}});
  map.addLayer({id:'me-ring-l',type:'line',source:'mepos',filter:['==',['geometry-type'],'Polygon'],paint:{'line-color':'#5AB0FF','line-width':1.4,'line-dasharray':[2,2],'line-opacity':0.85}});
  map.addLayer({id:'me-dot-h',type:'circle',source:'mepos',filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':16,'circle-color':'#3B9BFF','circle-opacity':0.22,'circle-blur':0.6}});
  map.addLayer({id:'me-dot',type:'circle',source:'mepos',filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':6.5,'circle-color':'#2F8BFF','circle-stroke-color':'#fff','circle-stroke-width':2.2}});
  map.addLayer({id:'myplaces',type:'circle',source:'myplaces',paint:{'circle-radius':['interpolate',['linear'],['zoom'],4,3,8,6],'circle-color':'#B07CFF','circle-stroke-color':'#fff','circle-stroke-width':['interpolate',['linear'],['zoom'],4,1.2,8,2]}});
  map.addLayer({id:'myplaces-t',type:'symbol',source:'myplaces',minzoom:6,layout:{'text-field':['get','n'],'text-font':['Noto Sans Bold'],'text-size':12,'text-offset':[0,1.1],'text-anchor':'top','text-allow-overlap':false},paint:{'text-color':'#fff','text-halo-color':'rgba(40,10,70,.9)','text-halo-width':1.8}});
  lastLv='';lastRa='';syncHome();syncMe();syncPlaces();
  if(tilt)set3d(true,'keep');
  if(!map._scaleAdded&&innerWidth>640){map.addControl(new maplibregl.ScaleControl({unit:'metric',maxWidth:110}),'bottom-left');map._scaleAdded=true;}
}
map.on('style.load',addOverlays);
// кінематографічне інтро: з космосу — на Україну вночі, поки збираються дані
let introDone=false,introT0=Date.now();if(INTRO)document.body.classList.add('intro');
function introFly(skip){if(introDone)return;introDone=true;sessionStorage.setItem('intro','1');const el=$('#intro');
  const mob=innerWidth<640;
  const cam={center:home||[31.4,48.6],zoom:home?(mob?7:7.6):(mob?4.75:5.6),pitch:mob?42:52,bearing:-14};
  const finish=()=>{document.body.classList.remove('intro');document.body.classList.add('intro-in');setTimeout(()=>document.body.classList.remove('intro-in'),2500);
    ['lsites-t','tg-n','tg-course','ru-t','hits'].forEach(id=>{if(map.getLayer(id))map.setLayoutProperty(id,'visibility','visible');});};
  if(skip||!INTRO){if(el)el.remove();if(INTRO)map.jumpTo(cam);finish();return;}
  // поки летимо — без підписів пусків і цілей (каша), вони з'являються в кінці польоту
  ['lsites-t','tg-n','tg-course','ru-t','hits'].forEach(id=>{if(map.getLayer(id))map.setLayoutProperty(id,'visibility','none');});
  const wait=Math.max(0,2300-(Date.now()-introT0));   // логотип встигає зіграти
  setTimeout(()=>{el&&el.classList.add('out');map.flyTo({...cam,duration:4200,curve:1.4,essential:true});window.__introAt=Date.now();tilt=true;
    setTimeout(finish,2600);setTimeout(()=>el&&el.remove(),1800);},wait);}
// живий статус у заставці
{let n=0;const st=$('#intro-st');const tick=setInterval(()=>{if(introDone||!st){clearInterval(tick);return;}n++;
  if(SNAP){const h=SNAP.health||{},c=(h.channels||{});const act=SNAP.tracks.filter(t=>t.status==='active').length;
    st.textContent=(c.channels?c.live+' з '+c.channels+' джерел наживо · ':'')+(act?act+' цілей у небі':'небо поки чисте');}else st.textContent=['Підключаюсь до джерел…','Читаю монітори…','Збираю картину неба…'][n%3];},450);}
map.once('idle',()=>introFly(false));
setTimeout(()=>introFly(false),7000);
{const el=$('#intro');if(el){if(!INTRO)el.remove();else el.onclick=()=>introFly(true);}}map.on('styledata',()=>{if(map.isStyleLoaded()&&!map.getSource('obl'))addOverlays();if(map.getSource('obl')&&!lastLv)syncLevels();});
map.on('click',e=>{if(!setHomeMode)return;const f=map.queryRenderedFeatures(e.point,{layers:['tg-hit']});if(f.length)return;home=[e.lngLat.lng,e.lngLat.lat];localStorage.setItem('home',JSON.stringify(home));setHomeMode=false;$('#b-home').classList.remove('on');syncHome();toast('Дім збережено');});
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
function posAt(tr,serverT){
  if(tr.status!=='active')return {p:[tr.lon,tr.lat],hd:tr.hd};
  // місце лише оцінене («курсом на X» — і вже в X), а нового пункту немає: далі не «ведемо» ціль навмання
  if(tr.pos_est&&!tr.route.length&&!tr.next)return {p:[tr.lon,tr.lat],hd:tr.hd};
  const V=tr.vmap||tr.speed;// швидкість просування на мапі (сервер: бектест), не паспортна
  let km=V*Math.max(0,serverT-tr.ts)/3600;
  const SHOW={shahed:25,molniya:20,jet:6,cruise:2,ballistic:1}[tr.type]??25;// хв: ціль рухається курсом, доки не прийде нове повідомлення (зона «де може бути» росте)
  const cap=Math.max(0,V*SHOW/60-V*Math.max(0,tr.ts-tr.last)/3600);
  if(!tr.route.length)km=Math.min(km,cap);
  const pts=[xy([tr.lon,tr.lat]),...tr.route.map(xy)];
  if(pts.length===1){if(tr.hd==null)return {p:[tr.lon,tr.lat],hd:tr.hd};const r=tr.hd*D2R;return {p:ll([pts[0][0]+Math.sin(r)*km,pts[0][1]+Math.cos(r)*km]),hd:tr.hd};}
  let acc=0;for(let i=1;i<pts.length;i++){const d=dist(pts[i-1],pts[i]);if(acc+d>=km){const f=(km-acc)/(d||1);const q=[pts[i-1][0]+(pts[i][0]-pts[i-1][0])*f,pts[i-1][1]+(pts[i][1]-pts[i-1][1])*f];return {p:ll(q),hd:brg(pts[i-1],pts[i])};}acc+=d;}
  // пункт пройдено — далі тим самим курсом
  const n=pts.length,h=brg(pts[n-2],pts[n-1]),r=h*D2R,ex=Math.min(km-acc,cap);
  return {p:ll([pts[n-1][0]+Math.sin(r)*ex,pts[n-1][1]+Math.cos(r)*ex]),hd:h};
}
const HD_Q={channels:[0,0,0,0,0,5,7,10,14,19,22,28,32,42,50,56,63,82,93,145],learned:[0,0,0,0,0,0,0,0,12,14,18,19,25,26,29,46,55,69,78,110],
  movement:[4,6,7,7,10,13,13,23,26,26,34,36,76,94,97,97,97,156,158,164],all:[0,0,0,0,0,4,7,12,14,18,22,26,32,42,49,56,71,88,97,150]};
function pToward(src,delta,dkm){const q=HD_Q[{from:'movement',course:'all'}[src]||src]||HD_Q.all;const w=Math.atan(15/Math.max(dkm,15))*180/Math.PI;
  let s=0;for(const e of q)s+=0.5*(Math.abs(delta-e)<=w)+0.5*(Math.abs(delta+e)<=w);return s/q.length;}
function homeRel(tr,p){
  if(!home)return null;const H=xy(home),P=xy(p);const d=dist(H,P);
  let rel=null,eta=null;
  const path=[P,...tr.route.map(xy)];
  let acc=0,best={d:1e9,c:0};for(let i=1;i<path.length;i++){const a=path[i-1],b=path[i];const vx=b[0]-a[0],vy=b[1]-a[1],L2=vx*vx+vy*vy;let t=L2?((H[0]-a[0])*vx+(H[1]-a[1])*vy)/L2:0;t=Math.max(0,Math.min(1,t));const q=[a[0]+vx*t,a[1]+vy*t];const dd=dist(H,q);if(dd<best.d)best={d:dd,c:acc+Math.sqrt(L2)*t};acc+=Math.sqrt(L2);}
  // ймовірність пройти ≤15 км від дому — з розподілу похибки курсу (бектест; той самий, що й у push.py)
  const pr=tr.hd!=null?pToward(tr.hd_src,angd(tr.hd,brg(P,H)),d):0;
  let maybe=false;
  if(best.d<8){rel='route';eta=best.c/tr.speed*60;}
  else if(tr.hd!=null&&pr>=0.4){rel='heading';eta=d/tr.speed*60;}
  else if(tr.hd!=null&&pr>=0.15&&d<=150&&d/tr.speed*60<=45)maybe=true;// «можлива загроза»: широке попередження, ще не тривога
  if(rel&&(d>150||eta>45)){rel=null;eta=null;}
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
      if(active&&(sel===tr.id||(rel&&rel.rel))&&tr.lpath&&tr.lpath.length&&!tr.route.length){const L=tr.lpath;lpf.push({type:'Feature',properties:{c},geometry:{type:'LineString',coordinates:[d.p,...L.map(x=>[x[0],x[1]])]}});
        L.forEach(x=>lpf.push({type:'Feature',properties:{c,l:'ймовірно '+x[2]+' · '+Math.round(x[3]*100)+'%'},geometry:{type:'Point',coordinates:[x[0],x[1]]}}));}
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
      for(const L of (SNAP.launches||[])){const w=launchWhat(L);ls.set(L.site,{type:'Feature',properties:{est:false,lid:L.id,l:'ПУСК: '+w.short+(L.count?' ×'+L.count:'')+'\nз '+L.site.replace(/ \(.*\)/,'')+(L.carrier?' ('+L.carrier+')':'')+' · '+fmt(L.t)},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});}
      for(const tr of SNAP.tracks){const L=tr.launch;if(!L||tr.status==='closed')continue;const isSel=sel===tr.id,d=DISP.get(tr.id);if(!d)continue;
        if(L.est&&!isSel)continue;
        ch.push({type:'Feature',properties:{c:L.est?'#FF8A8A':'#FF3B3B',o:isSel?0.95:(L.est?0.3:0.38),s:isSel},geometry:{type:'LineString',coordinates:[[L.lon,L.lat],[tr.entry[0],tr.entry[1]],...tr.trail.map(t=>[t[0],t[1]]),d.p]}});
        if(!ls.has(L.site))ls.set(L.site,{type:'Feature',properties:{est:true,l:'ймовірно · '+L.site.replace(/ \(.*\)/,'')},geometry:{type:'Point',coordinates:[L.lon,L.lat]}});}
      map.getSource('chains').setData({type:'FeatureCollection',features:ch});map.getSource('lsites').setData({type:'FeatureCollection',features:[...ls.values()]});}
    T3D.heads=feats.map(f=>({id:f.properties.id,type:f.properties.type,hd:f.properties.hd,active:f.properties.active,weak:f.properties.weak,p:f.geometry.coordinates}));
    if(slow){map.getSource('trails').setData({type:'FeatureCollection',features:trails});
    map.getSource('preds').setData({type:'FeatureCollection',features:preds});if(map.getSource('lpred'))map.getSource('lpred').setData({type:'FeatureCollection',features:lpf});}
    if(slow&&map.getSource('sel')){const d=sel&&DISP.get(sel);const tr=sel&&SNAP.tracks.find(t=>t.id===sel);map.getSource('sel').setData(d&&tr?{type:'FeatureCollection',features:[{type:'Feature',properties:{c:TYPE_COLOR[tr.type]},geometry:{type:'Point',coordinates:d.p}}]}:EMPTY);}
    if(follow&&sel&&!map.isMoving()){const d=DISP.get(sel);if(d){const c=map.getCenter();const k=0.12;map.jumpTo({center:[c.lng+(d.p[0]-c.lng)*k,c.lat+(d.p[1]-c.lat)*k]});}}
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
let OBLF=null;fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>{OBLF=j.features;lastRa='';syncOutside();});
// поза Україною — притемнено, щоб країна «світилася» на карті (маска готується на сервері)
function syncOutside(){}
function syncHolo(lv){if(!map.getSource('holo')||!RA)return;const F=[];
  RA.forEach(r=>{const l=lv[r.i];if(l)F.push({type:'Feature',properties:{l},geometry:r.polys.length===1?{type:'Polygon',coordinates:r.polys[0]}:{type:'MultiPolygon',coordinates:r.polys}});});
  const L=(SNAP&&SNAP.levels)||{};if(OBLF)OBLF.forEach(f=>{const l=L[f.properties.n];if(l)F.push({type:'Feature',properties:{l},geometry:f.geometry});});
  map.getSource('holo').setData({type:'FeatureCollection',features:F});}
let OBLN=null;function fetchOblNames(){if(OBLN)return Promise.resolve(OBLN);return fetch('/data/oblasts.geojson').then(r=>r.json()).then(j=>OBLN=j.features.map(f=>f.properties.n));}
function syncHome(){if(map.getSource('home'))map.getSource('home').setData(home?{type:'FeatureCollection',features:[{type:'Feature',properties:{},geometry:{type:'Point',coordinates:home}}]}:EMPTY);}
function syncAvia(){if(!SNAP||!map.getSource('avia'))return;const A=SNAP.avia||[];const P=[],Z=[],L=[];
  A.forEach(a=>{const c=[a.lon,a.lat];const tgt=a.to&&a.to[0]||[31.5,49];const r=Math.atan2((tgt[0]-a.lon)*Math.cos(a.lat*Math.PI/180),tgt[1]-a.lat)*180/Math.PI;
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
function launchWhat(L){const N={shahed:'шахеди',jet:'реактивні БпЛА',molniya:'«Молнії»',cruise:'крилаті ракети',ballistic:'балістика',kab:'КАБи',geran5:'«Герань-5»',banderol:'«Бандеролі»'};
  if(L.type)return {short:N[L.type]||L.type,full:(N[L.type]||L.type)+' (так написали канали)'};
  const linked=[...new Set((SNAP.tracks||[]).filter(t=>t.launch&&t.launch.id===L.id&&!t.launch.est).map(t=>t.type))];
  if(linked.length)return {short:linked.map(t=>N[t]||t).join(' + '),full:linked.map(t=>N[t]||t).join(' + ')+' (за цілями, що вже летять від цього пуску)'};
  const st=(L.site_types||[]).filter(t=>t!=='kab'||L.site_kind==='аеродром');
  if(st.length===1)return {short:'ймовірно '+(N[st[0]]||st[0]),full:'тип не названо; звідси зазвичай пускають '+(N[st[0]]||st[0])};
  return {short:'тип не названо',full:'тип не названо'+(st.length?'; звідси пускають: '+st.map(t=>N[t]||t).join(', '):'')};}
let kabPop=null;
function syncZones(){syncAvia();if(!SNAP||!map.getSource('zones'))return;map.getSource('zones').setData({type:'FeatureCollection',features:SNAP.zones.flatMap((z,zi)=>z.places.map(([lo,la])=>({type:'Feature',properties:{zi},geometry:{type:'Point',coordinates:[lo,la]}})))});}

/* ---------- лічильники, статус ---------- */
const CNTI={};
const CNT_LBL={shahed:'шахеди',jet:'реактивні',cruise:'крилаті',ballistic:'балістика',molniya:'«молнії»',kab:'КАБи',geran5:'Герань-5',banderol:'бандеролі',rszv:'РСЗВ',fpv:'FPV',fpvf:'FPV-оптоволокно',recon:'розвідники'};
// натиск на лічильник — показати всі цілі цього типу
function focusType(t){const ps=SNAP.tracks.filter(x=>x.status==='active'&&x.type===t).map(x=>(DISP.get(x.id)||{p:[x.lon,x.lat]}).p);if(!ps.length)return;
  const b=ps.reduce((a,p)=>a.extend(p),new maplibregl.LngLatBounds(ps[0],ps[0]));map.fitBounds(b,{padding:{top:140,bottom:180,left:60,right:60},maxZoom:9,duration:900});toast(TYPE_NAME[t]+': '+ps.length);}
function renderCounters(){
  const act=SNAP.tracks.filter(t=>t.status==='active');const by={};act.forEach(t=>by[t.type]=(by[t.type]||0)+(t.count||1));
  const order=['shahed','jet','geran5','cruise','banderol','ballistic','rszv','molniya','recon','fpv','fpvf'];
  $('#counters').innerHTML='';
  order.filter(t=>by[t]).forEach(t=>{const d=document.createElement('div');d.className='cnt';d.title=TYPE_NAME[t];const c=CNTI[t]||(CNTI[t]=drawTarget(t,28));const cc=document.createElement('canvas');cc.width=c.width;cc.height=c.height;cc.getContext('2d').drawImage(c,0,0);d.appendChild(cc);const w=document.createElement('div');w.className='cw';const b=document.createElement('b');b.textContent=by[t];if(renderCounters.prev&&renderCounters.prev[t]!==by[t])b.className='pop';
    const l=document.createElement('small');l.textContent=CNT_LBL[t]||TYPE_NAME[t];w.appendChild(b);w.appendChild(l);d.appendChild(w);d.style.setProperty('--tc',TYPE_COLOR[t]);d.onclick=()=>focusType(t);$('#counters').appendChild(d);});
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
let SHELTER=+(localStorage.getItem('shelter')||3);if($('#me-sh'))$('#me-sh').textContent=SHELTER;
if($('#me-set'))$('#me-set').onclick=()=>{const v=[1,2,3,5,7,10];SHELTER=v[(v.indexOf(SHELTER)+1)%v.length];localStorage.setItem('shelter',SHELTER);$('#me-sh').textContent=SHELTER;toast('До укриття: '+SHELTER+' хв');};
const MEI={};
function renderMe(threats){
  const box=$('#me');if(!home){box.className='me'+(box.classList.contains('open')?' open':'');$('#me-word').textContent='Що летить до мене?';$('#me-sub').innerHTML='Покажу, що летить саме до вас.<button class="cta" id="me-cta">Визначити моє місце</button>';const cta=$('#me-cta');if(cta)cta.onclick=()=>$('#b-locate').click();$('#me-list').innerHTML='';return;}
  const isStale=!SNAP||(Date.now()-recvAt)/1000>20;
  const near=SNAP.tracks.filter(t=>t.status==='active'&&t.conf>=0.5).map(t=>{const d=DISP.get(t.id);return d?{tr:t,r:homeRel(t,d.p)}:null;}).filter(x=>x&&x.r&&x.r.d<120).sort((a,b)=>(a.r.eta??999)-(b.r.eta??999)||a.r.d-b.r.d);
  const thr=near.filter(x=>x.r.rel);const first=thr[0];
  let cls='me',word='Над вами чисто',sub='Підтверджених цілей у ваш бік немає. Найближча: '+(near[0]?Math.round(near[0].r.d)+' км '+near[0].r.from:'далі 120 км')+'.';
  const mb=near.filter(x=>!x.r.rel&&x.r.maybe).sort((a,b)=>b.r.p-a.r.p)[0];
  if(!first&&mb){cls='me watch';word='Можлива загроза';sub=esc(TYPE_NAME[mb.tr.type])+' · '+Math.round(mb.r.d)+' км '+mb.r.from+' · ймовірність пройти поруч ~'+Math.round(mb.r.p*100)+'%. Будьте поруч з укриттям — це ще не тривога.';}
  if(isStale){cls='me watch';word='Невідомо';sub='Немає звʼязку з джерелами. Це <b>не відбій</b>.';}
  else if(first){const e=first.r.eta||0;cls=e<=5?'me danger':'me watch';word=e<=5?'Летить на вас':'У ваш бік';
    sub=esc(TYPE_NAME[first.tr.type])+' · '+Math.round(first.r.d)+' км '+first.r.from+(first.r.eta!=null?' · ~'+Math.max(1,Math.round(e))+' хв':'');}
  box.className=cls+(box.classList.contains('open')?' open':'');$('#me-word').textContent=word;
  // ГОЛОВНЕ: скільки хвилин саме у вас — великим числом з кільцем
  if(first&&!isStale&&first.r.eta!=null){const eta=Math.max(1,Math.round(first.r.eta)),k=Math.max(0.04,Math.min(1,eta/30));const C=2*Math.PI*44;
    sub='<div class="big"><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" class="trk"/><circle cx="50" cy="50" r="44" class="arc" style="stroke-dasharray:'+(C*k)+' '+C+'"/></svg><b>'+eta+'</b><i>хв</i></div>'+
      '<div class="big-t"><b>'+esc(TYPE_NAME[first.tr.type])+(first.tr.count>1?' ×'+first.tr.count:'')+'</b> · ~'+eta+' хв до вас<br><span>'+Math.round(first.r.d)+' км '+first.r.from+(first.tr.next?' · курс → '+esc(first.tr.next):'')+'</span></div>';}
  $('#me-sub').innerHTML=sub;
  $('#me-list').innerHTML='';
  (thr.length?thr:near).slice(0,3).forEach(x=>{const t=x.tr,r=x.r;const li=document.createElement('li');
    const c=MEI[t.type]||(MEI[t.type]=drawTarget(t.type,22));const cv=document.createElement('canvas');cv.width=c.width;cv.height=c.height;cv.getContext('2d').drawImage(c,0,0);
    const eta=r.eta!=null?Math.max(1,Math.round(r.eta)):null;
    li.innerHTML='<div class="me-row"><span class="n">'+esc(TYPE_NAME[t.type])+(t.count>1?' ×'+t.count:'')+' · '+Math.round(r.d)+' км '+r.from+'</span><span class="t">'+(eta?'~'+eta+' хв':(r.away?'віддаляється':t.hd==null?'курс невідомий':r.maybe?'можливо у ваш бік · '+Math.round(r.p*100)+'%':'летить повз'))+'</span></div>'+
      (eta?'<div class="me-act '+(eta<=5?'go':'ok')+'">'+(r.rel==='route'?'маршрут проходить поруч':'курс у ваш бік')+'</div>':'');
    li.querySelector('.me-row').prepend(cv);li.onclick=()=>openSheet(t.id);$('#me-list').appendChild(li);});
}
function renderBanner(threats){
  const b=$('#banner');if(!threats.length){b.hidden=true;return;}
  threats.sort((a,b)=>(a.rel.eta??999)-(b.rel.eta??999));const t=threats[0];
  b.hidden=false;b.innerHTML=esc(TYPE_NAME[t.tr.type])+(t.tr.count>1?' ×'+t.tr.count:'')+' · '+(t.rel.rel==='route'?'маршрут проходить біля дому':'курс на твій район')+(t.rel.eta!=null?' · ~'+Math.max(1,Math.round(t.rel.eta))+' хв':'')+'<small>'+Math.round(t.rel.d)+' км '+t.rel.from+(threats.length>1?' · ще '+(threats.length-1):'')+'</small>';
  b.onclick=()=>openSheet(t.tr.id);
  // кінематографічний переліт: нова загроза дому — камера плавно показує і дім, і ціль (якщо користувач не крутить карту)
  renderBanner.seen=renderBanner.seen||new Set();
  if(!renderBanner.seen.has(t.tr.id)){renderBanner.seen.add(t.tr.id);
    note({k:'home:'+t.tr.id,lvl:'red',ic:'⚠️',title:TYPE_NAME[t.tr.type]+(t.tr.count>1?' ×'+t.tr.count:'')+' — '+(t.rel.rel==='route'?'маршрут біля вашого дому':'курс на ваш район'),sub:Math.round(t.rel.d)+' км '+t.rel.from+(t.rel.eta!=null?' · ~'+Math.max(1,Math.round(t.rel.eta))+' хв':''),go:()=>openSheet(t.tr.id)});const d=DISP.get(t.tr.id);
    if(d&&home&&introDone&&Date.now()-(window.__introAt||0)>9000&&Date.now()-(window.__touch||0)>20000){const b2=new maplibregl.LngLatBounds(home,home).extend(d.p);
      const cam=map.cameraForBounds(b2,{padding:{top:140,bottom:160,left:80,right:380}});if(cam)map.flyTo({...cam,zoom:Math.min(cam.zoom,10),pitch:tilt?55:20,bearing:tilt?-18:0,curve:1.5,speed:0.7,essential:true});}}
}
['mousedown','touchstart','wheel'].forEach(ev=>document.getElementById('map').addEventListener(ev,()=>window.__touch=Date.now(),{passive:true}));

/* ---------- картка цілі ---------- */
// навчений прогноз траєкторії: куди такі цілі з цього місця летіли раніше + власна точність прогнозу
function lpHtml(tr){const L=tr.lpath||[];if(!L.length)return '';const A=(SNAP.pred_acc||{})[tr.type];
  return '<h4>Ймовірно далі <small>· навчено на попередніх перельотах'+(A?' · точність '+Math.round(A.acc*100)+'% з '+A.n:'')+'</small></h4><ol class="lp">'+L.map(x=>'<li><b>'+Math.round(x[3]*100)+'%</b> '+esc(x[2])+'</li>').join('')+'</ol>';}
function openSheet(id){if(follow&&id!==sel)stopFollow();sel=id;$('#sh-follow').classList.toggle('on',follow);$('#sh-follow').textContent=follow?'Зупинити стеження':'Стежити за ціллю';$('#sheet').hidden=false;fillSheet(true);const d=DISP.get(id);if(d)map.flyTo({center:d.p,zoom:Math.max(map.getZoom(),8.5),curve:1.3,speed:1.1,essential:true});}
function fillSheet(first){
  const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);if(!tr){$('#sheet').hidden=true;sel=null;return;}
  if(first||!fillSheet.icon||fillSheet.icon!==tr.type){const c=drawTarget(tr.type,40);$('#sh-icon').innerHTML='';$('#sh-icon').appendChild(c);fillSheet.icon=tr.type;}
  $('#sh-name').textContent=TYPE_NAME[tr.type]+(tr.count>1?' ×'+tr.count:'');
  $('#sh-course').innerHTML=tr.status!=='active'?(tr.status==='lost'?'Втрачено':'Більше не фіксується'):(tr.next?'Курс → <b>'+esc(tr.next)+'</b>':'Курс уточнюється');
  const d=DISP.get(tr.id);const r=d&&homeRel(tr,d.p);
  $('#sh-dist').textContent=!home?'вкажіть свою точку':r?Math.round(r.d)+' км '+r.side:'—';
  $('#sh-eta').textContent=!home?'—':!r?'—':r.eta!=null?'≈ '+Math.max(1,Math.round(r.eta))+' хв до вас':r.away?'віддаляється':tr.hd==null?'курс невідомий':'летить повз';
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
    $('#sh-route').innerHTML='<h4>Прогноз маршруту'+why+'</h4><ol>'+items.join('')+'</ol>'+(tr.pos_est?'<p class="est">Точне місце не названо — позицію оцінено'+(tr.pred==='learned-origin'?' за типовими маршрутами':' по пункту призначення')+'</p>':'')+lpHtml(tr);}else $('#sh-route').innerHTML=lpHtml(tr);
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
$('#sh-close').onclick=()=>{$('#sheet').hidden=true;if(!follow)sel=null;};
// «Стежити за ціллю»: камера веде ціль, картка ховається, зверху — компактна плашка з живими даними і «Зупинити»
let followPrev=null;
function startFollow(){if(!sel)return;follow=true;const d=DISP.get(sel);$('#sheet').hidden=true;
  if(d)map.flyTo({center:d.p,zoom:Math.max(map.getZoom(),9.2),pitch:tilt?50:0,duration:1400,essential:true});
  const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);followPrev=tr?{last:tr.last,next:tr.next}:null;renderFollow();toast('Стежу за ціллю — камера рухається разом з нею');}
function stopFollow(msg){if(!follow)return;follow=false;$('#follow-pill').hidden=true;if(msg)toast(msg);}
function renderFollow(){const el=$('#follow-pill');if(!follow||!sel){el.hidden=true;return;}
  const tr=SNAP&&SNAP.tracks.find(t=>t.id===sel);if(!tr||tr.status!=='active'){stopFollow('Ціль більше не фіксується — стеження зупинено');return;}
  const d=DISP.get(sel);const r=d&&homeRel(tr,d.p);
  let ev='';if(followPrev&&tr.last!==followPrev.last){ev='нова фіксація '+fmt(tr.last);el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}
  if(followPrev&&tr.next!==followPrev.next&&tr.next)ev='змінила курс → '+tr.next;followPrev={last:tr.last,next:tr.next,ev:ev||followPrev.ev};
  el.innerHTML='<span class="fp-dot" style="background:'+TYPE_COLOR[tr.type]+'"></span><div class="fp-t"><b>'+esc(TYPE_NAME[tr.type])+(tr.count>1?' ×'+tr.count:'')+(tr.next?' → '+esc(tr.next):'')+'</b><span>'+
    (r?Math.round(r.d)+' км '+r.side+' від вас'+(r.eta!=null?' · ~'+Math.max(1,Math.round(r.eta))+' хв до вас':''):'')+(followPrev.ev?' · '+esc(followPrev.ev):'')+' · фіксація '+fmt(tr.last)+'</span></div><button id="fp-card">Картка</button><button id="fp-stop">Зупинити</button>';
  el.hidden=false;$('#fp-stop').onclick=e=>{e.stopPropagation();stopFollow('Стеження зупинено');};$('#fp-card').onclick=e=>{e.stopPropagation();$('#sheet').hidden=false;fillSheet(true);};}
$('#sh-follow').onclick=()=>{if(follow)stopFollow('Стеження зупинено');else startFollow();$('#sh-follow').classList.toggle('on',follow);$('#sh-follow').textContent=follow?'Зупинити стеження':'Стежити за ціллю';};
map.on('dragstart',e=>{if(follow&&e.originalEvent)stopFollow('Ви зсунули карту — стеження зупинено');});
setInterval(()=>{if(follow)renderFollow();},1000);

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
document.querySelectorAll('.tools [data-b]').forEach(b=>b.onclick=()=>{const t=document.getElementById(b.dataset.b);if(!t)return;const keep=b.dataset.b==='b-3d'||b.dataset.b==='b-layers';if(!keep)$('#settings').hidden=true;t.click();});
$('#b-daily').onclick=()=>{location.href='/daily.html';};
if($('#b-an'))$('#b-an').onclick=()=>{location.href='/analysis.html';};
$('#b-feed').onclick=()=>{$('#drawer').hidden=false;renderFeed();};
$('#dr-close').onclick=()=>$('#drawer').hidden=true;

/* ---------- живий потік ---------- */
function onSnap(s){LIVE=s;if(REPLAY)return;SNAP=s;try{notesCheck(s);}catch(e){console.warn(e);}recvAt=Date.now();offset=s.now-Date.now()/1000;renderCounters();renderAsOf();syncLevels();syncZones();syncRaions();renderForecast();if(!$('#drawer').hidden)renderFeed();}
let LIVE=null,REPLAY=null;
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
  syncXray();toast(on?'Рентген неба увімкнено':'Звичайна карта');}
$('#b-xray').onclick=()=>setXray(!XRAY);
{const L=$('#xr-legend');if(L){L.addEventListener('click',()=>setXray(false));L.title='Натисніть, щоб вимкнути рентген';}
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&XRAY)setXray(false);});
 map.on('moveend',()=>{if(XRAY)syncXray();});}
map.on('styledata',()=>{if(XRAY&&map.getLayer('xr-dim')&&map.getLayoutProperty('xr-dim','visibility')!=='visible')setXray(true);});
function syncXray(){if(!XRAY||!SNAP||!map.getSource('xr'))return;const F=[],nm=k=>SNAP.sources[k]?.name||k;
  // лише обрана ціль, або до 6 найсвіжіших цілей у кадрі — інакше «павутиння» на пів країни
  const bb=map.getBounds();const pool=SNAP.tracks.filter(t=>t.status==='active'&&t.ev&&(sel?t.id===sel:bb.contains([t.lon,t.lat]))).sort((a,b)=>b.last-a.last).slice(0,sel?1:6);
  for(const tr of pool){
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
  $('#st-3d').checked=tilt;$('#st-sys').checked=!!PREF.sys&&'Notification' in window&&Notification.permission==='granted';$('#st-ru').checked=!!PREF.ru;$('#st-launch').checked=!!PREF.launch;$('#st-zones').checked=!!PREF.zones;}
function applyLayers(){const vis=(ids,on)=>ids.forEach(i=>{if(map.getLayer(i))map.setLayoutProperty(i,'visibility',on?'visible':'none');});
  vis(['ru-glow','ru-dot','ru-t','hits'],PREF.ru);vis(['chains','lsites','lsites-t'],PREF.launch);vis(['zones','zones-t','avia','avia-z','avia-zl','avia-l'],PREF.zones);}
map.on('styledata',()=>{if(map.getLayer('ru-glow'))applyLayers();});
function syncRu(){if(!SNAP||!map.getSource('ru'))return;
  // останнє зведення МО РФ: на карті — лише точки регіонів (з кількістю, якщо названа) і ОДИН підсумковий підпис
  const ev=(SNAP.ru||[]).slice().sort((a,b)=>b.t-a.t)[0];if(!ev){map.getSource('ru').setData(EMPTY);return;}
  const PER=p=>!p?'':/ноч/.test(p)?'за ніч':/дня/.test(p)?'за день':/суток/.test(p)?'за добу':'';
  const F=ev.regions.map(r=>({type:'Feature',properties:{c:r.cnt?Math.min(12,r.cnt/3):3,l:'наші дрони'+(r.cnt?' ×'+r.cnt:'')+'\n'+r.n,n:r.n,cnt:r.cnt||0},geometry:{type:'Point',coordinates:[r.lon,r.lat]}}));
  const lo=ev.regions.reduce((s,r)=>s+r.lon,0)/ev.regions.length,la=ev.regions.reduce((s,r)=>s+r.lat,0)/ev.regions.length;
  F.push({type:'Feature',properties:{c:0,sum:true,l:'Наші дрони над РФ '+PER(ev.period)+': '+ev.total+' «збитих» за МО РФ · '+ev.regions.length+' рег. · '+fmt(ev.t)},geometry:{type:'Point',coordinates:[lo+1.5,la+0.6]}});
  map.getSource('ru').setData({type:'FeatureCollection',features:F});}
setInterval(syncRu,5000);
let HITS=[];
function syncHits(){if(!SNAP||!map.getSource('hits'))return;const seen=new Map();
  for(const h of (SNAP.hits||[]).slice().sort((a,b)=>b.t-a.t)){const k=h.place+'|'+h.what;if(!seen.has(k))seen.set(k,h);}
  HITS=[...seen.values()];map.getSource('hits').setData({type:'FeatureCollection',features:HITS.map((h,hi)=>({type:'Feature',properties:{hi,l:(h.src==='ASTRA'?'Приліт: ':'Уражено: ')+h.what+'\n'+h.place+' · '+new Date(h.t*1000).toLocaleDateString('uk-UA',{day:'2-digit',month:'2-digit'}),link:h.link},geometry:{type:'Point',coordinates:[h.lon,h.lat]}}))});}
setInterval(syncHits,10000);
$('#b-set').onclick=()=>{$('#settings').hidden=false;syncSettingsUI();loadLan();
  const h=SNAP&&SNAP.health||{},c=h.channels||{};$('#st-tech').textContent='Джерела: '+(c.channels||'—')+' Telegram-каналів моніторингу (наживо '+(c.live||0)+'), офіційні тривоги й фіксації цілей alerts.in.ua (Повітряні сили / War Monitor), заяви МО РФ — для шару «куди летіли наші дрони». Роботу ППО й влучання в Україні не показуємо.';};
$('#st-close').onclick=()=>$('#settings').hidden=true;
$('#st-widget').onclick=()=>window.__openWidget&&window.__openWidget();
document.querySelectorAll('.seg[data-pref]').forEach(g=>g.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const k=g.dataset.pref,v=b.dataset.v;
  if(k==='theme'){PREF.theme=v;PREF.base=null;savePref();applyTheme(true);}
  else if(k==='base'){PREF.base=v;savePref();setBase(v);setTimeout(syncSettingsUI,50);}
  else if(k==='shelter'){SHELTER=+v;localStorage.setItem('shelter',SHELTER);if($('#me-sh'))$('#me-sh').textContent=SHELTER;syncSettingsUI();}}));
$('#st-3d').onchange=e=>set3d(e.target.checked,true);
(function(){const S=window.NXSound;if(!S)return;const g=S.get();
  const segs={'snd-mode':'mode','snd-tone':'tone','snd-voice':'voice'};
  Object.entries(segs).forEach(([id,k])=>{const box=document.getElementById(id);if(!box)return;box.querySelectorAll('button').forEach(b=>{b.classList.toggle('on',b.dataset.v===g[k]);b.onclick=()=>{S.set(k,b.dataset.v);box.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));if(k==='voice'){S.speakOnly('Привіт. Так звучить голос '+b.textContent+'.');}else if(k==='tone'||b.dataset.v!=='off')S.test();};});});
  const vol=document.getElementById('snd-vol');if(vol){vol.value=Math.round(g.vol*100);vol.oninput=()=>S.set('vol',vol.value/100);}
  const tb=document.getElementById('snd-test');if(tb)tb.onclick=()=>S.test();
  const vh=document.getElementById('snd-voice-hint');if(vh)setTimeout(()=>{fetch('/api/tts/status').then(r=>r.json()).then(t=>{vh.textContent=t.piper?'Голоси Лада, Тетяна, Микита, Олекса — українська нейромережева озвучка (Piper)':'Готую українську озвучку на сервері (перший раз кілька хвилин); поки — голос пристрою';}).catch(()=>{});},1200);})();
$('#st-sys').onchange=async e=>{if(e.target.checked&&'Notification' in window&&Notification.permission!=='granted'){const r=await Notification.requestPermission();if(r!=='granted'){e.target.checked=false;toast('Браузер не дозволив сповіщення');}}PREF.sys=e.target.checked;savePref();};
$('#st-ru').onchange=e=>{PREF.ru=e.target.checked;savePref();applyLayers();};
$('#st-launch').onchange=e=>{PREF.launch=e.target.checked;savePref();applyLayers();};
$('#st-zones').onchange=e=>{PREF.zones=e.target.checked;savePref();applyLayers();};
$('#st-geo').onclick=()=>{$('#b-locate').click();};
$('#st-pick').onclick=()=>{$('#settings').hidden=true;setHomeMode=true;$('#b-home').classList.add('on');toast('Торкніться карти, щоб позначити дім');};
$('#st-clear').onclick=()=>{home=null;localStorage.removeItem('home');syncHome();toast('Дім прибрано');};
let lanDone=false;function loadLan(){if(!$('#st-qr'))return;fetch('/api/lan').then(r=>r.json()).then(j=>{lanDone=true;const urls=j.urls||[];const host=location.hostname;
  const sec=(j.secure||[]).sort((a,b)=>(/\/\/192\.168\./.test(b)-/\/\/192\.168\./.test(a)));const best=sec[0]||((host!=='localhost'&&host!=='127.0.0.1')?location.origin:(urls[0]||location.origin));
  $('#st-urls').innerHTML=[...sec,...(urls.length?urls:[location.origin])].map(u=>'<code>'+esc(u)+'</code>').join('');
  try{$('#st-qr').innerHTML='';new QRCode($('#st-qr'),{text:best,width:132,height:132,colorDark:'#0B0F17',colorLight:'#ffffff'});}catch(e){$('#st-qr').textContent=best;}}).catch(()=>{});}
let actx=null;function beep(){try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();const o=actx.createOscillator(),g=actx.createGain();o.type='sine';o.frequency.value=880;o.connect(g);g.connect(actx.destination);
  const t=actx.currentTime;g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(0.3,t+0.02);g.gain.exponentialRampToValueAtTime(0.0001,t+0.5);o.start(t);o.stop(t+0.55);
  const o2=actx.createOscillator();o2.frequency.value=660;o2.connect(g);o2.start(t+0.6);o2.stop(t+1.1);g.gain.setValueAtTime(0.3,t+0.6);g.gain.exponentialRampToValueAtTime(0.0001,t+1.1);}catch(e){}}
window.__beep=(txt)=>{if(window.NXSound)NXSound.alert(txt);else if(PREF.sound)beep();};
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
  if(n.lvl==='red'||n.lvl==='orange'){window.__beep&&window.__beep((n.title||'')+(n.sub?'. '+String(n.sub).replace(/~/g,'приблизно ').replace(/·/g,','):''));if(navigator.vibrate)try{navigator.vibrate([120,60,120]);}catch(e){}}
  if(PREF.sys&&document.hidden&&'Notification' in window&&Notification.permission==='granted'){
    try{const sn=new Notification(n.title,{body:n.sub||'',tag:n.k,icon:'brand/icon-192.png',renotify:false});sn.onclick=()=>{window.focus();n.go&&n.go();sn.close();};}catch(e){}}
}
function notesAll(){const box=$('#notes');let a=box.querySelector('.all');const n=box.querySelectorAll('.note-c').length;
  if(n>=2&&!a){a=document.createElement('button');a.className='all';a.textContent='Закрити всі';a.onclick=()=>{box.innerHTML='';};box.prepend(a);}
  if(n<2&&a)a.remove();}
function flyP(p,z){map.flyTo({center:p,zoom:Math.max(map.getZoom(),z||7),essential:true});}
const TNAME_PL={shahed:'Шахеди',jet:'Реактивні шахеди',molniya:'«Молнії»',cruise:'Крилаті ракети',ballistic:'Балістика',kab:'КАБи',geran5:'«Герань-5»',banderol:'«Бандеролі»',rszv:'РСЗВ',fpv:'FPV-дрони',fpvf:'FPV на оптоволокні',recon:'Дрони-розвідники'};
/* ---------- мої громади й області для сповіщень ---------- */
const NZLV=new Map();
function myZones(){const Z=PREF.nz||{obl:[],hrom:[]};if(!Z.obl.length&&!Z.hrom.length&&home&&window.OBLPOLY){const o=window.OBLPOLY(home[0],home[1]);if(o)return {obl:[o],hrom:[],auto:true};}return Z;}
function ringIn(r,x,y){let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const a=r[i],b=r[j];if(((a[1]>y)!==(b[1]>y))&&(x<(b[0]-a[0])*(y-a[1])/((b[1]-a[1])||1e-12)+a[0]))c=!c;}return c;}
function geomIn(g,x,y){const P=g.type==='Polygon'?[g.coordinates]:g.coordinates;return P.some(p=>ringIn(p[0],x,y));}
function zoneOf(p){const Z=myZones();if(Z.obl.length&&window.OBLPOLY){const o=window.OBLPOLY(p[0],p[1]);if(o&&Z.obl.includes(o))return o+' обл.';}
  if(Z.hrom.length&&HPDATA){for(const h of Z.hrom){const f=HPDATA.features[h.id];if(f&&geomIn(f.geometry,p[0],p[1]))return h.n;}}return null;}
function loadHP(){if(HPDATA||HPLOADING)return Promise.resolve(HPDATA);HPLOADING=true;return fetch('/data/hromadas.geojson').then(r=>r.json()).then(d=>{HPDATA=d;if(map.getSource('hp'))map.getSource('hp').setData(d);HPPREV={};return d;}).catch(()=>{HPLOADING=false;});}
function renderZones(){const ul=$('#st-zones-list');if(!ul)return;const Z=myZones();ul.innerHTML='';
  if(Z.auto)ul.innerHTML='<li><span style="opacity:.75;font-weight:500">Зараз: '+esc(Z.obl[0])+' обл. (за домом). Додайте свої громади або області:</span></li>';
  else if(!Z.obl.length&&!Z.hrom.length)ul.innerHTML='<li><span style="opacity:.75;font-weight:500">Не обрано — сповіщення лише про пуски й про загрози біля дому/моїх місць</span></li>';
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
  // 1) пуски — за налаштуванням (типово так: пуск стосується всієї країни)
  for(const L of (s.launches||[])){const k='L:'+L.site+':'+Math.round((L.t||0)/60);if(first||now-(L.t||now)>1200||PREF.nLaunch===false){NSEEN.add(k);continue;}
    note({k,t:L.t,lvl:'red',ic:'🚀',title:'Пуск: '+L.site,sub:[L.type?(TNAME_PL[L.type]||TYPE_NAME[L.type]):'',L.count?'×'+L.count:'',L.carrier||''].filter(Boolean).join(' · ')||'деталі уточнюються',go:()=>flyP([L.lon,L.lat],6)});}
  // 2) нові цілі — лише ті, що в моїх громадах/областях або летять туди протягом 30 хв (або всі, якщо так обрано)
  const serverT=Date.now()/1000+offset;
  for(const t of (s.tracks||[])){if(t.status!=='active')continue;const k='T:'+t.id;
    if(first||(t.conf||0)<0.5){NSEEN.add(k);continue;}
    if(NSEEN.has(k))continue;
    const fast=['ballistic','cruise','jet'].includes(t.type);
    let z=null;const p0=(DISP.get(t.id)||{p:[t.lon,t.lat]}).p;z=zoneOf(p0);let eta=0;
    if(!z){for(let m=5;m<=30;m+=5){const q=posAt(t,serverT+m*60).p;z=zoneOf(q);if(z){eta=m;break;}}}
    if(!z&&!(PREF.nAll&&fast))continue;   // не моя зона — мовчимо
    note({k,lvl:z?'red':(t.type==='jet'?'orange':'red'),ic:t.type==='ballistic'?'🔺':t.type==='cruise'?'✈️':t.type==='jet'?'🔥':'⚠️',
      title:(TYPE_NAME[t.type]||'Ціль')+(t.count>1?' ×'+t.count:'')+(t.next?' → '+t.next:''),
      sub:z?(eta?'за ~'+eta+' хв буде в зоні «'+z+'»':'у зоні «'+z+'»'):'Нова ціль'+(t.launch&&t.launch.site&&!t.launch.est?' · запуск: '+t.launch.site:''),go:()=>openSheet(t.id)});}
  // 3) тривога / відбій у моїх областях і громадах
  const Z=myZones();
  for(const o of Z.obl){const lv=(s.levels||{})[o]||0,pv=NZLV.get('o:'+o);
    if(pv!==undefined&&!first){if(!pv&&lv)note({k:'A:'+o+':'+Math.round(now),lvl:'red',ic:'🔴',title:'Повітряна тривога: '+o+' обл.',sub:'офіційна тривога'});
      else if(pv&&!lv)note({k:'O:'+o+':'+Math.round(now),lvl:'green',ic:'🟢',title:'Відбій тривоги: '+o+' обл.',sub:'У межах окремих громад тривога може ще тривати'});}
    NZLV.set('o:'+o,lv);}
  const HL=((s.official||{}).hromadas)||{};
  for(const h of Z.hrom){const lv=HL[h.id]||((s.levels||{})[h.o]?1:0),pv=NZLV.get('h:'+h.id);
    if(pv!==undefined&&!first){if(!pv&&lv)note({k:'AH:'+h.id+':'+Math.round(now),lvl:'red',ic:'🔴',title:'Тривога: '+h.n+' громада',sub:h.o+' обл.'});
      else if(pv&&!lv)note({k:'OH:'+h.id+':'+Math.round(now),lvl:'green',ic:'🟢',title:'Відбій: '+h.n+' громада',sub:h.o+' обл.'});}
    NZLV.set('h:'+h.id,lv);}
  // 0) мапа доби о 09:00
  if(s.daily){let seen=null;try{seen=localStorage.getItem('dailySeen');}catch(e){}
    if(seen!==s.daily){try{localStorage.setItem('dailySeen',s.daily);}catch(e){}
      note({k:'D:'+s.daily,lvl:'violet',ic:'🗺️',title:'Мапа доби готова',sub:'Маршрути, пуски й вибухи за добу до 09:00 — натисніть, щоб відкрити',go:()=>{location.href='/daily.html?d='+s.daily;}});}}
  // 4) що вразили наші (офіційно)
  for(const h of (s.hits||[])){const k='H:'+(h.link||'')+':'+h.place+':'+h.what;if(first){NSEEN.add(k);continue;}
    note({k,t:h.t,lvl:'blue',ic:'🎯',title:'Уражено: '+h.what+' · '+h.place,sub:'Генштаб ЗСУ',go:()=>flyP([h.lon,h.lat],7)});}
}

window.__note=note;

/* ---------- «Стеж за мною»: загрози в радіусі R від поточного місця пристрою ---------- */
const FOL={watch:null,pos:null,acc:null,fired:new Map()};
function ringGeo(c,km){const P=xy(c),pts=[];for(let i=0;i<=64;i++){const a=i/64*2*Math.PI;pts.push(ll([P[0]+Math.sin(a)*km,P[1]+Math.cos(a)*km]));}return {type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[pts]}};}
function syncMe(){if(!map.getSource('mepos'))return;map.getSource('mepos').setData(PREF.follow&&FOL.pos?{type:'FeatureCollection',features:[ringGeo(FOL.pos,PREF.radius||10),{type:'Feature',properties:{},geometry:{type:'Point',coordinates:FOL.pos}}]}:EMPTY);}
function followOn(){
  if(!navigator.geolocation){toast('Геолокація недоступна');return false;}
  if(FOL.watch!=null)return true;
  FOL.watch=navigator.geolocation.watchPosition(p=>{const first=!FOL.pos;FOL.pos=[p.coords.longitude,p.coords.latitude];FOL.acc=p.coords.accuracy;syncMe();
      if(first){toast('Стежу за вами · радіус '+(PREF.radius||10)+' км');map.flyTo({center:FOL.pos,zoom:Math.max(map.getZoom(),9.5)});}},
    e=>{toast(e.code===1?'Доступ до геолокації заборонено в браузері':'Не вдалося визначити місце');},{enableHighAccuracy:true,maximumAge:20000,timeout:20000});
  if('Notification' in window&&Notification.permission==='default')Notification.requestPermission().then(r=>{if(r==='granted'){PREF.sys=true;savePref();}});
  return true;}
function followOff(){if(FOL.watch!=null)navigator.geolocation.clearWatch(FOL.watch);FOL.watch=null;FOL.pos=null;FOL.fired.clear();syncMe();}
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
function addPlaceAt(lon,lat){askName('',n=>{PLACES.push({id:Date.now(),name:n,lon:+lon.toFixed(5),lat:+lat.toFixed(5)});savePlaces();toast('📍 «'+n+'» додано — стежу за загрозами поруч');});}
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
        title:(TYPE_NAME[tr.type]||'Ціль')+(tr.count>1?' ×'+tr.count:'')+(inside?' — '+Math.max(1,Math.round(d))+' км '+W.label:' — за ~'+eta+' хв у '+R+' км '+W.label),
        sub:Math.round(d)+' км '+side+(tr.next?' · курс → '+tr.next:''),go:()=>openSheet(tr.id)});
      if(W.k==='me'&&navigator.vibrate)try{navigator.vibrate(inside?[300,120,300,120,300]:[200,100,200]);}catch(e){}
    }
  }
},3000);
{const cb=$('#st-follow'),seg=$('#st-radius');
  if(cb){cb.checked=!!PREF.follow;cb.onchange=()=>{PREF.follow=cb.checked;savePref();if(PREF.follow){if(!followOn()){PREF.follow=false;cb.checked=false;savePref();}}else followOff();};}
  if(seg){const upd=()=>seg.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.v===(PREF.radius||10)));upd();
    seg.onclick=e=>{const b=e.target.closest('button');if(!b)return;PREF.radius=+b.dataset.v;savePref();upd();syncMe();FOL.fired.clear();toast('Радіус '+PREF.radius+' км');};}
  if(PREF.follow)followOn();}
})();
