import {$,lerp,cl,sm} from './util.js';

/* 2D comparison mode: two flat equirectangular maps side by side (Moon-Earth or Mars-Earth).
   Visual = the surface texture. Thermal = the SAME modelled-temperature physics as the 3D shader (scene.js),
   evaluated per pixel for a Sun directly over the map centre (lat 0, lon 0). Modelled, not measured. */
const MP={moon:{Tn:95,Td:395,Aref:.12,Alo:.03,Ak:.28,inr:1,lf:.45},mars:{Tn:165,Td:295,Aref:.25,Alo:.04,Ak:.34,inr:.9,lf:.22},earth:{Tn:262,Td:335,Aref:.1,Alo:.05,Ak:.1,inr:.6,lf:.18}};
const RNG={moon:[50,400],mars:[125,300],earth:[215,335]};
const INFO={moon:['MOON','3,474 km | 0.165 g'],mars:['MARS','6,779 km | 0.379 g'],earth:['EARTH','12,742 km | 1.00 g']};
const SRC={moon:'assets/textures/moon.jpg',mars:'assets/textures/mars.jpg',earth:'assets/textures/earth_map.jpg'};
const W=1024,H=512,IMG={},PIX={};
const jet=t=>{t=cl(t);let r=cl(1.5-Math.abs(4*t-3)),g=cl(1.5-Math.abs(4*t-2)),b=cl(1.5-Math.abs(4*t-1));
  const k=sm(0,.12,t);return[lerp(.2,r,k),lerp(0,g,k),lerp(.32,b,k)]};
const load=k=>IMG[k]||(IMG[k]=new Promise(res=>{const i=new Image();i.onload=()=>{const c=document.createElement('canvas');c.width=W;c.height=H;const x=c.getContext('2d');x.drawImage(i,0,0,W,H);PIX[k]=x.getImageData(0,0,W,H);res(c)};i.onerror=()=>res(null);i.src=SRC[k]}));

function temperature(k,px,j,i){
  const lat=Math.abs((j+.5)/H-.5)*2,la=(.5-(j+.5)/H)*Math.PI,lo=((i+.5)/W-.5)*2*Math.PI,cs=Math.max(Math.cos(la)*Math.cos(lo),0);
  const d=PIX[k].data,o=(j*W+i)*4,r=d[o]/255,g=d[o+1]/255,b=d[o+2]/255;
  if(k==='earth'&&Math.abs(d[o]-14)+Math.abs(d[o+1]-52)+Math.abs(d[o+2]-96)<22)return lerp(271,301,Math.pow(1-lat,1.3))+2*cs; /* ocean pixel (matches the map fill colour) */
  const p=MP[k],lum=.3*r+.59*g+.11*b,A=cl(p.Alo+p.Ak*lum,.02,.9),f=(1-A)/(1-p.Aref),ice=sm(.72,.9,lum)*sm(.55,.75,lat);
  const lp=Math.pow(lat,1.4),tn=p.Tn*(1-p.lf*lp),td=p.Td*(1-p.lf*.5*lp),a4=Math.pow(tn/100,4),b4=Math.pow(td/100,4),tr=100*Math.pow(a4+(b4-a4)*cs*f,.25);
  return lerp(tn+(td-tn)*.55,tr,p.inr)-48*ice;
}
function graticule(x){x.strokeStyle='rgba(255,255,255,.16)';x.lineWidth=1;x.beginPath();
  for(let i=1;i<12;i++){x.moveTo(W*i/12,0);x.lineTo(W*i/12,H)}for(let j=1;j<6;j++){x.moveTo(0,H*j/6);x.lineTo(W,H*j/6)}x.stroke();
  x.strokeStyle='rgba(255,255,255,.34)';x.beginPath();x.moveTo(0,H/2);x.lineTo(W,H/2);x.moveTo(W/2,0);x.lineTo(W/2,H);x.stroke()}

export function initFlat(){
  const root=$('#flat'),body=document.body,st={dim:'3d',pair:'moon'};
  const seg=(id,key,after)=>document.querySelectorAll(id+' button').forEach(b=>b.onclick=()=>{st[key]=b.dataset.v;$(id).dataset.m=b.dataset.v;
    document.querySelectorAll(id+' button').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on)});after()});
  const apply=()=>{if(window.ADE&&window.ADE.setFlat)window.ADE.setFlat(st.dim==='flat');body.classList.toggle('flat2d',st.dim==='flat');if(st.dim==='flat')render()};
  seg('#dm','dim',apply);seg('#pr','pair',apply);
  async function draw(k,cv){await load(k);if(!PIX[k])return;const thermal=body.classList.contains('thermal'),own=$('#tsc').dataset.own==='true',x=cv.getContext('2d');cv.width=W;cv.height=H;
    if(!thermal){x.drawImage(await IMG[k],0,0)}
    else{const lo=own?RNG[k][0]:80,hi=own?RNG[k][1]:420,im=x.createImageData(W,H),o=im.data;
      for(let j=0;j<H;j++)for(let i=0;i<W;i++){const c=jet((temperature(k,PIX[k],j,i)-lo)/(hi-lo)),n=(j*W+i)*4;o[n]=c[0]*255;o[n+1]=c[1]*255;o[n+2]=c[2]*255;o[n+3]=255}
      x.putImageData(im,0,0)}
    graticule(x)}
  let busy=0;
  async function render(){const id=++busy,ks=[st.pair,'earth'];
    ks.forEach((k,n)=>{const f=root.children[n];f.querySelector('b').textContent=INFO[k][0];f.querySelector('.v').textContent=INFO[k][1];
      f.querySelector('.t').textContent=body.classList.contains('thermal')?`modelled ~${RNG[k][0]} - ${RNG[k][1]} K`:'surface texture'});
    await Promise.all(ks.map((k,n)=>draw(k,root.children[n].querySelector('canvas'))));if(id!==busy)return}
  /* re-render when the Visual/Thermal switch or the shared/own scale button changes */
  const mo=new MutationObserver(()=>{if(st.dim==='flat')render()});mo.observe($('#vw'),{attributes:true,attributeFilter:['data-m']});mo.observe($('#tsc'),{attributes:true,attributeFilter:['data-own']});
}
