// EU5 land battle engine. Pure TS, no DOM. Math follows /tmp/eu5w/SPEC.md section 2; every GUESS is listed in APPROX.
import type { BattleInput, BattleLog, Cat, SideInput, SideState, Summary, Unit, UnitsData } from './units';

export const APPROX: string[] = [
  'Damage per day is COMBAT_DAMAGE_MULT x dice x LAND_STRENGTH/MORALE_DAMAGE_MODIFIER (x men for strength), rebuilt from the wiki\'s hourly formula.',
  'Military tactics: damage is divided by 1 + (target tactics - attacker tactics) when the target has more. The real function is unknown.',
  'Discipline multiplies damage done by (1 + own) and damage taken by 1 / (1 + own).',
  'Levy efficiency is min(1, 0.75 x (1 + levy combat efficiency)): levies hitting regulars deal x that, regulars hitting levies deal / that.',
  'Combined arms: bonus per type x (categories with 10%+ of regiments - 1), none if one category has 50%+. Auxiliaries do not count.',
  'Unit terrain modifiers (topography, vegetation, river) multiply. The river one applies to both sides when the river box is ticked.',
  'Formation numbers are read as ratios. The strongest regiments deploy first; past 125% of a section\'s frontage they wait in reserve.',
  'Reserves move up with chance combat speed x (1 + modifier) x 0.1 a day, to their formation section first.',
  'Bombard: each artillery regiment fires with chance 0.2 + bombard efficiency a day at a random enemy in its section, with the normal damage formula. Nobody engages during it.',
  'Army initiative multiplies unit initiative. The days-in-combat bonus to engaging never resets.',
  'Morale = (base + flat) x (1 + morale modifiers + army tradition x 0.002).',
  'A regiment breaks at 0 morale. A beaten side whose morale is at or under 5% and who is outnumbered 2:1 is wiped; otherwise its survivors lose 10% retreating.',
  'Dice are clamped to 0..COMBAT_MAX. Cavalry damage taken (0.3) is applied literally to men and morale.',
  'Not modelled: morale vs base morale scaling, forts, pursuit, morale recovery, experience gain, late joiners.',
];

const RESERVE = 3, MAX_DAYS = 365;

// unit_formation_preference/army.txt; the numbers are treated as ratios (GUESS), auxiliaries go to reserves.
const all2: Partial<Record<Cat, number>> = { light_cavalry: 2, heavy_cavalry: 2, artillery: 2, heavy_infantry: 2, light_infantry: 2 };
const cav: Partial<Record<Cat, number>> = { heavy_cavalry: 10, light_cavalry: 10 };
const FORMATIONS: Record<SideInput['formation'], Partial<Record<Cat, number>>[]> = {
  balanced_army: [all2, all2, all2],
  cav_inf_cav: [cav, { artillery: 2, heavy_infantry: 20, light_infantry: 20 }, cav],
};

interface Reg {
  u: Unit; levy: boolean; art: boolean;
  sec0: number; sec: number; pref: number;    // 0 left, 1 center, 2 right, 3 reserve; section s faces enemy section s
  max: number; men: number; maxMorale: number; morale: number;
  engaged: boolean; broken: boolean; target: Reg | null; dMen: number; dMor: number;
  // per-battle constants
  offStr: number; offMor: number;             // attacker side: everything but dice, men and pair terms
  defStr: number; defMor: number;             // target side
  engP: number; moveP: number; bombP: number; flank: number; secure: number; front: number; str: number;
}

interface Side {
  regs: Reg[]; frontage: number; diceMod: number; levyF: number; tactics: number; discipline: number; levyDiscipline: number; combined: number;
  dice: number; used: number[]; front: Reg[][]; eng: Reg[][]; adj: number[];
}

interface Prep { s: [Side, Side]; K: Record<string, number>; hasArt: boolean; random: boolean; fixed: [number, number] }

