// 3D-режим: рельєф, небо і 3D-моделі цілей (Three.js у шарі MapLibre).
(()=>{
'use strict';
if(!window.THREE){console.warn('THREE не завантажився — 3D-моделі вимкнено');window.T3D={enable(){},disable(){}};return;}
const RGB=h=>{h=h.replace('#','');return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)];};
const D2R=Math.PI/180;
function soft(hex,k){const c=RGB(hex);return new THREE.Color(...c.map(v=>(v+(255-v)*k)/255));}
function lathe(prof,seg){const g=new THREE.LatheGeometry(prof.map(([y,r])=>new THREE.Vector2(r,y)),seg||28);g.rotateZ(-Math.PI/2);return g;}
function body(len,r,nose,tail){const p=[];const N=18;for(let i=0;i<=N;i++){const t=i/N;const y=-len/2+t*len;let rr=r;if(t<tail)rr=r*(0.55+0.45*Math.sin(t/tail*Math.PI/2));if(t>1-nose){const u=(t-(1-nose))/nose;rr=r*Math.cos(u*Math.PI/2);}p.push([y,Math.max(rr,0.0005)]);}return lathe(p);}
function wingG(pts,th){const sh=new THREE.Shape();pts.forEach(([x,z],i)=>i?sh.lineTo(x,z):sh.moveTo(x,z));sh.closePath();const g=new THREE.ExtrudeGeometry(sh,{depth:th,bevelEnabled:true,bevelThickness:th*0.45,bevelSize:th*0.6,bevelSegments:3,curveSegments:6});g.rotateX(Math.PI/2);g.translate(0,th/2,0);return g;}
function finG(pts,th){const sh=new THREE.Shape();pts.forEach(([x,y],i)=>i?sh.lineTo(x,y):sh.moveTo(x,y));sh.closePath();const g=new THREE.ExtrudeGeometry(sh,{depth:th,bevelEnabled:true,bevelThickness:th*0.4,bevelSize:th*0.5,bevelSegments:2,curveSegments:4});g.translate(0,0,-th/2);return g;}
function mat(hex,k,extra){const c=new THREE.Color(hex);if(k<0)c.multiplyScalar(1+k);else c.lerp(new THREE.Color(0xffffff),k*0.5);return new THREE.MeshStandardMaterial(Object.assign({color:c,roughness:0.38,metalness:0.25},extra||{}));}
function buildModel(type){
  const g=new THREE.Group();const c=TYPE_COLOR[type];const mB=mat(c,0),mW=mat(c,-0.18),mD=mat('#2A3448',0.1,{roughness:0.5});
  const add=(geo,m,x,y,z)=>{const o=new THREE.Mesh(geo,m);o.position.set(x||0,y||0,z||0);g.add(o);return o;};
  if(type==='shahed'){add(body(1,0.05,0.18,0.12),mB);add(wingG([[0.2,0],[-0.42,0.5],[-0.5,0.5],[-0.5,-0.5],[-0.42,-0.5]],0.02),mW);
    [0.5,-0.5].forEach(z=>add(finG([[-0.42,0],[-0.5,0],[-0.5,0.17],[-0.46,0.17]],0.012),mW,0,0,z));
    const pr=add(new THREE.CylinderGeometry(0.1,0.1,0.006,32),new THREE.MeshStandardMaterial({color:0xffffff,transparent:true,opacity:0.22,roughness:0.2}),-0.53,0,0);pr.rotation.z=Math.PI/2;g.userData.prop=pr;}
  else if(type==='jet'){add(body(1.05,0.052,0.24,0.1),mB);add(body(0.34,0.03,0.2,0.3),mD,-0.12,0.065,0);add(wingG([[0.12,0],[-0.44,0.34],[-0.5,0.34],[-0.5,-0.34],[-0.44,-0.34]],0.018),mW);add(finG([[-0.28,0.05],[-0.5,0.05],[-0.5,0.22],[-0.42,0.22]],0.012),mW);
    const ex=add(new THREE.CircleGeometry(0.035,24),new THREE.MeshBasicMaterial({color:0xffd9a0}),-0.53,0,0);ex.rotation.y=-Math.PI/2;}
  else if(type==='molniya'){add(body(0.9,0.055,0.2,0.2),mB);add(wingG([[0.09,0.5],[-0.07,0.5],[-0.07,-0.5],[0.09,-0.5]],0.018),mW);
    [1,-1].forEach(sg=>{const f=add(finG([[-0.32,0],[-0.46,0],[-0.46,0.17],[-0.4,0.17]],0.01),mW,0,0.03,0.04*sg);f.rotation.x=sg*0.6;});
    const pr=add(new THREE.CylinderGeometry(0.08,0.08,0.005,28),new THREE.MeshStandardMaterial({color:0xffffff,transparent:true,opacity:0.22}),0.46,0,0);pr.rotation.z=Math.PI/2;g.userData.prop=pr;}
  else if(type==='cruise'){add(body(1,0.038,0.16,0.06),mB);add(wingG([[0.06,0],[-0.06,0.27],[-0.12,0.27],[-0.08,0],[-0.12,-0.27],[-0.06,-0.27]],0.012),mW);
    add(finG([[-0.4,0.03],[-0.5,0.03],[-0.5,0.14],[-0.46,0.14]],0.01),mW);[1,-1].forEach(sg=>{const f=add(finG([[-0.4,0],[-0.5,0],[-0.5,0.11],[-0.46,0.11]],0.01),mW);f.rotation.x=sg*2.2;});}
  else if(type==='ballistic'){add(body(1,0.065,0.32,0.02),mB);for(let k=0;k<4;k++){const f=add(finG([[-0.34,0.05],[-0.5,0.05],[-0.5,0.16],[-0.44,0.16]],0.012),mW);f.rotation.x=k*Math.PI/2+Math.PI/4;}
    const ex=add(new THREE.CircleGeometry(0.05,24),new THREE.MeshBasicMaterial({color:0xffe2b0}),-0.505,0,0);ex.rotation.y=-Math.PI/2;}
  else if(type==='kab'){add(body(0.85,0.09,0.22,0.22),mB);add(wingG([[0.06,0.46],[-0.04,0.46],[-0.04,-0.46],[0.06,-0.46]],0.012),mW,0,0.09,0);for(let k=0;k<4;k++){const f=add(finG([[-0.3,0.07],[-0.43,0.07],[-0.43,0.17],[-0.38,0.17]],0.01),mW);f.rotation.x=k*Math.PI/2+Math.PI/4;}}
  // темний контур по силуету (back-face outline) — модель читається на будь-якій підкладці
  const outl=new THREE.MeshBasicMaterial({color:0x0b0b10,side:THREE.BackSide});
  [...g.children].forEach(m=>{if(!m.isMesh||m.material.transparent||m.material.type==='MeshBasicMaterial')return;const o=new THREE.Mesh(m.geometry,outl);o.position.copy(m.position);o.rotation.copy(m.rotation);o.scale.copy(m.scale).multiplyScalar(1.07);g.add(o);});
  const up=new THREE.Group();up.rotation.x=Math.PI/2;up.add(g);up.userData=g.userData;return up;
}
let SHADOW_TEX=null;
function shadowTex(){if(SHADOW_TEX)return SHADOW_TEX;const cv=document.createElement('canvas');cv.width=cv.height=128;const x=cv.getContext('2d');const gr=x.createRadialGradient(64,64,4,64,64,62);gr.addColorStop(0,'rgba(0,0,0,0.55)');gr.addColorStop(0.6,'rgba(0,0,0,0.18)');gr.addColorStop(1,'rgba(0,0,0,0)');x.fillStyle=gr;x.fillRect(0,0,128,128);SHADOW_TEX=new THREE.CanvasTexture(cv);return SHADOW_TEX;}

