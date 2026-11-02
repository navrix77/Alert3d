// Економія ресурсів без втрати функцій: обмеження частоти перемальовування карти.
// 30 кадр/с, коли в кадрі є цілі; 4 кадр/с, коли неба порожнє; 0 — коли вкладку/застосунок згорнуто;
// режим економії (вручну або батарея < 20% без зарядки) — 15 кадр/с і без важкого рельєфу.
(function(){
  const P={saver:false,auto:false,last:0,timer:0};
  try{P.saver=localStorage.getItem('saver')==='1';}catch(e){}
  function fps(){if(document.hidden)return 0;const busy=(window.FX&&window.FX.length)||document.body.classList.contains('intro');
    if(P.saver||P.auto)return busy?15:3;return busy?30:4;}
  window.NXPERF={fps,get saver(){return P.saver||P.auto;},setSaver(v){P.saver=!!v;try{localStorage.setItem('saver',v?'1':'0');}catch(e){}document.dispatchEvent(new Event('nxsaver'));}};
  window.nxRepaint=function(map){if(P.timer)return;const f=fps();if(!f)return;const gap=1000/f,el=performance.now()-P.last;
    P.timer=setTimeout(()=>{P.timer=0;P.last=performance.now();map.triggerRepaint();},Math.max(0,gap-el));};
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&window.tryvogaMap)window.tryvogaMap.triggerRepaint();});
  if(navigator.getBattery)navigator.getBattery().then(b=>{const u=()=>{const a=!b.charging&&b.level<0.2;if(a!==P.auto){P.auto=a;document.dispatchEvent(new Event('nxsaver'));}};u();b.addEventListener('levelchange',u);b.addEventListener('chargingchange',u);}).catch(()=>{});
})();
