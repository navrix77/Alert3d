// Звукові сповіщення: режим (вимк / сигнал / голос / сигнал + голос), тип сигналу, гучність, голос (озвучує текст сповіщення), перевірка.
(function(){
  const DEF={mode:'off',tone:'siren',vol:0.7,rate:1.0,voice:'lada'};
  let S=Object.assign({},DEF);try{const o=JSON.parse(localStorage.getItem('snd')||'null');if(o)S=Object.assign(S,o);else if(JSON.parse(localStorage.getItem('pref')||'{}').sound)S.mode='tone';}catch(e){}
  const save=()=>{try{localStorage.setItem('snd',JSON.stringify(S));}catch(e){}};
  let ac=null;const ctx=()=>{ac=ac||new (window.AudioContext||window.webkitAudioContext)();if(ac.state!=='running')ac.resume();return ac;};
  // iOS: Web Audio мовчить при беззвучному режимі, доки сторінка не відтворить звичайний <audio>, «розблоковуємо» тишею
  const SILENT='data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQQAAACAgICA';
  let unlocked=false;function unlock(){if(unlocked)return;unlocked=true;try{const a=new Audio(SILENT);a.setAttribute('playsinline','');a.loop=true;a.volume=0.01;a.play().catch(()=>{unlocked=false;});}catch(e){unlocked=false;}
    try{ctx();}catch(e){}try{if('speechSynthesis' in window){const u=new SpeechSynthesisUtterance(' ');u.volume=0;speechSynthesis.speak(u);}}catch(e){}}
  // iOS дозволяє програвати без дотику лише той <audio>, який уже запускали з дотику, тому весь голос іде через один елемент
  const VA=new Audio();VA.setAttribute('playsinline','');VA.preload='auto';let vaOk=false;
  function vaUnlock(){if(vaOk)return;try{VA.src=SILENT;const p=VA.play();p&&p.then(()=>{vaOk=true;}).catch(()=>{});}catch(e){}}
  ['touchend','click','keydown'].forEach(ev=>{document.addEventListener(ev,unlock,{passive:true});document.addEventListener(ev,vaUnlock,{passive:true});});
  let vaEnd=null,held=null,alerting=0;
  function vaPlay(url,vol,rate){return new Promise(res=>{let done=false;const fin=ok=>{if(done)return;done=true;if(VA.onended&&vaEnd===fin){VA.onended=VA.onerror=null;}res(ok);};
    if(vaEnd)vaEnd(true);vaEnd=fin;try{VA.pause();}catch(e){}VA.onended=()=>fin(true);VA.onerror=()=>fin(false);try{VA.preservesPitch=true;VA.defaultPlaybackRate=rate||1;}catch(e){}VA.src=url;VA.volume=vol==null?1:vol;try{VA.playbackRate=rate||1;}catch(e){}
    const p=VA.play();if(p)p.catch(()=>fin(false));
    // сторож від зависання: лише якщо звук справді не грає (довге зведення радіо триває й 60+ с - не обриваємо)
    const dog=()=>{if(done)return;if((held&&held.fin===fin)||(vaEnd===fin&&!VA.paused&&!VA.ended)){setTimeout(dog,5000);return;}fin(true);};setTimeout(dog,30000);});}
  // 04.11 власник: сповіщення важливіше за радіо й ефір: їхній голос ставиться на паузу, звучить сповіщення, потім продовжується з того ж місця
  function hold(){if(held||alerting>1)return;try{if(vaEnd&&!VA.paused&&!VA.ended){held={src:VA.src,t:VA.currentTime,fin:vaEnd,vol:VA.volume,rate:VA.defaultPlaybackRate};vaEnd=null;VA.onended=VA.onerror=null;VA.pause();}}catch(e){held=null;}}
  function unhold(){const h=held;held=null;if(!h)return;vaEnd=h.fin;VA.onended=()=>h.fin(true);VA.onerror=()=>h.fin(false);
    try{try{VA.defaultPlaybackRate=h.rate||1;}catch(e){}VA.src=h.src;VA.volume=h.vol;try{VA.playbackRate=h.rate||1;}catch(e){}const go=()=>{try{VA.currentTime=Math.max(0,h.t-0.5);}catch(e){}const p=VA.play();if(p)p.catch(()=>h.fin(false));};
      if(VA.readyState>=1)go();else VA.addEventListener('loadedmetadata',go,{once:true});}catch(e){h.fin(false);}}
  const fire=on=>{try{window.dispatchEvent(new CustomEvent('sky-alert',{detail:{on}}));}catch(e){}};
  const afterAlert=()=>new Promise(r=>{if(!alerting)return r();const f=e=>{if(!e.detail.on){removeEventListener('sky-alert',f);r();}};addEventListener('sky-alert',f);});
  window.SKYVOICE={play:(url,vol,rate)=>alerting?afterAlert().then(()=>vaPlay(url,vol,rate)):vaPlay(url,vol,rate),stop:()=>{try{VA.pause();}catch(e){}if(vaEnd)vaEnd(true);},get alerting(){return alerting>0;}};
  function env(g,t,a,d,v){g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(Math.max(0.001,v),t+a);g.gain.exponentialRampToValueAtTime(0.0001,t+a+d);}
  function osc(type,f,t,dur,v,f2){const a=ctx(),o=a.createOscillator(),g=a.createGain();o.type=type;o.frequency.setValueAtTime(f,t);if(f2)o.frequency.linearRampToValueAtTime(f2,t+dur);o.connect(g);g.connect(a.destination);env(g,t,0.02,dur,v);o.start(t);o.stop(t+dur+0.05);}
  const TONES={
    siren:(v)=>{const t=ctx().currentTime;for(let i=0;i<3;i++){osc('sawtooth',520,t+i*0.7,0.33,v*0.35,980);osc('sawtooth',980,t+i*0.7+0.35,0.33,v*0.35,520);}return 2.2;},
    beep:(v)=>{const t=ctx().currentTime;for(let i=0;i<3;i++)osc('square',1000,t+i*0.28,0.16,v*0.3);return 0.9;},
    chime:(v)=>{const t=ctx().currentTime;[[880,0],[1175,0.18],[1568,0.36]].forEach(([f,d])=>osc('sine',f,t+d,0.9,v*0.5));return 1.3;},
    soft:(v)=>{const t=ctx().currentTime;osc('sine',660,t,0.6,v*0.45);osc('sine',440,t+0.55,0.8,v*0.45);return 1.4;},
  };
  let voices=[];const loadV=()=>{try{voices=speechSynthesis.getVoices();}catch(e){}};if('speechSynthesis' in window){loadV();speechSynthesis.onvoiceschanged=loadV;}
  // голос: серверна українська озвучка (Piper: Лада/Микита/Тетяна/Олекса), а якщо сервер ще не готовий, голос пристрою
  let curA=null;
  // speak повертає Promise, що завершується, коли голос договорив (потрібно, щоб знати, коли продовжити радіо)
  function speak(text){if(!text)return Promise.resolve(false);
    // 04.11: спершу із заготовок (фрази з кешу, без нових витрат), якщо ні - озвучка цілим текстом, далі голос пристрою
    if(S.voice&&S.voice!=='device'){try{const q='voice='+encodeURIComponent(S.voice)+'&rate='+S.rate+'&text='+encodeURIComponent(text);
      return vaPlay('/api/voice/alert?'+q,S.vol).then(ok=>ok||vaPlay('/api/tts?v=3&'+q,S.vol)).then(ok=>ok||sysSpeak(text));}catch(e){}}
    return sysSpeak(text);}
  function sysSpeak(text){return new Promise(res=>{if(!text||!('speechSynthesis' in window))return res(false);try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);
    const v=voices.find(x=>/^uk/i.test(x.lang))||voices.find(x=>/^ru/i.test(x.lang)&&false);if(v)u.voice=v;u.lang='uk-UA';u.rate=S.rate;u.volume=S.vol;
    u.onend=u.onerror=()=>res(true);speechSynthesis.speak(u);setTimeout(()=>res(true),20000);}catch(e){res(false);}});}
  // 04.11 власник: режим «Вібро» (без звуку). Android: Vibration API. iPhone/Safari його не має, тому пробуємо тактильний відгук
  // перемикача (iOS 17.4+; часом потребує дотику до екрана), а доставку із закритим застосунком робить push (вібрація за налаштуваннями iOS).
  const VIB=[400,150,400,150,400,150,800];
  let hapt=null;function vib(p){let ok=false;try{if(navigator.vibrate)ok=navigator.vibrate(p||VIB);}catch(e){}
    if(!ok)try{if(!hapt){const l=document.createElement('label');l.style.cssText='position:fixed;left:-99px;top:-99px;opacity:0;pointer-events:none';l.innerHTML='<input type="checkbox" switch>';document.body.appendChild(l);hapt=l;}
      let n=0;const t=setInterval(()=>{hapt.click();if(++n>=6)clearInterval(t);},180);ok=true;}catch(e){}
    return ok;}
  async function play(text,force){const m=S.mode;if(m==='off'&&!force)return;let wait=0;
    if(m==='vibro'){vib();return;}
    alerting++;fire(true);hold();
    try{if(m==='tone'||m==='both'||(force&&m==='off'))try{wait=TONES[S.tone](S.vol);}catch(e){}
      if(wait)await new Promise(r=>setTimeout(r,wait*1000));
      if((m==='voice'||m==='both')&&text)await speak(text);
      await new Promise(r=>setTimeout(r,400));}
    finally{alerting--;if(!alerting){fire(false);unhold();}}}
  // анти-спам: не частіше ніж раз на 8 с, той самий текст, не частіше ніж раз на 2 хв
  let lastT=0;const said=new Map();
  window.NXSound={get:()=>Object.assign({},S),set(k,v){S[k]=v;save();},hasUkVoice:()=>voices.some(x=>/^uk/i.test(x.lang)),
    alert(text){const now=Date.now();if(now-lastT<8000)return;if(text&&said.has(text)&&now-said.get(text)<120000)return;lastT=now;if(text)said.set(text,now);play(text);},
    test(){unlock();const txt='Тест. Шахед, двадцять кілометрів з півдня, приблизно вісім хвилин до вас.';const m=S.mode;
      if(m==='vibro'){vib();return;}
      if(m==='voice'||m==='both')speak(txt);            // голос, одразу в межах натискання (вимога iOS)
      if(m!=='voice')try{TONES[S.tone](S.vol);}catch(e){}  // сигнал (у режимі «Вимк», теж, щоб почути звук)
    },
    speakOnly:speak};
})();
