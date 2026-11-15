const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms)),RED=matchMedia('(prefers-reduced-motion: reduce)').matches;
const lerp=(a,b,t)=>a+(b-a)*t,cl=(x,a=0,b=1)=>Math.min(b,Math.max(a,x)),sm=(a,b,x)=>{x=cl((x-a)/(b-a));return x*x*(3-2*x)};
const hs=s=>{let h=2166136261;for(const c of s)h=Math.imul(h^c.charCodeAt(0),16777619);return h>>>0};
const rnd=s=>()=>{s|=0;s=s+0x6D2B79F5|0;let t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296};
const TAU=Math.PI*2,spin=(o,w)=>{o.rotation.y=(o.rotation.y+w)%TAU};/* wrapped so angles never grow without bound */
export {$,sleep,RED,lerp,cl,sm,hs,rnd,TAU,spin};
