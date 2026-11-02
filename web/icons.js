// Силуети цілей зверху (ніс угору = північ). Малюються на canvas, щоб бути чіткими на будь-якому екрані.
window.TYPE_COLOR={shahed:'#FFA31A',jet:'#FF2BD6',molniya:'#7CFF2A',cruise:'#9D3CFF',ballistic:'#FF2E2E',kab:'#22E1FF'};
window.TYPE_NAME={shahed:'Шахед',jet:'Реактивний БпЛА',molniya:'«Молнія»',cruise:'Крилата ракета',ballistic:'Балістика',kab:'КАБ'};
window.drawTarget=function(type,px,opts){
  opts=opts||{};const s=px*2,c=document.createElement('canvas');c.width=c.height=s;const x=c.getContext('2d');
  x.translate(s/2,s/2);x.scale(s/100,s/100);
  const col=opts.dim?'#8A93A5':(TYPE_COLOR[type]||'#fff');
  const shapes={
    shahed:'M0,-40 L5,-26 L6,-10 L40,26 L40,32 L6,22 L5,30 L-5,30 L-6,22 L-40,32 L-40,26 L-6,-10 L-5,-26 Z',
    jet:'M0,-44 L5,-28 L6,-6 L30,24 L30,30 L6,24 L8,36 L-8,36 L-6,24 L-30,30 L-30,24 L-6,-6 L-5,-28 Z',
    molniya:'M0,-38 L5,-26 L5,-10 L42,-6 L42,2 L5,4 L4,22 L16,30 L16,34 L-16,34 L-16,30 L-4,22 L-5,4 L-42,2 L-42,-6 L-5,-10 L-5,-26 Z',
    cruise:'M0,-46 L4,-34 L4,-6 L22,6 L22,11 L4,6 L4,30 L12,40 L12,44 L-12,44 L-12,40 L-4,30 L-4,6 L-22,11 L-22,6 L-4,-6 L-4,-34 Z',
    ballistic:'M0,-46 L7,-26 L7,28 L16,40 L16,44 L-16,44 L-16,40 L-7,28 L-7,-26 Z',
    kab:'M0,-36 L9,-22 L9,-4 L44,-2 L44,4 L9,6 L9,22 L20,34 L-20,34 L-9,22 L-9,6 L-44,4 L-44,-2 L-9,-4 L-9,-22 Z'
  };
  const p=new Path2D(shapes[type]||shapes.shahed);
  x.shadowColor='rgba(0,0,0,.55)';x.shadowBlur=8;x.shadowOffsetY=3;
  x.fillStyle=col;x.fill(p);x.shadowColor='transparent';
  x.lineWidth=3.2;x.strokeStyle='rgba(20,14,8,.85)';x.lineJoin='round';x.stroke(p);
  x.lineWidth=1.4;x.strokeStyle='rgba(255,255,255,.55)';x.stroke(p);
  if(type==='shahed'||type==='molniya'){x.beginPath();x.ellipse(0,type==='shahed'?33:37,10,2.6,0,0,Math.PI*2);x.fillStyle='rgba(255,255,255,.5)';x.fill();}
  return c;
};
window.drawHome=function(px){const s=px*2,c=document.createElement('canvas');c.width=c.height=s;const x=c.getContext('2d');x.scale(s/100,s/100);
  x.beginPath();x.arc(50,50,40,0,Math.PI*2);x.fillStyle='#fff';x.shadowColor='rgba(0,0,0,.45)';x.shadowBlur=10;x.fill();x.shadowColor='transparent';
  x.lineWidth=6;x.strokeStyle='#1E6BFF';x.stroke();
  x.beginPath();x.moveTo(28,52);x.lineTo(50,33);x.lineTo(72,52);x.lineTo(72,70);x.lineTo(58,70);x.lineTo(58,58);x.lineTo(42,58);x.lineTo(42,70);x.lineTo(28,70);x.closePath();x.fillStyle='#0B0F17';x.fill();return c;};
// Якщо реалістичні спрайти завантажились — інтерфейсні іконки (лічильники, картка, таймер) малюються з них.
(()=>{const SP={};const base=window.drawTarget;
  Object.keys(TYPE_COLOR).forEach(t=>{const im=new Image();im.src='sprites/t-'+t+'.png';SP[t]=im;});
  window.drawTarget=function(type,px,opts){const im=SP[type];if(!im||!im.complete||!im.naturalWidth||(opts&&opts.dim))return base(type,px,opts);
    const s=px*2,c=document.createElement('canvas');c.width=c.height=s;const x=c.getContext('2d');x.translate(s/2,s/2);x.rotate(Math.PI/4);x.drawImage(im,-s*0.62,-s*0.62,s*1.24,s*1.24);return c;};
})();
