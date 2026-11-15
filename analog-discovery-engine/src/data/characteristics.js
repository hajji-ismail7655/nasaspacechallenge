export const COUNT = 8;

export const CHARACTERISTICS = Array.from({ length: COUNT }, (_, i) => {
  const letter = String.fromCharCode(65 + i);
  return {
    id: letter.toLowerCase(), letter, label: `Characteristic ${letter}`,
    description: null, // TODO(dataset)
    unit: null, // TODO(dataset)
    defaultWeight: 50,
  };
});

export const defaultWeights = () => Object.fromEntries(CHARACTERISTICS.map((c) => [c.id, c.defaultWeight]));
