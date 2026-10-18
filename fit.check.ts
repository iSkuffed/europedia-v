// Self-check for src/lib/fit.ts against the real data: node --experimental-strip-types fit.check.ts
import { readFileSync } from 'node:fs';
import { strict as assert } from 'node:assert';
import { fits } from './src/lib/fit.ts';
const json = (f: string) => JSON.parse(readFileSync(new URL(f, import.meta.url), 'utf8'));
const S = json('public/scope.json'), P = json('public/privileges.json');
const ara = { tag: 'ARA', ...S.countries.ARA }, eng = { tag: 'ENG', ...S.countries.ENG };
const by = (xs: any[], id: string) => xs.find(x => x.id === id).who;
assert.equal(fits(by(P.privileges, 'general_privilege'), ara), 'yes');            // country: Aragon
assert.equal(fits(by(P.privileges, 'general_privilege'), eng), 'no');
assert.equal(fits(by(P.reforms, 'east_india_trading_company'), ara), 'no');       // unlock + unlocked for England
assert.equal(fits(by(P.reforms, 'east_india_trading_company'), eng), 'maybe');    // England, once unlocked
assert.equal(fits([], ara), 'yes');
assert.equal(fits([{ type: 'religion', kind: 'religion', ids: ['catholic'], not: true }], ara), 'no');
assert.equal(fits([{ type: 'any', any: [{ type: 'tag', ids: ['FRA'] }, { type: 'culture_group', ids: ['iberian_group'] }] }], ara), 'yes');
assert.equal(fits([{ type: 'sub_continent', ids: ['western_europe'], cap: 1 }], ara), 'yes');
console.log('fit ok');
// advances.py nests any/all as `parts`
assert.equal(fits([{ type: 'any', parts: [{ type: 'tag', ids: ['FRA'] }, { type: 'culture_group', ids: ['iberian_group'] }] }], ara), 'yes');
assert.equal(fits([{ type: 'any', parts: [{ type: 'tag', ids: ['FRA'] }] }], ara), 'no');
console.log('fit parts ok');
assert.equal(fits([{ type: 'any', parts: [{ type: 'religion', ids: ['catholic'], not: 1 }] }], ara), 'no');  // a NOT inside an OR
console.log('fit nested not ok');
