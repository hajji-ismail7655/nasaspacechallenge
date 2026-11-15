export function weightedBreakdown(scores, weights) {
  const ids = Object.keys(scores);
  const usable = ids.filter((id) => Number.isFinite(scores[id]));
  const total = usable.reduce((n, id) => n + Math.max(0, Number(weights[id]) || 0), 0);
  const equal = total === 0 && usable.length > 0;

  const items = ids.map((id) => {
    const has = Number.isFinite(scores[id]);
    const w = Math.max(0, Number(weights[id]) || 0);
    const share = !has ? 0 : equal ? 1 / usable.length : w / total;
    return { id, score: has ? scores[id] : null, weight: w, share, impact: has ? share * scores[id] : 0, missing: !has };
  });
  return { overall: items.reduce((n, it) => n + it.impact, 0), items };
}
