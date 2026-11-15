/* THE ONLY PLACE THE REAL DATASETS PLUG IN.
   getComparison({ body, selection }) must resolve to:
   { scores: { a: 0..100|null, ... h },
     thermal: { earth, target, legend: [{ code, meaning }] },
     texts: { a: '...', ... } }
   selection: { type:'point', lat, lon } | { type:'area', area:{shape:'rect',bounds:{south,west,north,east}} | {shape:'cap',center,radiusDeg,bounds} } | { type:'both', point, area }
   Longitudes -180..180 (east +), latitudes -90..90 (north +).
   TODO(dataset): replace with the real loader. */
export async function getComparison(/* { body, selection } */) {
  throw new Error('DATASET_NOT_CONNECTED');
}
