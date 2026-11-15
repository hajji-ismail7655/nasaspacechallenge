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