const ALT={shahed:1800,jet:3500,molniya:900,cruise:1200,ballistic:12000,kab:2500};
const SIZE={shahed:30,jet:34,molniya:22,cruise:32,ballistic:36,kab:24};
const layer={id:'t3d',type:'custom',renderingMode:'3d',
  onAdd(map,gl){this.map=map;this.camera=new THREE.Camera();this.scene=new THREE.Scene();
    const hemi=new THREE.HemisphereLight(0xeef3ff,0x202634,0.55);hemi.position.set(0,0,1);this.scene.add(hemi);
    const sun=new THREE.DirectionalLight(0xffffff,1.35);sun.position.set(-0.6,-1,1.6);this.scene.add(sun);
    const rim=new THREE.DirectionalLight(0x9cc7ff,0.45);rim.position.set(1,1,0.4);this.scene.add(rim);
    this.renderer=new THREE.WebGLRenderer({canvas:map.getCanvas(),context:gl,antialias:true});this.renderer.autoClear=false;
    this.origin=maplibregl.MercatorCoordinate.fromLngLat([33,49],0);this.s=this.origin.meterInMercatorCoordinateUnits();this.objs=new Map();},
  toM(ll,z){const mc=maplibregl.MercatorCoordinate.fromLngLat(ll,z||0);return [(mc.x-this.origin.x)/this.s,-(mc.y-this.origin.y)/this.s];},
  mkShadow(){return new THREE.Mesh(new THREE.PlaneGeometry(1,1),new THREE.MeshBasicMaterial({map:shadowTex(),transparent:true,depthWrite:false}));},
  sync(){
    const heads=(window.T3D&&window.T3D.heads)||[];const seen=new Set();const map=this.map;
    const mpp=40075016*Math.cos(49*D2R)/(512*Math.pow(2,map.getZoom()));
    const k=Math.max(0.55,Math.min(1.2,(map.getZoom()-4.5)/3));
    for(const h of heads){
      let o=this.objs.get(h.id);
      if(!o||o.type!==h.type){if(o)this.scene.remove(o.grp);const model=buildModel(h.type);const sh=this.mkShadow();const grp=new THREE.Group();grp.add(model);grp.add(sh);const col=new THREE.Color(TYPE_COLOR[h.type]);const lg=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0),new THREE.Vector3(0,0,1)]);const tether=new THREE.Line(lg,new THREE.LineBasicMaterial({color:col,transparent:true,opacity:0.85}));grp.add(tether);const dot=new THREE.Mesh(new THREE.CircleGeometry(1,32),new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:0.95,depthWrite:false}));grp.add(dot);const ring=new THREE.Mesh(new THREE.RingGeometry(1.25,1.6,40),new THREE.MeshBasicMaterial({color:0x0b0b10,transparent:true,opacity:0.8,depthWrite:false}));grp.add(ring);this.scene.add(grp);o={grp,model,sh,tether,dot,ring,type:h.type};this.objs.set(h.id,o);}
      seen.add(h.id);
      let ground=0;try{ground=map.queryTerrainElevation?(map.queryTerrainElevation(h.p)||0):0;}catch(e){}
      const [x,y]=this.toM(h.p);o.grp.position.set(x,y,0);
      const size=SIZE[h.type]*mpp*k;const alt=Math.max(ALT[h.type],size*2.2);
      o.model.position.set(0,0,ground+alt);o.model.scale.setScalar(size);o.model.rotation.set(Math.PI/2,0,0);
      o.model.rotateOnWorldAxis(new THREE.Vector3(0,0,1),(90-h.hd)*D2R);
      o.sh.position.z=ground+30;o.sh.scale.setScalar(size*1.3);o.sh.material.opacity=0.55;
      o.tether.position.z=ground+40;o.tether.scale.set(1,1,Math.max(1,alt-40));
      const ds=Math.max(3*mpp,size*0.09);o.dot.position.z=ground+45;o.dot.scale.setScalar(ds);o.ring.position.z=ground+44;o.ring.scale.setScalar(ds);
      o.model.traverse(m=>{if(m.material&&m.material.color&&!m.material.map){m.material.transparent=!h.active||h.weak;m.material.opacity=h.active?(h.weak?0.55:1):0.35;}});
      if(o.model.userData.prop)o.model.userData.prop.rotation.x+=0.6;
    }
    for(const [id,o] of this.objs)if(!seen.has(id)){this.scene.remove(o.grp);this.objs.delete(id);}
  },
  render(gl,args){
    try{this.sync();
      const m=args&&args.defaultProjectionData?args.defaultProjectionData.mainMatrix:args;
      const l=new THREE.Matrix4().makeTranslation(this.origin.x,this.origin.y,this.origin.z).scale(new THREE.Vector3(this.s,-this.s,this.s));
      this.camera.projectionMatrix=new THREE.Matrix4().fromArray(m).multiply(l);
      this.renderer.resetState();this.renderer.render(this.scene,this.camera);this.map.triggerRepaint();
    }catch(e){console.error('3D',e);}
  }};