const DEFINES = ['COMBAT_BASE', 'COMBAT_MAX', 'COMBAT_DICE_SIDE', 'COMBAT_DAMAGE_MULT', 'COMBAT_DAILY_MORALE_TICK', 'DAYS_PER_PHASE',
  'BOMBARD_DAYS', 'BOMBARD_BASE_CHANCE', 'MINIMUM_COMBAT_DAYS', 'STRAIT_CROSSING_DICE', 'RIVER_CROSSING_DICE', 'SEA_LANDING_DICE',
  'MAX_FRONTAGE_OVERSTACKING', 'LAND_LEVY_COMBAT_IMPACT', 'MORALE_SIZE_RATIO_MAX', 'INITIATIVE_BASE_CHANCE', 'INITIATIVE_CHANCE_EACH',
  'INITIATIVE_CHANCE_PER_DAY', 'INITIATIVE_CHANCE_MAX', 'COMBAT_SPEED_SCALE', 'LAND_EXPERIENCE_DAMAGE_REDUCTION', 'LAND_STRENGTH_DAMAGE_MODIFIER',
  'LAND_MORALE_DAMAGE_MODIFIER', 'NOT_ENGAGED_STRENGTH_DAMAGE_MODIFIER', 'NOT_ENGAGED_MORALE_DAMAGE_MODIFIER', 'INITIAL_OVERRUN_FACTOR',
  'MORALE_OVERRUN_FACTOR', 'BASE_MORALE_DAMAGE', 'RETREAT_STRENGTH_DAMAGE', 'MORALE_COLLAPSE_THRESHOLD', 'LAND_MORALE', 'MIN_FRONTAGE_AFTER_TERRAIN'];

