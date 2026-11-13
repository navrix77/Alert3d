// «Арсенал»: чим РФ обстрілює Україну, ТТХ із відкритих джерел + що є на мапі NAVRYX SKY
(function(){
const A=[
 {"t":"shahed","n":"«Шахед-136» / «Герань-2»","k":"Ударний БпЛА-камікадзе","s":[["Швидкість","~180 км/год"],["Дальність","1000–2500 км"],["Бойова частина","50–90 кг"],["Запуск","з території РФ і окупованого Криму"],["Час у повітрі","кілька годин, до 14 год на граничну дальність"]],"d":"Летить низько й повільно, характерний звук «мопеда». Разом із ним запускають «Гербери» й «Гарпії»."},
 {"t":"jet","n":"«Герань-3» / «Герань-4»","k":"Реактивний ударний БпЛА","s":[["Швидкість","300–370 км/год; «Герань-4» до 500 км/год"],["Висота","«Герань-4»: до 5 км"],["Дальність","до 1000 км («Герань-3»), до 450 км («Герань-4»)"],["Бойова частина","50 або 90 кг"],["Час у повітрі","≈2–3 год"]],"d":"Удвічі-втричі швидший за звичайний «Шахед», часу на реакцію значно менше. Канали пишуть «реактивний БпЛА / реактивний шахед»."},
 {"t":"geran5","n":"«Герань-5»","k":"Реактивний дрон-ракета","s":[["Швидкість","450–600 км/год"],["Дальність","до ~950 км"],["Маса","~850 кг; БЧ ~90 кг, довжина ~6 м, розмах до 5,5 м"],["Висота","до 6 км, фіксували 200 м – 3 км"],["Носії","наземний запуск"],["Час у повітрі","до 2 год"]],"d":"Ближчий до крилатої ракети, ніж до дрона. Показуємо окремо, лише коли канал прямо пише «Герань-5»."},
 {"t":"molniya","n":"«Молнія»","k":"Малий ударний БпЛА літакового типу","s":[["Швидкість","~100–120 км/год"],["Дальність","десятки км від лінії фронту"],["Бойова частина","кілька кг"],["Час у повітрі","не встановлено"]],"d":"Дешевий дрон для ударів по прифронтових містах і техніці. Діє в межах кількох десятків кілометрів від фронту."},
 {"t":"cruise","n":"Крилаті ракети: Х-101, «Калібр», Х-59/69, «Іскандер-К»","i":"cruise","g":[["kalibr","Калібр"],["x59","Х-59"],["x69","Х-69"],["iskander","Іскандер-К"]],"k":"Дозвукові крилаті ракети","s":[["Х-101","до 2500–2800 км, БЧ 450 кг; Ту-95МС, Ту-160"],["Х-59/Х-69","до 290/400 км, БЧ ~310 кг; Су-34/Су-35"],["«Іскандер-К»","наземний запуск, сотні км"],["Час у повітрі","від десятків хвилин до кількох годин"]],"d":"Летять низько, огинаючи рельєф, з маневрами. Від пуску до цілі, від десятків хвилин до кількох годин."},
 {"t":"cruise","n":"Х-22 / Х-32","i":"x22","k":"Надзвукові протикорабельні ракети","s":[["Швидкість","до ~4000 км/год"],["Дальність","600–1000 км"],["Бойова частина","до ~950 кг (Х-22)"],["Носій","Ту-22М3"],["Час у повітрі","хвилини, залежить від траєкторії"]],"d":"Дуже неточні на суші, тому особливо небезпечні для житлових кварталів. На мапі, як крилата ракета."},
 {"t":"banderol","n":"«Бандероль» (S8000)","k":"Мала крилата ракета","s":[["Швидкість","до 650 км/год, крейсерська ~560"],["Бойова частина","114 кг (49,5 кг ВР)"],["Носії","БпЛА «Оріон», вертоліт Мі-28Н"],["Час у повітрі","≈1 год на 500 км"],["Дальність","до 500–600 км"]],"d":"Порівняно дешева ракета з комерційним двигуном. Показуємо окремо, лише коли канал прямо пише «Бандероль»."},
 {"t":"cruise","n":"«Філін»","k":"Мала крилата ракета наземного пуску","s":[["Швидкість","заявлено до 800 км/год"],["Дальність","до 1200 км"],["Бойова частина","50 або 100 кг"],["Висота","від наднизьких до 6 км"],["Запуск","наземна установка"]],"d":"Нова мала крилата ракета наземного пуску; на мапі — як крилата ціль."},
 {"t":"ballistic","n":"«Кинджал» (9-С-7760 / Х-47М2)","i":"kinzhal","g":[["mig31","Носій МіГ-31К/І"]],"k":"Аеробалістична ракета, носій МіГ-31К/І","s":[["Клас","аеробалістична, твердопаливна, одноступенева"],["Носії","МіГ-31К / МіГ-31І"],["Дальність","до 1000–2000 км, БЧ 450 кг"],["Час у повітрі","лічені хвилини від пуску"]],"d":"Зліт МіГ-31К/І на мапі — окремий етап «носій у повітрі», а не пуск. Кількість бортів не дорівнює кількості ракет."},
 {"t":"ballistic","n":"«Циркон» (3М22)","k":"За ГУР балістична ракета","s":[["Класифікація","балістична за ГУР; раніше — «гіперзвукова крилата»"],["Бойова частина","~120 кг"],["Швидкість","до 6,8 М на окремих ділянках"],["Носії","кораблі й підводні човни (УКСК 3С14), адаптовано під береговий «Бастіон-М»"],["Час польоту з Криму","Харків ~4 хв, Київ ~3,5 хв, південь ~1 хв"]],"d":"У SKY «Циркон» іде як балістика: без вигаданої траєкторії, лише названа територія й вік повідомлення. Максимальну швидкість не беремо як постійну."},
 {"t":"ballistic","n":"Балістика: «Іскандер-М», KN-23, С-300/С-400 по наземних","k":"Балістичні ракети","s":[["«Іскандер-М» 9М723","до ~500 км, БЧ ~480 кг"],["KN-23 (КНДР)","до ~700 км"],["С-300/С-400 по землі","до ~150–250 км"],["Звідки","Бєлгородщина, Курщина, Воронежчина, Ростовщина, Крим"],["KN-23","рішення KN-23 інтегровано у виробництво «Іскандера-М»; пусків поставлених КНДР ракет останнім часом не фіксували"]],"d":"Від пуску до удару лічені хвилини."},
 {"t":"cruise","n":"«Онікс» (П-800)","i":"onyx","k":"Надзвукова протикорабельна крилата ракета","s":[["Дальність","300 км на типовій траєкторії, 120 км на маловисотній"],["Швидкість","до ~Мах 2,2"],["Бойова частина","200 кг ОФ або 250 кг напівбронебійна"],["Носії","берегові «Бастіон-П/С», кораблі"]],"d":"Б'є з Криму по півдню. «Онікс / Циркон» у повідомленні означає, що тип не встановлено, а не дві ракети."},
 {"t":"cruise","n":"Носії: Ту-95МС, Ту-160, Ту-22М3, МіГ-31К/І","i":"tu95","g":[["tu160","Ту-160"],["tu22","Ту-22М3"],["mig31","МіГ-31К/І"]],"k":"Стратегічна й дальня авіація","s":[["Ту-95МС","турбогвинтовий стратегічний ракетоносець: Х-101, Х-55/Х-555"],["Ту-160","надзвуковий стратегічний ракетоносець: Х-101, Х-55/Х-555"],["Ту-22М3","дальній бомбардувальник: Х-22, Х-32"],["МіГ-31К/І","носій «Кинджала», не стратегічний бомбардувальник"],["Аеродроми, які згадують Повітряні сили","Енгельс-2, Оленья, Шайківка, Сольці, Моздок, Українка"]],"d":"У SKY ці події розділені: зліт або переліт носія, загроза застосування, пуск, ракети в повітрі, відбій. Зліт чи переліт не є пуском, і швидкість літака не переноситься на ракету."},
 {"t":"kab","n":"КАБ: ФАБ/ОДАБ з УМПК","k":"Керовані авіабомби","s":[["Маса","250–3000 кг"],["Дальність планування","40–70 км для ФАБ-250/500/1500 з УМПК, 50–60 км для ФАБ-3000"],["Звідки","з-над РФ і окупованих територій біля кордону"],["Час у повітрі","кілька хвилин, залежить від висоти й відстані"]],"d":"Літак скидає бомбу, не заходячи в зону ППО. Тому на мапі ми показуємо не лише зону загрози КАБ, а й ворожу авіацію та район її пусків."},
 {"t":"rszv","n":"РСЗВ: «Град», «Ураган», «Смерч», «Торнадо-С»","k":"Реактивні системи залпового вогню","s":[["«Град» 122 мм","~20–40 км"],["«Ураган» 220 мм","~35 км"],["«Смерч» / «Торнадо-С» 300 мм","~70–120 км"],["Час у повітрі","від десятків секунд до кількох хвилин"]],"d":"Б'ють по прифронтових і прикордонних громадах: Харківщина, Сумщина, Херсон, Нікополь. Показуємо, лише коли прямо пишуть «РСЗВ»."},
 {"t":"recon","n":"Дрони-розвідники: «Орлан-10», ZALA, Supercam, «Мерлін»","k":"Розвідувальні БпЛА","s":[["Швидкість","~80–150 км/год"],["Висота","до 3–5 км"],["Задача","пошук цілей і коригування ударів ракет, КАБ, артилерії"],["Час у повітрі","від 2 до 16+ год залежно від моделі"]],"d":"Сам не б'є, але після розвідника часто летять ракети, КАБ або артилерія."},
 {"t":"gerbera","n":"«Гербера»","k":"Дрон-імітатор, окрема платформа","s":[["Роль","хибна ціль, баражуючий або розвідувальний; «Гербера-2» має й ударну версію"],["Запуск","разом із «Шахедами»"],["Швидкість","до 180–200 км/год"],["Дальність","«Гербера-2»: до 1200 км"],["Бойова частина","10–25 кг, запальні пакети"],["Час у повітрі","«Гербера-2»: до 10 год; для першої версії надійного максимуму не встановлено"]],"d":"Канали рідко відрізняють «Гербери» від «Шахедів» у польоті, тому на мапі вони йдуть як «Шахед». Безпечною ціллю її вважати не можна."},
 {"t":"shahed","i":"harpiya","n":"«Гарпія-А1»","k":"Ударний БпЛА, аналог «Шахеда» іншого виробника","s":[["Швидкість","максимум 185 км/год"],["Дальність","до 1500 км"],["Бойова частина","50 кг"]],"d":"У повітрі від «Шахеда» не відрізнити, тому на мапі це «Шахед»."},
 {"t":"parodiya","n":"«Пародія»","k":"Дрон-імітатор","s":[["Характеристики","не наводимо, доки немає надійних відкритих даних"]],"d":"Показано для впізнавання зовнішнього вигляду. На мапі окремим типом не виділяємо."},
 {"t":"lancet","n":"«Ланцет-1» / «Ланцет-3»","k":"Баражуючий боєприпас","s":[["Швидкість","80–110 км/год"],["Час у повітрі","30–40 хв"],["Дальність","30–40 км"],["Злітна маса","5 кг / 12 кг"],["Корисне навантаження","1 кг / 3 кг"]],"d":"Кружляє над районом і пікірує на техніку біля фронту. Ранні версії впізнають за двома групами Х-подібних крил і гвинтом у хвості."},
 {"t":"fpv","n":"FPV-дрони","k":"Тактичні дрони-камікадзе","s":[["Швидкість","80–150 км/год"],["Радіус","~10–20 км від лінії фронту"],["Бойова частина","1–3 кг"],["Час у повітрі","залежить від збірки, акумулятора й навантаження"]],"d":"Полюють на людей і транспорт у прифронтовій зоні. Показуємо, лише коли канал прямо пише «FPV»."},
 {"t":"fpvf","n":"FPV на оптоволокні","k":"FPV, яким керують по кабелю","s":[["Дальність","~10–40 км (довжина кабелю)"],["Особливість","не глушиться РЕБ"],["Час у повітрі","залежить від збірки: довжина котушки не визначає, на скільки вистачить акумулятора"]],"d":"Кабель тягнеться за дроном, тож радіоелектронна боротьба його не зупиняє. На мапі синій."}
];
const LEG=[
 ['tgt','#FFA31A','Ціль','реалістичний силует типу, ніс за курсом. Чим ближче масштаб, тим більший силует. Торкніться, щоб побачити докази й прогноз'],
 ['est','#FFA31A','Місце не назване','напівпрозорий силует у тонкому білому кільці: канали назвали лише курс, а місце оцінив SKY. Підпис «→ пункт · місце не названо»'],
 ['rep','#FFFFFF','Повідомлення і оцінка','у вибраної цілі: біла точка з часом, де її востаннє назвали канали («Повідомлення · 21:42»), і тонкий пунктир до поточного розрахованого положення з підписом «Оцінка · дані 4 хв тому». Біла хвиля від цілі: щойно прийшло нове повідомлення'],
 ['still','#FFA31A','Курс невідомий','кольорове кільце навколо цілі: де вона, відомо, а куди летить, ні. SKY не рухає таку ціль, щоб не вигадувати шлях'],
 ['flow','#FFA31A','Рух уперед','біжучі штрихи від цілі: куди вона долетить за ~8 хв, якщо триматиме курс'],
 ['trail','#FFA31A','Пройдений шлях','крапки по місцях, які називали канали. У всіх цілей ледь помітні білі, у вибраної й тих, що летять до вас, кольором цілі'],
 ['route','#FFA31A','Куди летить за каналами','штрихи кольору цілі до пункту, який назвали канали («курсом на…»). Для вибраної цілі й тих, що летять до вас'],
 ['pred','#FFA31A','Ймовірно далі','дрібний пунктир і підпис «ймовірно пункт»: куди ціль найчастіше летіла далі на попередніх перельотах, коли канали пункту ще не назвали'],
 ['home','#2FE38A','Дім','ваша точка; кольорове коло показує стан: зелений спокійно, жовтий увага, червоний загроза. Торкніться, щоб перемістити або видалити'],
 ['dot','#FF3B3B','Місце пуску','червона точка в РФ або на окупованій території; бліда, якщо місце лише оцінене. Торкніться, щоб побачити, що й коли пускали'],
 ['plane','#FF3B3B','Ворожа тактична авіація','силует літака над типовим районом пусків КАБ; блякне з часом'],
 ['ring','#FF5A5A','Зона пусків КАБ','пунктирне коло навколо району, звідки скидають КАБи'],
 ['kab','#22E1FF','Загроза КАБ','значок авіабомби над громадою; зникає за 10–15 хв без нових пусків або після «відбою»'],
 ['fill','#E8B931','Тривога','офіційна тривога: заливка області, району чи громади'],
 ['hl','#FF2BD6','Лічильники вгорі','торкніться типу: мапа покаже всі такі цілі й на кілька секунд підсвітить їх хвилями'],
 ['fire','#FF7A1A','Вибухи (мапа доби)','вогонь там, де за добу повідомляли про прильоти'],
];
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function legIcon(k,c){const C=document.createElement('canvas');C.width=C.height=72;const x=C.getContext('2d');x.translate(36,36);x.lineWidth=3;x.strokeStyle=c;x.fillStyle=c;
  const spr=(t,al,cb)=>{const i=new Image();i.src='sprites/t-'+t+'.png?v=ref13';i.onload=()=>{x.save();x.globalAlpha=al;x.rotate(0.5);x.drawImage(i,-24,-24,48,48);x.restore();cb&&cb();};};
  if(k==='tgt'){x.globalAlpha=.35;x.fillStyle='#000';x.beginPath();x.arc(2,4,24,0,7);x.filter='blur(6px)';x.fill();x.filter='none';x.globalAlpha=1;spr('shahed',1);return C;}
  if(k==='est'){x.strokeStyle='rgba(255,255,255,.55)';x.lineWidth=1.5;x.beginPath();x.arc(0,0,28,0,7);x.stroke();spr('shahed',.45);return C;}
  if(k==='rep'){x.strokeStyle='#fff';x.lineWidth=1.6;x.setLineDash([2,4]);x.beginPath();x.moveTo(-24,20);x.lineTo(10,-8);x.stroke();x.setLineDash([]);x.fillStyle='#fff';x.beginPath();x.arc(-24,20,5,0,7);x.fill();x.strokeStyle='#0B0F17';x.lineWidth=2;x.stroke();x.translate(14,-11);x.scale(.6,.6);spr('shahed',1);return C;}
  if(k==='still'){x.globalAlpha=.6;x.lineWidth=1.6;x.beginPath();x.arc(0,0,30,0,7);x.stroke();x.globalAlpha=1;spr('shahed',1);return C;}
  if(k==='flow'){x.setLineDash([7,6]);x.lineWidth=2.4;x.beginPath();x.moveTo(-10,10);x.lineTo(30,-24);x.stroke();x.setLineDash([]);x.translate(-14,13);x.scale(.7,.7);spr('shahed',1);return C;}
  if(k==='route'){x.setLineDash([5,6]);x.lineWidth=2.4;x.beginPath();x.moveTo(-28,20);x.lineTo(24,-18);x.stroke();x.setLineDash([]);x.fillStyle='#fff';x.font='bold 10px sans-serif';x.fillText('→',16,-20);return C;}
  if(k==='home'){x.globalAlpha=.25;x.beginPath();x.arc(0,0,30,0,7);x.fill();x.globalAlpha=1;x.lineWidth=2;x.beginPath();x.arc(0,0,30,0,7);x.stroke();
    x.fillStyle='#fff';x.beginPath();x.arc(0,0,13,0,7);x.fill();x.strokeStyle='#2F7BFF';x.lineWidth=3;x.stroke();x.fillStyle='#1B2A4A';x.beginPath();x.moveTo(-7,1);x.lineTo(0,-6);x.lineTo(7,1);x.lineTo(5,1);x.lineTo(5,7);x.lineTo(-5,7);x.lineTo(-5,1);x.closePath();x.fill();return C;}
  if(k==='hl'){for(const [r,a] of [[30,.35],[22,.7]]){x.globalAlpha=a;x.lineWidth=2;x.beginPath();x.arc(0,0,r,0,7);x.stroke();}x.globalAlpha=1;x.strokeStyle='#fff';x.beginPath();x.arc(0,0,16,0,7);x.stroke();x.scale(.6,.6);spr('jet',1);return C;}
  if(k==='dot'){x.beginPath();x.arc(0,0,11,0,7);x.fill();x.strokeStyle='#fff';x.stroke();}
  else if(k==='plane'){const p=new Path2D('M0,-26 L3,-19 L3,-8 L22,5 L22,9 L3,5 L3,15 L9,20 L9,23 L0,21 L-9,23 L-9,20 L-3,15 L-3,5 L-22,9 L-22,5 L-3,-8 L-3,-19 Z');x.fill(p);x.strokeStyle='#fff';x.lineWidth=1.5;x.stroke(p);}
  else if(k==='ring'){x.globalAlpha=.2;x.beginPath();x.arc(0,0,26,0,7);x.fill();x.globalAlpha=1;x.setLineDash([6,5]);x.stroke();}
  else if(k==='kab'){const i=new Image();i.src='sprites/t-kab.png?v=ref13';i.onload=()=>{x.drawImage(i,-28,-28,56,56);};}
  else if(k==='trail'){for(let i=-26;i<=26;i+=9){x.globalAlpha=.35;x.fillStyle='#E8ECF4';x.beginPath();x.arc(i,-10+i*.25,2.4,0,7);x.fill();x.globalAlpha=1;x.fillStyle=c;x.beginPath();x.arc(i,10+i*.25,2.6,0,7);x.fill();}}
  else if(k==='pred'){x.lineWidth=2.2;x.setLineDash([2,6]);x.lineCap='round';x.beginPath();x.moveTo(-26,14);x.quadraticCurveTo(0,-14,22,-6);x.stroke();x.setLineDash([]);x.font='bold 9px sans-serif';x.fillText('ймовірно',-6,-18);}
  else if(k==='fill'){x.globalAlpha=.45;x.fillRect(-26,-20,52,40);x.globalAlpha=1;x.strokeStyle='#fff';x.lineWidth=2;x.strokeRect(-26,-20,52,40);}
  else if(k==='ru'){[[-14,-8],[8,-14],[2,10],[18,6]].forEach(([a,b])=>{x.beginPath();x.arc(a,b,5,0,7);x.fillStyle='#FFD500';x.fill();x.strokeStyle='#2F7BFF';x.lineWidth=2;x.stroke();});}
  else if(k==='fire'){const g=x.createRadialGradient(0,4,2,0,0,26);g.addColorStop(0,'rgba(255,230,140,.9)');g.addColorStop(.4,'rgba(255,120,30,.6)');g.addColorStop(1,'rgba(255,60,0,0)');x.fillStyle=g;x.beginPath();x.arc(0,0,26,0,7);x.fill();}
  return C;}
function build(){const el=document.getElementById('arsenal');if(el.dataset.ok)return;el.dataset.ok=1;
  const box=el.querySelector('.ars-list');
  A.forEach(a=>{const c=document.createElement('article');c.className='ars-card';c.style.setProperty('--tc',(window.TYPE_COLOR||{})[a.t]||'#fff');
    c.innerHTML='<div class="ars-img"><img alt="" decoding="async" src="sprites/ref/'+(a.i||a.t)+'.png?v=ref17" onerror="this.onerror=function(){this.style.visibility=\'hidden\'};this.src=\'sprites/t-'+a.t+'.png\'"></div><div class="ars-b"><small>'+esc(a.k)+'</small><h4>'+esc(a.n)+'</h4><dl>'+a.s.map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+esc(v)+'</dd>').join('')+'</dl><p>'+esc(a.d)+'</p>'+(a.g?'<div class="ars-g" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">'+a.g.map(([f,n])=>'<figure style="margin:0;text-align:center;width:64px"><img alt="" loading="lazy" src="sprites/ref/'+f+'.png?v=ref17" style="width:64px;height:64px;object-fit:contain"><figcaption style="font-size:10px;opacity:.7">'+esc(n)+'</figcaption></figure>').join('')+'</div>':'')+'<button class="ars-map" data-t="'+a.t+'" hidden></button></div>';
    c.querySelector('.ars-map').onclick=()=>{const n=((window.NX&&NX.snap())?NX.snap().tracks:[]).filter(x=>x.status==='active'&&x.type===a.t).length;if(!n&&a.t!=='kab'){if(window.NX)NX.toast('Зараз у повітрі не видно: '+a.n);return;}el.hidden=true;if(a.t==='kab'){const z=((window.NX&&NX.snap())?NX.snap().zones:[])[0];if(z&&window.tryvogaMap)tryvogaMap.flyTo({center:z.places[0],zoom:8});else if(window.NX)NX.toast('Зараз загроз КАБ немає');return;}if(window.NX)NX.focusType(a.t);};
    box.appendChild(c);});
  const lg=el.querySelector('.ars-leg');
  LEG.forEach(([k,c,n,d])=>{const r=document.createElement('div');r.className='ars-lr';r.appendChild(legIcon(k,c));const t=document.createElement('div');t.innerHTML='<b>'+esc(n)+'</b><span>'+esc(d)+'</span>';r.appendChild(t);lg.appendChild(r);});
  const sp=document.createElement('div');sp.className='ars-lr';const cv=document.createElement('canvas');cv.width=cv.height=72;sp.appendChild(cv);
  const g=cv.getContext('2d');let i=0;const ks=Object.keys(window.TYPE_COLOR||{}).filter(k=>k!=='kab');setInterval(()=>{if(el.hidden)return;const im=new Image();im.src='sprites/t-'+ks[i++%ks.length]+'.png';im.onload=()=>{g.clearRect(0,0,72,72);g.drawImage(im,6,6,60,60);};},1200);
  sp.insertAdjacentHTML('beforeend','<div><b>Ціль у повітрі</b><span>колір = тип (див. картки вище); ×N, група; торкніться цілі, щоб побачити докази: які канали, коли й що написали</span></div>');lg.prepend(sp);}
function liveBtns(){const S=window.NX?NX.snap():null;
  document.querySelectorAll('#arsenal .ars-map').forEach(b=>{const t=b.dataset.t;let n=0;
    if(S){n=t==='kab'?(S.zones||[]).length:(S.tracks||[]).filter(x=>x.status==='active'&&x.type===t).reduce((s,x)=>s+(x.count||1),0);}
    b.hidden=!n;b.textContent=t==='kab'?'Загроз КАБ зараз: '+n:'У повітрі зараз: '+n;});}
window.openArsenal=function(){build();liveBtns();document.getElementById('arsenal').hidden=false;const s=document.getElementById('settings');if(s)s.hidden=true;};
document.addEventListener('DOMContentLoaded',()=>{const b=document.getElementById('b-ars');if(b)b.onclick=window.openArsenal;const c=document.getElementById('ars-close');if(c)c.onclick=()=>document.getElementById('arsenal').hidden=true;});
})();

