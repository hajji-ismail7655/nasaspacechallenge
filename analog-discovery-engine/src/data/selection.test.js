import test from 'node:test';
import assert from 'node:assert/strict';
import { capBounds, toProviderSelection, makeRect, toVec, angleDeg } from './selection.js';

test('cap bounds near the equator', () => { const b = capBounds(0, 10, 5); assert.equal(b.south, -5); assert.equal(b.north, 5); assert.equal(b.west, 5); assert.equal(b.east, 15); });
test('cap over a pole spans all longitudes', () => { const b = capBounds(88, 0, 5); assert.equal(b.west, -180); assert.equal(b.east, 180); assert.equal(b.north, 90); });
test('cap crossing the antimeridian has west > east', () => { const b = capBounds(0, 178, 5); assert.ok(b.west > b.east); });
test('provider selection shapes', () => {
  const p = { lat: 1, lon: 2 }, a = makeRect({ lat: 0, lon: 0 }, { lat: 5, lon: 6 });
  assert.equal(toProviderSelection({ point: p, area: null }).type, 'point');
  assert.equal(toProviderSelection({ point: null, area: a }).type, 'area');
  assert.equal(toProviderSelection({ point: p, area: a }).type, 'both');
  assert.deepEqual(a.bounds, { south: 0, north: 5, west: 0, east: 6 });
});
test('angle between points on the equator', () => { assert.ok(Math.abs(angleDeg(toVec(0, 0), toVec(0, 90)) - 90) < 1e-9); });
