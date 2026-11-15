import {lerp} from './util.js';
const h3=(x,y,z)=>{let h=Math.imul(x,374761393)^Math.imul(y,668265263)^Math.imul(z,1274126177);h=Math.imul(h^h>>>13,1274126177);return((h^h>>>16)>>>0)/4294967296};
function n3(x,y,z){const X=Math.floor(x),Y=Math.floor(y),Z=Math.floor(z),a=x-X,b=y-Y,c=z-Z,u=a*a*(3-2*a),v=b*b*(3-2*b),w=c*c*(3-2*c);
 return lerp(lerp(lerp(h3(X,Y,Z),h3(X+1,Y,Z),u),lerp(h3(X,Y+1,Z),h3(X+1,Y+1,Z),u),v),lerp(lerp(h3(X,Y,Z+1),h3(X+1,Y,Z+1),u),lerp(h3(X,Y+1,Z+1),h3(X+1,Y+1,Z+1),u),v),w)}
function fbm(x,y,z,o=5){let s=0,a=.5,f=1;for(let i=0;i<o;i++){s+=a*n3(x*f,y*f,z*f);f*=2.03;a*=.5}return s}
function crat(x,y,z,s,sd){const px=x*s,py=y*s,pz=z*s,ix=Math.floor(px),iy=Math.floor(py),iz=Math.floor(pz);if(h3(ix+sd,iy,iz)>.5)return 0;
 const cx=ix+.35+.3*h3(ix,iy+sd,iz),cy=iy+.35+.3*h3(ix,iy,iz+sd),cz=iz+.35+.3*h3(ix+7,iy,iz+sd),r=.12+.2*h3(ix,iy+9,iz+sd),d=Math.hypot(px-cx,py-cy,pz-cz)/r;
 return d<1?-(1-d*d)*.6:d<1.3?.25*(1.3-d)/.3:0}
export {h3,n3,fbm,crat};
