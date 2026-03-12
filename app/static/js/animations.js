
/* ══════════════════════════════════════════════════════
   PREMIUM PROCEDURAL ANIMATIONS — 日本水墨 × 工芸 Style
   Sakura Tree + Daruma — Canvas 2D @ 2× Retina
   ══════════════════════════════════════════════════════ */

// ─── Noise helper for organic textures ────
const _perm=[];(function(){const p=[];for(let i=0;i<256;i++)p[i]=i;for(let i=255;i>0;i--){const j=Math.floor(Math.random()*(i+1));[p[i],p[j]]=[p[j],p[i]];}for(let i=0;i<512;i++)_perm[i]=p[i&255];})();
function noise2d(x,y){const X=Math.floor(x)&255,Y=Math.floor(y)&255;x-=Math.floor(x);y-=Math.floor(y);const u=x*x*(3-2*x),v=y*y*(3-2*y);const a=_perm[X]+Y,b=_perm[X+1]+Y;return lerp(v,lerp(u,grad2(_perm[a],x,y),grad2(_perm[b],x-1,y)),lerp(u,grad2(_perm[a+1],x,y-1),grad2(_perm[b+1],x-1,y-1)));}
function grad2(h,x,y){const v=h&3;return(v===0?x+y:v===1?-x+y:v===2?x-y:-x-y);}
function lerp(t,a,b){return a+t*(b-a);}

// ━━━━━━━━━━━━━━ BONSAI / SAKURA TREE ━━━━━━━━━━━━━━━
function renderBonsai(streak,containerId){
  const c=document.getElementById(containerId);if(!c)return;
  const dW=c.clientWidth||280,dH=c.clientHeight||320,S=2,W=dW*S,H=dH*S;
  c.innerHTML=`<div class="anim-canvas-wrap"><canvas id="cv-${containerId}" width="${W}" height="${H}" style="width:${dW}px;height:${dH}px"></canvas><div class="petal-overlay" id="pl-${containerId}" style="display:none"></div></div>`;
  const ctx=document.getElementById(`cv-${containerId}`).getContext('2d');
  if(streak===0){paintZenScene(ctx,W,H);return;}
  paintTreeGrowth(ctx,W,H,streak>=7,()=>{if(streak>=7){const p=document.getElementById(`pl-${containerId}`);if(p){p.style.display='block';petalRain(p);}}});
}

function paintZenScene(ctx,W,H){
  // Sky
  const sky=ctx.createLinearGradient(0,0,0,H*0.6);
  sky.addColorStop(0,'#e8e0d4');sky.addColorStop(1,'#f5efe5');
  ctx.fillStyle=sky;ctx.fillRect(0,0,W,H);
  // Ground
  const gY=H*0.62;
  const gnd=ctx.createLinearGradient(0,gY,0,H);
  gnd.addColorStop(0,'#ddd5c5');gnd.addColorStop(1,'#c8bda8');
  ctx.fillStyle=gnd;ctx.fillRect(0,gY,W,H-gY);
  // Raked lines with noise
  ctx.strokeStyle='rgba(160,145,120,0.35)';ctx.lineWidth=1.2;
  const cx=W/2;
  for(let r=1;r<=9;r++){
    ctx.beginPath();
    for(let a=0;a<=360;a+=2){
      const rad=a*Math.PI/180;
      const rx=35+r*18+noise2d(a*0.05,r)*4;
      const ry=12+r*6+noise2d(a*0.05+10,r)*2;
      const px=cx+Math.cos(rad)*rx,py=gY+18+Math.sin(rad)*ry;
      a===0?ctx.moveTo(px,py):ctx.lineTo(px,py);
    }ctx.stroke();
  }
  // Main rock — organic shape with noise displacement
  paintRock(ctx,cx-5,gY-2,45,35,'#707070','#555');
  paintRock(ctx,cx+30,gY+5,22,17,'#808080','#606060');
  // Moss
  for(let i=0;i<12;i++){
    const mx=cx-10+(Math.random()-0.3)*30,my=gY+2+Math.random()*8;
    ctx.beginPath();ctx.arc(mx,my,Math.random()*3+1.5,0,Math.PI*2);
    ctx.fillStyle=`rgba(${70+Math.random()*40},${110+Math.random()*50},${60+Math.random()*30},${0.4+Math.random()*0.3})`;ctx.fill();
  }
  ctx.fillStyle='#a09078';ctx.font=`${W*0.035}px "Noto Serif TC",serif`;ctx.textAlign='center';ctx.fillText('枯山水',cx,H-12);
}

