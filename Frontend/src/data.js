import {hs,rnd} from './modules/util.js';
export const ICON={composite:'<circle cx="12" cy="12" r="8"/><path d="M12 4v16M4 12h16"/>',topography:'<path d="M2 19l6-11 4 7 3-4 7 8z"/>',mineralogy:'<path d="M12 3l7 4v10l-7 4-7-4V7z"/><path d="M5 7l7 4 7-4M12 11v10"/>',thermal_illumination:'<path d="M10 14V5a2 2 0 014 0v9a4 4 0 11-4 0z"/><path d="M12 9v7"/>',granular_aeolian:'<path d="M2 17c4-8 8-8 10-3s6 3 10-2"/><path d="M6 20h.01M12 20h.01M18 20h.01"/>',volatiles_subsurface:'<path d="M12 3c4 5 6 8 6 11a6 6 0 01-12 0c0-3 2-6 6-11z"/>'};
export const ASP=[['composite','Composite','Weighted blend of all five domains. Move the sliders to re-rank what matters for your mission.'],
 ['topography','Topography','Slope, roughness and crater density from LAEA-reprojected elevation tiles, compared across octaves from 30 to 480 m.'],
 ['mineralogy','Mineralogy','Match of surface materials: basaltic, ilmenite-bearing or hydrated phases against Earth terrain.'],
 ['thermal_illumination','Thermal and light','Diurnal temperature range and sun-angle geometry, including grazing polar illumination.'],
 ['granular_aeolian','Dust and dunes','Regolith grain behaviour, dune activity and wind transport. This drives rover slip and dust hazards.'],
 ['volatiles_subsurface','Ice and caves','Ice, permafrost and lava-tube volumes that could hold resources or shelter crews.']].map(a=>({id:a[0],n:a[1],d:a[2]}));
export const META={moon_shackleton_degerlache:['Shackleton - de Gerlache Rim','moon','Autonomous Lidar Hazard Detection & Avoidance under 1.5 deg grazing illumination','-89.9','0.0'],moon_malapert_massif:['Malapert Massif','moon','High-elevation line-of-sight comms/relay validation','-85.9','0.1'],moon_aristarchus_plateau:['Aristarchus Plateau','moon','High-Ti basaltic regolith beneficiation & ilmenite reduction','23.7','-47.4'],moon_marius_hills_skylight:['Marius Hills Skylight','moon','Subsurface lava-tube robotic mesh-network navigation','14.1','-56.8'],
 mars_jezero_western_fan:['Jezero Western Fan','mars','Astrobiology sampling & deltaic stratigraphy analysis','18.4','77.7'],mars_arcadia_planitia:['Arcadia Planitia','mars','ISRU water-ice excavation & landing site validation','47.2','-164.0'],mars_arsia_mons_pits:['Arsia Mons Pits','mars','Subsurface cave robotic exploration & thermal retention study','-9.2','-120.1'],mars_bagnold_dunes:['Bagnold Dunes','mars','Rover mobility & wheel-slip hazard assessment on active dunes','-4.6','137.4']};
export const PH={moon:{g:.165,p:101325,rad:470,th:-38,n:'vacuum'},mars:{g:.379,p:100715,rad:230,th:-78,n:'thin CO2'}};
export const API=window.ANALOG_API||'http://localhost:8000';
export const OCT=[30,60,120,240,480];
export const score=(id,a)=>Math.round(38+rnd(hs(id+a))()*52);
export const tgt=id=>{const m=META[id]||[id.replace(/_/g,' '),id.startsWith('moon')?'moon':'mars','Generic analog field validation','-','-'];return{id,name:m[0],body:m[1],test:m[2],lat:m[3],lon:m[4]}};
export const WIDS=ASP.slice(1).map(a=>a.id);
export const compOf=(id,w)=>{const s=WIDS.reduce((n,a)=>n+w[a]+1,0);return WIDS.reduce((n,a)=>n+score(id,a)*(w[a]+1),0)/s};
/* One place to hook the backend: GET {API}/targets -> {targets:[id,...]}; falls back to the demo list. */
export async function loadTargets(){try{const r=await fetch(API+'/targets',{signal:AbortSignal.timeout(2500)});return{ids:(await r.json()).targets,live:true}}catch{return{ids:Object.keys(META),live:false}}}
