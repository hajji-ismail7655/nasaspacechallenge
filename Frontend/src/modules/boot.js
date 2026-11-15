import {SFX,MUS,initAudio} from './audio.js';
import {buildScene} from './scene.js';
import {initFlat} from './flat.js';
import {$,sleep,RED,lerp,cl,sm,hs,rnd,TAU,spin} from './util.js';
import {h3,n3,fbm,crat} from './noise.js';
let started=false;
export function boot(){
if(started)return;started=true;
initAudio();
initFlat();
setInterval(()=>{const n=new Date();$('#utc').textContent=n.toISOString().slice(0,19).replace('T',' ');$('#sol').textContent=((n-new Date('2026-01-01'))/88775244).toFixed(1).padStart(6,'0')},1000);
(async()=>{await sleep(60);let S;try{S=await buildScene()}catch(e){console.error(e);$('#begin').textContent='3D failed to load. Check connection';return}
 const b=$('#begin');b.disabled=false;b.textContent='Click to begin';window.ADE=S;document.querySelectorAll('#sz button').forEach(b=>b.onclick=()=>{S.setScale(b.dataset.m);$('#sz').dataset.m=b.dataset.m;document.querySelectorAll('#sz button').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on)})});
 document.querySelectorAll('#vw button').forEach(v=>v.onclick=()=>{S.setView(v.dataset.v);$('#vw').dataset.m=v.dataset.v;document.body.classList.toggle('thermal',v.dataset.v==='thermal');document.querySelectorAll('#vw button').forEach(x=>{const on=x===v;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on)})});
 $('#tsc').onclick=()=>{const own=$('#tsc').dataset.own!=='true';$('#tsc').dataset.own=own;$('#tsc').textContent=own?'Each planet':'Shared scale';S.setTScale(own);[...document.querySelectorAll('#tlg .tk span')].forEach((e,i)=>e.textContent=own?['HOT','','','','COLD'][i]:['420 K','335','250','165','80'][i])};
 b.onclick=async()=>{b.disabled=true;b.style.opacity=0;SFX.init();MUS.prime();const f=RED?.3:1;await sleep(700*f);$('#logo').classList.add('show');await sleep(4000*f);$('#logo').classList.remove('show');MUS.start();await sleep(2600*f);
  $('#intro').classList.add('gone');S.go();document.body.classList.add('ready');setTimeout(()=>$('#intro').remove(),1800)}})();
}
