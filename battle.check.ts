// Self-check for src/lib/battle.ts: node --experimental-strip-types battle.check.ts
// Runs on a hand-made fixture (values from /tmp/eu5w/SPEC.md and landtable.txt), and on public/units.json when it exists.
import { existsSync, readFileSync } from 'node:fs';
import { strict as assert } from 'node:assert';
import { simulate, simulateOnce, sideStats } from './src/lib/battle.ts';
import type { BattleInput, Cat, SideInput, Unit, UnitsData } from './src/lib/units.ts';

const unit = (id: string, cat: Cat, o: Partial<Unit>): Unit => ({
  id, name: id, cat, age: 1, levy: false, buildable: true, str: 0.5, cp: 1, init: 1, speed: 2, front: 1, flank: 1, secure: 0.05,
  move: 2, sdd: 0, sdt: 0, mdd: 0, mdt: 0, taken: 1, terrain: {}, combinedArms: true, who: [], whoText: '', unique: false, ...o,
});
const cavTerrain = { jungle: -0.1, wetlands: -0.1, mountains: -0.1, river: -0.1 };
const fixture: UnitsData = {
  units: [
    unit('a_footmen', 'heavy_infantry', { sdt: -0.05 }),
    unit('a_footmen_levy', 'heavy_infantry', { sdt: -0.05, levy: true, buildable: false }),
    unit('a_archers', 'light_infantry', { init: 5, speed: 3, flank: 1.1, move: 2.5, sdd: -0.1, mdt: 0.1 }),
    unit('a_armored_horsemen', 'heavy_cavalry', { str: 0.2, cp: 2.6, init: 2, speed: 5, flank: 1.6, secure: 0, taken: 0.3, terrain: cavTerrain }),
    unit('a_horsemen', 'light_cavalry', { str: 0.2, cp: 2.6, init: 5, speed: 5, flank: 1.6, secure: 0, sdd: -0.1, mdt: 0.1, taken: 0.3, terrain: cavTerrain }),
    unit('a_houfnice', 'artillery', { age: 2, str: 0.2, cp: 3, speed: 1, secure: 0, taken: 1.25, bombard: 0.125 }),
    unit('a_camp_followers', 'auxiliary', { str: 0.05, cp: 0.25, speed: 0.1, secure: 0, taken: 1.25, combinedArms: false }),
  ],
  topography: [{ id: 'flatland', name: 'Flatland', dice: 0, front: 0 }, { id: 'hills', name: 'Hills', dice: 1, front: -3 }, { id: 'mountains', name: 'Mountains', dice: 2, front: -4 }],
  vegetation: [{ id: 'farmland', name: 'Farmland', dice: 0, front: 0 }, { id: 'woods', name: 'Woods', dice: 1, front: -2 }, { id: 'forest', name: 'Forest', dice: 1, front: -3 }],
  ranks: [{ id: 'rural_settlement', name: 'Rural Settlement', front: 0 }, { id: 'town', name: 'Town', front: -1 }, { id: 'city', name: 'City', front: -2 }],
  baseFrontage: 10,
  defines: {
    RETREAT_STRENGTH_DAMAGE: 0.1, MORALE_COLLAPSE_THRESHOLD: 0.05, MINIMUM_COMBAT_DAYS: 5, BOMBARD_BASE_CHANCE: 0.2, BOMBARD_DAYS: 3,
    DAYS_PER_PHASE: 4, COMBAT_DICE_SIDE: 10, COMBAT_BASE: 5, COMBAT_MAX: 15, COMBAT_DAMAGE_MULT: 0.12, COMBAT_DAILY_MORALE_TICK: 0.03,
    STRAIT_CROSSING_DICE: -2, RIVER_CROSSING_DICE: -1, SEA_LANDING_DICE: -1, MAX_FRONTAGE_OVERSTACKING: 1.25, LAND_LEVY_COMBAT_IMPACT: 0.75,
    MORALE_SIZE_RATIO_MAX: 4, INITIATIVE_BASE_CHANCE: 0.6, INITIATIVE_CHANCE_EACH: 0.025, INITIATIVE_CHANCE_PER_DAY: 0.03,
    INITIATIVE_CHANCE_MAX: 0.3, COMBAT_SPEED_SCALE: 0.1, LAND_EXPERIENCE_DAMAGE_REDUCTION: 0.5, LAND_STRENGTH_DAMAGE_MODIFIER: 0.04,
    LAND_MORALE_DAMAGE_MODIFIER: 0.25, NOT_ENGAGED_STRENGTH_DAMAGE_MODIFIER: 1.1, NOT_ENGAGED_MORALE_DAMAGE_MODIFIER: 1.2,
    INITIAL_OVERRUN_FACTOR: 10, MORALE_OVERRUN_FACTOR: 2, BASE_MORALE_DAMAGE: 1, EXPERIENCE_GAIN: 30, LAND_MORALE: 3, MIN_FRONTAGE_AFTER_TERRAIN: 2,
  },
  traits: [{ id: 'strategist', name: 'Strategist', mods: { discipline: 0.1, commander_combat_bonus: 2 } },
    { id: 'offensive_planner', name: 'Offensive Planner', mods: { commander_combat_bonus: 1 } }],
  ageMods: {}, focusMods: { adm: {}, dip: {}, mil: {} },
  general: {
    adm: { possible_frontage_modifier: 0.001, correct_box_chance: 0.001 },
    dip: { land_morale_modifier: 0.002, army_initiative: 0.01 },
    mil: { discipline: 0.001, combat_speed_modifier: 0.005 },
  },
  levyMods: { discipline: -0.2 }, regularMods: {},
  base: { military_tactics: 1, combined_arms_max_threshold: 0.5, combined_arms_min_percent_for_bonus: 0.1, combined_bonus_per_type: 0.025 },
};

