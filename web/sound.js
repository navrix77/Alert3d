// Звукові сповіщення: режим (вимк / сигнал / голос / сигнал + голос), тип сигналу, гучність, голос (озвучує текст сповіщення), перевірка.
(function(){
  const DEF={mode:'off',tone:'siren',vol:0.7,rate:1.05};
  let S=Object.assign({},DEF);try{const o=JSON.parse(localStorage.getItem('snd')||'null');if(o)S=Object.assign(S,o);else if(JSON.parse(localStorage.getItem('pref')||'{}').sound)S.mode='tone';}catch(e){}
  const save=()=>{try{localStorage.setItem('snd',JSON.stringify(S));}catch(e){}};
  let ac=null;const ctx=()=>{ac=ac||new (window.AudioContext||window.webkitAudioContext)();if(ac.state==='suspended')ac.resume();return ac;};
  function env(g,t,a,d,v){g.gain.setValueAtTime(0.0001,t);g.gain.exponentialRampToValueAtTime(Math.max(0.001,v),t+a);g.gain.exponentialRampToValueAtTime(0.0001,t+a+d);}
  function osc(type,f,t,dur,v,f2){const a=ctx(),o=a.createOscillator(),g=a.createGain();o.type=type;o.frequency.setValueAtTime(f,t);if(f2)o.frequency.linearRampToValueAtTime(f2,t+dur);o.connect(g);g.connect(a.destination);env(g,t,0.02,dur,v);o.start(t);o.stop(t+dur+0.05);}
  const TONES={
    siren:(v)=>{const t=ctx().currentTime;for(let i=0;i<3;i++){osc('sawtooth',520,t+i*0.7,0.33,v*0.35,980);osc('sawtooth',980,t+i*0.7+0.35,0.33,v*0.35,520);}return 2.2;},
    beep:(v)=>{const t=ctx().currentTime;for(let i=0;i<3;i++)osc('square',1000,t+i*0.28,0.16,v*0.3);return 0.9;},
    chime:(v)=>{const t=ctx().currentTime;[[880,0],[1175,0.18],[1568,0.36]].forEach(([f,d])=>osc('sine',f,t+d,0.9,v*0.5));return 1.3;},
    soft:(v)=>{const t=ctx().currentTime;osc('sine',660,t,0.6,v*0.45);osc('sine',440,t+0.55,0.8,v*0.45);return 1.4;},
  };
  let voices=[];const loadV=()=>{try{voices=speechSynthesis.getVoices();}catch(e){}};if('speechSynthesis' in window){loadV();speechSynthesis.onvoiceschanged=loadV;}
  function speak(text){if(!text||!('speechSynthesis' in window))return false;try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);
    const v=voices.find(x=>/^uk/i.test(x.lang))||voices.find(x=>/^ru/i.test(x.lang)&&false);if(v)u.voice=v;u.lang='uk-UA';u.rate=S.rate;u.volume=S.vol;speechSynthesis.speak(u);return true;}catch(e){return false;}}
  function play(text,force){const m=S.mode;if(m==='off'&&!force)return;let wait=0;
    if(m==='tone'||m==='both'||(force&&m==='off'))try{wait=TONES[S.tone](S.vol);}catch(e){}
    if((m==='voice'||m==='both')&&text)setTimeout(()=>speak(text),m==='both'?wait*1000:0);}
  // анти-спам: не частіше ніж раз на 8 с, той самий текст — не частіше ніж раз на 2 хв
  let lastT=0;const said=new Map();
  window.NXSound={get:()=>Object.assign({},S),set(k,v){S[k]=v;save();},hasUkVoice:()=>voices.some(x=>/^uk/i.test(x.lang)),
    alert(text){const now=Date.now();if(now-lastT<8000)return;if(text&&said.has(text)&&now-said.get(text)<120000)return;lastT=now;if(text)said.set(text,now);play(text);},
    test(){const prev=S.mode;play('Тест. Шахед, двадцять кілометрів з півдня, приблизно вісім хвилин до вас.',true);if(prev==='voice'||prev==='both'){}},
    speakOnly:speak};
})();
