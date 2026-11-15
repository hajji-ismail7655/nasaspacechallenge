import * as THREE from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import {$,sleep,RED,lerp,cl,sm,hs,rnd,TAU,spin} from './util.js';
import {h3,n3,fbm,crat} from './noise.js';
/* ---- planet textures ---- */
function planetTex(kind,R){const W=kind==='earth'?1536:1024,H=W/2,mk=()=>{const c=document.createElement('canvas');c.width=W;c.height=H;return c},cv=[mk(),mk(),mk(),mk(),mk()],im=cv.map(c=>c.getContext('2d').createImageData(W,H));
 for(let j=0;j<H;j++){const lat=(.5-(j+.5)/H)*Math.PI,cs=Math.cos(lat),y=Math.sin(lat);
  for(let i=0;i<W;i++){const lon=(i+.5)/W*6.2832,x=cs*Math.cos(lon),z=cs*Math.sin(lon),k=(j*W+i)*4;let r,g,b,h,ro=200,cc=0,em=0;
   if(kind==='earth'){const wx=fbm(x*1.6+11,y*1.6,z*1.6,3)-.5,e=fbm(x*2.1+5+wx*1.1,y*2.1+wx*.8,z*2.1,6),SL=.565;let lit=0;
    if(e<SL){const d=e/SL,sh=sm(.86,1,d);r=lerp(4,26,sh)+d*8;g=lerp(18,98,sh)+d*14;b=lerp(46,132,sh)+d*20;ro=115;h=.5}
    else{const el=(e-SL)/.35,mo=fbm(x*3+1,y*3+8,z*3,5);let t=cl((mo-.4)*3.5);t=cl(t-Math.exp(-((Math.abs(y)-.42)**2)/.025)*.6);
     const dr=[176,150,100],sv=[96,104,56],fo=[30,66,36],u=t<.5?t*2:(t-.5)*2,A=t<.5?dr:sv,B=t<.5?sv:fo;
     r=lerp(A[0],B[0],u);g=lerp(A[1],B[1],u);b=lerp(A[2],B[2],u);const tu=sm(.68,.86,Math.abs(y));r=lerp(r,112,tu);g=lerp(g,120,tu);b=lerp(b,108,tu);
     const mt=cl(el*1.6-.35);r=lerp(r,118,mt);g=lerp(g,108,mt);b=lerp(b,100,mt);h=.52+el*.7;
     lit=Math.abs(y)<.68&&fbm(x*16,y*16,z*16,3)>.6?sm(.4,.8,fbm(x*3.5+2,y*3.5,z*3.5,4)):0}
    if(Math.abs(y)+(fbm(x*6,y*6,z*6,3)-.5)*.14>.88){r=g=b=238;h=.54;ro=120;lit=0}
    cc=sm(.54,.8,fbm(x*3.2+9+wx*2,y*4.5+2,z*3.2,6));em=lit}
   else if(kind==='moon'){let ba=.52+(fbm(x*3,y*3,z*3,5)-.5)*.5;const mare=sm(0,.12,fbm(x*1.3+7,y*1.3,z*1.3,3)-.5),c=crat(x,y,z,5,1)+.8*crat(x,y,z,12,2)+.6*crat(x,y,z,26,3);
    ba*=1-.35*mare;const v=cl(55+ba*165+c*70,0,255),tn=fbm(x*1.8+3,y*1.8,z*1.8,3)-.5;r=v*(1+tn*.3+mare*.05);g=v*(.98+tn*.05);b=v*(.94-tn*.3+mare*.12);h=.5+c*.5+(ba-.5)*.3}
   else{const ba=fbm(x*2.4,y*2.4+3,z*2.4,6),pa=sm(0,.1,fbm(x*1.2+3,y*1.2,z*1.2,4)-.5),c=.7*crat(x,y,z,7,4)+.5*crat(x,y,z,16,5);
    r=(150+ba*75+c*40)*(1-.4*pa);g=(72+ba*42+c*20)*(1-.4*pa);b=(42+ba*28+c*12)*(1-.35*pa);h=ba*.6+c*.4+.3;const LD=lon*57.2958,tt=(LD-270)/70,vm=tt>0&&tt<1?Math.exp(-Math.pow(((lat*57.2958)+8-3*Math.sin(tt*6.28))/2.4,2))*Math.sin(tt*3.1416):0;r*=1-.55*vm;g*=1-.5*vm;b*=1-.45*vm;h-=vm*.4;
    if(Math.abs(y)>.9+(fbm(x*5,y*5,z*5,3)-.5)*.08){r=228;g=222;b=214;h=.6}}
   const d=[im[0].data,im[1].data,im[2].data,im[3].data,im[4].data];d[0][k]=r;d[0][k+1]=g;d[0][k+2]=b;d[0][k+3]=255;
   d[1][k]=d[1][k+1]=d[1][k+2]=cl(h,0,1)*255;d[1][k+3]=255;d[2][k]=d[2][k+1]=d[2][k+2]=ro;d[2][k+3]=255;d[3][k]=d[3][k+1]=d[3][k+2]=255;d[3][k+3]=cc*215;d[4][k]=em*255;d[4][k+1]=em*185;d[4][k+2]=em*95;d[4][k+3]=255}}
 const T=cv.map((c,n)=>{c.getContext('2d').putImageData(im[n],0,0);const t=new THREE.CanvasTexture(c);t.anisotropy=R.capabilities.getMaxAnisotropy();if(n===0||n===3||n===4)t.encoding=THREE.sRGBEncoding;return t});
 return{name:kind,map:T[0],bump:T[1],rough:T[2],cloud:T[3],emis:T[4]}}