const side = (regs: [string, number][], o: Partial<SideInput> = {}): SideInput => ({
  regs: regs.map(([unit, n]) => ({ unit, n })), general: null, discipline: 0, tactics: 1, moraleFlat: 0, moraleMod: 0, experience: 0,
  levyEff: 0, initiativeMod: 0, speedMod: 0, frontageMod: 0, combinedPerType: 0.025, catPower: {}, armyTradition: 0, formation: 'balanced_army', ...o,
});
const battle = (att: SideInput, def: SideInput, o: Partial<BattleInput> = {}): BattleInput => ({
  att, def, topography: 'flatland', vegetation: 'farmland', rank: 'rural_settlement', river: false, strait: false, landing: false, dice: 'random', seed: 1, ...o,
});
const pct = (x: number) => `${(x * 100).toFixed(0)}%`;
const line = (label: string, d: UnitsData, b: BattleInput, n = 1000) => {
  const s = simulate(d, b, n);
  console.log(`  ${label}: att ${pct(s.attWin)} / def ${pct(s.defWin)} / draw ${pct(s.draw)}, ${s.days.avg.toFixed(1)} days (${s.days.min}-${s.days.max}), losses att ${s.losses.att.avg.toFixed(0)} def ${s.losses.def.avg.toFixed(0)}`);
  return s;
};