const DEM='https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
window.T3D={heads:[],on:false,
  enable(map){this.on=true;
    if(!map.getSource('dem'))map.addSource('dem',{type:'raster-dem',tiles:[DEM],tileSize:256,encoding:'terrarium',maxzoom:13,attribution:'Рельєф: Mapzen/AWS Terrain Tiles'});
    if(!map.getSource('dem-h'))map.addSource('dem-h',{type:'raster-dem',tiles:[DEM],tileSize:256,encoding:'terrarium',maxzoom:13});
    if(!map.getLayer('hill'))map.addLayer({id:'hill',type:'hillshade',source:'dem-h',paint:{'hillshade-exaggeration':0.35,'hillshade-shadow-color':'#000','hillshade-highlight-color':'#fff'}},map.getLayer('obl-fill')?'obl-fill':undefined);
    try{map.setTerrain({source:'dem',exaggeration:1.6});}catch(e){}
    try{map.setSky({'sky-color':'#8EC1F0','horizon-color':'#DCE9F7','fog-color':'#B9CCE0','sky-horizon-blend':0.5,'horizon-fog-blend':0.6,'fog-ground-blend':0.8,'atmosphere-blend':0.6});}catch(e){}
    // цілі показуються реалістичними спрайтами (шар tg) — процедурні 3D-моделі вимкнено
  },
  disable(map){this.on=false;try{map.setTerrain(null);}catch(e){}
    if(map.getLayer('t3d'))map.removeLayer('t3d');if(map.getLayer('hill'))map.removeLayer('hill');
    ['tg','tg-n'].forEach(id=>map.getLayer(id)&&map.setLayoutProperty(id,'visibility','visible'));layer.objs&&layer.objs.clear();}
};
})();