const atmo=(r,col,pw,k,s,sv)=>new THREE.Mesh(new THREE.SphereGeometry(r*s,64,64),new THREE.ShaderMaterial({uniforms:{c:{value:new THREE.Color(col)},pw:{value:pw},k:{value:k},sv:{value:sv},cm:{value:Math.sqrt(1-1/(s*s))}},
 vertexShader:'varying vec3 n,v;void main(){n=normalize(normalMatrix*normal);vec4 m=modelViewMatrix*vec4(position,1.);v=-m.xyz;gl_Position=projectionMatrix*m;}',
 fragmentShader:'uniform vec3 c,sv;uniform float pw,k,cm;varying vec3 n,v;void main(){float q=-dot(normalize(n),normalize(v));float f=pow(smoothstep(0.,cm,q),pw)*k*(.1+.9*smoothstep(-.25,.6,dot(normalize(n),sv)));gl_FragColor=vec4(c*f,f);}',
 blending:THREE.AdditiveBlending,side:THREE.BackSide,transparent:true,depthWrite:false}));
function starField(R){const N=5500,M=0,T=N+M,P=new Float32Array(T*3),C=new Float32Array(T*3),S=new Float32Array(T),Ph=new Float32Array(T),rn=Math.random;
 for(let i=0;i<T;i++){let x,y,z;if(i<N){const u=rn()*2-1,a=rn()*6.2832,s=Math.sqrt(1-u*u);x=s*Math.cos(a);y=u;z=s*Math.sin(a)}
  else{const a=rn()*6.2832,th=(rn()+rn()+rn()-1.5)*.22;x=Math.cos(a)*Math.cos(th);y=Math.sin(th);z=Math.sin(a)*Math.cos(th);const ty=y*Math.cos(.9)-z*Math.sin(.9),tz=y*Math.sin(.9)+z*Math.cos(.9);y=ty;z=tz}
  P.set([x*900,y*900,z*900],i*3);const t=rn(),c=t<.15?[.7,.8,1]:t<.75?[1,1,1]:[1,.88,.72],br=i<N?.38+Math.pow(rn(),3)*.45:.1+rn()*.16;C.set([c[0]*br,c[1]*br,c[2]*br],i*3);S[i]=i<N?1+Math.pow(rn(),7)*3.4:.9+rn()*1;Ph[i]=rn()}
 const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(P,3));g.setAttribute('col',new THREE.BufferAttribute(C,3));g.setAttribute('size',new THREE.BufferAttribute(S,1));g.setAttribute('ph',new THREE.BufferAttribute(Ph,1));
 const m=new THREE.ShaderMaterial({uniforms:{t:{value:0},px:{value:R.getPixelRatio()}},vertexShader:'attribute vec3 col;attribute float size,ph;varying vec3 vc;uniform float t,px;void main(){vc=col*(.86+.14*sin(t*.6+ph*6.28));gl_PointSize=size*px;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
  fragmentShader:'varying vec3 vc;void main(){float d=length(gl_PointCoord-.5);float a=smoothstep(.5,0.,d);gl_FragColor=vec4(vc,min(1.,a*1.6));}',transparent:true,depthWrite:false,blending:THREE.AdditiveBlending});
 return new THREE.Points(g,m)}
