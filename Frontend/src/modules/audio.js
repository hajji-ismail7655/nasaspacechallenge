import {$,sleep,RED,lerp,cl,sm,hs,rnd,TAU,spin} from './util.js';
import {h3,n3,fbm,crat} from './noise.js';
/* ---- audio ---- */
const SFX=(()=>{let ctx,buf,last=0;return{
 init(){if(!ctx){ctx=new(window.AudioContext||window.webkitAudioContext)();fetch('assets/audio/click.mp3').then(r=>r.ok?r.arrayBuffer():Promise.reject()).then(b=>ctx.decodeAudioData(b)).then(b=>buf=b).catch(()=>{})}ctx.resume()},
 click(){if(!ctx)return;const t=ctx.currentTime,g=ctx.createGain();if(buf){const s=ctx.createBufferSource();s.buffer=buf;g.gain.value=.5;s.connect(g).connect(ctx.destination);s.start();return}
  const o=ctx.createOscillator();o.frequency.setValueAtTime(1500,t);o.frequency.exponentialRampToValueAtTime(700,t+.05);g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.07,t+.004);g.gain.exponentialRampToValueAtTime(.0001,t+.07);o.connect(g).connect(ctx.destination);o.start(t);o.stop(t+.08)},
 type(){if(!ctx)return;const n=performance.now();if(n-last<30)return;last=n;const t=ctx.currentTime,o=ctx.createOscillator(),f=ctx.createBiquadFilter(),g=ctx.createGain();o.type='square';o.frequency.value=1100+Math.random()*900;f.type='bandpass';f.frequency.value=2200;f.Q.value=4;g.gain.setValueAtTime(.03,t);g.gain.exponentialRampToValueAtTime(.0001,t+.03);o.connect(f).connect(g).connect(ctx.destination);o.start(t);o.stop(t+.035)}}})();
const MUS=(()=>{const SRC='assets/audio/quiet-echoes.mp3',OV=4,V=.3;
 /* endless loop: two players; the next one starts OV seconds before the current one ends, so the track's own fade-out overlaps its fade-in (no silent gap).
    Each cycle uses a FRESH element, so it never needs to seek (simple servers such as python http.server have no Range support, which breaks seeking). */
 let on=true,lv=0,run=false,iv=0,P,Q;
 const mk=()=>{const a=new Audio(SRC);a.preload='auto';a.volume=on?lv:0;a.onerror=()=>{$('#load').hidden=false};a.onended=()=>{if(a!==P)return;if(Q.paused)go(Q);swap()};return a},
  vol=()=>{P.volume=Q.volume=on?lv:0},go=e=>{e.play().catch(()=>{})},swap=()=>{const old=P;P=Q;Q=mk();old.onended=null;try{old.pause()}catch(e){}};
 P=mk();Q=mk();
 const tick=()=>{if(!run)return;if(lv<V){lv=Math.min(V,lv+.008);vol()}const d=P.duration;if(d&&isFinite(d)&&!P.paused&&d-P.currentTime<=OV&&Q.paused)go(Q)},begin=()=>{run=true;vol();clearInterval(iv);iv=setInterval(tick,100)};
 return{prime(){P.play().catch(()=>{})},start(){lv=0;vol();if(P.currentTime>0.05){P.onended=null;P=mk()}go(P);begin()},toggle(){on=!on;vol();return on},dbg:()=>({P,Q}),
  file(f){const u=URL.createObjectURL(f);P.src=Q.src=u;go(P);begin();$('#mname').textContent=f.name.slice(0,28).toUpperCase()}}})();
export {SFX,MUS};
export function initAudio(){
document.addEventListener('pointerdown',()=>SFX.click());
$('#mt').onclick=()=>{const o=MUS.toggle();$('#mt').textContent=o?'Mute':'Unmute';$('#mt').dataset.on=o};
$('#load input').onchange=e=>e.target.files[0]&&MUS.file(e.target.files[0]);
}
