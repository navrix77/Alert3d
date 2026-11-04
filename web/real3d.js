// Справжні 3D-моделі міст: Google Photorealistic 3D Tiles через deck.gl поверх MapLibre.
// Вмикається в налаштуваннях, коли на сервері задано GOOGLE_TILES_KEY. Підвантажується лише за потреби.
(function(){
let overlay=null,loading=false,credits='';
const KEY=()=>(window.NXCFG&&NXCFG.gtilesKey)||null;
function load(src){return new Promise((ok,err)=>{const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=err;document.head.appendChild(s);});}
async function on(){const map=window.tryvogaMap,key=KEY();if(!map||!key||overlay||loading)return false;loading=true;
  try{if(!window.deck)await load('https://unpkg.com/deck.gl@9.0.38/dist.min.js');
    const {MapboxOverlay,Tile3DLayer}=window.deck;
    const before=['zones','trails','fx'].find(id=>map.getLayer(id));
    const layer=new Tile3DLayer({id:'g3d',beforeId:before,data:'https://tile.googleapis.com/v1/3dtiles/root.json',
      loadOptions:{fetch:{headers:{'X-GOOG-API-KEY':key}}},operation:'terrain+draw',
      onTilesetLoad:ts=>{ts.options.onTraversalComplete=sel=>{const c=new Set();sel.forEach(t=>{const s=(t.content&&t.content.gltf&&t.content.gltf.asset&&t.content.gltf.asset.copyright)||'';s.split(';').forEach(x=>x.trim()&&c.add(x.trim()));});credits=[...c].join('; ');setCredit();return sel;};}});
    overlay=new MapboxOverlay({interleaved:true,layers:[layer]});map.addControl(overlay);
    if(map.getLayer('bld3d'))map.setLayoutProperty('bld3d','visibility','none');
    if(map.getZoom()<14)map.flyTo({center:[36.2304,49.9935],zoom:15.6,pitch:62,bearing:-25,duration:2600,essential:true});
    setCredit();return true;}
  catch(e){console.warn('3D tiles',e);return false;}finally{loading=false;}}
function off(){const map=window.tryvogaMap;if(overlay&&map){map.removeControl(overlay);overlay=null;}if(map&&map.getLayer('bld3d'))map.setLayoutProperty('bld3d','visibility','visible');setCredit();}
function setCredit(){let el=document.getElementById('g3d-credit');
  if(!overlay){if(el)el.remove();return;}
  if(!el){el=document.createElement('div');el.id='g3d-credit';document.body.appendChild(el);}
  el.innerHTML='<b>Google</b>'+(credits?' · '+credits.replace(/[<>&]/g,''):'');}
window.Real3D={on,off,available:()=>!!KEY(),active:()=>!!overlay};
})();