let NIGHT=null;
/* box of the real surface only: the GLB also holds a cloud shell and a hidden atmosphere shell that used to inflate the size, so Earth rendered smaller than its siblings */
function surfaceBox(sc,k){const b=new THREE.Box3();if(k==='earth'){sc.traverse(o=>{if(o.isMesh&&(o.material.name==='earth'||o.material.name==='ocean'))b.expandByObject(o)})}else b.setFromObject(sc);return b}
function planetFromGLB(gltf,r,k){const sc=gltf.scene,Q=new THREE.Group(),P=new THREE.Group();let mesh;sc.updateMatrixWorld(true);sc.traverse(o=>{if(o.isMesh&&!mesh)mesh=o});
 if(mesh&&mesh.geometry.attributes.uv){const uv=mesh.geometry.attributes.uv,ps=mesh.geometry.attributes.position,a=new THREE.Vector3(),n=new THREE.Vector3();let c=0;
  for(let i=0;i<uv.count;i++){const v=uv.getY(i);if(v>.995||v<.005){a.fromBufferAttribute(ps,i);n.add(v>.5?a:a.negate());c++}}
  if(c&&n.lengthSq()>1e-6){n.transformDirection(mesh.matrixWorld);sc.quaternion.premultiply(new THREE.Quaternion().setFromUnitVectors(n,new THREE.Vector3(0,1,0)))}}
 sc.updateMatrixWorld(true);const box=surfaceBox(sc,k),sz=box.getSize(new THREE.Vector3()),ct=box.getCenter(new THREE.Vector3()),kk=r/(Math.max(sz.x,sz.y,sz.z)/2);
 sc.scale.multiplyScalar(kk);sc.position.copy(ct).multiplyScalar(-kk);
 P.userData.parts={};sc.traverse(o=>{if(o.isMesh){const m=o.material;m.side=THREE.FrontSide;
  if(k==='earth'){const nm=m.name;
   (P.userData.parts[nm]=P.userData.parts[nm]||[]).push(o);if(nm==='atmous'){o.visible=false;return}
   if(nm==='ocean')o.renderOrder=2;
   if(nm==='clouds'){o.renderOrder=3;m.emissive.setScalar(0);P.userData.cl=o}}
  if(k==='earth'&&m.name==='earth'&&NIGHT){m.emissiveMap=NIGHT;m.emissive=new THREE.Color(0xffffff);m.emissiveIntensity=1.7;m.needsUpdate=true;m.onBeforeCompile=sh=>{sh.fragmentShader=sh.fragmentShader.replace('#include <emissivemap_fragment>','#include <emissivemap_fragment>\n totalEmissiveRadiance*=1.0-smoothstep(-.05,.25,dot(normalize(normal),directionalLights[0].direction));')}}}});
 Q.add(sc);P.add(Q);P.userData.q=Q;return P}