function paintRock(ctx,x,y,w,h,c1,c2){
  ctx.save();
  const g=ctx.createRadialGradient(x-w*0.2,y-h*0.3,2,x,y,w);
  g.addColorStop(0,c1);g.addColorStop(1,c2);ctx.fillStyle=g;
  ctx.beginPath();
  const pts=24;
  for(let i=0;i<=pts;i++){
    const a=(i/pts)*Math.PI*2;
    const r=(i<pts/2?1:0.95)*(1+noise2d(i*0.8,y*0.01)*0.15);
    const px=x+Math.cos(a)*w*0.5*r,py=y+Math.sin(a)*h*0.5*r*(Math.sin(a)>0?1.1:0.9);
    i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);
  }
  ctx.closePath();ctx.fill();
  // Texture
  for(let i=0;i<30;i++){
    const tx=x+(Math.random()-0.5)*w*0.8,ty=y+(Math.random()-0.5)*h*0.7;
    ctx.beginPath();ctx.arc(tx,ty,Math.random()+0.3,0,Math.PI*2);
    ctx.fillStyle=`rgba(40,40,40,${Math.random()*0.15})`;ctx.fill();
  }
  // Top highlight
  ctx.beginPath();ctx.ellipse(x-w*0.1,y-h*0.25,w*0.2,h*0.12,-0.3,0,Math.PI*2);
  ctx.fillStyle='rgba(255,255,255,0.12)';ctx.fill();
  ctx.restore();
}