function checks(d: UnitsData, U: { inf: string; levy: string; hc: string; lc: string; li: string; art: string; aux: string }, tag: string) {
  console.log(`[${tag}]`);
  const F = (n: number) => side([[U.inf, n]]);
  const MIN = d.defines.MINIMUM_COMBAT_DAYS;

  // seeded determinism
  const b0 = battle(F(10), F(10), { seed: 42 });
  assert.deepEqual(simulateOnce(d, b0), simulateOnce(d, b0));
  assert.deepEqual(simulate(d, b0, 50), simulate(d, b0, 50));
  assert.notDeepEqual(simulateOnce(d, b0).daily, simulateOnce(d, { ...b0, seed: 43 }).daily);

  // symmetric battle is close to 50/50
  const sym = line('10 v 10 footmen, flat', d, battle(F(10), F(10)), 4000);
  assert.ok(Math.abs(sym.attWin - sym.defWin) < 0.06, `symmetric ${sym.attWin} vs ${sym.defWin}`);

  // 2:1 numbers win most of the time
  const two = line('20 v 10 footmen', d, battle(F(20), F(10)));
  assert.ok(two.attWin > 0.85, `2:1 won only ${two.attWin}`);

  // attacking into mountains + forest + river is worse than flatland
  const mtn = line('10 v 10 into mountains/forest/river', d, battle(F(10), F(10), { topography: 'mountains', vegetation: 'forest', river: true }));
  assert.ok(mtn.attWin < sym.attWin - 0.2, `mountain attack ${mtn.attWin} vs flat ${sym.attWin}`);
  assert.ok(mtn.losses.att.avg - mtn.losses.def.avg > sym.losses.att.avg - sym.losses.def.avg);

  // levies lose to equal regulars
  const lev = line('10 regulars v 10 levies', d, battle(F(10), side([[U.levy, 10]])));
  assert.ok(lev.attWin > 0.85, `regulars beat levies only ${lev.attWin}`);

  // 10:1 overruns on day 1
  const ov = simulateOnce(d, battle(F(10), F(1)));
  assert.equal(ov.winner, 'att'); assert.equal(ov.days, 1); assert.equal(ov.losses.def, ov.start.def.men);
  assert.ok(ov.notes.some(n => /overrun/.test(n)), ov.notes.join());
  assert.equal(simulateOnce(d, battle(F(1), F(10))).winner, 'def');

  // nothing ends before MINIMUM_COMBAT_DAYS unless overrun (incl. lopsided small fights whose front empties early)
  for (const [a, b] of [[1, 1], [3, 1], [5, 1], [9, 1], [10, 2], [20, 10]]) {
    for (let seed = 1; seed <= 60; seed++) {
      const log = simulateOnce(d, battle(F(a), F(b), { seed }));
      if (log.days < MIN) assert.ok(log.notes.some(n => /overrun/.test(n)), `${a}v${b} seed ${seed} ended day ${log.days}: ${log.notes}`);
      assert.equal(log.daily.length, log.days);
    }
  }

  // draw rate of a symmetric battle
  console.log(`  10v10 draw rate: ${(sym.draw * 100).toFixed(2)}%`);
  assert.ok(sym.draw < 0.05, `draw rate ${sym.draw}`);

  // monotonicity: each change moves the attacker's win rate the expected way (same seeds, so noise mostly cancels)
  const N = 800, base = battle(F(10), F(10), { seed: 11 }), w0 = simulate(d, base, N).attWin;
  const A = (o: Partial<SideInput>) => ({ ...base, att: { ...base.att, ...o } }), Dd = (o: Partial<SideInput>) => ({ ...base, def: { ...base.def, ...o } });
  const half = side([[U.inf, 5], [U.levy, 5]]), lb = battle(half, half, { seed: 11 }), lw0 = simulate(d, lb, N).attWin;
  const mono: [string, BattleInput, 1 | -1, number?][] = [
    ['discipline +0.1', A({ discipline: 0.1 }), 1], ['discipline -0.1', A({ discipline: -0.1 }), -1],
    ['tactics +0.5', A({ tactics: 1.5 }), 1], ['tactics -0.5', A({ tactics: 0.5 }), -1],
    ['experience +50', A({ experience: 50 }), 1], ['def experience +50', Dd({ experience: 50 }), -1],
    ['heavy infantry power +0.2', A({ catPower: { heavy_infantry: 0.2 } }), 1], ['def heavy infantry power +0.2', Dd({ catPower: { heavy_infantry: 0.2 } }), -1],
    ['morale modifier +0.2', A({ moraleMod: 0.2 }), 1], ['morale modifier -0.2', A({ moraleMod: -0.2 }), -1],
    ['flat morale +0.5', A({ moraleFlat: 0.5 }), 1],
    ['levy efficiency +0.3 (half-levy armies)', { ...lb, att: { ...lb.att, levyEff: 0.3 } }, 1, lw0],
    ['general mil 100', A({ general: { adm: 0, dip: 0, mil: 100, traits: [] } }), 1],
    ['general dip 100', A({ general: { adm: 0, dip: 100, mil: 0, traits: [] } }), 1],
    ['+1 combat bonus trait', A({ general: { adm: 0, dip: 0, mil: 0, traits: ['offensive_planner'] } }), 1],
    ['def +1 combat bonus trait', Dd({ general: { adm: 0, dip: 0, mil: 0, traits: ['offensive_planner'] } }), -1],
    ...d.topography.filter(t => t.dice > 0).map(t => [`attack into ${t.id}`, { ...base, topography: t.id }, -1] as [string, BattleInput, -1]),
    ...d.vegetation.filter(t => t.dice > 0).map(t => [`attack into ${t.id}`, { ...base, vegetation: t.id }, -1] as [string, BattleInput, -1]),
    ['river crossing', { ...base, river: true }, -1], ['strait crossing', { ...base, strait: true }, -1], ['sea landing', { ...base, landing: true }, -1],
    ['fixed dice 9 v 0', { ...base, dice: 'fixed', fixed: { att: 9, def: 0 } }, 1], ['fixed dice 0 v 9', { ...base, dice: 'fixed', fixed: { att: 0, def: 9 } }, -1],
  ];
  const deltas: string[] = [];
  for (const [label, b, sign, ref = w0] of mono) {
    const dw = simulate(d, b, N).attWin - ref;
    deltas.push(`${label} ${dw >= 0 ? '+' : ''}${(dw * 100).toFixed(0)}`);
    assert.ok(dw * sign > 0, `${label}: attWin moved ${dw} (expected sign ${sign})`);
  }
  console.log(`  monotonicity (attWin pts vs ${pct(w0)}): ${deltas.join(', ')}`);

  // auxiliaries do not count toward a day-1 overrun; a side with only auxiliaries is overrun by real troops
  const aux = simulateOnce(d, battle(side([[U.aux, 200]]), F(1)));
  assert.equal(aux.winner, 'def'); assert.equal(aux.days, 1);
  assert.equal(simulateOnce(d, battle(side([[U.aux, 5]]), side([[U.aux, 5]]))).winner, 'draw');

  // an empty line with fresh reserves fights on: the loser never has non-broken infantry reserves left (narrow mountain front)
  for (let seed = 1; seed <= 200; seed++) {
    const log = simulateOnce(d, battle(F(25), F(20), { seed, topography: 'mountains', vegetation: 'forest' }));
    const last = log.daily[log.daily.length - 1], loser = log.winner === 'att' ? last.def : log.winner === 'def' ? last.att : null;
    if (loser) assert.ok(loser.front === 0 && loser.reserve === 0, `seed ${seed}: loser had ${loser.reserve} reserves`);
  }

  // guards: junk numbers and n stay finite / bounded
  assert.equal(simulate(d, b0, NaN).n, 1); assert.equal(simulate(d, b0, -5).n, 1);
  const junk = simulateOnce(d, battle(side([[U.inf, 10]], { discipline: NaN, tactics: Infinity, moraleMod: -5, frontageMod: -3, levyEff: -9, armyTradition: 1e9 }), F(10)));
  assert.ok(Number.isFinite(junk.losses.att) && Number.isFinite(junk.losses.def) && junk.days <= 365, JSON.stringify(junk.losses));
  assert.ok(sideStats(d, battle(side([[U.inf, 10]], { frontageMod: -3 }), F(10)), 'att').frontage >= d.defines.MIN_FRONTAGE_AFTER_TERRAIN);

  // fixed dice: equal fixed rolls on a symmetric field still decide by targeting luck only; a big fixed gap decides it
  const fx = simulate(d, battle(F(10), F(10), { dice: 'fixed', fixed: { att: 9, def: 0 } }), 300);
  assert.ok(fx.attWin > 0.95, `fixed 9 v 0 won ${fx.attWin}`);

  // general: strategist + 100 mil beats no general
  const gen = line('10 v 10, att general 0/0/100 + strategist', d, battle(side([[U.inf, 10]], { general: { adm: 0, dip: 0, mil: 100, traits: ['strategist'] } }), F(10)));
  assert.ok(gen.attWin > 0.75);

  // mixed armies with artillery and auxiliaries run; sideStats is sane
  const mixed = side([[U.inf, 16], [U.li, 8], [U.hc, 6], [U.lc, 4], [U.art, 4], [U.aux, 2]]);  // no category at 50%+, so combined arms applies
  const mb = battle(mixed, mixed);
  const st = sideStats(d, mb, 'att');
  assert.equal(st.regiments, 40); assert.equal(st.front + st.reserve, 40);
  assert.ok(st.reserve >= 2);  // auxiliaries stay in reserve
  assert.ok(st.combinedArms > 0, 'combined arms');
  assert.equal(sideStats(d, battle(F(10), F(10), { topography: 'mountains', vegetation: 'forest', river: true }), 'att').diceMod, -4);
  const ml = simulateOnce(d, mb);
  assert.ok(ml.notes.some(n => /Bombard/.test(n)));
  line('40 v 40 mixed', d, mb);
  line('cav_inf_cav v balanced', d, battle({ ...mixed, formation: 'cav_inf_cav' }, mixed));

  // timing: 1,000 iterations of 40 v 40
  simulate(d, mb, 100);  // warm up
  const t0 = performance.now();
  simulate(d, mb, 1000);
  const ms = performance.now() - t0;
  console.log(`  timing: 1000 x 40v40 in ${ms.toFixed(0)} ms`);
  assert.ok(ms < 1000, `too slow: ${ms} ms`);
  const s = simulateOnce(d, battle(F(10), F(10), { seed: 7 }));
  console.log(`  sample 10v10 seed 7: ${s.winner} in ${s.days} days, losses ${s.losses.att}/${s.losses.def}; ${s.notes.join('; ')}`);
}

checks(fixture, { inf: 'a_footmen', levy: 'a_footmen_levy', hc: 'a_armored_horsemen', lc: 'a_horsemen', li: 'a_archers', art: 'a_houfnice', aux: 'a_camp_followers' }, 'fixture');

const real = new URL('public/units.json', import.meta.url);
if (existsSync(real)) {
  const d: UnitsData = JSON.parse(readFileSync(real, 'utf8'));
  checks(d, { inf: 'a_footmen', levy: 'a_footmen_levy', hc: 'a_armored_horsemen', lc: 'a_horsemen', li: 'a_archers', art: 'a_houfnice', aux: 'a_camp_followers' }, 'units.json');
} else console.log('[units.json] not found, skipped');
console.log('battle ok');