async function buildScene(){
 const R=new THREE.WebGLRenderer({canvas:$('#bg'),antialias:true,powerPreference:'high-performance'});R.setPixelRatio(Math.min(Math.max(devicePixelRatio,1.5),2));R.setSize(innerWidth,innerHeight);R.outputEncoding=THREE.sRGBEncoding;R.toneMapping=THREE.ACESFilmicToneMapping;
 const S=new THREE.Scene(),C=new THREE.PerspectiveCamera(26,innerWidth/innerHeight,.1,2000),G=new THREE.Group(),st=starField(R);S.add(st,G);
 const SUN=new THREE.Vector3(-6,1.8,4).normalize(),sunV=new THREE.Vector3(),sun=new THREE.DirectionalLight(0xfff1e0,2.2);sun.position.copy(SUN).multiplyScalar(20);S.add(sun,new THREE.AmbientLight(0x2a3d60,.42));const rim=new THREE.DirectionalLight(0x4f7dff,.95);rim.position.set(7,1,-3);S.add(rim);
 const mat=(t,bs)=>{const m=new THREE.MeshStandardMaterial({map:t.map,bumpMap:t.bump,bumpScale:bs,roughnessMap:t.rough,roughness:1,metalness:0});
  if(t.name==='earth'){m.emissiveMap=t.emis;m.emissive=new THREE.Color(0xffffff);m.emissiveIntensity=1.1;m.onBeforeCompile=sh=>{sh.fragmentShader=sh.fragmentShader.replace('#include <emissivemap_fragment>','#include <emissivemap_fragment>\n totalEmissiveRadiance*=1.0-smoothstep(-.05,.25,dot(normalize(normal),directionalLights[0].direction));')}}return m};
 const mk=(k,bs,tilt)=>{let P;if(GL[k])P=planetFromGLB(GL[k],1,k);else{const Q=new THREE.Group(),me=new THREE.Mesh(new THREE.SphereGeometry(1,160,160),matFor(k,bs));Q.add(me);P=new THREE.Group();P.add(Q);P.userData.q=Q;P.userData.me=me}P.rotation.z=tilt;G.add(P);return P};
 const GL={};[GL.earth]=await Promise.all(['earth'].map(n=>new Promise(r=>{try{new GLTFLoader().load('assets/models/'+n+'.glb',g=>r(g),e=>{const b=$('#begin');if(b&&b.disabled&&e.lengthComputable&&e.total)b.textContent='Initializing surfaces '+Math.min(99,Math.round(e.loaded/e.total*100))+'%'},()=>r(null))}catch(e){r(null)}})));
 const TX=n=>new Promise(r=>new THREE.TextureLoader().load('assets/textures/'+n+'.jpg',t=>{t.anisotropy=R.capabilities.getMaxAnisotropy();r(t)},undefined,()=>r(null)));
 const RT={};[RT.ed,RT.en,RT.ec,RT.moon,RT.mars,RT.mw,RT.sky]=await Promise.all(['earth_day','earth_night','earth_clouds','moon','mars','milkyway','sky'].map(TX));
 NIGHT=await new Promise(r=>new THREE.TextureLoader().load('assets/textures/earth_night.png',t=>{t.flipY=false;t.encoding=THREE.sRGBEncoding;t.anisotropy=R.capabilities.getMaxAnisotropy();r(t)},undefined,()=>r(null)));/* generated city lights, same orientation as the GLB land texture */
 const T={};for(const k of['earth','moon','mars']){if(!GL[k]&&!(k==='earth'?RT.ed:RT[k])){T[k]=planetTex(k,R);await sleep(30)}}
 if(RT.mw){RT.mw.encoding=THREE.sRGBEncoding;const bgm=new THREE.Mesh(new THREE.SphereGeometry(1500,48,48),new THREE.MeshBasicMaterial({map:RT.mw,side:THREE.BackSide,depthWrite:false,color:0x9aa3b5}));bgm.rotation.set(.5,1,.3);S.add(bgm)}
 const earthMat=()=>new THREE.ShaderMaterial({uniforms:{dM:{value:RT.ed},nM:{value:RT.en||RT.ed},cM:{value:RT.ec||RT.ed},hn:{value:RT.en?1:0},hc:{value:RT.ec?1:0},sd:{value:sunV}},
  vertexShader:'varying vec2 vUv;varying vec3 vN,vV;void main(){vUv=uv;vN=normalize(normalMatrix*normal);vec4 m=modelViewMatrix*vec4(position,1.);vV=-m.xyz;gl_Position=projectionMatrix*m;}',
  fragmentShader:`uniform sampler2D dM,nM,cM;uniform vec3 sd;uniform float hn,hc;varying vec2 vUv;varying vec3 vN,vV;
vec3 lin(vec3 c){return pow(c,vec3(2.2));}
void main(){vec3 N=normalize(vN),V=normalize(vV),L=normalize(sd);float nl=dot(N,L),dl=smoothstep(-.1,.3,nl),lt=max(nl,0.);
 vec3 day=lin(texture2D(dM,vUv).rgb);
 float cl=hc>.5?pow(texture2D(cM,vUv).r,2.2):0.;
 float sh=hc>.5?pow(texture2D(cM,vUv+vec2(.0035,-.0018)).r,2.2):0.;
 vec3 col=day*(.015+1.35*lt)*(1.-.5*sh*dl);
 float oc=smoothstep(.02,.14,day.b-max(day.r,day.g)*1.1);
 vec3 H=normalize(L+V);float sp=pow(max(dot(N,H),0.),110.)*oc*dl*(1.-cl);col+=vec3(1.,.93,.8)*sp*1.6;
 col=mix(col,vec3(.03+1.25*lt),cl*.9);
 vec3 nt=hn>.5?lin(texture2D(nM,vUv).rgb)*2.2:vec3(0.);col+=nt*(1.-dl)*(1.-cl*.85);
 float tw=smoothstep(-.02,.12,nl)*smoothstep(.4,.1,nl);col*=mix(vec3(1.),vec3(1.3,.78,.55),tw*.8);
 float rim=pow(1.-max(dot(N,V),0.),3.2);col+=vec3(.22,.5,1.)*rim*(.1+.9*smoothstep(-.25,.5,nl))*1.15;
 gl_FragColor=vec4(col,1.);
 #include <tonemapping_fragment>
 #include <encodings_fragment>
}`});
 const matFor=(k,bs)=>{if(k==='earth'&&RT.ed)return earthMat();const rt=RT[k];if(rt){rt.encoding=THREE.sRGBEncoding;return new THREE.MeshStandardMaterial({map:rt,bumpMap:rt,bumpScale:bs*.6,roughness:1,metalness:0})}return mat(T[k],bs)};
 const moon=mk('moon',.07,.1),earth=mk('earth',.04,.41),mars=mk('mars',.05,.44),PS=[moon,earth,mars];
 const NC=RT.ed||GL.earth,clouds=NC?new THREE.Object3D():new THREE.Mesh(new THREE.SphereGeometry(1.012,96,96),new THREE.MeshStandardMaterial({map:T.earth.cloud,transparent:true,depthWrite:false,roughness:1}));if(!NC)earth.add(clouds);
 const GLOW=[atmo(1,0x4a90d9,2.2,.8,1.07,sunV),atmo(1,0x7fc0ff,4.5,.4,1.17,sunV)];GLOW.forEach(g=>earth.add(g));{const g=atmo(1,0xd9895a,2.6,.5,1.05,sunV);GLOW.push(g);mars.add(g)}

 /* ---- thermal view: false-colour MODELLED surface temperature on a shared kelvin scale ----
    T from radiative balance: T^4 = Tn^4 + (Td^4-Tn^4) * cos(sun angle) * (1-albedo)/(1-albedoRef), albedo from the visible texture, polar cooling by latitude,
    blended toward a mean for planets with thermal inertia (Earth). Oceans: sea-surface model. Clouds: cold tops. This is an estimate, not measured data. */
 const TV='varying vec2 vUv;varying vec3 vN,vV;void main(){vUv=uv;vN=normalize(normalMatrix*normal);vec4 m=modelViewMatrix*vec4(position,1.);vV=-m.xyz;gl_Position=projectionMatrix*m;}';
 const TF=`uniform sampler2D tex;uniform vec3 sd;uniform float Tn,Td,Aref,Alo,Ak,inr,lf,kind,hasA,Tmin,Tmax;varying vec2 vUv;varying vec3 vN,vV;
vec3 jet(float t){t=clamp(t,0.,1.);return clamp(vec3(1.5-abs(4.*t-3.),1.5-abs(4.*t-2.),1.5-abs(4.*t-1.)),0.,1.);}
void main(){vec3 N=normalize(vN),V=normalize(vV),L=normalize(sd);float cs=max(dot(N,L),0.);vec4 tx=texture2D(tex,vUv);float lat=abs(vUv.y-.5)*2.;float T=250.,al=1.;
 if(kind<.5){if(hasA>.5&&tx.a<.5)discard;float lum=dot(tx.rgb,vec3(.3,.59,.11));float A=clamp(Alo+Ak*lum,.02,.9),f=(1.-A)/(1.-Aref),ice=smoothstep(.72,.9,lum)*smoothstep(.55,.75,lat);
  float lp=pow(lat,1.4),tn=Tn*(1.-lf*lp),td=Td*(1.-lf*.5*lp);float a4=pow(tn/100.,4.),b4=pow(td/100.,4.);float tr=100.*pow(a4+(b4-a4)*cs*f,.25);T=mix(tn+(td-tn)*.55,tr,inr)-48.*ice;}
 else if(kind<1.5){T=mix(271.,301.,pow(1.-lat,1.3))+2.*cs;}
 else{al=smoothstep(.2,.8,tx.a)*.92;T=222.+26.*(1.-tx.a);}
 float t=(T-Tmin)/(Tmax-Tmin);vec3 c=jet(t);c=mix(vec3(.2,0.,.32),c,smoothstep(0.,.12,t));
 c*=mix(.5,1.,pow(max(dot(N,V),0.),.45));gl_FragColor=vec4(c,al);}`;
 const TM=[];/* every thermal material, so the scale mode can retarget its range */
 const tmat=o=>new THREE.ShaderMaterial({uniforms:{tex:{value:o.tex||null},sd:{value:sunV},Tn:{value:o.Tn||0},Td:{value:o.Td||0},Aref:{value:o.Aref||.2},Alo:{value:o.Alo||0},Ak:{value:o.Ak||0},inr:{value:o.inr||1},lf:{value:o.lf||0},kind:{value:o.kind||0},hasA:{value:o.hasA||0},Tmin:{value:80},Tmax:{value:420}},vertexShader:TV,fragmentShader:TF,transparent:o.kind===2,depthWrite:o.kind!==2});
 const mkT=(o,rng)=>{const m=tmat(o);TM.push([m.uniforms,rng]);return m};
 const RNG={moon:[50,400],mars:[125,300],earth:[215,335]};
 const MP={moon:{Tn:95,Td:395,Aref:.12,Alo:.03,Ak:.28,inr:1,lf:.45},mars:{Tn:165,Td:295,Aref:.25,Alo:.04,Ak:.34,inr:.9,lf:.22},earth:{Tn:262,Td:335,Aref:.1,Alo:.05,Ak:.1,inr:.6,lf:.18}};
 const TR=[],regT=(m,mt)=>TR.push([m,m.material,mt]),ep=earth.userData.parts,etex=RT.ed||(T.earth&&T.earth.map);
 if(moon.userData.me)regT(moon.userData.me,mkT({...MP.moon,tex:moon.userData.me.material.map},RNG.moon));
 if(mars.userData.me)regT(mars.userData.me,mkT({...MP.mars,tex:mars.userData.me.material.map},RNG.mars));
 if(ep&&ep.earth&&ep.earth[0].material.map){const lt=ep.earth[0].material.map;ep.earth.forEach(o=>regT(o,mkT({...MP.earth,tex:lt,hasA:1},RNG.earth)));(ep.ocean||[]).forEach(o=>regT(o,mkT({kind:1,tex:lt},RNG.earth)));(ep.clouds||[]).forEach(o=>o.material.map&&regT(o,mkT({kind:2,tex:o.material.map},RNG.earth)))}
 else if(earth.userData.me&&etex)regT(earth.userData.me,mkT({...MP.earth,tex:etex},RNG.earth));
 /* shared = one 80-420 K scale for all three (honest comparison); own = each planet stretched over its own range (shows more detail) */
 const setTScale=own=>TM.forEach(([u,r])=>{u.Tmin.value=own?r[0]:80;u.Tmax.value=own?r[1]:420});
 const HIDE=[...(ep&&ep.oceanFloor||[]),...GLOW];
 const setView=v=>{const on=v==='thermal';for(const[m,m0,mt]of TR)m.material=on?mt:m0;HIDE.forEach(o=>{o.visible=!on})};

 /* photo sky: a camera-fixed backdrop (the photo is not a 360 map), 25% oversized and drifting on sine paths, so it never shows an edge and loops forever */
 let sky=null;const SKA=[0,0];
 if(RT.sky){RT.sky.encoding=THREE.sRGBEncoding;RT.sky.generateMipmaps=false;RT.sky.minFilter=THREE.LinearFilter;sky=new THREE.Mesh(new THREE.PlaneGeometry(1,1),new THREE.MeshBasicMaterial({map:RT.sky,color:0x4a4f5c,depthTest:false,depthWrite:false,toneMapped:false,fog:false}));
  sky.renderOrder=-10;sky.frustumCulled=false;sky.position.z=-1500;sky.userData.ia=RT.sky.image.width/RT.sky.image.height;C.add(sky);S.add(C)}
 /* aligned row Moon - Earth - Mars on one centre line; 'equal' = same radius, 'real' = true diameter ratios (Earth 12742 km, Mars 6779, Moon 3474) */
 const SZ={equal:[1.95,1.95,1.95],real:[.709,2.6,1.383]},STEP=6.2,cs=SZ.equal.slice(),cx=[0,0,0],cy=[0,0,0],tp=[[0,0],[0,0],[0,0]];let mode='equal',tall=false;
 const place=()=>{tall=innerWidth/innerHeight<1;for(let i=0;i<3;i++){const o=(i-1)*STEP;tp[i][0]=tall?0:o;tp[i][1]=tall?-o:-.35}};
 let lw=0,lh=0;const fit=()=>{if(lw!==innerWidth||lh!==innerHeight){lw=innerWidth;lh=innerHeight;R.setSize(lw,lh);C.aspect=lw/lh;C.updateProjectionMatrix()}const a=C.aspect;place();
  const vh=2*22*Math.tan(.22689),vw=vh*a,s=Math.min(1,(tall?vh:vw)/(2*(STEP+2.05)*1.08));G.scale.setScalar(s);G.position.set(0,tall?-.6:0,0);
  /* landscape: centre the row in the free band between the hero text and the dock, and cap the radius so nothing overlaps the HUD */
  let cap=1.95;if(!tall){let yo=-.35;const hr=$('.hero'),dk=$('.dock');if(hr&&dk){const H=innerHeight,u=H/vh*s,t=hr.getBoundingClientRect().bottom+10,b=dk.getBoundingClientRect().top-10-62;if(b-t>120){yo=-((t+b)/2-H/2)/u;cap=Math.max(.9,Math.min(cap,(b-t)/2/u))}}for(let i=0;i<3;i++)tp[i][1]=yo}
  SZ.equal=[cap,cap,cap];const f=Math.min(1,cap/2.6);SZ.real=[.709*f,2.6*f,1.383*f];
  if(sky){const Vh=2*1500*Math.tan(.22689),Vw=Vh*a,ia=sky.userData.ia;let H=Vh*1.25,W=H*ia;if(W<Vw*1.25){W=Vw*1.25;H=W/ia}sky.scale.set(W,H,1);SKA[0]=(W-Vw)/2;SKA[1]=(H-Vh)/2}};
 fit();for(let i=0;i<3;i++){cx[i]=tp[i][0];cy[i]=tp[i][1];cs[i]=SZ[mode][i]}addEventListener('resize',fit);if(document.fonts)document.fonts.ready.then(fit);if(window.ResizeObserver){const ro=new ResizeObserver(fit);ro.observe($('.hero'));ro.observe($('.dock'))}/* dock gets its chips after the first pass and may wrap */
 const TL=[.1,.41,.44];let ob=0,ph=Math.PI,go=null,mx=0,my=0,tx=0,ty=0,prev=performance.now();addEventListener('pointermove',e=>{tx=e.clientX/innerWidth-.5;ty=e.clientY/innerHeight-.5});
 C.position.z=27;
 /* planet labels + click targets (screen-space) + adaptive resolution governor */
 const V3=new THREE.Vector3(),LB=[...document.querySelectorAll('.pl')],HIT=[0,1,2].map(()=>({x:-9e9,y:-9e9,r:0}));let fa=.016,dpr=R.getPixelRatio();const DM=dpr;let tg=0,tc=-1e9;
 const labels=()=>{const gs=G.scale.x,kk=lh/(2*Math.tan(.22689));for(let i=0;i<3;i++){V3.set(G.position.x+PS[i].position.x*gs,G.position.y+PS[i].position.y*gs,0);const d=C.position.distanceTo(V3);V3.project(C);const x=(V3.x*.5+.5)*lw,y=(-V3.y*.5+.5)*lh,r=cs[i]*gs*kk/d,h=HIT[i];h.x=x;h.y=y;h.r=r;if(i===0&&LB[0]){const o=ob>.05;LB[0].style.opacity=o?'0':'1';LB[0].style.pointerEvents=o?'none':'auto'}if(LB[i])LB[i].style.transform='translate('+x.toFixed(1)+'px,'+(y+r+12).toFixed(1)+'px) translateX(-50%)'}};
 const gov=(dt,now)=>{fa+=(dt-fa)*.04;if(now-tg<2500)return;tg=now;let n=dpr;if(fa>.024&&dpr>1)n=Math.max(1,dpr-.25);else if(fa<.0185&&dpr<DM&&now-tc>8000)n=Math.min(DM,dpr+.25);if(n!==dpr){dpr=n;tc=now;R.setPixelRatio(dpr);st.material.uniforms.px.value=dpr}};
 const hit=(x,y)=>{if(!document.body.classList.contains('ready')||$('#panel').classList.contains('open'))return -1;for(const i of[0,2]){const h=HIT[i];if(i===0&&ob>.5&&Math.sin(ph)<0&&Math.hypot(x-HIT[1].x,y-HIT[1].y)<HIT[1].r)continue;if(Math.hypot(x-h.x,y-h.y)<=h.r)return i}return -1};
 addEventListener('pointermove',e=>{$('#bg').style.cursor=hit(e.clientX,e.clientY)>=0?'pointer':''});
 $('#bg').addEventListener('click',e=>{const i=hit(e.clientX,e.clientY);if(i>=0)window.pickBody(i===0?'moon':'mars')});
 /* True scale: Mars steps outward and the Moon orbits Earth (orbit radius compressed to fit the screen, direction of travel and tidal lock kept) */
 const MX=()=>{const f=SZ.real[1]/2.6;return Math.min(STEP+1,Math.max(STEP,1.9*SZ.real[1]+SZ.real[2]+.9*f))};
 const loop=now=>{requestAnimationFrame(loop);if(document.hidden){prev=now;return}const dt=Math.min(.05,(now-prev)/1000);prev=now;
  const ns=now/1000,ts=ns%1047.1975511965977,k=1-Math.exp(-dt*2.6),Z=SZ[mode],fl=Math.sin(ts*.3)*.05;/* 1047.19 s = whole periods of the twinkle and libration sines, so the wrap is invisible */
  spin(earth.userData.q,dt*.11);spin(clouds,dt*.13);if(earth.userData.cl)spin(earth.userData.cl,dt*.03);spin(mars.userData.q,dt*.095);spin(st,dt*.002);
  moon.userData.q.rotation.x=Math.sin(ts*.18)*.05;/* Moon is tidally locked: near side always faces Earth, only a slow libration */
  st.material.uniforms.t.value=ts;
  for(let i=0;i<3;i++){cs[i]+=(Z[i]-cs[i])*k;cx[i]+=((i===2&&mode==='real'&&!tall?MX():tp[i][0])-cx[i])*k;cy[i]+=(tp[i][1]-cy[i])*k;PS[i].scale.setScalar(cs[i]);PS[i].position.set(cx[i],cy[i]+fl+Math.sin(ts*.18+i*2.1)*.025*cs[i],0);PS[i].rotation.z=TL[i]+Math.sin(ts*.24+i*1.7)*.015}
  ob+=((mode==='real'?1:0)-ob)*(1-Math.exp(-dt*1.4));ph=(ph+dt*.12)%TAU;/* 52 s per lap */
  if(ob>.0005){const E=PS[1].position,a=cs[1]*1.9,P0=PS[0].position;P0.set(lerp(P0.x,E.x+Math.cos(ph)*a,ob),lerp(P0.y,E.y+Math.sin(ph)*a*.2,ob),Math.sin(ph)*a*.9*ob)}
  {const lib=Math.sin(ts*.12)*.16,lk=Math.atan2(-Math.cos(ph),-Math.sin(ph));let d=lk-lib;d=Math.atan2(Math.sin(d),Math.cos(d));moon.userData.q.rotation.y=lib+d*ob}
  if(sky)sky.position.set(Math.sin(ns*.031)*SKA[0]*.7-mx*SKA[0]*.25,Math.cos(ns*.023)*SKA[1]*.7+my*SKA[1]*.25,-1500);
  
  const z=go===null?27:lerp(27,22,1-Math.pow(1-cl((now-go)/(RED?1500:14000)),3));mx+=(tx-mx)*.03;my+=(ty-my)*.03;C.position.set(mx*.7+Math.sin(ts*.06)*.4,-my*.5+Math.cos(ts*.12)*.15,z);C.lookAt(0,0,0);C.updateMatrixWorld();sunV.copy(SUN).transformDirection(C.matrixWorldInverse);labels();gov(dt,now);R.render(S,C)};
 requestAnimationFrame(loop);return{real:!!RT.ed,go(){go=performance.now()},setScale(m){if(SZ[m])mode=m},setView,setTScale,setFlat(v){G.visible=!v},thermalParts:()=>TR.length,orbit:()=>({ob,ph}),fps:()=>1/fa,dpr:()=>dpr,info(){return{tp,SZ,cs,STEP,cx:cx.slice(),cy:cy.slice()}}}}
export {buildScene};
