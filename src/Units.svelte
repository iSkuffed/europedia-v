<script lang="ts">
  // Units tab: a browser for every land unit (#u, #u/<unitId>) and a land battle simulator (#u/battle) on battle.ts.
  import { loadUnits, type UnitsData, type Unit, type Cat, type SideInput, type BattleInput, type Summary, type General, type SideState } from './lib/units';
  import { simulate, sideStats, APPROX } from './lib/battle';
  import { fits, type Fit, type WhoItem } from './lib/fit';
  import { SCOPE } from './lib/scope.svelte';
  import { loadAdvances } from './lib/cards';
  import { ROMAN } from './lib/production';
  import { DATA } from './lib/data';

  let { id }: { id: string | null } = $props();
  let D = $state.raw<UnitsData>();
  let ADV = $state.raw<Record<string, { icon?: string }>>({});
  loadUnits().then(d => { D = d; B = loadSetup(d); });
  loadAdvances().then((d: { advances: { id: string; icon?: string }[] }) => ADV = Object.fromEntries(d.advances.map(a => [a.id, a])));

  // ---- vocabulary ------------------------------------------------------------------------------------------------
  const CATN: Record<Cat, string> = { heavy_infantry: 'Heavy infantry', light_infantry: 'Light infantry', heavy_cavalry: 'Heavy cavalry',
    light_cavalry: 'Light cavalry', artillery: 'Artillery', auxiliary: 'Auxiliary' };
  const CATS = Object.keys(CATN) as Cat[];
  const AGES = [1, 2, 3, 4, 5, 6];
  const ageName = (n: number) => `Age ${ROMAN[n]}: ${DATA.ages[n] ?? ''}`;
  const catIc = (c: Cat) => `icons/units/army_${c}.png`;
  const art = (u: Unit) => `icons/units/${u.icon ?? u.id}.webp`;
  const sign = (v: number) => v > 0 ? '+' : v < 0 ? '−' : '';
  const pct = (v: number) => `${sign(v)}${+(Math.abs(v) * 100).toFixed(1)}%`;
  const num = (v: number) => `${+v.toFixed(3)}`;
  const snum = (v: number) => `${sign(v)}${+Math.abs(v).toFixed(3)}`;
  const men = (v: number) => Math.round(v).toLocaleString('en');
  const kmen = (v: number) => v >= 1000 ? `${+(v / 1000).toFixed(1)}k` : `${Math.round(v)}`;

  // modifier keys (traits, general points) in words; pct = shown as a percentage
  const ML: Record<string, [string, boolean]> = {
    military_tactics: ['Military tactics', false], commander_combat_bonus: ['Dice roll', false], discipline: ['Discipline', true],
    army_initiative: ['Army initiative', true], land_morale_modifier: ['Morale', true], land_morale: ['Morale (flat)', false],
    land_morale_recovery: ['Morale recovery (not simulated)', true], possible_frontage_modifier: ['Frontage', true], combat_speed_modifier: ['Combat speed', true],
    levy_combat_efficiency_modifier: ['Levy efficiency', true], combined_bonus_per_type: ['Combined arms per type', true],
    ...Object.fromEntries(CATS.map(c => [`army_${c}_power`, [`${CATN[c]} power`, true]])),
  };
  const modTxt = (k: string, v: number) => { const [l, p] = ML[k] ?? [k.replace(/_/g, ' '), false]; return `${l} ${p ? pct(v) : snum(v)}`; };
  const mods = (m: Record<string, number>) => Object.entries(m).map(([k, v]) => modTxt(k, v)).join(', ');

  // plain-English stat explanations (SPEC 1.2-1.8, and how battle.ts uses them)
  type StatKey = 'str' | 'cp' | 'front' | 'init' | 'speed' | 'move' | 'flank' | 'secure' | 'sdd' | 'sdt' | 'mdd' | 'mdt' | 'taken' | 'bombard';
  const STATS: { k: StatKey; l: string; f: (v: number) => string; good: 1 | -1 | 0; t: string }[] = [
    { k: 'str', l: 'Men', f: v => men(v * 1000), good: 1, t: 'Regiment size at full strength (max_strength 0.5 = 500 men). Damage dealt scales with the men still standing.' },
    { k: 'cp', l: 'Combat power', f: num, good: 1, t: 'The regiment\'s base damage: everything it deals is multiplied by it.' },
    { k: 'front', l: 'Frontage', f: num, good: 0, t: 'How much of a battle section\'s width it fills. A section holds 10 on open ground, less in rough terrain or towns.' },
    { k: 'init', l: 'Initiative', f: num, good: 1, t: 'Daily chance to engage an enemy: 60% base, +2.5% per point, up to +30% at 12 points.' },
    { k: 'speed', l: 'Combat speed', f: num, good: 1, t: 'How fast it moves up from the reserve: a 10% chance per point each day.' },
    { k: 'move', l: 'Movement speed', f: num, good: 1, t: 'Speed on the map. It plays no part in the battle itself.' },
    { k: 'flank', l: 'Flanking', f: num, good: 1, t: 'Damage multiplier when it hits an enemy in another section, e.g. once the section opposite is cleared.' },
    { k: 'secure', l: 'Secure flanks', f: pct, good: 1, t: 'Cuts the damage it takes by this much for each neighbouring section its own side still holds.' },
    { k: 'sdd', l: 'Strength damage done', f: pct, good: 1, t: 'More or fewer men killed by each hit it lands.' },
    { k: 'sdt', l: 'Strength damage taken', f: pct, good: -1, t: 'More or fewer men lost to each hit it takes. Lower is better.' },
    { k: 'mdd', l: 'Morale damage done', f: pct, good: 1, t: 'More or less morale knocked off the enemy by each hit.' },
    { k: 'mdt', l: 'Morale damage taken', f: pct, good: -1, t: 'More or less morale lost to each hit it takes. Lower is better.' },
    { k: 'taken', l: 'Category damage taken', f: num, good: -1, t: 'Set by the category: infantry 1, cavalry 0.3 (armour; the engine scales cavalry regiments), artillery and auxiliaries 1.25. Multiplies all damage it takes.' },
    { k: 'bombard', l: 'Bombard', f: pct, good: 1, t: 'Artillery only. In the opening 3-day bombard phase each artillery regiment fires with a daily chance of 20% + this.' },
  ];

  // terrain ids in unit `combat` blocks -> names; climate and coast are not part of the simulator
  const TNAME = $derived<Record<string, string>>(D ? { ...Object.fromEntries([...D.topography, ...D.vegetation].map(t => [t.id, t.name])),
    river: 'River crossing', arid: 'Arid climate', coastal: 'Coastal', inland: 'Inland' } : {});
  const simTerrain = (k: string) => k === 'river' || !!D?.topography.some(t => t.id === k) || !!D?.vegetation.some(t => t.id === k);
  const terrainOf = (u: Unit) => Object.entries(u.terrain).sort((a, b) => b[1] - a[1]);

  // ---- lookups -------------------------------------------------------------------------------------------------------
  const U = $derived(new Map((D?.units ?? []).map(u => [u.id, u])));
  const GEN = $derived.by(() => {  // the generic regular of each age and category, and the generic levy of each age
    const m = new Map<string, Unit>();
    for (const u of D?.units ?? []) if (!u.unique) { const k = u.levy ? `${u.age}:levy` : `${u.age}:${u.cat}`; if (!m.has(k)) m.set(k, u); }
    return m;
  });
  const isBattle = $derived(id === 'battle');
  const unit = $derived(id && !isBattle ? U.get(id) : undefined);

  // ---- "viewing as" a nation -------------------------------------------------------------------------------------------
  const FIT = $derived.by(() => {
    const m = new Map<string, Fit>();
    if (D && SCOPE.ctx) for (const u of D.units) m.set(u.id, fits(u.who, SCOPE.ctx));
    return m;
  });
  const fitOf = (u: Unit): Fit => FIT.get(u.id) ?? 'yes';
  const vis = $derived((D?.units ?? []).filter(u => fitOf(u) !== 'no'));
  const nHidden = $derived((D?.units.length ?? 0) - vis.length);
  const nMaybe = $derived(vis.filter(u => fitOf(u) === 'maybe').length);
  const COND = 'Conditional: part of what it needs (an unlock, event, DLC or condition) cannot be checked from the data, so it may still apply.';

  // ---- browser filters -------------------------------------------------------------------------------------------------
  let q = $state(''), cats = $state<Cat[]>([]), ages = $state<number[]>([]), kind = $state(''), origin = $state(''), avail = $state('');
  const toggle = <T,>(a: T[], v: T) => a.includes(v) ? a.filter(x => x !== v) : [...a, v];
  const AVAIL: [string, string][] = [['', 'Any'], ['everyone', 'Everyone'], ['country', 'Country'], ['culture', 'Culture'], ['religion', 'Religion'], ['region', 'Region'], ['other', 'Other']];
  const ACAT: Record<string, string> = { tag: 'country', culture: 'culture', culture_group: 'culture', language: 'culture', religion: 'religion',
    religion_group: 'religion', region: 'region', area: 'region', sub_continent: 'region', continent: 'region' };
  function availOf(u: Unit): Set<string> {  // what kinds of positive restriction a unit has; none = everyone
    const s = new Set<string>();
    const walk = (its: WhoItem[], neg: boolean) => { for (const it of its) {
      const n = neg !== !!it.not;
      if (it.parts || it.any || it.all) walk([...(it.parts ?? []), ...(it.any ?? []), ...(it.all ?? [])], n);
      else if (!n) s.add(ACAT[it.type] ?? 'other');
    } };
    walk(u.who, false);
    if (!s.size) s.add('everyone');
    return s;
  }
  const AV = $derived(new Map((D?.units ?? []).map(u => [u.id, availOf(u)])));
  const textOK = (u: Unit) => !q.trim() || q.toLowerCase().split(/\s+/).every(w => `${u.name} ${u.id} ${u.whoText} ${CATN[u.cat]}`.toLowerCase().includes(w));
  const base = $derived(vis.filter(u => textOK(u) && (!cats.length || cats.includes(u.cat)) && (!ages.length || ages.includes(u.age))
    && (!kind || (kind === 'levy') === u.levy) && (!origin || (origin === 'unique') === u.unique)));
  const availN = $derived(Object.fromEntries(AVAIL.map(([k]) => [k, k ? base.filter(u => AV.get(u.id)!.has(k)).length : base.length])));
  const shown = $derived(avail ? base.filter(u => AV.get(u.id)!.has(avail)) : base);
  const catN = (c: Cat) => vis.filter(u => u.cat === c).length;

  // overview: sortable table or cards, grouped by category
  type SortKey = 'name' | 'age' | 'str' | 'cp' | 'init' | 'speed' | 'flank' | 'sdd' | 'sdt' | 'mdd' | 'mdt';
  const COLS: [SortKey, string, string][] = [['age', 'Age', 'Age the unit belongs to'], ['str', 'Men', 'Regiment size at full strength'], ['cp', 'CP', 'Combat power: base damage'],
    ['init', 'Init', 'Initiative: chance to engage each day'], ['speed', 'Speed', 'Combat speed: how fast it moves up from the reserve'], ['flank', 'Flank', 'Flanking: damage multiplier against other sections'],
    ['sdd', 'Str done', 'Strength damage done'], ['sdt', 'Str taken', 'Strength damage taken (lower is better)'], ['mdd', 'Mor done', 'Morale damage done'], ['mdt', 'Mor taken', 'Morale damage taken (lower is better)']];
  let sortK = $state<SortKey>('age'), sortD = $state(1);
  const sortBy = (k: SortKey) => { if (sortK === k) sortD = -sortD; else { sortK = k; sortD = k === 'name' || k === 'age' || k === 'sdt' || k === 'mdt' ? 1 : -1; } };
  const cmp = (a: Unit, b: Unit) => (sortK === 'name' ? a.name.localeCompare(b.name) : (a[sortK] - b[sortK])) * sortD || a.age - b.age || +a.unique - +b.unique || a.name.localeCompare(b.name);
  const groups = $derived(CATS.map(c => ({ c, list: shown.filter(u => u.cat === c).sort(cmp) })).filter(g => g.list.length));
  const sideList = $derived(CATS.map(c => ({ c, list: shown.filter(u => u.cat === c).sort((a, b) => a.age - b.age || +a.unique - +b.unique || a.name.localeCompare(b.name)) })).filter(g => g.list.length));
  let cards = $state(localStorage.getItem('unitView') === 'cards');
  $effect(() => localStorage.setItem('unitView', cards ? 'cards' : 'table'));

  // ---- one unit ------------------------------------------------------------------------------------------------------------
  const generic = $derived(unit ? GEN.get(`${unit.age}:${unit.cat}`) : undefined);
  const cmpTo = $derived(generic && generic.id !== unit?.id ? generic : undefined);
  const preds = (u: Unit) => (D?.units ?? []).filter(x => x.upgrades === u.id);
  const line = $derived.by(() => {  // the upgrade line through this unit: back while there is one predecessor, forward to the end
    if (!unit) return [];
    const out = [unit];
    for (let p = preds(unit); p.length === 1 && !out.includes(p[0]); p = preds(p[0])) out.unshift(p[0]);
    for (let n = unit.upgrades && U.get(unit.upgrades); n && !out.includes(n); n = n.upgrades && U.get(n.upgrades)) out.push(n);
    return out;
  });
  const otherPreds = $derived(unit ? preds(unit).filter(p => !line.includes(p)) : []);
  const kin = $derived(unit ? vis.filter(u => u.cat === unit.cat && u.age === unit.age && u.id !== unit.id).sort((a, b) => +a.unique - +b.unique || a.name.localeCompare(b.name)) : []);

  let mainEl = $state<HTMLElement>();
  let sideEl = $state<HTMLElement>();
  $effect(() => { id; mainEl?.scrollTo(0, 0); });
  // scroll only the sidebar (scrollIntoView would also nudge the page)
  $effect(() => { if (id && D) queueMicrotask(() => {
    const a = sideEl?.querySelector<HTMLElement>('.blist a.on');
    if (!sideEl || !a) return;
    const r = a.getBoundingClientRect(), s = sideEl.getBoundingClientRect();
    if (r.top < s.top) sideEl.scrollTop += r.top - s.top - 8;
    else if (r.bottom > s.bottom) sideEl.scrollTop += r.bottom - s.bottom + 8;
  }); });
  const toggleCard = (e: MouseEvent) => (e.target as Element).closest('section.card > h4')?.parentElement!.classList.toggle('shut');

  // ==== battle simulator =====================================================================================================
  type Side = 'att' | 'def';
  type Mods = Omit<SideInput, 'regs' | 'general'>;
  type NumKey = Exclude<keyof Mods, 'catPower' | 'formation'>;
  type Focus = '' | 'adm' | 'dip' | 'mil';
  interface SideCfg { age: number; focus: Focus; regs: { unit: string; n: number }[]; genOn: boolean; gen: General; m: Mods }
  interface Setup {
    att: SideCfg; def: SideCfg; topography: string; vegetation: string; rank: string; river: boolean; strait: boolean; landing: boolean;
    dice: 'random' | 'fixed'; fixed: { att: number; def: number }; iters: number; seed: number;
  }
  const KEY = 'unitsBattle';
  const FOCUS: [Focus, string][] = [['', 'None'], ['mil', 'Military'], ['adm', 'Administrative'], ['dip', 'Diplomatic']];
  const newSeed = () => (Math.random() * 4294967296) >>> 0;

  // what an age (and the age focus) gives every country: SideInput fields from ageMods / focusMods
  function ageMods(d: UnitsData, age: number, focus: Focus, keep?: Mods): Mods {
    const t: Record<string, number> = {};
    for (const src of [d.ageMods[age], focus ? d.focusMods[focus]?.[age] : undefined]) for (const k in src ?? {}) t[k] = (t[k] ?? 0) + src![k];
    const g = (k: string) => t[k] ?? 0;
    return {
      discipline: g('discipline'), tactics: (d.base.military_tactics ?? 1) + g('military_tactics'), moraleFlat: g('land_morale'), moraleMod: g('land_morale_modifier'),
      levyEff: g('levy_combat_efficiency_modifier'), initiativeMod: g('army_initiative'), speedMod: g('combat_speed_modifier'), frontageMod: g('possible_frontage_modifier'),
      combinedPerType: (d.base.combined_bonus_per_type ?? 0) + g('combined_bonus_per_type'),
      catPower: Object.fromEntries(CATS.filter(c => g(`army_${c}_power`)).map(c => [c, g(`army_${c}_power`)])),
      experience: keep?.experience ?? 0, armyTradition: keep?.armyTradition ?? 0, formation: keep?.formation ?? 'balanced_army',
    };
  }
  // the same regiment one age on: generic levies to that age's levy, generic regulars to the same category's; uniques stay
  function upgradeTo(u: Unit, age: number): string {
    if (u.unique) return u.id;
    return (u.levy ? GEN.get(`${age}:levy`) : GEN.get(`${age}:${u.cat}`))?.id ?? u.id;
  }
  function setAge(c: SideCfg, age: number) {
    c.age = age;
    c.m = ageMods(D!, age, c.focus, c.m);
    const regs: SideCfg['regs'] = [];
    for (const r of c.regs) {
      const u = U.get(r.unit), to = u ? upgradeTo(u, age) : r.unit, same = regs.find(x => x.unit === to);
      if (same) same.n += r.n; else regs.push({ unit: to, n: r.n });
    }
    c.regs = regs;
  }
  const setFocus = (c: SideCfg, f: Focus) => { c.focus = f; c.m = ageMods(D!, c.age, f, c.m); };
  function newSide(d: UnitsData, age: number): SideCfg {
    const g = (k: string) => d.units.find(u => !u.unique && (k === 'levy' ? u.levy && u.age === age : !u.levy && u.age === age && u.cat === k))?.id;
    const regs = [g('heavy_infantry'), g('levy')].filter((x): x is string => !!x).map(unit => ({ unit, n: 10 }));
    return { age, focus: '', regs, genOn: false, gen: { adm: 50, dip: 50, mil: 50, traits: [] }, m: ageMods(d, age, '') };
  }
  const defaults = (d: UnitsData): Setup => ({ att: newSide(d, 1), def: newSide(d, 1), topography: 'flatland', vegetation: 'farmland', rank: 'rural_settlement',
    river: false, strait: false, landing: false, dice: 'random', fixed: { att: 5, def: 5 }, iters: 1000, seed: newSeed() });
  function loadSetup(d: UnitsData): Setup {
    const def = defaults(d);
    try {
      const s = JSON.parse(localStorage.getItem(KEY) ?? 'null');
      if (!s?.att?.m || !s?.def?.m) return def;
      const ids = new Set(d.units.map(u => u.id)), trait = new Set(d.traits.map(t => t.id));
      const side = (x: SideCfg, dd: SideCfg): SideCfg => ({ ...dd, ...x, m: { ...dd.m, ...x.m }, gen: { ...dd.gen, ...x.gen, traits: (x.gen?.traits ?? []).filter(t => trait.has(t)) },
        regs: (Array.isArray(x.regs) ? x.regs : []).filter(r => ids.has(r.unit) && r.n >= 0) });
      const has = (xs: { id: string }[], v: string) => xs.some(x => x.id === v);
      return { ...def, ...s, att: side(s.att, def.att), def: side(s.def, def.def),
        topography: has(d.topography, s.topography) ? s.topography : def.topography, vegetation: has(d.vegetation, s.vegetation) ? s.vegetation : def.vegetation,
        rank: has(d.ranks, s.rank) ? s.rank : def.rank, fixed: { ...def.fixed, ...s.fixed } };
    } catch { return def; }
  }
  let B = $state<Setup>();
  $effect(() => { if (B) localStorage.setItem(KEY, JSON.stringify($state.snapshot(B))); });

  const sideIn = (c: SideCfg): SideInput => ({ ...c.m, regs: c.regs.filter(r => r.n > 0 && U.has(r.unit)), general: c.genOn ? c.gen : null });
  const toInput = (s: Setup): BattleInput => ({ att: sideIn(s.att), def: sideIn(s.def), topography: s.topography, vegetation: s.vegetation, rank: s.rank,
    river: s.river, strait: s.strait, landing: s.landing, dice: s.dice, fixed: s.fixed, seed: s.seed });
  const input = $derived(B && D ? toInput($state.snapshot(B) as Setup) : null);
  const ready = $derived(!!input && input.att.regs.length > 0 && input.def.regs.length > 0);
  const stats = $derived.by(() => {
    if (!D || !input) return null;
    try { return { att: sideStats(D, input, 'att'), def: sideStats(D, input, 'def') }; } catch { return null; }
  });

  // run on the main thread, debounced: about 100 ms per 1,000 battles
  let result = $state.raw<Summary | null>(null), busy = $state(false), err = $state('');
  $effect(() => {
    if (!isBattle || !D || !input) return;
    const d = D, inp = input, n = B!.iters;
    if (!ready) { result = null; busy = false; return; }
    busy = true;
    const t = setTimeout(() => {
      try { result = simulate(d, inp, n); err = ''; } catch (e) { result = null; err = e instanceof Error ? e.message : String(e); }
      busy = false;
    }, 250);
    return () => clearTimeout(t);
  });

  // regiments
  const menOf = (r: { unit: string; n: number }) => (U.get(r.unit)?.str ?? 0) * 1000 * r.n;
  function addRegs(c: SideCfg, unitId: string, n: number) {
    const r = c.regs.find(x => x.unit === unitId);
    if (r) r.n = Math.max(0, r.n + n); else c.regs.push({ unit: unitId, n: Math.max(1, n) });
  }
  const quick = (c: SideCfg, what: 'levy' | 'heavy_infantry') => GEN.get(`${c.age}:${what}`);
  const inBattle = (w: Side, uid: string) => B?.[w].regs.find(r => r.unit === uid)?.n ?? 0;

  // unit picker: searchable, by category, the scoped nation's units first, then the side's age
  let pick = $state<{ w: Side; i: number } | null>(null), pq = $state('');
  const openPick = (w: Side, i: number) => { pick = pick && pick.w === w && pick.i === i ? null : { w, i }; pq = ''; };
  const pickList = $derived.by(() => {
    if (!pick || !D || !B) return [];
    const age = B[pick.w].age, words = pq.toLowerCase().split(/\s+/).filter(Boolean);
    const ok = (u: Unit) => words.every(w => `${u.name} ${u.whoText} ${u.levy ? 'levy' : 'regular'}`.toLowerCase().includes(w));
    const rank = (u: Unit) => (fitOf(u) === 'no' ? 100 : 0) + Math.abs(u.age - age) * 2 + (u.unique ? 1 : 0);
    const by = (a: Unit, b: Unit) => rank(a) - rank(b) || a.name.localeCompare(b.name);
    // viewing as a nation: the unique units it can recruit come first, in their own group
    const own = SCOPE.ctx ? D.units.filter(u => u.unique && fitOf(u) === 'yes' && ok(u)).sort(by) : [];
    return [...(own.length ? [{ key: 'own', c: null, label: `${SCOPE.name || SCOPE.ctx!.tag}'s own units`, list: own }] : []),
      ...CATS.map(c => ({ key: c, c, label: CATN[c], list: D!.units.filter(u => u.cat === c && ok(u)).sort(by) })).filter(g => g.list.length)];
  });
  function choose(uid: string) {
    if (!pick || !B) return;
    const c = B[pick.w];
    if (pick.i < 0) addRegs(c, uid, 1);
    else {
      const r = c.regs[pick.i], other = c.regs.findIndex((x, j) => x.unit === uid && j !== pick!.i);
      if (other >= 0) { c.regs[other].n += r.n; c.regs.splice(pick.i, 1); } else r.unit = uid;
    }
    pick = null;
  }
  const closePick = (e: PointerEvent) => { if (pick && !(e.target as Element).closest?.('.picker, .pickbtn')) pick = null; };

  function swap() {
    if (!B) return;
    const a = $state.snapshot(B.att), f = B.fixed;
    B.att = $state.snapshot(B.def) as SideCfg; B.def = a as SideCfg; B.fixed = { att: f.def, def: f.att };
  }
  const reset = () => { if (D) B = defaults(D); };

  const ADVM: [NumKey, string, 'pct' | 'num' | 'int', string][] = [
    ['discipline', 'Discipline', 'pct', 'Damage done ×(1 + discipline), damage taken ÷(1 + discipline). Levies get −20% on top.'],
    ['tactics', 'Military tactics', 'num', 'Base 1, +1 from Feudalism, +0.25 per later age. Facing more tactics, your damage is divided by 1 + the gap.'],
    ['moraleFlat', 'Morale, flat', 'num', 'Added to the base 3.0 morale of every regiment.'],
    ['moraleMod', 'Morale modifier', 'pct', 'Multiplies maximum morale (army tradition and the general\'s diplomacy add to it).'],
    ['experience', 'Experience', 'int', '0 to 100. At 100 the army takes 50% less damage.'],
    ['armyTradition', 'Army tradition', 'int', '0 to 100. At 100, +20% morale.'],
    ['levyEff', 'Levy efficiency', 'pct', 'Levies fight at 75% against regulars: they deal ×F and take ÷F, F = min(1, 0.75 × (1 + this)).'],
    ['initiativeMod', 'Army initiative', 'pct', 'Multiplies every unit\'s initiative.'],
    ['speedMod', 'Combat speed', 'pct', 'Multiplies how fast reserves move up.'],
    ['frontageMod', 'Frontage', 'pct', 'Widens every battle section.'],
    ['combinedPerType', 'Combined arms', 'pct', 'Bonus damage per category beyond the first with 10%+ of the regiments (auxiliaries don\'t count); none if one category is half the army. Base 2.5%.'],
  ];
  const r2 = (v: number) => Math.round(v * 100) / 100;

  // battlefield
  const field = $derived.by(() => {
    if (!D || !B) return null;
    const topo = D.topography.find(t => t.id === B!.topography), veg = D.vegetation.find(t => t.id === B!.vegetation), rank = D.ranks.find(t => t.id === B!.rank);
    const raw = D.baseFrontage + (topo?.front ?? 0) + (veg?.front ?? 0) + (rank?.front ?? 0);
    const K = D.defines;
    const dice = -(topo?.dice ?? 0) - (veg?.dice ?? 0) + (B.river ? K.RIVER_CROSSING_DICE : 0) + (B.strait ? K.STRAIT_CROSSING_DICE : 0) + (B.landing ? K.SEA_LANDING_DICE : 0);
    return { front: Math.max(K.MIN_FRONTAGE_AFTER_TERRAIN, raw), dice, topo, veg, rank };
  });

  // ---- sample battle chart ----------------------------------------------------------------------------------------------
  const ATT = '#e48a5c', DEF = '#82bde6';
  let cw = $state(760), hov = $state<number | null>(null);
  const PAD = { l: 52, r: 16, t: 24, men: 150, gap: 40, mor: 84, b: 26 };
  const CH_H = PAD.t + PAD.men + PAD.gap + PAD.mor + PAD.b;
  const chart = $derived.by(() => {
    const log = result?.sample;
    if (!log) return null;
    const pts: { att: SideState; def: SideState; da?: number; dd?: number }[] = [log.start, ...log.daily.map(x => ({ att: x.att, def: x.def, da: x.diceAtt, dd: x.diceDef }))];
    // the engine logs the last day before the wipe/retreat; fold that into the final point so it matches the losses
    const end = pts.at(-1)!;
    if (pts.length > 1) pts[pts.length - 1] = { ...end, att: { ...end.att, men: Math.max(0, log.start.att.men - log.losses.att) }, def: { ...end.def, men: Math.max(0, log.start.def.men - log.losses.def) } };
    const days = pts.length - 1, pw = Math.max(50, cw - PAD.l - PAD.r);
    const step = (m: number) => { const r = m / 4, p = 10 ** Math.floor(Math.log10(r || 1)); return [1, 2, 2.5, 5, 10].map(x => x * p).find(x => x >= r) ?? p * 10; };
    const menStep = step(Math.max(pts[0].att.men, pts[0].def.men, 1)), menMax = Math.ceil(Math.max(pts[0].att.men, pts[0].def.men, 1) / menStep) * menStep;
    const morMax = Math.max(1, Math.ceil(Math.max(pts[0].att.maxMorale, pts[0].def.maxMorale) * 2) / 2);
    const x = (i: number) => PAD.l + (days ? i / days : 0.5) * pw;
    const ym = (v: number) => PAD.t + PAD.men * (1 - v / menMax);
    const y0 = PAD.t + PAD.men + PAD.gap, yo = (v: number) => y0 + PAD.mor * (1 - v / morMax);
    const path = (f: (p: typeof pts[0]) => number, y: (v: number) => number) => pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(f(p)).toFixed(1)}`).join('');
    const dstep = [1, 2, 5, 10, 20, 50, 100].find(s => days / s <= 10) ?? 100;
    return {
      pts, days, x, ym, yo, y0, pw,
      menAtt: path(p => p.att.men, ym), menDef: path(p => p.def.men, ym), morAtt: path(p => p.att.morale, yo), morDef: path(p => p.def.morale, yo),
      menTicks: Array.from({ length: Math.round(menMax / menStep) + 1 }, (_, i) => i * menStep), morTicks: [0, morMax / 2, morMax],
      dayTicks: Array.from({ length: Math.floor(days / dstep) + 1 }, (_, i) => i * dstep).filter(d => d <= days - dstep * 0.6),
      bombard: log.notes.some(n => n.startsWith('Bombard')) ? D!.defines.BOMBARD_DAYS : 0,
    };
  });
  function hover(e: PointerEvent) {
    if (!chart) return;
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    hov = Math.max(0, Math.min(chart.days, Math.round((e.clientX - r.left - PAD.l) / chart.pw * chart.days)));
  }
  const winner = (w: string) => w === 'att' ? 'the attacker' : w === 'def' ? 'the defender' : 'neither side';
</script>

<svelte:window onpointerdown={closePick} onkeydown={e => { if (e.key === 'Escape') pick = null; }} />

<!-- ================= snippets ================= -->
{#snippet flag(t: string)}<span class="fl"><img src="flags/{t}.png" alt="" onerror={e => e.currentTarget.remove()}></span>{/snippet}

{#snippet clause(c: WhoItem)}
  {#if c.parts}
    <span class="og">{#if c.not}<span class="or">none of</span>{/if}
      {#each c.parts as p, i}{#if i}<span class="or">{c.type === 'any' ? 'or' : 'and'}</span>{/if}{@render clause(p)}{/each}</span>
  {:else}
    {@const names = (c as WhoItem & { names?: string[] }).names ?? c.ids ?? []}
    <span class="cl" class:not={c.not}>
      {#if c.type !== 'other'}<span class="tl">{c.not ? 'not ' : ''}{c.cap ? 'capital in ' : ''}{c.type.replace(/_/g, ' ')}</span>{:else if c.not}<span class="tl">not</span>{/if}
      {#each c.ids ?? [] as t, k}
        {#if c.type === 'tag'}<a class="chip nat" href="#n/{t}">{@render flag(t)}{names[k]}</a>
        {:else}<span class="tag big">{names[k]}</span>{/if}
      {/each}
    </span>
  {/if}
{/snippet}

{#snippet who(u: Unit)}
  {#if u.who.length}{#each u.who as c}<div class="wrow">{@render clause(c)}</div>{/each}
  {:else}<p>Every country can recruit it once it is unlocked.</p>{/if}
{/snippet}

{#snippet cond(u: Unit)}{#if fitOf(u) === 'maybe'}<span class="cond" title={COND}>conditional</span>{/if}{/snippet}

{#snippet signed(v: number, good: number, f: (v: number) => string)}
  {#if v}<span class:up={v * good > 0} class:down={v * good < 0}>{f(v)}</span>{:else}<span class="zero">·</span>{/if}
{/snippet}

{#snippet terrain(u: Unit, max = 99)}
  {@const ts = terrainOf(u)}
  {#each ts.slice(0, max) as [k, v]}<span class="tp" class:up={v > 0} class:down={v < 0} class:nosim={!simTerrain(k)}
    title="{pct(v)} damage done in {TNAME[k] ?? k}{simTerrain(k) ? '' : ' (not part of the simulator)'}">{pct(v)} {TNAME[k] ?? k}</span>{/each}
  {#if ts.length > max}<span class="tag">+{ts.length - max}</span>{/if}
{/snippet}

{#snippet scopeNote()}
  {#if SCOPE.ctx && D}
    <p class="meta scopenote">Viewing as {@render flag(SCOPE.ctx.tag)}<b>{SCOPE.name}</b>: {nHidden} of {D.units.length} units hidden because it can't recruit them{#if nMaybe}, {nMaybe} marked <span class="cond" title={COND}>conditional</span>{/if}.</p>
  {/if}
{/snippet}

{#snippet modeSwitch()}
  <div class="pfb mode"><a class:on={!isBattle} href="#u">Units</a><a class:on={isBattle} href="#u/battle">Battle simulator</a></div>
{/snippet}

{#snippet sidePanel(w: Side)}
  {@const c = B![w]}
  {@const st = stats?.[w]}
  {@const lv = quick(c, 'levy')}
  {@const rg = quick(c, 'heavy_infantry')}
  <div class="side {w}">
    <div class="shead">
      <h3>{w === 'att' ? 'Attacker' : 'Defender'}</h3>
      <div class="agepick" title="Pre-fills the age's generic advances below and moves generic regiments to that age's units">
        {#each AGES as a}<button class:on={c.age === a} onclick={() => setAge(c, a)} title={ageName(a)}>{ROMAN[a]}</button>{/each}
      </div>
    </div>
    <div class="focus"><span class="flbl">Age focus</span>
      {#each FOCUS as [f, l]}<button class:on={c.focus === f} onclick={() => setFocus(c, f)} title={f ? `Adds the ${l} focus advances of ${ageName(c.age)} and earlier` : 'Generic advances only'}>{l}</button>{/each}
    </div>
    {#if st}
      <div class="ro">
        <div title="Men in all regiments at full strength"><span>Men</span><b>{men(st.men)}</b></div>
        <div title="{st.front} deploy on the front ({st.sections.left} left, {st.sections.center} centre, {st.sections.right} right), {st.reserve} wait in reserve"><span>Regiments</span><b>{st.regiments}</b><i>{st.reserve ? `${st.reserve} in reserve` : 'all on the front'}</i></div>
        <div title="Width of each of the three sections; deployment can overstack it by 25%"><span>Frontage</span><b>{num(r2(st.frontage))}</b><i>per section</i></div>
        <div title="Average maximum morale over the regiments"><span>Morale</span><b>{st.maxMorale.toFixed(2)}</b></div>
        <div title="Regulars / levies (levies get −20%)"><span>Discipline</span><b>{pct(st.discipline)}</b><i>levies {pct(st.levyDiscipline)}</i></div>
        <div title="Added to every 0-9 roll on top of the base 5: general, traits, and for the attacker terrain and crossings"><span>Dice</span><b class:up={st.diceMod > 0} class:down={st.diceMod < 0}>{st.diceMod ? snum(st.diceMod) : '±0'}</b><i>tactics {num(r2(st.tactics))}</i></div>
      </div>
    {/if}

    <section class="card"><h4>Regiments<small>{c.regs.reduce((t, r) => t + r.n, 0)} regiments · {men(c.regs.reduce((t, r) => t + menOf(r), 0))} men</small></h4>
      {#each c.regs as r, i (i)}
        {@const u = U.get(r.unit)}
        <div class="reg">
          <button class="pickbtn" onclick={() => openPick(w, i)} title="Change the unit">
            {#if u}<img class="thumb" src={art(u)} alt="" loading="lazy"><span class="rn">{u.name}{#if u.levy}<span class="lv">levy</span>{/if}</span><span class="tag">{ROMAN[u.age]}</span>{/if}
          </button>
          <span class="step">
            <button onclick={e => r.n = Math.max(0, r.n - (e.shiftKey ? 5 : 1))} title="One fewer (shift: five)" aria-label="Fewer">−</button>
            <input type="number" min="0" max="999" bind:value={r.n} aria-label="Regiments">
            <button onclick={e => r.n = Math.min(999, r.n + (e.shiftKey ? 5 : 1))} title="One more (shift: five)" aria-label="More">+</button>
          </span>
          <span class="rm">{kmen(menOf(r))}</span>
          <button class="x" onclick={() => c.regs.splice(i, 1)} title="Remove" aria-label="Remove">×</button>
          {#if pick?.w === w && pick.i === i}{@render picker()}{/if}
        </div>
      {:else}<p class="none">No regiments yet.</p>{/each}
      <div class="adds">
        {#if lv}<button onclick={() => addRegs(c, lv.id, 5)} title="Five regiments of {lv.name}, the generic levy of Age {ROMAN[c.age]}">+5 levies</button>{/if}
        {#if rg}<button onclick={() => addRegs(c, rg.id, 5)} title="Five regiments of {rg.name}, the generic heavy infantry of Age {ROMAN[c.age]}">+5 regulars</button>{/if}
        <span class="pickwrap"><button class="pickbtn other" onclick={() => openPick(w, -1)}>+ Other unit…</button>
          {#if pick?.w === w && pick.i === -1}{@render picker()}{/if}</span>
      </div>
    </section>

    <section class="card"><h4>General<small>{c.genOn ? `${c.gen.adm} / ${c.gen.dip} / ${c.gen.mil}` : 'none'}</small></h4>
      <label class="tgl on1"><input type="checkbox" bind:checked={c.genOn}> Led by a general</label>
      {#if c.genOn && D}
        {#each [['adm', 'Administrative'], ['dip', 'Diplomatic'], ['mil', 'Military']] as [k, l] (k)}
          {@const key = k as 'adm' | 'dip' | 'mil'}
          {@const eff = Object.entries(D.general[key] ?? {}).filter(([m]) => m in ML && !m.includes('recovery')).map(([m, v]) => modTxt(m, v * c.gen[key]))}
          <div class="abil"><span class="flbl">{l}</span><input type="range" min="0" max="100" bind:value={c.gen[key]}><b>{c.gen[key]}</b>
            <span class="eff">{eff.join(', ') || 'no combat effect'}</span></div>
        {/each}
        {#each [['general', 'General traits'], ['ruler', 'Ruler traits, when the ruler leads']] as [k, l] (k)}
          <div class="flbl tr">{l}</div>
          <div class="traits">{#each D.traits.filter(t => t.kind === k) as t (t.id)}
            <button class:on={c.gen.traits.includes(t.id)} onclick={() => c.gen.traits = toggle(c.gen.traits, t.id)} title={mods(t.mods)}>{t.name}</button>{/each}</div>
        {/each}
      {/if}
    </section>

    <details class="advm">
      <summary>Advanced modifiers<span class="meta">pre-filled from Age {ROMAN[c.age]}{c.focus ? ` and ${FOCUS.find(f => f[0] === c.focus)?.[1]} focus` : ''}</span></summary>
      <div class="mgrid">
        {#each ADVM as [k, l, kind, t] (k)}
          <label title={t}><span>{l}</span>
            {#if kind === 'pct'}<input type="number" step="1" bind:value={() => r2(c.m[k] * 100), v => c.m[k] = (+v || 0) / 100}><i>%</i>
            {:else if kind === 'int'}<input type="number" min="0" max="100" step="1" bind:value={() => c.m[k], v => c.m[k] = Math.max(0, Math.min(100, Math.round(+v || 0)))}><i></i>
            {:else}<input type="number" step="0.05" bind:value={() => r2(c.m[k]), v => c.m[k] = +v || 0}><i></i>{/if}
          </label>
        {/each}
        {#each CATS as cat (cat)}
          <label title="army_{cat}_power: multiplies the combat power of {CATN[cat].toLowerCase()}"><span><img src={catIc(cat)} alt="">{CATN[cat]} power</span>
            <input type="number" step="1" bind:value={() => r2((c.m.catPower[cat] ?? 0) * 100), v => c.m.catPower[cat] = (+v || 0) / 100}><i>%</i></label>
        {/each}
        <label class="wide" title="How regiments are spread over the left, centre and right sections"><span>Formation</span>
          <select bind:value={c.m.formation}><option value="balanced_army">Balanced</option><option value="cav_inf_cav">Cavalry on the flanks</option></select></label>
      </div>
    </details>
  </div>
{/snippet}

{#snippet picker()}
  <div class="picker" role="dialog" aria-label="Pick a unit">
    <input class="nfilter" placeholder="Find a unit, culture, country…" bind:value={pq} autocomplete="off" {@attach el => el.focus()}
      onkeydown={e => { if (e.key === 'Enter' && pickList[0]?.list[0]) choose(pickList[0].list[0].id); }}>
    <div class="plist">
      {#each pickList as g (g.key)}
        <div class="pcat">{#if g.c}<img src={catIc(g.c)} alt="">{:else if SCOPE.ctx}{@render flag(SCOPE.ctx.tag)}{/if}{g.label}</div>
        {#each g.list as u (u.id)}
          <button class="pu" class:gone={fitOf(u) === 'no'} onclick={() => choose(u.id)} title={u.whoText || 'Everyone'}>
            <img class="thumb" src={art(u)} alt="" loading="lazy"><span class="rn">{u.name}{#if u.levy}<span class="lv">levy</span>{/if}</span>
            {#if SCOPE.ctx && fitOf(u) === 'no'}<i>not {SCOPE.ctx.tag}</i>{:else if u.unique}<i>unique</i>{/if}<span class="tag">{ROMAN[u.age]}</span></button>
        {/each}
      {:else}<p class="none">No unit matches.</p>{/each}
    </div>
  </div>
{/snippet}

<!-- ================= page ================= -->
<div class="layout">
  <aside bind:this={sideEl}>
    {#if isBattle}
      <h3>Battle simulator</h3>
      {@render modeSwitch()}
      {#if B && D && field}
        <h3>Topography</h3>
        <div class="modes tsel">{#each D.topography as t (t.id)}<button class:on={B.topography === t.id} onclick={() => B!.topography = t.id}
          title="Attacker dice {t.dice ? '−' + t.dice : '±0'}, section width {t.front ? t.front : '±0'}">{t.name}<i>{t.dice ? `−${t.dice} die` : ''}{t.dice && t.front ? ' · ' : ''}{t.front ? `${t.front} width` : ''}</i></button>{/each}</div>
        <h3>Vegetation</h3>
        <div class="modes tsel">{#each D.vegetation as t (t.id)}<button class:on={B.vegetation === t.id} onclick={() => B!.vegetation = t.id}
          title="Attacker dice {t.dice ? '−' + t.dice : '±0'}, section width {t.front ? t.front : '±0'}">{t.name}<i>{t.dice ? `−${t.dice} die` : ''}{t.dice && t.front ? ' · ' : ''}{t.front ? `${t.front} width` : ''}</i></button>{/each}</div>
        <h3>Location</h3>
        <div class="pfb">{#each D.ranks as r (r.id)}<button class:on={B.rank === r.id} onclick={() => B!.rank = r.id} title="Section width {r.front || '±0'}">{r.name}</button>{/each}</div>
        <div class="toggles">
          <label class="tgl" title="Attacker dice {D.defines.RIVER_CROSSING_DICE}; units' river modifiers apply to both sides"><input type="checkbox" bind:checked={B.river}> River crossing</label>
          <label class="tgl" title="Attacker dice {D.defines.STRAIT_CROSSING_DICE}"><input type="checkbox" bind:checked={B.strait}> Strait</label>
          <label class="tgl" title="Attacker dice {D.defines.SEA_LANDING_DICE}"><input type="checkbox" bind:checked={B.landing}> Sea landing</label>
        </div>
        <p class="meta fsum">Each section holds <b>{field.front}</b> width{field.front !== D.baseFrontage ? ` (open ground ${D.baseFrontage})` : ''}. Terrain and crossings give the attacker <b class:down={field.dice < 0}>{field.dice ? snum(field.dice) : '±0'}</b> on every roll.</p>

        <h3>Dice</h3>
        <div class="pfb"><button class:on={B.dice === 'random'} onclick={() => B!.dice = 'random'}>Random</button><button class:on={B.dice === 'fixed'} onclick={() => B!.dice = 'fixed'}>Fixed</button></div>
        {#if B.dice === 'fixed'}
          {#each [['att', 'Attacker'], ['def', 'Defender']] as [w, l] (w)}
            {@const s = w as Side}
            <div class="fixed {s}"><span class="flbl">{l}</span>{#each Array(10) as _, v}<button class:on={B.fixed[s] === v} onclick={() => B!.fixed[s] = v}>{v}</button>{/each}</div>
          {/each}
          <p class="meta">Every phase uses this roll (0-9), before the base {D.defines.COMBAT_BASE} and modifiers.</p>
        {:else}<p class="meta">A new 0-9 roll per side every {D.defines.DAYS_PER_PHASE} days.</p>{/if}

        <h3>Battles to run</h3>
        <div class="pfb">{#each [100, 1000, 5000] as n (n)}<button class:on={B.iters === n} onclick={() => B!.iters = n}>{n.toLocaleString('en')}</button>{/each}</div>
        <div class="acts">
          <button onclick={swap} title="Attacker and defender trade places">⇄ Swap sides</button>
          <button onclick={() => B!.seed = newSeed()} title="Same setup, a fresh set of random battles">Re-roll</button>
          <button onclick={reset} title="Back to the starting setup">Reset</button>
        </div>
        <p class="meta">The setup is saved in this browser.</p>
      {:else}<p class="meta">Loading…</p>{/if}
    {:else}
      <h3>Units</h3>
      {@render modeSwitch()}
      {@render scopeNote()}
      <input class="nfilter" placeholder="Find a unit, culture, country…" bind:value={q} autocomplete="off">
      {#if D}
        <div class="pfl">Category</div>
        <div class="cats">{#each CATS as c (c)}<button class:on={cats.includes(c)} onclick={() => cats = toggle(cats, c)} title="{catN(c)} units"><img src={catIc(c)} alt="">{CATN[c]}</button>{/each}</div>
        <div class="pfl">Age</div>
        <div class="agepick">{#each AGES as a (a)}<button class:on={ages.includes(a)} onclick={() => ages = toggle(ages, a)} title={ageName(a)}>{ROMAN[a]}</button>{/each}</div>
        <div class="pfl">Raised as</div>
        <div class="pfb">{#each [['', 'Any'], ['regular', 'Regulars'], ['levy', 'Levies']] as [k, l] (k)}<button class:on={kind === k} onclick={() => kind = k}
          title={k === 'levy' ? 'Raised from pops for free; −20% discipline and 75% efficiency against regulars' : k ? 'Recruited and paid for' : ''}>{l}</button>{/each}</div>
        <div class="pfl">Kind</div>
        <div class="pfb">{#each [['', 'Any'], ['generic', 'Generic'], ['unique', 'Unique']] as [k, l] (k)}<button class:on={origin === k} onclick={() => origin = k}
          title={k === 'generic' ? 'The standard unit line every country gets' : k ? 'Tied to a country, culture, religion or region' : ''}>{l}</button>{/each}</div>
        <div class="pfl">Available to</div>
        <div class="pfb">{#each AVAIL as [k, l] (k)}<button class:on={avail === k} onclick={() => avail = k}>{l}<span class="n">{availN[k]}</span></button>{/each}</div>
        <div class="blist">
          <a href="#u" class:on={!id}>Overview<span class="tag up-tag">{shown.length}</span></a>
          {#each sideList as g (g.c)}
            <h3><span><img class="hic" src={catIc(g.c)} alt="">{CATN[g.c]}</span><span class="cnt">{g.list.length}</span></h3>
            {#each g.list as u (u.id)}
              <a href="#u/{u.id}" class:on={id === u.id} class:dim={fitOf(u) === 'maybe'}><span class="nm">{u.name}</span>{#if u.levy}<span class="lv">levy</span>{/if}{#if u.unique}<span class="dot" title={u.whoText}></span>{/if}<span class="tag up-tag">{ROMAN[u.age]}</span></a>
            {/each}
          {:else}<p class="meta">No unit matches.</p>{/each}
        </div>
      {:else}<p class="meta">Loading units…</p>{/if}
    {/if}
  </aside>

  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
  <main bind:this={mainEl} onclick={toggleCard}>{#key id}<div class="enter">
    {#if !D}
      <p class="meta">Loading units…</p>
    {:else if isBattle}
      <!-- ================= simulator ================= -->
      <div class="title"><div><h2>Land battle simulator</h2>
        <p class="desc">Pick two armies, a general and the ground, and the page fights the battle {B ? B.iters.toLocaleString('en') : ''} times with the game's dice and damage rules. Regiments come from the
          unit browser (every unit page has an <b>Add to battle</b> button) or the pickers below. The age buttons fill in that age's generic advances; open <i>Advanced modifiers</i> to change them.</p>
        <details class="how"><summary>How this is calculated, and what is approximated</summary>
          <p>The results are <b>estimates</b> built from the game's unit files and combat defines, not the game itself. The engine is compiled code, so the parts below are
            reconstructed from defines, localisation and the wiki, and may differ from what the game does.</p>
          <ul class="tips">{#each APPROX as a}<li>{a}</li>{/each}</ul>
        </details>
      </div></div>

      {#if B}
        <div class="verdict" class:busy>
          {#if result && ready}
            <div class="vnum att"><b>{Math.round(result.attWin * 100)}%</b><span>attacker wins</span></div>
            <div class="vbar" title="Out of {result.n.toLocaleString('en')} battles: attacker {pct(result.attWin).slice(1)}, draw {pct(result.draw).slice(1)}, defender {pct(result.defWin).slice(1)}">
              <span class="a" style:width="{result.attWin * 100}%"></span><span class="d" style:width="{result.draw * 100}%"></span><span class="b" style:width="{result.defWin * 100}%"></span>
            </div>
            <div class="vnum def"><b>{Math.round(result.defWin * 100)}%</b><span>defender wins</span></div>
            <div class="vmeta">{result.draw ? `${pct(result.draw).slice(1)} draws · ` : ''}{result.n.toLocaleString('en')} battles · {result.days.avg.toFixed(1)} days on average</div>
          {:else if !ready}<p class="meta">Give both sides at least one regiment.</p>
          {:else if err}<p class="meta">The simulation failed: {err}</p>
          {:else}<p class="meta">Simulating…</p>{/if}
          {#if busy}<span class="spin" title="Simulating">Simulating…</span>{/if}
        </div>

        <div class="sides">
          {@render sidePanel('att')}
          <div class="vs" aria-hidden="true">VS</div>
          {@render sidePanel('def')}
        </div>

        {#if result && ready}
          {@const s = result.sample}
          <div class="rgrid">
            <section class="card"><h4 class="gold">Outcome<small>over {result.n.toLocaleString('en')} battles</small></h4>
              <table class="ptab res">
                <thead><tr><th></th><th class="n">Average</th><th class="n">Fewest</th><th class="n">Most</th></tr></thead>
                <tbody>
                  <tr><td>Days</td><td class="n">{result.days.avg.toFixed(1)}</td><td class="n">{result.days.min}</td><td class="n">{result.days.max}</td></tr>
                  <tr><td class="ca">Attacker losses</td><td class="n">{men(result.losses.att.avg)}</td><td class="n">{men(result.losses.att.min)}</td><td class="n">{men(result.losses.att.max)}</td></tr>
                  <tr><td class="cd">Defender losses</td><td class="n">{men(result.losses.def.avg)}</td><td class="n">{men(result.losses.def.min)}</td><td class="n">{men(result.losses.def.max)}</td></tr>
                </tbody>
              </table>
              {#if stats}<p class="meta">On average the attacker loses <b class="ca">{Math.round(result.losses.att.avg / Math.max(1, stats.att.men) * 100)}%</b> of its {men(stats.att.men)} men
                and the defender <b class="cd">{Math.round(result.losses.def.avg / Math.max(1, stats.def.men) * 100)}%</b> of its {men(stats.def.men)}. Losses count the dead and the 10% lost in a retreat.</p>{/if}
            </section>
            <section class="card"><h4 class="gold">A typical battle<small>the run closest to the median length: {s.days} days, won by {winner(s.winner)}</small></h4>
              <div class="legend"><span class="ca">— Attacker</span><span class="cd">— Defender</span><span class="meta">hover for the day's numbers</span></div>
              <div class="chart" bind:clientWidth={cw}>
                {#if chart}
                  {@const c = chart}
                  <svg width={cw} height={CH_H} role="img" aria-label="Men and morale of both sides, day by day" onpointermove={hover} onpointerleave={() => hov = null}>
                    {#if c.bombard}<rect x={c.x(0)} y={PAD.t} width={c.x(Math.min(c.bombard, c.days)) - c.x(0)} height={PAD.men + PAD.gap + PAD.mor} class="bomb" /><text x={c.x(0) + 4} y={CH_H - PAD.b - 4} class="bl">bombard</text>{/if}
                    <text x={PAD.l} y={PAD.t - 10} class="pl">Men</text>
                    {#each c.menTicks as v}<line x1={PAD.l} x2={PAD.l + c.pw} y1={c.ym(v)} y2={c.ym(v)} class="grid" /><text x={PAD.l - 6} y={c.ym(v) + 4} class="yl">{kmen(v)}</text>{/each}
                    <text x={PAD.l} y={c.y0 - 10} class="pl">Morale</text>
                    {#each c.morTicks as v}<line x1={PAD.l} x2={PAD.l + c.pw} y1={c.yo(v)} y2={c.yo(v)} class="grid" /><text x={PAD.l - 6} y={c.yo(v) + 4} class="yl">{num(v)}</text>{/each}
                    {#each c.dayTicks as d}<text x={c.x(d)} y={CH_H - 8} class="xl">{d}</text>{/each}
                    <text x={PAD.l + c.pw} y={CH_H - 8} class="xl end">day {c.days}</text>
                    <path d={c.menAtt} stroke={ATT} class="ln" /><path d={c.menDef} stroke={DEF} class="ln" />
                    <path d={c.morAtt} stroke={ATT} class="ln" /><path d={c.morDef} stroke={DEF} class="ln" />
                    {#if hov !== null}
                      {@const p = c.pts[hov]}
                      <line x1={c.x(hov)} x2={c.x(hov)} y1={PAD.t} y2={c.y0 + PAD.mor} class="cross" />
                      <circle cx={c.x(hov)} cy={c.ym(p.att.men)} r="4" fill={ATT} /><circle cx={c.x(hov)} cy={c.ym(p.def.men)} r="4" fill={DEF} />
                      <circle cx={c.x(hov)} cy={c.yo(p.att.morale)} r="4" fill={ATT} /><circle cx={c.x(hov)} cy={c.yo(p.def.morale)} r="4" fill={DEF} />
                    {/if}
                  </svg>
                  {#if hov !== null}
                    {@const p = c.pts[hov]}
                    <div class="ctip" style:left="{c.x(hov)}px" class:flip={c.x(hov) > cw * 0.6}>
                      <b>{hov ? `Day ${hov}` : 'Start'}</b>
                      <table><tbody>
                        <tr><td></td><td class="ca">Attacker</td><td class="cd">Defender</td></tr>
                        <tr><td>Men</td><td>{men(p.att.men)}</td><td>{men(p.def.men)}</td></tr>
                        <tr><td>Morale</td><td>{p.att.morale.toFixed(2)}</td><td>{p.def.morale.toFixed(2)}</td></tr>
                        <tr><td>Fighting</td><td>{p.att.front}<i> +{p.att.reserve}</i></td><td>{p.def.front}<i> +{p.def.reserve}</i></td></tr>
                        <tr><td>Broken</td><td>{p.att.broken}</td><td>{p.def.broken}</td></tr>
                        {#if p.da !== undefined}<tr><td>Dice</td><td>{p.da}</td><td>{p.dd}</td></tr>{/if}
                      </tbody></table>
                    </div>
                  {/if}
                {/if}
              </div>
              <p class="meta">Men count every regiment, broken ones too; morale is the average over regiments still fighting. Dice are the effective rolls after the base {D.defines.COMBAT_BASE} and modifiers. "Fighting" is regiments at the front, plus those in reserve.</p>
              {#if s.notes.length}<ul class="notes">{#each s.notes as n}<li>{n}</li>{/each}</ul>{/if}
            </section>
          </div>
        {/if}
      {/if}

    {:else if id && !unit}
      <div class="title"><div><h2>Unknown unit</h2><p class="desc">There is no land unit called "{id}". <a class="chip" href="#u">Back to the units</a></p></div></div>

    {:else if unit}
      <!-- ================= one unit ================= -->
      {@const u = unit}
      {#if SCOPE.ctx && fitOf(u) !== 'yes'}
        <p class="scopebanner" class:no={fitOf(u) === 'no'}>{#if fitOf(u) === 'no'}Not available to {@render flag(SCOPE.ctx.tag)}<b>{SCOPE.name}</b>: its conditions rule this nation out. It is hidden from your lists and shown here because you opened it directly.
          {:else}Conditional for {@render flag(SCOPE.ctx.tag)}<b>{SCOPE.name}</b>: {COND.replace('Conditional: ', '')}{/if}</p>
      {/if}
      <div class="title unit">
        <span class="uart big"><img src={art(u)} alt=""></span>
        <div><h2>{u.name}</h2>
          <div class="meta"><span><img class="hic" src={catIc(u.cat)} alt="">{CATN[u.cat]}</span><span>{ageName(u.age)}</span><span>{u.levy ? 'Levy' : 'Regular'}</span><span>{u.unique ? 'Unique' : 'Generic'}</span>
            {#if !u.levy && !u.buildable}<span>not recruitable directly</span>{/if}</div>
          {#if u.desc}<p class="desc">{u.desc}</p>{/if}
          <div class="addb"><span class="flbl">Add to battle</span>
            {#each [['att', 'Attacker'], ['def', 'Defender']] as [w, l] (w)}
              {@const s = w as Side}
              <button class="ab {s}" onclick={() => B && addRegs(B[s], u.id, 1)} title="Add one regiment of {u.name} to the {l.toLowerCase()}">+ {l}{#if inBattle(s, u.id)}<b>{inBattle(s, u.id)}</b>{/if}</button>
            {/each}
            {#if B && (inBattle('att', u.id) || inBattle('def', u.id))}<a class="chip go" href="#u/battle">Open the simulator →</a>{/if}
          </div>
        </div>
        <a class="chip back" href="#u">All units</a>
      </div>

      <div class="ncols">
        <div>
          <section class="card"><h4 class="out">Combat stats<small>{cmpTo ? `compared with ${cmpTo.name}, the generic ${CATN[u.cat].toLowerCase()} of Age ${ROMAN[u.age]}` : 'hover a stat for what it does'}</small></h4>
            {#each STATS.filter(s => s.k !== 'bombard' || u.bombard !== undefined) as s (s.k)}
              {@const v = u[s.k] ?? 0}
              {@const dv = cmpTo ? r2((v - (cmpTo[s.k] ?? 0)) * 1000) / 1000 : 0}
              <div class="srow"><span class="term" title={s.t}>{s.l}</span><b>{s.f(v)}</b>
                <span class="dv">{#if dv}{@render signed(dv, s.good, s.k === 'str' ? x => `${sign(x)}${men(Math.abs(x) * 1000)}` : ['secure', 'sdd', 'sdt', 'mdd', 'mdt', 'bombard'].includes(s.k) ? pct : snum)}{/if}</span></div>
            {/each}
            <div class="srow"><span class="term" title="Combined arms: an army with several categories (each 10%+ of it, none half or more) deals bonus damage. Auxiliaries never count.">Combined arms</span><b>{u.combinedArms ? 'counts' : 'excluded'}</b><span></span></div>
            {#if u.levy}<p class="meta lnote"><b>Levy:</b> raised from pops instead of recruited. In battle levies get −20% discipline and fight regulars at 75% efficiency (levy combat efficiency raises it).</p>{/if}
          </section>
          <section class="card"><h4 class="pop">Terrain<small>damage it deals on this ground</small></h4>
            {#if terrainOf(u).length}<div class="tps">{@render terrain(u)}</div>
              <p class="meta">Topography, vegetation and river crossings feed the simulator; climate and coast do not.</p>
            {:else}<p class="none">No terrain modifiers: it fights the same everywhere.</p>{/if}
          </section>
          {#if line.length > 1 || otherPreds.length}
            <section class="card"><h4 class="gold">Upgrade line<small>{u.levy ? 'levies are replaced by the next age\'s levy, not upgraded' : 'what it upgrades from and to'}</small></h4>
              <div class="uline">{#each line as x, i (x.id)}{#if i}<span class="arrow">→</span>{/if}
                <a class="ucard" class:cur={x.id === u.id} href="#u/{x.id}"><span class="uart"><img src={art(x)} alt="" loading="lazy"></span><span class="un2"><b>{x.name}</b><span class="tag">{ROMAN[x.age]}</span></span></a>{/each}</div>
              {#if otherPreds.length}<div class="wline"><span class="flbl">Also upgraded from</span>{#each otherPreds as p (p.id)}<a class="chip" href="#u/{p.id}">{p.name}</a>{/each}</div>{/if}
            </section>
          {/if}
        </div>
        <div>
          <section class="card"><h4 class="pop">Who can recruit it<small>{u.who.length ? 'all of these must hold' : 'everyone'}</small></h4>{@render who(u)}</section>
          <section class="card"><h4 class="in">How it unlocks</h4>
            {#if u.unlock?.length}<div class="chips">{#each u.unlock as a (a.id)}<a class="chip adv" href="#r/{a.id}">{#if ADV[a.id]?.icon}<img class="ic" src="icons/advances/{ADV[a.id].icon}.png" alt="" loading="lazy">{/if}{a.name}</a>{/each}</div>
              <p class="meta">{u.levy ? 'Researching it makes this the levy pops raise' : 'Researching it lets you recruit the unit'}{u.unlock.length > 1 ? ' (any one of these)' : ''}.</p>
            {:else}<p class="none">No advance unlocks it: it comes from an event, a decision or a special rule.</p>{/if}
          </section>
          {#if kin.length}
            <section class="card"><h4 class="gold">Other {CATN[u.cat].toLowerCase()} of Age {ROMAN[u.age]}<small>{kin.length}</small></h4>
              <div class="chips">{#each kin as k (k.id)}<a class="chip" class:gen={!k.unique} href="#u/{k.id}" title={k.whoText || 'Everyone'}>{k.name}{#if k.levy}<span class="lv">levy</span>{/if}</a>{/each}</div>
            </section>
          {/if}
        </div>
      </div>

    {:else}
      <!-- ================= overview ================= -->
      <div class="title"><div><h2>Units</h2>
        <p class="desc">{#if SCOPE.ctx}The {vis.length} land units open to {SCOPE.name} (of {D.units.length}){:else}All {D.units.length} land units in the game{/if}, in six categories. Every age brings a generic line
          that any country can recruit, plus unique units tied to a country, culture, religion or region. <b>Levies</b> are raised from pops for free but fight worse; <b>regulars</b> are recruited and paid for.
          Click a column to sort; open a unit for what every stat does, or try it in the <a class="lnk" href="#u/battle">battle simulator</a>.</p>
        {@render scopeNote()}
        <div class="wline"><span class="flbl">View</span><span class="pfb"><button class:on={!cards} onclick={() => cards = false}>Table</button><button class:on={cards} onclick={() => cards = true}>Cards</button></span>
          <span class="meta">{shown.length} shown</span></div>
      </div></div>

      {#each groups as g (g.c)}
        <section class="card"><h4 class="gold"><span class="h4i"><img src={catIc(g.c)} alt="">{CATN[g.c]}</span><small>{g.list.length} units</small></h4>
          {#if cards}
            <div class="ucards">{#each g.list as u (u.id)}
              <a class="ucard2" href="#u/{u.id}">
                <span class="uart"><img src={art(u)} alt="" loading="lazy"><span class="age">{ROMAN[u.age]}</span>{#if u.levy}<span class="lvb">Levy</span>{/if}</span>
                <b>{u.name}{@render cond(u)}</b>
                <span class="ul">{men(u.str * 1000)} men · CP {num(u.cp)} · init {num(u.init)} · speed {num(u.speed)}</span>
                <span class="uw">{u.whoText || 'Everyone'}</span>
              </a>
            {/each}</div>
          {:else}
            <div class="tw"><table class="ptab utab">
              <thead><tr>
                <th><button class:on={sortK === 'name'} onclick={() => sortBy('name')}>Unit{sortK === 'name' ? (sortD > 0 ? ' ▲' : ' ▼') : ''}</button></th>
                {#each COLS as [k, l, t] (k)}<th class="n"><button class:on={sortK === k} onclick={() => sortBy(k)} title={t}>{l}{sortK === k ? (sortD > 0 ? ' ▲' : ' ▼') : ''}</button></th>{/each}
                <th>Terrain</th>
              </tr></thead>
              <tbody>{#each g.list as u (u.id)}
                <tr>
                  <td><a class="un" href="#u/{u.id}"><img class="thumb" src={art(u)} alt="" loading="lazy"><span><b>{u.name}</b>{#if u.levy}<span class="lv">levy</span>{/if}{@render cond(u)}
                    <i title={u.whoText}>{u.whoText || 'Everyone'}</i></span></a></td>
                  <td class="n">{ROMAN[u.age]}</td><td class="n">{men(u.str * 1000)}</td><td class="n">{num(u.cp)}</td><td class="n">{num(u.init)}</td><td class="n">{num(u.speed)}</td><td class="n">{num(u.flank)}</td>
                  <td class="n">{@render signed(u.sdd, 1, pct)}</td><td class="n">{@render signed(u.sdt, -1, pct)}</td><td class="n">{@render signed(u.mdd, 1, pct)}</td><td class="n">{@render signed(u.mdt, -1, pct)}</td>
                  <td class="tt">{@render terrain(u, 3)}</td>
                </tr>
              {/each}</tbody>
            </table></div>
          {/if}
        </section>
      {:else}<p class="meta">No unit matches the filters.</p>{/each}
    {/if}
  </div>{/key}</main>
</div>

<style>
  /* sidebar */
  .pfl { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: var(--dim); margin: 8px 0 3px; }
  .pfb { display: flex; flex-wrap: wrap; gap: 3px; }
  .pfb button, .pfb a { cursor: pointer; font-size: 12px; color: var(--text); background: #0d1117; border: 1px solid var(--line); border-radius: 3px; padding: 2px 8px; }
  .pfb button:hover, .pfb a:hover { border-color: var(--frame); }
  .pfb .on { border-color: var(--frame-hi) !important; color: var(--gold) !important; box-shadow: 0 0 6px #d8b46a55; background: linear-gradient(#3a3017, #1d1a10) !important; }
  .pfb .n { margin-left: 5px; color: var(--dim); font-size: 11px; font-variant-numeric: tabular-nums; }
  .mode { margin: 0 0 8px; }
  .mode a { flex: 1; text-align: center; font-size: 13px; padding: 3px 8px; }
  .cats { display: grid; grid-template-columns: 1fr 1fr; gap: 3px; }
  .cats button { display: flex; align-items: center; gap: 6px; padding: 2px 6px; cursor: pointer; font-size: 12.5px; color: var(--text); text-align: left;
    background: #0d1117aa; border: 1px solid var(--line); border-radius: 3px; }
  .cats button img { width: 24px; height: 24px; object-fit: contain; filter: drop-shadow(0 1px 1px #000c); }
  .cats button:hover { border-color: var(--frame); }
  .cats button.on { border-color: var(--frame-hi); color: var(--gold); box-shadow: 0 0 8px #d8b46a44; background: #2a2416; }
  .agepick { display: flex; gap: 3px; }
  .agepick button { cursor: pointer; width: 30px; height: 30px; border-radius: 50%; font-size: 13px; font-weight: 700; color: var(--gold); text-shadow: 0 1px 1px #000;
    border: 1px solid var(--frame); background: radial-gradient(circle at 40% 35%, #34503a, #16241b); box-shadow: inset 0 0 0 1px #000; }
  .agepick button:hover { border-color: var(--frame-hi); }
  .agepick button.on { border: 2px solid var(--frame-hi); box-shadow: 0 0 8px #f0d58c99; background: radial-gradient(circle at 40% 35%, #7a6328, #3b2c10); color: #fff6d8; }
  aside .blist h3 { display: flex; justify-content: space-between; align-items: center; }
  aside .blist h3 .hic { width: 18px; height: 18px; }
  .blist .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  aside .blist a.dim .nm { font-style: italic; color: var(--dim); }
  .blist .dot { flex: none; width: 6px; height: 6px; border-radius: 50%; background: var(--frame-hi); margin-left: 2px; }
  .lv { margin-left: 5px; font-size: 10.5px; letter-spacing: .5px; text-transform: uppercase; color: #c4b48a; border: 1px dotted #6b5a33; border-radius: 6px; padding: 0 4px; font-style: normal; font-weight: 400; white-space: nowrap; }
  .cnt { color: var(--gold); font-size: 12px; }
  .scopenote { margin: 0 0 8px; font-size: 12.5px; }
  .scopenote b { color: var(--gold); font-weight: normal; }
  .scopenote :global(.fl), .scopebanner :global(.fl) { margin-right: 4px; vertical-align: middle; }
  .scopebanner { margin: 0 0 10px; padding: 6px 10px; font-size: 13px; color: var(--dim); border: 1px solid var(--line); border-left: 2px solid var(--frame-hi); background: var(--panel2); }
  .scopebanner.no { color: var(--text); border-left-color: var(--in); }
  .scopebanner b { color: var(--gold); font-weight: normal; }
  .cond { margin-left: 6px; padding: 0 6px; font-size: 11px; font-weight: 400; font-style: italic; color: var(--dim); border: 1px dotted #6b5a33; border-radius: 8px; white-space: nowrap; cursor: help; }
  .lnk { color: var(--gold); text-decoration: underline; }
  .hic { width: 20px; height: 20px; vertical-align: middle; margin-right: 6px; object-fit: contain; }

  /* the game's unit art: a wide 1080x440 painting in a gilded frame */
  .uart { position: relative; flex: none; display: block; width: 160px; aspect-ratio: 320 / 130; border: 1px solid var(--frame); border-radius: 4px; overflow: hidden;
    background: #0d1117; box-shadow: 0 2px 6px #0009, inset 0 0 0 1px #0008; transition: border-color .15s, box-shadow .15s; }
  .uart img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .uart.big { width: 320px; border: 2px solid var(--frame); box-shadow: 0 0 0 1px #000, 0 3px 10px #000c; }
  .uart.big::after { content: ""; position: absolute; inset: 0; box-shadow: inset 0 0 18px #000a; pointer-events: none; }
  img.thumb { flex: none; width: 64px; height: 26px; object-fit: cover; border: 1px solid #6b5a33; border-radius: 2px; box-shadow: 0 1px 2px #000a; }

  /* overview table */
  .tw { overflow-x: auto; }
  .utab th { vertical-align: bottom; }
  .utab th.n button { max-width: 4.6em; white-space: normal; line-height: 1.15; text-align: right; }
  .utab th button { cursor: pointer; font: inherit; font-weight: 600; color: var(--gold); background: none; border: 1px solid transparent; border-radius: 3px; padding: 1px 4px; }
  .utab th button:hover, .utab th button.on { border-color: var(--frame-hi); background: #0006; }
  .utab th.n { text-align: right; }
  .utab td { padding: 3px 6px; vertical-align: middle; }
  .utab td.n { font-size: 13px; }
  .utab .zero { color: #ffffff30; }
  .utab tbody tr:hover { background: var(--panel2); }
  .un { display: flex; align-items: center; gap: 8px; min-width: 200px; }
  .un > span { min-width: 0; }
  .un b { font-weight: 600; }
  .un:hover b { color: var(--gold); }
  .un i { display: block; font-size: 12px; color: var(--dim); max-width: 210px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .utab td.tt { min-width: 130px; }
  .utab td.tt .tp { margin-bottom: 2px; }
  .tp { display: inline-block; margin: 1px 3px 1px 0; padding: 0 7px; font-size: 12px; white-space: nowrap; border-radius: 9px; border: 1px solid #6b5a33; background: #0d1117; }
  .tp.up { border-color: #4f7d3a; }
  .tp.down { border-color: #7d3a3a; }
  .tp.nosim { border-style: dashed; opacity: .75; }
  .tps .tp { font-size: 13px; padding: 1px 9px; margin: 2px 4px 2px 0; }
  .h4i { display: inline-flex; align-items: center; gap: 8px; }
  .h4i img { width: 26px; height: 26px; margin: -4px 0; object-fit: contain; filter: drop-shadow(0 1px 1px #000c); }

  /* overview cards */
  .ucards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px 10px; padding: 8px 2px 4px; }
  .ucard2 { display: flex; flex-direction: column; gap: 3px; padding: 6px; border-radius: 5px; min-width: 0; }
  .ucard2 .uart { width: 100%; }
  .ucard2 .uart .age { position: absolute; top: 5px; left: 5px; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 50%; font-size: 11px; font-weight: 700;
    color: var(--gold); border: 1px solid var(--frame); background: radial-gradient(circle at 40% 35%, #34503a, #16241b); box-shadow: 0 1px 3px #000; }
  .ucard2 .uart .lvb { position: absolute; top: 6px; right: 6px; font-size: 10.5px; letter-spacing: .6px; text-transform: uppercase; padding: 0 5px; color: #f3e6c4; background: #000a; border: 1px solid #6b5a33; border-radius: 3px; }
  .ucard2 > b { font-weight: 600; margin-top: 2px; }
  .ucard2 .ul { font-size: 12.5px; color: var(--text); opacity: .85; }
  .ucard2 .uw { font-size: 12px; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ucard2:hover { background: var(--panel2); }
  .ucard2:hover > b { color: var(--gold); }
  .ucard2:hover .uart, .ucard:hover .uart { border-color: var(--frame-hi); box-shadow: 0 0 10px #d8b46a66; }

  /* one unit */
  .title.unit { align-items: flex-start; }
  .back { margin-left: auto; align-self: flex-start; flex: none; }
  .addb { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 10px; }
  .ab { cursor: pointer; font-size: 13px; padding: 3px 12px; color: var(--c); border: 1px solid color-mix(in srgb, var(--c) 60%, transparent); border-radius: 3px;
    background: linear-gradient(color-mix(in srgb, var(--c) 18%, #1d2631), #141a22); box-shadow: inset 0 0 0 1px #000; }
  .ab:hover { border-color: var(--c); box-shadow: 0 0 8px color-mix(in srgb, var(--c) 40%, transparent); }
  .ab b { margin-left: 8px; padding: 0 6px; border-radius: 8px; font-size: 12px; color: #0d1117; background: var(--c); }
  .ab.att, .side.att { --c: var(--in); --tint: #3d2417; }
  .ab.def, .side.def { --c: var(--pop); --tint: #16304a; }
  .chip.go { color: var(--gold); }
  .srow { display: grid; grid-template-columns: 1fr auto 5.5em; gap: 10px; align-items: baseline; padding: 3px 4px; border-bottom: 1px solid #ffffff0d; }
  .srow:nth-of-type(even) { background: var(--stripe); }
  .srow b { font-weight: 600; color: var(--gold); font-variant-numeric: tabular-nums; text-align: right; }
  .srow .dv { font-size: 12.5px; text-align: right; font-variant-numeric: tabular-nums; }
  .lnote { margin: 8px 0 0; }
  .lnote b { color: var(--gold); font-weight: 600; }
  .uline { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 2px; padding: 6px 0 2px; }
  .ucard { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; width: 120px; font-size: 12.5px; line-height: 1.25; }
  .ucard .uart { width: 120px; }
  .ucard.cur .uart { border: 2px solid var(--frame-hi); box-shadow: 0 0 10px #d8b46a66; }
  .ucard.cur b { color: var(--gold); }
  .ucard b { font-weight: 600; }
  .ucard .tag { font-size: 10.5px; flex: none; }
  .ucard .un2 { display: flex; align-items: baseline; gap: 4px; width: 100%; }
  .chips { display: flex; flex-wrap: wrap; gap: 1px; }
  .chip.gen { border-color: #6b5a33; }
  .chip .lv { margin-left: 4px; }
  .wrow { padding: 5px 0; border-bottom: 1px solid #ffffff0d; }
  .wline { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; margin-top: 8px; }
  .wline .flbl { margin-right: 8px; }
  .cl { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 3px; }
  .tl { font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; color: var(--gold); margin-right: 6px; }
  .cl.not .tl { color: var(--in); }
  .tag.big { font-size: 13px; padding: 2px 8px; color: var(--text); }
  .og { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 3px 4px; }

  /* simulator: battlefield sidebar */
  .tsel { grid-template-columns: 1fr 1fr; }
  .tsel button { flex-direction: column; align-items: flex-start; gap: 0; line-height: 1.25; padding: 3px 8px; }
  .tsel button i { font-size: 11px; color: var(--dim); font-style: normal; min-height: 13px; }
  .tsel button.on i { color: #c4b48a; }
  .fsum { margin: 8px 0 0; font-size: 12.5px; }
  .fsum b { color: var(--gold); font-weight: 600; }
  .fixed { display: flex; align-items: center; gap: 2px; margin-top: 6px; }
  .fixed .flbl { width: 68px; color: var(--c); }
  .fixed.att { --c: var(--in); } .fixed.def { --c: var(--pop); }
  .fixed button { cursor: pointer; width: 21px; height: 22px; padding: 0; font-size: 12px; color: var(--text); background: #0d1117; border: 1px solid var(--line); border-radius: 3px; }
  .fixed button:hover { border-color: var(--c); }
  .fixed button.on { color: #0d1117; background: var(--c); border-color: var(--c); font-weight: 700; }
  .acts { display: flex; gap: 4px; margin-top: 14px; }
  .acts button { flex: 1; cursor: pointer; font-size: 13px; padding: 4px 6px; color: var(--gold); border: 1px solid var(--frame); border-radius: 3px;
    background: linear-gradient(#2a3542, #1d2631); box-shadow: inset 0 0 0 1px #000, 0 1px 3px #000a; }
  .acts button:hover { border-color: var(--frame-hi); }

  /* simulator: verdict strip, sticky so a change shows its effect anywhere on the page */
  .how { margin-top: 8px; font-size: 13px; }
  .how summary { color: var(--dim); font-size: 13px; }
  .how p { margin: 6px 0; max-width: 820px; }
  .how b { color: var(--gold); }
  .how .tips { font-size: 13px; color: var(--dim); max-width: 860px; }
  .how .tips li { margin-bottom: 4px; }
  .verdict { position: sticky; top: -16px; z-index: 3; display: grid; grid-template-columns: 8.5em 1fr 8.5em; align-items: center; gap: 4px 14px; margin: 0 0 16px; padding: 8px 14px;
    border: 1px solid var(--frame); background: linear-gradient(#1d2631f5, #141a22f5); box-shadow: inset 0 0 0 1px #000, 0 4px 10px #000a; min-height: 58px; }
  .verdict > p { grid-column: 1 / -1; margin: 0; }
  .verdict.busy > :not(.spin) { opacity: .55; transition: opacity .2s; }
  .vnum { display: flex; flex-direction: column; line-height: 1.1; }
  .vnum b { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; text-shadow: 0 1px 2px #000; }
  .vnum span { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: var(--dim); }
  .vnum.att b { color: var(--in); }
  .vnum.def { text-align: right; } .vnum.def b { color: var(--pop); }
  .vbar { display: flex; height: 14px; border: 1px solid #000; outline: 1px solid var(--frame); border-radius: 2px; overflow: hidden; background: #0d1117; }
  .vbar span { display: block; height: 100%; transition: width .35s cubic-bezier(.2, .7, .2, 1); }
  .vbar .a { background: linear-gradient(#f0a57d, #b8603a); }
  .vbar .d { background: repeating-linear-gradient(135deg, #5a5446, #5a5446 3px, #3a3628 3px, #3a3628 6px); }
  .vbar .b { background: linear-gradient(#a8d4f2, #4f86b3); }
  .vmeta { grid-column: 2; text-align: center; font-size: 12.5px; color: var(--dim); margin-top: -2px; }
  .spin { position: absolute; right: 12px; bottom: 4px; font-size: 11px; color: var(--gold); letter-spacing: .5px; }

  /* simulator: the two armies */
  .sides { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px 54px; align-items: start; }
  .vs { position: absolute; left: 50%; top: 6px; transform: translateX(-50%); z-index: 1; width: 40px; height: 40px; display: grid; place-items: center; border-radius: 50%;
    font-size: 13px; font-weight: 700; letter-spacing: 1px; color: var(--gold); text-shadow: 0 1px 1px #000; border: 2px solid var(--frame-hi);
    background: radial-gradient(circle at 40% 35%, #7a6328, #3b2c10); box-shadow: 0 0 0 1px #000, 0 2px 8px #000c; }
  .side { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .shead { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 12px; border: 1px solid var(--frame); border-top: 3px solid var(--c);
    background: linear-gradient(90deg, var(--tint), #18202a 75%); box-shadow: inset 0 0 0 1px #000, 0 2px 6px #0008; }
  .side.def .shead { background: linear-gradient(270deg, var(--tint), #18202a 75%); }
  .shead h3 { margin: 0; font-size: 18px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--c); text-shadow: 0 1px 2px #000; font-weight: 700; }
  .side.def .shead { flex-direction: row-reverse; }
  .focus { display: flex; flex-wrap: wrap; align-items: center; gap: 3px; }
  .focus button { cursor: pointer; font-size: 12px; color: var(--text); background: #0d1117; border: 1px solid var(--line); border-radius: 3px; padding: 1px 8px; }
  .focus button:hover { border-color: var(--frame); }
  .focus button.on { border-color: var(--c); color: var(--c); background: color-mix(in srgb, var(--c) 14%, #0d1117); }
  .ro { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; }
  .ro > div { display: flex; flex-direction: column; padding: 3px 8px 4px; border: 1px solid var(--line); border-left: 2px solid color-mix(in srgb, var(--c) 70%, transparent); border-radius: 2px; background: #0d1117aa; cursor: help; min-width: 0; }
  .ro span { font-size: 10.5px; letter-spacing: 1px; text-transform: uppercase; color: var(--dim); }
  .ro b { font-size: 17px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; line-height: 1.2; }
  .ro i { font-size: 11.5px; color: var(--dim); font-style: normal; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .side section.card > h4 { color: var(--c); background: linear-gradient(90deg, color-mix(in srgb, var(--c) 16%, var(--band)), #1b232e); }
  .reg { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) auto 3.4em 20px; align-items: center; gap: 6px; padding: 3px 0; border-bottom: 1px solid #ffffff0d; }
  .pickbtn { display: flex; align-items: center; gap: 8px; min-width: 0; cursor: pointer; font: inherit; font-size: 13.5px; color: var(--text); text-align: left;
    padding: 2px 6px 2px 2px; background: none; border: 1px solid transparent; border-radius: 3px; }
  .pickbtn:hover { border-color: var(--frame); background: var(--panel2); color: var(--gold); }
  .pickbtn .rn { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .step { display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 3px; background: #0d1117; }
  .step button { cursor: pointer; width: 22px; height: 24px; padding: 0; font-size: 15px; line-height: 1; color: var(--gold); background: none; border: none; }
  .step button:hover { background: var(--panel2); }
  .step input { width: 40px; height: 24px; text-align: center; color: var(--text); background: none; border: none; border-left: 1px solid var(--line); border-right: 1px solid var(--line); -moz-appearance: textfield; appearance: textfield; }
  .step input::-webkit-inner-spin-button { -webkit-appearance: none; }
  .rm { text-align: right; font-size: 12.5px; color: var(--dim); font-variant-numeric: tabular-nums; }
  .x { cursor: pointer; padding: 0; font-size: 17px; line-height: 1; color: var(--dim); background: none; border: none; }
  .x:hover { color: #e06060; }
  .adds { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
  .adds > button, .pickbtn.other { cursor: pointer; font-size: 12.5px; padding: 2px 10px; color: var(--c); border: 1px solid color-mix(in srgb, var(--c) 45%, var(--line)); border-radius: 3px; background: #0d1117; }
  .adds > button:hover, .pickbtn.other:hover { border-color: var(--c); background: color-mix(in srgb, var(--c) 12%, #0d1117); color: var(--c); }
  .pickwrap { position: relative; }
  .picker { position: absolute; top: 100%; left: 0; z-index: 10; width: min(380px, 90vw); margin-top: 2px; padding: 6px; border: 1px solid var(--frame); outline: 1px solid #000; border-radius: 3px;
    background: linear-gradient(#1d2631, #131921); box-shadow: 0 8px 22px #000d; }
  .picker .nfilter { margin-bottom: 4px; }
  .plist { max-height: 340px; overflow-y: auto; }
  .pcat { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 6px; padding: 3px 6px; font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; color: var(--gold);
    background: linear-gradient(90deg, var(--band), #1b232e); border-bottom: 1px solid var(--line); }
  .pcat > img { width: 20px; height: 20px; object-fit: contain; }
  .pcat :global(.fl) { margin-right: 0; }
  .pu { display: flex; align-items: center; gap: 8px; width: 100%; cursor: pointer; font: inherit; font-size: 13px; color: var(--text); text-align: left; padding: 2px 6px 2px 2px; background: none; border: none; border-bottom: 1px solid #ffffff0a; }
  .pu:hover, .pu:focus-visible { background: var(--panel2); color: var(--gold); outline: none; }
  .pu img.thumb { width: 48px; height: 20px; }
  .pu .rn { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pu i { font-size: 11px; color: var(--dim); }
  .pu.gone { opacity: .5; }
  .tgl.on1 { margin: 0 0 4px; display: inline-flex; align-items: center; gap: 6px; color: var(--text); }
  .abil { display: grid; grid-template-columns: 7.5em minmax(0, 1fr) 2.2em; align-items: center; gap: 2px 8px; padding: 3px 0; }
  .abil .flbl { margin: 0; }
  .abil input { width: 100%; accent-color: var(--c); }
  .abil b { text-align: right; color: var(--gold); font-variant-numeric: tabular-nums; }
  .abil .eff { grid-column: 2 / -1; font-size: 12px; color: var(--dim); margin-top: -3px; }
  .flbl.tr { display: block; margin: 8px 0 3px; }
  .traits { display: flex; flex-wrap: wrap; gap: 3px; }
  .traits button { cursor: pointer; font-size: 12px; padding: 1px 8px; color: var(--text); background: #0d1117; border: 1px solid var(--line); border-radius: 10px; }
  .traits button:hover { border-color: var(--frame); }
  .traits button.on { color: var(--c); border-color: var(--c); background: color-mix(in srgb, var(--c) 15%, #0d1117); }
  .advm { margin: 0; padding: 6px 12px 8px; border: 1px solid var(--line); border-radius: 2px; background: #10161dcc; }
  .advm > summary { font-size: 13px; letter-spacing: .5px; }
  .advm > summary .meta { margin-left: 8px; font-size: 12px; font-style: italic; }
  .mgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 3px 14px; margin-top: 8px; }
  .mgrid label { display: grid; grid-template-columns: minmax(0, 1fr) 54px 14px; align-items: center; gap: 4px; font-size: 12.5px; cursor: help; }
  .mgrid label span { display: flex; align-items: center; gap: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--dim); }
  .mgrid label span img { width: 18px; height: 18px; object-fit: contain; }
  .mgrid label i { color: var(--dim); font-style: normal; font-size: 12px; }
  .mgrid input, .mgrid select { width: 100%; padding: 1px 4px; font: inherit; font-size: 12.5px; text-align: right; color: var(--text); background: #0d1117; border: 1px solid var(--line); border-radius: 3px; }
  .mgrid input { -moz-appearance: textfield; appearance: textfield; }
  .mgrid input::-webkit-inner-spin-button { -webkit-appearance: none; }
  .mgrid input:focus, .mgrid select:focus { outline: none; border-color: var(--frame-hi); }
  .mgrid label.wide { grid-column: 1 / -1; grid-template-columns: 9em 1fr; }
  .mgrid select { text-align: left; }

  /* simulator: results */
  .rgrid { display: grid; grid-template-columns: minmax(300px, 1fr) minmax(0, 2.2fr); gap: 16px; margin-top: 16px; align-items: start; }
  @media (max-width: 1500px) { .rgrid { grid-template-columns: minmax(0, 1fr); } }
  .res td.n, .res th.n { text-align: right; }
  .ca { color: var(--in) !important; } .cd { color: var(--pop) !important; }
  .legend { display: flex; gap: 16px; align-items: baseline; font-size: 13px; margin-bottom: 2px; }
  .legend .meta { margin-left: auto; font-size: 12px; font-style: italic; }
  .chart { position: relative; width: 100%; }
  .chart svg { display: block; cursor: crosshair; touch-action: none; }
  .chart .grid { stroke: #ffffff14; stroke-width: 1; }
  .chart .ln { fill: none; stroke-width: 2; stroke-linejoin: round; }
  .chart .cross { stroke: var(--frame-hi); stroke-width: 1; stroke-dasharray: 3 3; }
  .chart circle { stroke: #0d1117; stroke-width: 1.5; }
  .chart text { font-size: 11px; fill: var(--dim); font-family: var(--serif); }
  .chart .yl { text-anchor: end; font-variant-numeric: tabular-nums; }
  .chart .xl { text-anchor: middle; }
  .chart .xl.end { text-anchor: end; }
  .chart .pl { fill: var(--gold); font-size: 11px; letter-spacing: 1px; text-transform: uppercase; }
  .chart .bomb { fill: #f0d58c0d; }
  .chart .bl { font-size: 10.5px; fill: #c4b48a; font-style: italic; }
  .ctip { position: absolute; top: 10px; transform: translateX(12px); pointer-events: none; z-index: 2; padding: 6px 10px; font-size: 12.5px; white-space: nowrap;
    background: linear-gradient(#1d2631, #131921); border: 1px solid var(--frame); outline: 1px solid #000; border-radius: 3px; box-shadow: 0 6px 18px #000c; }
  .ctip.flip { transform: translateX(calc(-100% - 12px)); }
  .ctip > b { color: var(--gold); font-size: 13.5px; }
  .ctip table { border-collapse: collapse; margin-top: 2px; }
  .ctip td { padding: 1px 6px; text-align: right; font-variant-numeric: tabular-nums; }
  .ctip td:first-child { text-align: left; color: var(--dim); padding-left: 0; }
  .ctip td i { color: var(--dim); font-style: normal; font-size: 11.5px; }
  .notes { margin: 8px 0 0; padding-left: 18px; font-size: 13px; }
  .notes li { margin-bottom: 2px; }

  @media (max-width: 1250px) { .sides { grid-template-columns: minmax(0, 1fr); } .vs { display: none; } }
  @media (prefers-reduced-motion: reduce) { .vbar span { transition: none; } }
</style>