// ── Tree Growth ──
function paintTreeGrowth(ctx,W,H,sakura,onDone){
  const segs=[];const flowers=[];let sd=12345;
  function sr(){sd=(sd*48271)%2147483647;return(sd&0x7fffffff)/2147483647;}
  const sx=W/2,sy=H-35,tLen=H*0.28,maxD=11;
  
  function grow(x,y,ang,len,d,tw){
    if(d>maxD||len<1.5)return;
    const bend=(sr()-0.5)*0.2;const ma=ang+bend;
    const ex=x+Math.cos(ma)*len,ey=y+Math.sin(ma)*len;
    const cpx=x+Math.cos(ma+bend)*len*0.55,cpy=y+Math.sin(ma+bend)*len*0.55;
    segs.push({x1:x,y1:y,cx:cpx,cy:cpy,x2:ex,y2:ey,d,tw:Math.max(0.5,tw)});
    if(d>=6&&sakura){
      const n=Math.floor(sr()*4)+2;
      for(let k=0;k<n;k++){
        flowers.push({x:ex+(sr()-0.5)*len*0.5,y:ey+(sr()-0.5)*len*0.4,
          r:sr()*7+5,np:5+Math.floor(sr()*2),rot:sr()*Math.PI*2});
      }
    }
    const bf=0.62+sr()*0.14,sp=0.28+sr()*0.22;
    grow(ex,ey,ma-sp,len*bf,d+1,tw*0.68);
    grow(ex,ey,ma+sp,len*bf,d+1,tw*0.68);
    if(sr()>0.5&&d<7)grow(ex,ey,ma+(sr()-0.5)*0.6,len*bf*0.7,d+1,tw*0.55);
  }
  grow(sx,sy,-Math.PI/2,tLen,0,W*0.035);
  segs.sort((a,b)=>a.d-b.d);

  // Background
  function drawBg(){
    // Soft sky
    const sk=ctx.createLinearGradient(0,0,0,H*0.75);
    if(sakura){sk.addColorStop(0,'#fce4ec');sk.addColorStop(0.5,'#fff3e0');sk.addColorStop(1,'#fff8f0');}
    else{sk.addColorStop(0,'#e8f5e9');sk.addColorStop(0.5,'#f1f8e9');sk.addColorStop(1,'#fafff5');}
    ctx.fillStyle=sk;ctx.fillRect(0,0,W,H);
    // Ground
    const gr=ctx.createLinearGradient(0,H-40,0,H);
    gr.addColorStop(0,'#8d6e4a');gr.addColorStop(0.3,'#6d5234');gr.addColorStop(1,'#5a432a');
    ctx.fillStyle=gr;
    ctx.beginPath();ctx.moveTo(0,H-25);
    ctx.quadraticCurveTo(W/2,H-35,W,H-25);ctx.lineTo(W,H);ctx.lineTo(0,H);ctx.fill();
    // Grass tufts
    for(let i=0;i<40;i++){
      const gx=sr()*W,gy=H-25-sr()*8;
      ctx.beginPath();ctx.moveTo(gx,gy+5);
      ctx.quadraticCurveTo(gx-3+sr()*6,gy-6-sr()*8,gx+sr()*4-2,gy-4);
      ctx.strokeStyle=`rgba(${50+sr()*40},${90+sr()*60},${40+sr()*20},0.5)`;
      ctx.lineWidth=1+sr();ctx.stroke();
    }
  }

  function drawSeg(s,p){
    const px=s.x1+(s.x2-s.x1)*p,py=s.y1+(s.y2-s.y1)*p;
    const cx=s.x1+(s.cx-s.x1)*p,cy=s.y1+(s.cy-s.y1)*p;
    // Shadow pass
    ctx.beginPath();ctx.moveTo(s.x1+1.5,s.y1+1.5);ctx.quadraticCurveTo(cx+1.5,cy+1.5,px+1.5,py+1.5);
    ctx.strokeStyle='rgba(0,0,0,0.08)';ctx.lineWidth=s.tw+1;ctx.lineCap='round';ctx.stroke();
    // Main branch
    ctx.beginPath();ctx.moveTo(s.x1,s.y1);ctx.quadraticCurveTo(cx,cy,px,py);
    if(s.d<=2){
      const bg=ctx.createLinearGradient(s.x1-s.tw/2,s.y1,s.x1+s.tw/2,s.y1);
      bg.addColorStop(0,'#2e1a0e');bg.addColorStop(0.35,'#4a3020');bg.addColorStop(0.5,'#5a3c28');bg.addColorStop(0.65,'#4a3020');bg.addColorStop(1,'#2e1a0e');
      ctx.strokeStyle=bg;
    }else if(s.d<=5){
      const t=(s.d-2)/3;ctx.strokeStyle=`rgb(${Math.round(74-t*10)},${Math.round(48+t*5)},${Math.round(32+t*5)})`;
    }else{
      if(sakura){const t=Math.min(1,(s.d-5)/5);ctx.strokeStyle=`rgb(${Math.round(90+t*60)},${Math.round(55+t*10)},${Math.round(45+t*30)})`;}
      else{const t=Math.min(1,(s.d-5)/5);ctx.strokeStyle=`rgb(${Math.round(60-t*15)},${Math.round(75+t*40)},${Math.round(40-t*10)})`;}
    }
    ctx.lineWidth=s.tw;ctx.lineCap='round';ctx.stroke();
    // Bark texture on thick branches
    if(s.d<=2&&p>0.2){
      for(let k=0;k<8;k++){
        const t=(k+0.3)/8*p;
        const bx=s.x1+(s.x2-s.x1)*t,by=s.y1+(s.y2-s.y1)*t;
        ctx.beginPath();ctx.moveTo(bx-s.tw*0.35,by-s.tw*0.05);
        ctx.lineTo(bx+s.tw*0.35,by+s.tw*0.1);
        ctx.strokeStyle=`rgba(20,12,5,${0.1+noise2d(k,s.x1*0.01)*0.1})`;ctx.lineWidth=0.6;ctx.stroke();
      }
    }
  }

  function drawFlower(f,p){
    const r=f.r*p,a=p*0.95;
    // Glow halo
    const gl=ctx.createRadialGradient(f.x,f.y,0,f.x,f.y,r*3);
    gl.addColorStop(0,`rgba(255,210,225,${a*0.2})`);gl.addColorStop(1,'rgba(255,200,220,0)');
    ctx.fillStyle=gl;ctx.beginPath();ctx.arc(f.x,f.y,r*3,0,Math.PI*2);ctx.fill();
    // 5 petals — teardrop beziers
    for(let i=0;i<f.np;i++){
      const pa=f.rot+(i/f.np)*Math.PI*2;
      ctx.save();ctx.translate(f.x,f.y);ctx.rotate(pa);
      ctx.beginPath();ctx.moveTo(0,0);
      ctx.bezierCurveTo(r*0.45,-r*0.4, r*1.0,-r*0.25, r*0.9,0);
      ctx.bezierCurveTo(r*1.0, r*0.25, r*0.45, r*0.4, 0,0);
      const pg=ctx.createLinearGradient(0,0,r*0.9,0);
      pg.addColorStop(0,`rgba(255,250,252,${a})`);
      pg.addColorStop(0.3,`rgba(255,225,235,${a})`);
      pg.addColorStop(0.7,`rgba(255,190,210,${a})`);
      pg.addColorStop(1,`rgba(245,155,185,${a*0.85})`);
      ctx.fillStyle=pg;ctx.fill();
      // Petal vein
      ctx.beginPath();ctx.moveTo(r*0.08,0);ctx.lineTo(r*0.75,0);
      ctx.strokeStyle=`rgba(210,140,170,${a*0.25})`;ctx.lineWidth=0.35;ctx.stroke();
      ctx.restore();
    }
    // Stamen center
    const cg=ctx.createRadialGradient(f.x,f.y,0,f.x,f.y,r*0.25);
    cg.addColorStop(0,`rgba(255,240,130,${a})`);cg.addColorStop(1,`rgba(220,170,60,${a})`);
    ctx.beginPath();ctx.arc(f.x,f.y,r*0.25,0,Math.PI*2);ctx.fillStyle=cg;ctx.fill();
    for(let i=0;i<5;i++){
      const sa=(i/5)*Math.PI*2;
      ctx.beginPath();ctx.arc(f.x+Math.cos(sa)*r*0.18,f.y+Math.sin(sa)*r*0.18,r*0.06,0,Math.PI*2);
      ctx.fillStyle=`rgba(190,130,40,${a})`;ctx.fill();
    }
  }

  function drawLeaf(b){
    for(let j=0;j<6;j++){
      const lx=b.x2+(sr()-0.5)*b.tw*8,ly=b.y2+(sr()-0.5)*b.tw*6;
      const lr=sr()*5+3;const la=sr()*Math.PI;
      ctx.save();ctx.translate(lx,ly);ctx.rotate(la);
      ctx.beginPath();ctx.moveTo(0,0);
      ctx.bezierCurveTo(lr*0.4,-lr*0.5,lr*1.1,-lr*0.2,lr*1.0,0);
      ctx.bezierCurveTo(lr*1.1,lr*0.2,lr*0.4,lr*0.5,0,0);
      const r=35+sr()*55,g=100+sr()*80,bl=25+sr()*35;
      ctx.fillStyle=`rgba(${r},${g},${bl},0.8)`;ctx.fill();
      ctx.beginPath();ctx.moveTo(lr*0.05,0);ctx.lineTo(lr*0.85,0);
      ctx.strokeStyle=`rgba(${r-15},${g-20},${bl-10},0.3)`;ctx.lineWidth=0.3;ctx.stroke();
      ctx.restore();
    }
  }

  // Animation
  const dur=5500,bDur=2800;let t0=null,bt0=null,done1=false,done2=false;
  function frame(ts){
    if(!t0)t0=ts;const el=ts-t0;
    ctx.clearRect(0,0,W,H);drawBg();
    const gp=Math.min(1,el/dur),nShow=Math.floor(gp*segs.length);
    for(let i=0;i<nShow;i++){
      const sp=Math.min(1,(el-(i/segs.length)*dur)/(dur/segs.length*3));
      if(sp>0)drawSeg(segs[i],sp);
    }
    if(gp>=1){
      if(!done1){done1=true;bt0=ts;}
      if(sakura){
        const be=ts-bt0,bp=Math.min(1,be/bDur);
        flowers.forEach((f,i)=>{
          const dl=(i/flowers.length)*bDur*0.4;
          const t=Math.max(0,Math.min(1,(be-dl)/900));
          if(t>0)drawFlower(f,1-Math.pow(1-t,3));
        });
        if(bp>=1&&!done2){done2=true;if(onDone)onDone();}
      }else{
        segs.filter(s=>s.d>=7).forEach(drawLeaf);
        if(!done2){done2=true;if(onDone)onDone();}
      }
      if(done2){idle(ctx,W,H,segs,flowers,sakura,sr);return;}
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function idle(ctx,W,H,segs,flowers,sak,sr){
  let ph=0;
  // Cache bg once
  const bgCv=document.createElement('canvas');bgCv.width=W;bgCv.height=H;
  const bgx=bgCv.getContext('2d');
  const sk=bgx.createLinearGradient(0,0,0,H*0.75);
  if(sak){sk.addColorStop(0,'#fce4ec');sk.addColorStop(0.5,'#fff3e0');sk.addColorStop(1,'#fff8f0');}
  else{sk.addColorStop(0,'#e8f5e9');sk.addColorStop(0.5,'#f1f8e9');sk.addColorStop(1,'#fafff5');}
  bgx.fillStyle=sk;bgx.fillRect(0,0,W,H);
  const gr=bgx.createLinearGradient(0,H-40,0,H);
  gr.addColorStop(0,'#8d6e4a');gr.addColorStop(0.3,'#6d5234');gr.addColorStop(1,'#5a432a');
  bgx.fillStyle=gr;bgx.beginPath();bgx.moveTo(0,H-25);bgx.quadraticCurveTo(W/2,H-35,W,H-25);bgx.lineTo(W,H);bgx.lineTo(0,H);bgx.fill();

  function sway(){
    ph+=0.01;ctx.clearRect(0,0,W,H);
    ctx.drawImage(bgCv,0,0);
    segs.forEach(s=>{
      const w=Math.sin(ph+s.d*0.5+s.x1*0.004)*s.d*0.4;
      const ss={...s,cx:s.cx+w*0.4,x2:s.x2+w};
      // Shadow
      ctx.beginPath();ctx.moveTo(ss.x1+1.5,ss.y1+1.5);ctx.quadraticCurveTo(ss.cx+1.5,ss.cy+1.5,ss.x2+1.5,ss.y2+1.5);
      ctx.strokeStyle='rgba(0,0,0,0.06)';ctx.lineWidth=ss.tw+1;ctx.lineCap='round';ctx.stroke();
      ctx.beginPath();ctx.moveTo(ss.x1,ss.y1);ctx.quadraticCurveTo(ss.cx,ss.cy,ss.x2,ss.y2);
      if(ss.d<=2){ctx.strokeStyle='#4a3020';}
      else if(ss.d<=5){ctx.strokeStyle='#5a3828';}
      else{ctx.strokeStyle=sak?`rgb(${90+Math.min(1,(ss.d-5)/5)*60},${55},${55})`:`rgb(${55},${80+Math.min(1,(ss.d-5)/5)*40},${40})`;}
      ctx.lineWidth=ss.tw;ctx.lineCap='round';ctx.stroke();
    });
    if(sak){
      flowers.forEach(f=>{
        const w=Math.sin(ph+f.x*0.006)*3;
        const sf={...f,x:f.x+w,y:f.y+Math.sin(ph*0.8+f.y*0.008)*1};
        drawFlowerStatic(ctx,sf);
      });
    }else{
      segs.filter(s=>s.d>=7).forEach(s=>{
        const w=Math.sin(ph+s.d*0.5)*s.d*0.4;
        for(let j=0;j<4;j++){
          const lx=s.x2+w+(Math.sin(j*7+ph)*4),ly=s.y2+(Math.cos(j*5+ph)*3);
          const lr=4;ctx.save();ctx.translate(lx,ly);ctx.rotate(j+ph*0.1);
          ctx.beginPath();ctx.moveTo(0,0);ctx.bezierCurveTo(lr*0.4,-lr*0.5,lr,-lr*0.2,lr,0);ctx.bezierCurveTo(lr,lr*0.2,lr*0.4,lr*0.5,0,0);
          ctx.fillStyle=`rgba(${50+j*15},${120+j*20},${40},0.75)`;ctx.fill();ctx.restore();
        }
      });
    }
    requestAnimationFrame(sway);
  }
  requestAnimationFrame(sway);
}

function drawFlowerStatic(ctx,f){
  const r=f.r,a=0.9;
  for(let i=0;i<f.np;i++){
    const pa=f.rot+(i/f.np)*Math.PI*2;
    ctx.save();ctx.translate(f.x,f.y);ctx.rotate(pa);
    ctx.beginPath();ctx.moveTo(0,0);
    ctx.bezierCurveTo(r*0.45,-r*0.4,r,-r*0.25,r*0.9,0);
    ctx.bezierCurveTo(r,r*0.25,r*0.45,r*0.4,0,0);
    const pg=ctx.createLinearGradient(0,0,r*0.9,0);
    pg.addColorStop(0,`rgba(255,250,252,${a})`);pg.addColorStop(0.3,`rgba(255,225,235,${a})`);
    pg.addColorStop(1,`rgba(245,155,185,${a*0.85})`);
    ctx.fillStyle=pg;ctx.fill();ctx.restore();
  }
  ctx.beginPath();ctx.arc(f.x,f.y,r*0.2,0,Math.PI*2);ctx.fillStyle='rgba(255,235,120,0.9)';ctx.fill();
}

function petalRain(el){setInterval(()=>{const p=document.createElement('div');p.className='spetal';const s=8+Math.random()*10;p.style.width=s+'px';p.style.height=s+'px';p.style.left=Math.random()*90+5+'%';p.style.top='-3%';p.style.animationDuration=4+Math.random()*4+'s';el.appendChild(p);setTimeout(()=>p.remove(),9000);},350);}

// ━━━━━━━━━━━━━━ DARUMA ━━━━━━━━━━━━━━━
function renderDaruma(state,containerId){
  const c=document.getElementById(containerId);if(!c)return;
  const dW=c.clientWidth||200,dH=c.clientHeight||220,S=2,W=dW*S,H=dH*S;
  c.innerHTML=`<div class="anim-canvas-wrap"><canvas id="cv-${containerId}" width="${W}" height="${H}" style="width:${dW}px;height:${dH}px"></canvas></div>`;
  const ctx=document.getElementById(`cv-${containerId}`).getContext('2d');
  animDaruma(ctx,W,H,state);
}

function animDaruma(ctx,W,H,state){
  const cx=W/2,cy=H*0.47,bw=W*0.38,bh=H*0.42;
  const dur=state>=2?5200:state>=1?4200:3200;
  let t0=null;
  function frame(ts){
    if(!t0)t0=ts;const p=Math.min(1,(ts-t0)/dur),st=p*60;
    ctx.clearRect(0,0,W,H);
    // Shadow
    ctx.beginPath();ctx.ellipse(cx,cy+bh*1.25,bw*0.75,bh*0.1,0,0,Math.PI*2);ctx.fillStyle='rgba(0,0,0,0.1)';ctx.fill();
    const bp=Math.min(1,st/18);if(bp>0)dBody(ctx,cx,cy,bw,bh,bp);
    const fp=Math.max(0,Math.min(1,(st-18)/14));if(fp>0)dFace(ctx,cx,cy,bw,bh,fp);
    const kp=Math.max(0,Math.min(1,(st-32)/10));if(kp>0)dKanji(ctx,cx,cy,bw,bh,kp);
    if(state>=1){const ep=Math.max(0,Math.min(1,(st-42)/6));if(ep>0)dEye(ctx,cx,cy,bw,bh,'left',ep);}
    if(state>=2){const e2=Math.max(0,Math.min(1,(st-49)/6));if(e2>0)dEye(ctx,cx,cy,bw,bh,'right',e2);if(st>56)dCeleb(ctx,cx,cy,bw,bh,Math.min(1,(st-56)/4));}
    if(p<1)requestAnimationFrame(frame);else dIdle(ctx,W,H,cx,cy,bw,bh,state);
  }
  requestAnimationFrame(frame);
}

function dBody(ctx,cx,cy,bw,bh,p){
  ctx.save();
  // Progressive clip
  const top=cy+bh*1.2-(cy+bh*1.2-(cy-bh*1.1))*p;
  ctx.beginPath();ctx.rect(0,top,cx*4,cy+bh*1.3-top);ctx.clip();
  // Daruma body — proper tumbler shape: wide bottom, narrow top
  ctx.beginPath();
  ctx.moveTo(cx,cy-bh*0.95);
  ctx.bezierCurveTo(cx+bw*0.5,cy-bh*0.98, cx+bw*1.05,cy-bh*0.35, cx+bw*1.08,cy+bh*0.15);
  ctx.bezierCurveTo(cx+bw*1.05,cy+bh*0.75, cx+bw*0.65,cy+bh*1.15, cx,cy+bh*1.18);
  ctx.bezierCurveTo(cx-bw*0.65,cy+bh*1.15, cx-bw*1.05,cy+bh*0.75, cx-bw*1.08,cy+bh*0.15);
  ctx.bezierCurveTo(cx-bw*1.05,cy-bh*0.35, cx-bw*0.5,cy-bh*0.98, cx,cy-bh*0.95);
  ctx.closePath();
  // Rich lacquer red gradient
  const bg=ctx.createRadialGradient(cx-bw*0.25,cy-bh*0.35,bw*0.05, cx+bw*0.1,cy+bh*0.2,bw*1.3);
  bg.addColorStop(0,'#f04040');bg.addColorStop(0.25,'#e02020');bg.addColorStop(0.5,'#c41818');bg.addColorStop(0.8,'#8f1010');bg.addColorStop(1,'#5a0808');
  ctx.fillStyle=bg;ctx.fill();
  ctx.strokeStyle='#4a0505';ctx.lineWidth=2.5;ctx.stroke();
  // Lacquer shine highlight
  ctx.beginPath();ctx.ellipse(cx-bw*0.35,cy-bh*0.45,bw*0.3,bh*0.25,-0.45,0,Math.PI*2);
  const sh=ctx.createRadialGradient(cx-bw*0.35,cy-bh*0.45,0,cx-bw*0.35,cy-bh*0.45,bw*0.3);
  sh.addColorStop(0,'rgba(255,255,255,0.22)');sh.addColorStop(0.5,'rgba(255,200,200,0.08)');sh.addColorStop(1,'rgba(255,255,255,0)');
  ctx.fillStyle=sh;ctx.fill();
  // Bottom rim shine
  ctx.beginPath();ctx.ellipse(cx+bw*0.15,cy+bh*0.85,bw*0.4,bh*0.15,0.2,0,Math.PI*2);
  const bs=ctx.createRadialGradient(cx+bw*0.15,cy+bh*0.85,0,cx+bw*0.15,cy+bh*0.85,bw*0.4);
  bs.addColorStop(0,'rgba(255,180,180,0.12)');bs.addColorStop(1,'rgba(255,255,255,0)');
  ctx.fillStyle=bs;ctx.fill();
  // Gold decorative bands
  ctx.strokeStyle='#c8960a';ctx.lineWidth=2.2;
  ctx.beginPath();ctx.moveTo(cx-bw*0.98,cy+bh*0.55);ctx.quadraticCurveTo(cx,cy+bh*0.68,cx+bw*0.98,cy+bh*0.55);ctx.stroke();
  ctx.strokeStyle='#a07808';ctx.lineWidth=1.5;
  ctx.beginPath();ctx.moveTo(cx-bw*0.95,cy+bh*0.62);ctx.quadraticCurveTo(cx,cy+bh*0.74,cx+bw*0.95,cy+bh*0.62);ctx.stroke();
  ctx.restore();
}

function dFace(ctx,cx,cy,bw,bh,p){
  ctx.save();ctx.globalAlpha=p;
  const fW=bw*0.68,fH=bw*0.58,fY=cy-bh*0.12;
  // Triple-ring border (traditional)
  [{r:9,c:'#a07808',w:2.5},{r:5,c:'#6a0808',w:2},{r:0,c:'#c8a050',w:1.5}].forEach(ring=>{
    ctx.beginPath();ctx.ellipse(cx,fY,fW+ring.r,fH+ring.r,0,0,Math.PI*2);
    ctx.strokeStyle=ring.c;ctx.lineWidth=ring.w;ctx.stroke();
  });
  // Face fill
  ctx.beginPath();ctx.ellipse(cx,fY,fW,fH,0,0,Math.PI*2);
  const fg=ctx.createRadialGradient(cx-fW*0.15,fY-fH*0.2,0,cx,fY,fW);
  fg.addColorStop(0,'#fffdf5');fg.addColorStop(0.6,'#fff5e0');fg.addColorStop(1,'#f0dbb8');
  ctx.fillStyle=fg;ctx.fill();
  ctx.strokeStyle='#c8a060';ctx.lineWidth=1;ctx.stroke();
  // Eye sockets
  const eY=fY-fH*0.05,eOff=fW*0.34,sR=fW*0.19;
  [-1,1].forEach(side=>{
    ctx.beginPath();ctx.arc(cx+side*eOff,eY,sR,0,Math.PI*2);ctx.fillStyle='#fff';ctx.fill();
    ctx.strokeStyle='#444';ctx.lineWidth=1.5;ctx.stroke();
  });
  // Fierce eyebrows — thick calligraphy brush strokes
  ctx.lineCap='round';ctx.strokeStyle='#1a1a1a';
  [-1,1].forEach(side=>{
    const ex=cx+side*eOff,bY=eY-sR-5;
    // Main brow — thick tapering stroke
    ctx.lineWidth=4;ctx.beginPath();
    ctx.moveTo(ex-side*sR*1.2,bY+3);
    ctx.quadraticCurveTo(ex-side*sR*0.2,bY-10,ex+side*sR*0.6,bY+2);ctx.stroke();
    // Brow flick
    ctx.lineWidth=2.5;ctx.beginPath();
    ctx.moveTo(ex+side*sR*0.6,bY+2);ctx.lineTo(ex+side*sR*1.0,bY-2);ctx.stroke();
  });
  // Nose
  ctx.beginPath();ctx.arc(cx,fY+fH*0.18,2.5,0,Math.PI*2);ctx.fillStyle='#4a4a4a';ctx.fill();
  // Mouth — stern traditional style
  ctx.lineWidth=2;ctx.strokeStyle='#2a2a2a';ctx.beginPath();
  ctx.moveTo(cx-fW*0.22,fY+fH*0.35);
  ctx.quadraticCurveTo(cx-fW*0.08,fY+fH*0.44,cx,fY+fH*0.38);
  ctx.quadraticCurveTo(cx+fW*0.08,fY+fH*0.44,cx+fW*0.22,fY+fH*0.35);ctx.stroke();
  // Cheek blush (subtle)
  [-1,1].forEach(side=>{
    ctx.beginPath();ctx.arc(cx+side*(eOff+sR*0.3),fY+fH*0.25,sR*0.45,0,Math.PI*2);
    ctx.fillStyle='rgba(240,140,120,0.1)';ctx.fill();
  });
  ctx.restore();
}

function dKanji(ctx,cx,cy,bw,bh,p){
  ctx.save();ctx.globalAlpha=p;
  const ky=cy+bh*0.58,ks=bw*0.52;
  ctx.font=`bold ${ks}px "Yu Mincho","Noto Serif TC",serif`;ctx.textAlign='center';ctx.textBaseline='middle';
  const kg=ctx.createLinearGradient(cx,ky-ks/2,cx,ky+ks/2);
  kg.addColorStop(0,'#f0c840');kg.addColorStop(0.5,'#d4a020');kg.addColorStop(1,'#b08010');
  ctx.fillStyle=kg;ctx.fillText('福',cx,ky);
  ctx.strokeStyle='#806010';ctx.lineWidth=0.6;ctx.strokeText('福',cx,ky);
  ctx.restore();
}

function dEye(ctx,cx,cy,bw,bh,side,p){
  ctx.save();
  const fW=bw*0.68,fH=bw*0.58,fY=cy-bh*0.12;
  const eY=fY-fH*0.05,eOff=fW*0.34;
  const ex=side==='left'?cx-eOff:cx+eOff;
  const sR=fW*0.19,pR=sR*0.6*p;
  // Ink splash at start
  if(p<0.5){for(let i=0;i<6;i++){const a=(i/6)*Math.PI*2;const d=pR*(1.2+Math.random()*0.8);ctx.beginPath();ctx.arc(ex+Math.cos(a)*d,eY+Math.sin(a)*d,0.5+Math.random(),0,Math.PI*2);ctx.fillStyle=`rgba(10,10,10,${p*0.4})`;ctx.fill();}}
  // Pupil
  ctx.beginPath();ctx.arc(ex,eY,pR,0,Math.PI*2);
  const eg=ctx.createRadialGradient(ex-pR*0.2,eY-pR*0.2,0,ex,eY,pR);
  eg.addColorStop(0,'#1a1a1a');eg.addColorStop(1,'#000');ctx.fillStyle=eg;ctx.fill();
  if(p>0.65){const sa=(p-0.65)/0.35;
    ctx.beginPath();ctx.arc(ex-pR*0.28,eY-pR*0.28,pR*0.2,0,Math.PI*2);ctx.fillStyle=`rgba(255,255,255,${sa*0.85})`;ctx.fill();
    ctx.beginPath();ctx.arc(ex+pR*0.15,eY+pR*0.15,pR*0.08,0,Math.PI*2);ctx.fillStyle=`rgba(255,255,255,${sa*0.45})`;ctx.fill();
  }
  ctx.restore();
}

function dCeleb(ctx,cx,cy,bw,bh,p){
  ctx.save();ctx.globalAlpha=p;
  const cols=['#FFD700','#FF5252','#FFB7C5','#FF6D00','#4CAF50','#E040FB','#FF9100'];
  for(let i=0;i<20;i++){
    const a=(i/20)*Math.PI*2+p*0.8;const d=bw*1.5+Math.sin(i*2)*bw*0.3;
    const px=cx+Math.cos(a)*d*p,py=cy+Math.sin(a)*d*p-bh*0.15;
    const r=1.5+Math.sin(i*3)*1.5;
    ctx.beginPath();
    if(i%4===0){for(let k=0;k<8;k++){const sa=(k/8)*Math.PI*2-Math.PI/2;ctx.lineTo(px+Math.cos(sa)*(k%2?r*0.4:r+1),py+Math.sin(sa)*(k%2?r*0.4:r+1));}}
    else ctx.arc(px,py,r,0,Math.PI*2);
    ctx.fillStyle=cols[i%cols.length];ctx.fill();
  }
  ctx.fillStyle='#ffd700';ctx.font=`${bw*0.2}px serif`;ctx.textAlign='center';
  for(let i=0;i<5;i++){const a=(i/5)*Math.PI*2+p;ctx.fillText('✦',cx+Math.cos(a)*bw*1.6,cy+Math.sin(a)*bw*1.5);}
  ctx.restore();
}

function dIdle(ctx,W,H,cx,cy,bw,bh,state){
  let ph=0;
  function wobble(){
    ph+=0.016;const ang=Math.sin(ph)*0.022,bounce=Math.sin(ph*1.8)*1.2;
    ctx.clearRect(0,0,W,H);
    ctx.beginPath();ctx.ellipse(cx+Math.sin(ph)*2,cy+bh*1.25,bw*0.75,bh*0.1,0,0,Math.PI*2);ctx.fillStyle='rgba(0,0,0,0.1)';ctx.fill();
    ctx.save();ctx.translate(cx,cy+bh*1.18);ctx.rotate(ang);ctx.translate(-cx,-(cy+bh*1.18));ctx.translate(0,bounce);
    dBody(ctx,cx,cy,bw,bh,1);dFace(ctx,cx,cy,bw,bh,1);dKanji(ctx,cx,cy,bw,bh,1);
    if(state>=1)dEye(ctx,cx,cy,bw,bh,'left',1);
    if(state>=2){dEye(ctx,cx,cy,bw,bh,'right',1);dCeleb(ctx,cx,cy,bw,bh,0.55+Math.sin(ph)*0.12);}
    ctx.restore();requestAnimationFrame(wobble);
  }requestAnimationFrame(wobble);
}

function createPetals(id){const el=document.getElementById(id);if(el)petalRain(el);}
