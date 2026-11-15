const DOMAINS = [
  ['topography', 'Topography'],
  ['mineralogy', 'Mineralogy'],
  ['thermal_illumination', 'Thermal and illumination'],
  ['granular_aeolian', 'Dust and dunes'],
  ['volatiles_subsurface', 'Ice and subsurface'],
];

export const CHARACTERISTICS = DOMAINS.map(([id, label]) => ({
  id,
  label,
  description: null,
  unit: null,
  defaultWeight: 50,
}));

export const defaultWeights = () => Object.fromEntries(
  CHARACTERISTICS.map((characteristic) => [characteristic.id, characteristic.defaultWeight]),
);

export const saveWeights = (weights) => {
  try { sessionStorage.setItem('ade.weights', JSON.stringify(weights)); } catch {}
};

export const loadWeights = () => {
  try { return { ...defaultWeights(), ...(JSON.parse(sessionStorage.getItem('ade.weights')) || {}) }; }
  catch { return defaultWeights(); }
};
