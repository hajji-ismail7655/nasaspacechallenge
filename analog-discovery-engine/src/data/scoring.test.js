import test from 'node:test';
import assert from 'node:assert/strict';
import { weightedBreakdown } from './scoring.js';

const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} !== ${b}`);

test('equal weights give the plain mean', () => { close(weightedBreakdown({ a: 80, b: 40 }, { a: 50, b: 50 }).overall, 60); });
test('weights are normalised', () => {
  const r = weightedBreakdown({ a: 100, b: 0 }, { a: 3, b: 1 });
  close(r.overall, 75); close(r.items[0].share, 0.75); close(r.items[0].impact, 75);
});
test('impacts add up to the overall', () => {
  const r = weightedBreakdown({ a: 10, b: 55, c: 92 }, { a: 20, b: 70, c: 5 });
  close(r.items.reduce((n, i) => n + i.impact, 0), r.overall);
  close(r.items.reduce((n, i) => n + i.share, 0), 1);
});
test('a missing score is excluded and flagged', () => {
  const r = weightedBreakdown({ a: 60, b: null, c: 20 }, { a: 1, b: 1, c: 1 });
  close(r.overall, 40); assert.equal(r.items[1].missing, true); close(r.items[1].impact, 0);
});
test('all weights zero falls back to equal weighting', () => { close(weightedBreakdown({ a: 90, b: 10 }, { a: 0, b: 0 }).overall, 50); });
test('overall stays within 0..100', () => { close(weightedBreakdown({ a: 100, b: 100 }, { a: 7, b: 9 }).overall, 100); });