/* 13.11: перегляд зображення з Арсеналу — плавне збільшення з мініатюри; закриття хрестиком, дотиком по фону, свайпом вниз або Esc */
(function(){
  let ov=null,src=null,busy=false;
  function rectOf(e){const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,w:r.width,h:r.height};}
  function close(){if(!ov||busy)return;busy=true;const im=ov.querySelector('img');const a=src&&document.body.contains(src)?rectOf(src):null,b=rectOf(im);
    ov.classList.remove('on');
    if(a){im.style.transition='transform .28s cubic-bezier(.2,.8,.2,1)';im.style.transform=`translate(${a.x-b.x}px,${a.y-b.y}px) scale(${a.w/b.w})`;}
    else{im.style.transition='transform .22s ease-in,opacity .22s';im.style.transform='translateY(60px)';im.style.opacity='0';}
    setTimeout(()=>{ov.remove();ov=null;busy=false;},290);}
  function open(img,caption){if(ov)return;src=img;
    ov=document.createElement('div');ov.className='ars-zoom';
    ov.innerHTML='<button class="az-x" aria-label="Закрити">×</button><img alt=""><div class="az-cap"></div>';
    const im=ov.querySelector('img');im.src=img.currentSrc||img.src;ov.querySelector('.az-cap').textContent=caption||'';
    document.body.appendChild(ov);
    const go=()=>{const a=rectOf(img),b=rectOf(im);im.style.transition='none';im.style.transform=`translate(${a.x-b.x}px,${a.y-b.y}px) scale(${a.w/Math.max(1,b.w)})`;
      requestAnimationFrame(()=>requestAnimationFrame(()=>{ov.classList.add('on');im.style.transition='transform .34s cubic-bezier(.2,.8,.2,1)';im.style.transform='';}));};
    im.complete?go():im.onload=go;
    ov.querySelector('.az-x').onclick=e=>{e.stopPropagation();close();};
    ov.onclick=e=>{if(e.target===ov)close();};
    // свайп вниз: картинка їде за пальцем, фон тьмяніє; відпустили далеко або різко — закриваємо
    let y0=0,t0=0,dy=0,drag=false;
    ov.addEventListener('touchstart',e=>{if(e.touches.length!==1)return;y0=e.touches[0].clientY;t0=Date.now();dy=0;drag=true;im.style.transition='none';},{passive:true});
    ov.addEventListener('touchmove',e=>{if(!drag)return;dy=Math.max(0,e.touches[0].clientY-y0);if(e.cancelable)e.preventDefault();im.style.transform=`translateY(${dy}px) scale(${1-Math.min(.25,dy/1200)})`;ov.style.background=`rgba(4,6,10,${.92*(1-Math.min(1,dy/400))})`;},{passive:false});
    ov.addEventListener('touchend',()=>{if(!drag)return;drag=false;const v=dy/Math.max(1,Date.now()-t0);if(dy>110||(v>.6&&dy>40)){ov.style.background='';close();}else{im.style.transition='transform .22s ease-out';im.style.transform='';ov.style.background='';}});
  }
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&ov)close();});
  document.addEventListener('click',e=>{const img=e.target.closest&&e.target.closest('#arsenal img');if(!img||img.style.visibility==='hidden')return;
    const card=img.closest('.ars-card');const sub=img.closest('figure,div')&&img.parentElement.querySelector('span,figcaption,small');
    const cap=(card&&card.querySelector('h4')?card.querySelector('h4').textContent:'')+(sub&&sub.textContent&&!img.closest('.ars-img')?' · '+sub.textContent:'');
    e.preventDefault();open(img,cap);},true);
})();