function mulberry32(a: number): () => number {
  return () => {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const find = <T extends { id: string }>(xs: T[], id: string, what: string): T => {
  const x = xs.find(x => x.id === id);
  if (!x) throw new Error(`unknown ${what} ${id}`);
  return x;
};

// General per-point modifiers plus trait modifiers, summed by modifier key.
function commanderMods(data: UnitsData, s: SideInput): Record<string, number> {
  const m: Record<string, number> = {};
  const add = (mods: Record<string, number>, k = 1) => { for (const key in mods) m[key] = (m[key] ?? 0) + mods[key] * k; };
  const g = s.general;
  if (g) {
    for (const a of ['adm', 'dip', 'mil'] as const) add(data.general[a] ?? {}, g[a]);
    for (const id of g.traits) add(find(data.traits, id, 'trait').mods);
  }
  return m;
}

function buildSide(data: UnitsData, input: BattleInput, who: 'att' | 'def', K: Record<string, number>): Side {
  const s = input[who];
  const m = commanderMods(data, s);
  const units = new Map(data.units.map(u => [u.id, u]));
  const topo = find(data.topography, input.topography, 'topography'), veg = find(data.vegetation, input.vegetation, 'vegetation');
  const rank = find(data.ranks, input.rank, 'rank');
  const frontage = Math.max(K.MIN_FRONTAGE_AFTER_TERRAIN, data.baseFrontage + rank.front + topo.front + veg.front)
    * (1 + s.frontageMod + (m.possible_frontage_modifier ?? 0));
  const tactics = s.tactics + (m.military_tactics ?? 0);
  const levyF = Math.min(1, K.LAND_LEVY_COMBAT_IMPACT * (1 + s.levyEff + (m.levy_combat_efficiency_modifier ?? 0)));  // additive form GUESS
  let diceMod = m.commander_combat_bonus ?? 0;
  if (who === 'att') {
    diceMod -= topo.dice + veg.dice;
    if (input.river) diceMod += K.RIVER_CROSSING_DICE;
    if (input.strait) diceMod += K.STRAIT_CROSSING_DICE;
    if (input.landing) diceMod += K.SEA_LANDING_DICE;
  }

  const list: Unit[] = [];
  for (const r of s.regs) {
    const u = units.get(r.unit);
    if (!u) throw new Error(`unknown unit ${r.unit}`);
    for (let i = 0; i < r.n; i++) list.push(u);
  }
  // combined arms (GUESS): perType x (qualifying categories - 1), off if any category reaches the max share
  const counted = list.filter(u => u.combinedArms), byCat: Record<string, number> = {};
  for (const u of counted) byCat[u.cat] = (byCat[u.cat] ?? 0) + 1;
  const shares = Object.values(byCat).map(c => c / counted.length);
  const maxT = data.base.combined_arms_max_threshold ?? 0.5, minP = data.base.combined_arms_min_percent_for_bonus ?? 0.1;
  const combined = shares.some(x => x >= maxT) ? 0
    : (s.combinedPerType + (m.combined_bonus_per_type ?? 0)) * Math.max(0, shares.filter(x => x >= minP).length - 1);

  const disc = (levy: boolean) => s.discipline + (m.discipline ?? 0) + ((levy ? data.levyMods : data.regularMods).discipline ?? 0);
  const expMul = 1 - K.LAND_EXPERIENCE_DAMAGE_REDUCTION * Math.min(100, Math.max(0, s.experience)) / 100;
  const tc = (u: Unit) => (1 + (u.terrain[input.topography] ?? 0)) * (1 + (u.terrain[input.vegetation] ?? 0)) * (1 + (input.river ? u.terrain.river ?? 0 : 0));
  const regs: Reg[] = list.map(u => {
    const cls = u.levy ? data.levyMods : data.regularMods;
    const g = (k: string) => (m[k] ?? 0) + (cls[k] ?? 0);
    const d = disc(u.levy);
    const off = u.cp * (1 + (s.catPower[u.cat] ?? 0) + g(`army_${u.cat}_power`)) * (1 + d) * tc(u) * (1 + (u.combinedArms ? combined : 0)) * K.COMBAT_DAMAGE_MULT;
    const def = expMul * u.taken / (1 + d);
    const maxMorale = (K.LAND_MORALE + s.moraleFlat + g('land_morale'))
      * (1 + s.moraleMod + s.armyTradition * 0.002 + g('land_morale_modifier'));  // 0.002/pt: +20% at 100 tradition (SPEC 1.9)
    const initEff = u.init * (1 + s.initiativeMod + g('army_initiative'));
    const max = u.str * 1000;
    return {
      u, levy: u.levy, art: u.cat === 'artillery', sec0: RESERVE, sec: RESERVE, pref: -1,
      max, men: max, maxMorale, morale: maxMorale, engaged: false, broken: false, target: null, dMen: 0, dMor: 0,
      offStr: off * K.LAND_STRENGTH_DAMAGE_MODIFIER * (1 + u.sdd),
      offMor: off * K.LAND_MORALE_DAMAGE_MODIFIER * K.BASE_MORALE_DAMAGE * (1 + u.mdd) / max,
      defStr: def * (1 + u.sdt), defMor: def * (1 + u.mdt),
      engP: K.INITIATIVE_BASE_CHANCE + Math.min(initEff * K.INITIATIVE_CHANCE_EACH, K.INITIATIVE_CHANCE_MAX),
      moveP: u.speed * (1 + s.speedMod + g('combat_speed_modifier')) * K.COMBAT_SPEED_SCALE,
      bombP: u.cat === 'artillery' ? K.BOMBARD_BASE_CHANCE + (u.bombard ?? 0) : 0,
      flank: u.flank, secure: u.secure, front: u.front, str: u.str,
    };
  });
  // deployment: strongest first (GUESS); each regiment goes where its category is least represented relative to the preset's ratio
  regs.sort((a, b) => b.u.cp * b.u.str - a.u.cp * a.u.str);
  const pre = FORMATIONS[s.formation] ?? FORMATIONS.balanced_army, cap = frontage * K.MAX_FRONTAGE_OVERSTACKING;
  const used = [0, 0, 0], count = [{} as Record<string, number>, {}, {}];
  for (const r of regs) {
    let pref = -1, best = -1, ps = Infinity, bs = Infinity;
    for (const p of [1, 0, 2]) {
      const w = pre[p][r.u.cat];
      if (!w) continue;
      const score = (count[p][r.u.cat] ?? 0) / w;
      if (score < ps) { ps = score; pref = p; }
      if (score < bs && used[p] + r.front <= cap + 1e-9) { bs = score; best = p; }
    }
    r.pref = pref;
    if (best >= 0) { r.sec0 = best; used[best] += r.front; count[best][r.u.cat] = (count[best][r.u.cat] ?? 0) + 1; }
  }
  return {
    regs, frontage, diceMod, levyF, tactics, discipline: disc(false), levyDiscipline: disc(true), combined,
    dice: 0, used: [0, 0, 0], front: [[], [], []], eng: [[], [], []], adj: [0, 0, 0],
  };
}

function prepare(data: UnitsData, input: BattleInput): Prep {
  const K: Record<string, number> = {};
  for (const k of DEFINES) {
    const v = data.defines[k];
    if (v === undefined) throw new Error(`units.json is missing define ${k}`);
    K[k] = v;
  }
  const s: [Side, Side] = [buildSide(data, input, 'att', K), buildSide(data, input, 'def', K)];
  // military tactics (GUESS): damage / (1 + how much more tactics the target has); folded into the attacker's constants
  for (let i = 0; i < 2; i++) {
    const t = 1 / (1 + Math.max(0, s[1 - i].tactics - s[i].tactics));
    for (const r of s[i].regs) { r.offStr *= t; r.offMor *= t; }
  }
  return {
    s, K, hasArt: s.some(x => x.regs.some(r => r.art)), random: input.dice !== 'fixed',
    fixed: [input.fixed?.att ?? 5, input.fixed?.def ?? 5],
  };
}

function state(S: Side): SideState {
  let men = 0, mor = 0, maxM = 0, alive = 0, front = 0, reserve = 0, broken = 0;
  for (const r of S.regs) {
    men += r.men;
    if (r.broken) { broken++; continue; }
    alive++; mor += r.morale; maxM += r.maxMorale;
    if (r.sec === RESERVE) reserve++; else front++;
  }
  return { men: Math.round(men), morale: alive ? mor / alive : 0, maxMorale: alive ? maxM / alive : 0, front, reserve, broken };
}

const hasFront = (S: Side) => S.regs.some(r => !r.broken && r.sec !== RESERVE);

function engage(S: Side, day: number, K: Record<string, number>, rng: () => number) {
  const u = S.used;
  u[0] = u[1] = u[2] = 0;
  for (const r of S.regs) if (!r.broken && r.engaged) u[r.sec] += r.front;
  const bonus = K.INITIATIVE_CHANCE_PER_DAY * day;
  for (const r of S.regs) {
    if (r.broken || r.engaged || r.sec === RESERVE || u[r.sec] + r.front > S.frontage + 1e-9) continue;
    if (rng() < r.engP + bonus) { r.engaged = true; u[r.sec] += r.front; }
  }
}

// Reserves roll to move up, strongest first, as many as there is free frontage (regs are sorted strongest first).
function reserves(S: Side, rng: () => number) {
  const free = S.used;
  free[0] = free[1] = free[2] = S.frontage;
  let any = false;
  for (const r of S.regs) if (!r.broken) { if (r.sec === RESERVE) any = true; else free[r.sec] -= r.front; }
  if (!any) return;
  let total = Math.max(0, free[0]) + Math.max(0, free[1]) + Math.max(0, free[2]), rolled = 0;
  for (const r of S.regs) {
    if (r.broken || r.sec !== RESERVE) continue;
    if (rolled + r.front > total + 1e-9) break;
    rolled += r.front;
    if (rng() >= r.moveP) continue;
    let to = r.pref >= 0 && free[r.pref] >= r.front - 1e-9 ? r.pref : -1;
    if (to < 0) to = free[1] >= free[0] && free[1] >= free[2] ? 1 : free[0] >= free[2] ? 0 : 2;
    r.sec = to; r.engaged = false; free[to] -= r.front;
  }
}

function lists(S: Side) {
  for (let p = 0; p < 3; p++) { S.front[p].length = 0; S.eng[p].length = 0; }
  for (const r of S.regs) {
    if (r.broken || r.sec === RESERVE) continue;
    S.front[r.sec].push(r);
    if (r.engaged) S.eng[r.sec].push(r);
  }
  const f = S.front;
  S.adj[0] = f[1].length ? 1 : 0; S.adj[2] = S.adj[0];
  S.adj[1] = (f[0].length ? 1 : 0) + (f[2].length ? 1 : 0);
}

const pickIn = (E: Side, p: number, rng: () => number): Reg | null => {
  const xs = E.eng[p].length ? E.eng[p] : E.front[p];
  return xs.length ? xs[Math.floor(rng() * xs.length)] : null;
};

// Opposing section first, engaged enemies first; else the nearest section (flanking).
function pick(E: Side, p: number, rng: () => number): Reg | null {
  if (E.front[p].length) return pickIn(E, p, rng);
  const order = p === 1 ? (rng() < 0.5 ? [0, 2] : [2, 0]) : [1, 2 - p];
  for (const q of order) if (E.front[q].length) return pickIn(E, q, rng);
  return null;
}

function hit(a: Reg, t: Reg, S: Side, E: Side, K: Record<string, number>) {
  const levy = a.levy === t.levy ? 1 : a.levy ? S.levyF : 1 / E.levyF;
  const flank = t.sec !== a.sec ? a.flank : 1;
  const common = S.dice * a.men * levy * flank * (1 - t.secure * E.adj[t.sec]);
  const ratio = Math.min(K.MORALE_SIZE_RATIO_MAX, Math.max(1 / K.MORALE_SIZE_RATIO_MAX, a.str / t.str));
  t.dMen += common * a.offStr * t.defStr * (t.engaged ? 1 : K.NOT_ENGAGED_STRENGTH_DAMAGE_MODIFIER);
  t.dMor += common * a.offMor * t.defMor * ratio * (t.engaged ? 1 : K.NOT_ENGAGED_MORALE_DAMAGE_MODIFIER);
}

function attack(S: Side, E: Side, K: Record<string, number>, rng: () => number) {
  for (const a of S.regs) {
    if (a.broken || !a.engaged) continue;
    if (!a.target || a.target.broken) a.target = pick(E, a.sec, rng);
    if (a.target) hit(a, a.target, S, E, K);
  }
}

function bombard(S: Side, E: Side, K: Record<string, number>, rng: () => number) {
  for (const a of S.regs) {
    if (!a.art || a.broken || a.sec === RESERVE || rng() >= a.bombP) continue;
    const xs = E.front[a.sec];
    if (xs.length) hit(a, xs[Math.floor(rng() * xs.length)], S, E, K);
  }
}

function settle(S: Side, K: Record<string, number>) {
  for (const r of S.regs) {
    if (r.broken) continue;
    r.men = Math.max(0, r.men - r.dMen);
    r.morale -= r.dMor + K.COMBAT_DAILY_MORALE_TICK;
    r.dMen = r.dMor = 0;
    if (r.morale <= 0 || r.men <= 0) { r.broken = true; r.engaged = false; r.morale = Math.max(0, r.morale); }  // break at 0 (GUESS vs collapse threshold)
  }
}

const totalMen = (S: Side) => S.regs.reduce((t, r) => t + r.men, 0);
const fightingMen = (S: Side) => S.regs.reduce((t, r) => t + (r.broken ? 0 : r.men), 0);
const NAME = ['Attacker', 'Defender'];

function run(P: Prep, seed: number, record: boolean): BattleLog {
  const rng = mulberry32(seed), [A, B] = P.s, K = P.K;
  for (const S of P.s) for (const r of S.regs) {
    r.sec = r.sec0; r.men = r.max; r.morale = r.maxMorale; r.engaged = r.broken = false; r.target = null; r.dMen = r.dMor = 0;
  }
  const notes: string[] = [], daily: BattleLog['daily'] = [];
  const start = { att: state(A), def: state(B) }, men0 = [totalMen(A), totalMen(B)];
  const finish = (winner: BattleLog['winner'], days: number): BattleLog => ({
    winner, days, start, daily, notes,
    losses: { att: Math.round(men0[0] - totalMen(A)), def: Math.round(men0[1] - totalMen(B)) },
  });
  if (!men0[0] && !men0[1]) return finish('draw', 0);

  // initial overrun: a strength ratio of INITIAL_OVERRUN_FACTOR or more wipes the smaller side on the first day
  for (let i = 0; i < 2; i++) {
    if (men0[i] >= K.INITIAL_OVERRUN_FACTOR * men0[1 - i]) {
      const ratio = men0[1 - i] ? `${Math.round(men0[i] / men0[1 - i])}:1` : 'no opposition';
      for (const r of P.s[1 - i].regs) { r.men = 0; r.broken = true; }
      notes.push(`${NAME[1 - i]} overrun on day 1 (${ratio})`);
      if (record) daily.push({ att: state(A), def: state(B), diceAtt: 0, diceDef: 0 });
      return finish(i ? 'def' : 'att', 1);
    }
  }

  const roll = (S: Side, i: number) => {
    const r = P.random ? Math.floor(rng() * K.COMBAT_DICE_SIDE) : Math.min(K.COMBAT_DICE_SIDE - 1, Math.max(0, P.fixed[i]));
    S.dice = Math.min(K.COMBAT_MAX, Math.max(0, K.COMBAT_BASE + r + S.diceMod));
  };
  const bombDays = P.hasArt ? K.BOMBARD_DAYS : 0;
  if (bombDays) notes.push(`Bombard phase: ${bombDays} days`);
  for (let day = 1; day <= MAX_DAYS; day++) {
    if (day === 1 || (day > bombDays && (day - bombDays - 1) % K.DAYS_PER_PHASE === 0)) { roll(A, 0); roll(B, 1); }
    if (day <= bombDays) {
      lists(A); lists(B);
      bombard(A, B, K, rng); bombard(B, A, K, rng);
    } else {
      engage(A, day - 1, K, rng); engage(B, day - 1, K, rng);
      reserves(A, rng); reserves(B, rng);
      lists(A); lists(B);
      attack(A, B, K, rng); attack(B, A, K, rng);
    }
    settle(A, K); settle(B, K);
    if (record) daily.push({ att: state(A), def: state(B), diceAtt: A.dice, diceDef: B.dice });
    if (day < K.MINIMUM_COMBAT_DAYS) continue;
    // a side with an empty front gets one more reserve roll to refill it, else it is beaten
    const out = P.s.map(S => { if (hasFront(S)) return false; reserves(S, rng); return !hasFront(S); });
    if (!out[0] && !out[1]) continue;
    if (out[0] && out[1]) { notes.push(`Both sides broke on day ${day}`); return finish('draw', day); }
    const w = out[0] ? 1 : 0, L = P.s[1 - w];
    let mor = 0, men = 0;
    for (const r of L.regs) { men += r.men; mor += r.men * Math.max(0, r.morale) / r.maxMorale; }
    const collapsed = !men || mor / men <= K.MORALE_COLLAPSE_THRESHOLD, wm = fightingMen(P.s[w]);
    if (collapsed && wm >= K.MORALE_OVERRUN_FACTOR * men) {
      for (const r of L.regs) r.men = 0;
      notes.push(`${NAME[1 - w]} wiped on day ${day}: morale collapsed at ${men ? (wm / men).toFixed(1) : '∞'}:1`);
    } else {
      for (const r of L.regs) r.men *= 1 - K.RETREAT_STRENGTH_DAMAGE;
      notes.push(`${NAME[1 - w]} retreats on day ${day}, losing ${Math.round(K.RETREAT_STRENGTH_DAMAGE * 100)}% of its survivors`);
    }
    return finish(w ? 'def' : 'att', day);
  }
  notes.push(`No result after ${MAX_DAYS} days`);
  return finish('draw', MAX_DAYS);
}

const randomSeed = () => (Math.random() * 4294967296) >>> 0;

export function simulateOnce(data: UnitsData, input: BattleInput): BattleLog {
  return run(prepare(data, input), input.seed ?? randomSeed(), true);
}

export function simulate(data: UnitsData, input: BattleInput, n: number): Summary {
  const P = prepare(data, input), base = input.seed ?? randomSeed();
  n = Math.max(1, Math.floor(n));
  const seeds: number[] = [], days: number[] = [], la: number[] = [], ld: number[] = [];
  let att = 0, def = 0;
  for (let i = 0; i < n; i++) {
    const seed = (base + Math.imul(i, 0x9E3779B9)) >>> 0, log = run(P, seed, false);
    seeds.push(seed); days.push(log.days); la.push(log.losses.att); ld.push(log.losses.def);
    if (log.winner === 'att') att++; else if (log.winner === 'def') def++;
  }
  const stat = (xs: number[]) => ({ avg: xs.reduce((a, b) => a + b, 0) / xs.length, min: xs.reduce((a, b) => Math.min(a, b)), max: xs.reduce((a, b) => Math.max(a, b)) });
  const median = [...days].sort((a, b) => a - b)[n >> 1];
  let best = 0;
  for (let i = 1; i < n; i++) if (Math.abs(days[i] - median) < Math.abs(days[best] - median)) best = i;
  return {
    n, attWin: att / n, defWin: def / n, draw: (n - att - def) / n,
    days: stat(days), losses: { att: stat(la), def: stat(ld) },
    sample: run(P, seeds[best], true),  // deterministic replay of the median-length run, with the daily log
  };
}

export interface SideStats {
  men: number; regiments: number; front: number; reserve: number;
  frontage: number;                 // possible frontage per section (engaged cap); deployment holds up to MAX_FRONTAGE_OVERSTACKING of it
  maxMorale: number;                // average over regiments
  discipline: number; levyDiscipline: number; tactics: number;
  levyEfficiency: number;           // F in the levy vs regular multiplier
  combinedArms: number;             // bonus applied to damage
  diceMod: number;                  // added to every 0..9 roll on top of COMBAT_BASE (commander bonus, attacker terrain/crossing penalties)
  sections: { left: number; center: number; right: number };  // regiments deployed per section
}

export function sideStats(data: UnitsData, input: BattleInput, who: 'att' | 'def'): SideStats {
  const S = prepare(data, input).s[who === 'att' ? 0 : 1], regs = S.regs;
  const at = (p: number) => regs.filter(r => r.sec0 === p).length;
  return {
    men: regs.reduce((t, r) => t + r.max, 0), regiments: regs.length, front: regs.length - at(RESERVE), reserve: at(RESERVE),
    frontage: S.frontage, maxMorale: regs.length ? regs.reduce((t, r) => t + r.maxMorale, 0) / regs.length : 0,
    discipline: S.discipline, levyDiscipline: S.levyDiscipline, tactics: S.tactics, levyEfficiency: S.levyF,
    combinedArms: S.combined, diceMod: S.diceMod,
    sections: { left: at(0), center: at(1), right: at(2) },
  };
}

