// Крейсер «Москва»: кінематографічна сцена при натисканні на значок у Чорному морі.
// Озвучка — файл web/media/ship.mp3 (якщо покладено); хвилі й вибухи синтезуються в браузері.
(function(){
let busy=false,AC=null;
function sfx(){try{AC=AC||new (window.AudioContext||window.webkitAudioContext)();AC.resume&&AC.resume();}catch(e){return null;}
  const ac=AC,out=ac.createGain();out.gain.value=0.9;out.connect(ac.destination);
  // хвилі: коричневий шум з повільною «дихаючою» гучністю
  const len=ac.sampleRate*12,buf=ac.createBuffer(1,len,ac.sampleRate),d=buf.getChannelData(0);let l=0;
  for(let i=0;i<len;i++){const w=Math.random()*2-1;l=(l+0.02*w)/1.02;d[i]=l*3.2;}
  const src=ac.createBufferSource();src.buffer=buf;const lp=ac.createBiquadFilter();lp.type='lowpass';lp.frequency.value=700;
  const g=ac.createGain();g.gain.value=0;src.connect(lp);lp.connect(g);g.connect(out);const t0=ac.currentTime;
  g.gain.linearRampToValueAtTime(0.35,t0+1.2);for(let k=0;k<6;k++){g.gain.linearRampToValueAtTime(0.18,t0+1.8+k*1.7);g.gain.linearRampToValueAtTime(0.38,t0+2.6+k*1.7);}
  src.start();
  function boom(at,vol){const n=ac.createBufferSource();const b=ac.createBuffer(1,ac.sampleRate*2.5,ac.sampleRate),q=b.getChannelData(0);for(let i=0;i<q.length;i++)q[i]=(Math.random()*2-1)*Math.pow(1-i/q.length,3);
    n.buffer=b;const f=ac.createBiquadFilter();f.type='lowpass';f.frequency.setValueAtTime(1800,t0+at);f.frequency.exponentialRampToValueAtTime(90,t0+at+1.6);
    const bg=ac.createGain();bg.gain.value=vol;n.connect(f);f.connect(bg);bg.connect(out);n.start(t0+at);
    const o=ac.createOscillator();o.type='sine';o.frequency.setValueAtTime(70,t0+at);o.frequency.exponentialRampToValueAtTime(28,t0+at+1.2);const og=ac.createGain();og.gain.setValueAtTime(vol*0.9,t0+at);og.gain.exponentialRampToValueAtTime(0.001,t0+at+1.4);o.connect(og);og.connect(out);o.start(t0+at);o.stop(t0+at+1.5);}
  boom(2.4,1.0);boom(3.1,0.7);
  return {stop(){try{out.gain.linearRampToValueAtTime(0,ac.currentTime+0.6);setTimeout(()=>{try{src.stop();}catch(e){}},700);}catch(e){}}};}
function play(){if(busy)return;busy=true;
  const el=document.createElement('div');el.className='cine';
  el.innerHTML='<div class="cine-img"><img src="media/moskva.jpg" alt=""></div><div class="cine-flash"></div><div class="cine-bar t"></div><div class="cine-bar b"></div>'+
    '<div class="cine-cap"><small>острів Зміїний · 24 лютого 2022</small><q></q><em>Крейсер «Москва» — на дні Чорного моря з 14 квітня 2022</em></div><div class="cine-hint">торкніться, щоб закрити</div>';
  document.body.appendChild(el);const s=sfx();
  const voice=new Audio('media/ship.mp3');voice.preload='auto';let vOk=false;voice.oncanplaythrough=()=>{vOk=true;};
  requestAnimationFrame(()=>el.classList.add('on'));
  const T=[];const at=(ms,f)=>T.push(setTimeout(f,ms));
  at(2350,()=>{el.classList.add('boom');setTimeout(()=>el.classList.remove('boom'),700);});
  at(3050,()=>{el.classList.add('boom');setTimeout(()=>el.classList.remove('boom'),600);});
  at(3600,()=>{voice.play().catch(()=>{});type(el.querySelector('q'),'Русский военный корабль, иди на х**!');});
  at(7400,()=>el.classList.add('fin'));
  const close=()=>{T.forEach(clearTimeout);try{voice.pause();}catch(e){}s&&s.stop();el.classList.remove('on');el.classList.add('off');setTimeout(()=>{el.remove();busy=false;},700);document.removeEventListener('keydown',esc);};
  const esc=e=>{if(e.key==='Escape')close();};document.addEventListener('keydown',esc);
  setTimeout(()=>el.addEventListener('click',close),800);}
function type(q,txt){let i=0;q.classList.add('on');const iv=setInterval(()=>{q.textContent=txt.slice(0,++i);if(i>=txt.length)clearInterval(iv);},55);}
window.playMoskva=play;
function hook(){const m=window.tryvogaMap;if(!m){setTimeout(hook,500);return;}
  const bind=()=>{if(!m.getLayer('memo')){setTimeout(bind,800);return;}
    m.on('click','memo',e=>{const f=e.features&&e.features[0];if(f&&f.properties.i==='moskva')play();});
    m.on('mouseenter','memo',e=>{const f=e.features&&e.features[0];if(f&&f.properties.i==='moskva')m.getCanvas().style.cursor='pointer';});
    m.on('mouseleave','memo',()=>{m.getCanvas().style.cursor='';});};
  bind();}
hook();
})();
