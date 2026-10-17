// Production Chains page: goods / buildings views rendered as HTML strings into the page shell.
import { DATA, type Recipe } from './data';
import { AGE } from './age.svelte';

type Use = [bid: string, r: Recipe];  // a building running a recipe
type Card = [body: string, heading: string, emptyText: string, cls?: string];  // cls 'big': gets a wider column

const {goods: G, buildings: B, demands: D, pops: P, cats: CATS, units: U, demandRefs: DREF} = DATA;
const HAS = Object.fromEntries(Object.entries(DATA.icons).map(([k, v]) => [k, new Set(v)]));
export const fmt = (n: number | null | undefined) => n == null ? '' : (Math.abs(n) < 0.01 ? +n.toPrecision(2) : +n.toFixed(3)).toString();  // keep tiny demands readable
export const esc = (s: unknown) => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]!));

export function icon(kind: string, id: string, label: string) {
  if (HAS[kind]?.has(id)) return `<img class="ic" src="icons/${kind}/${id}.png" alt="" title="${esc(label)}">`;
  const ab = label.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  return `<span class="ic-fb ${kind === 'buildings' ? 'b' : ''}" title="${esc(label)}">${esc(ab)}</span>`;
}
// what one pop of type p buys of good g: (own + all + upper) x own multiplier x upper multiplier, then the chosen age's modifier
export function popDemand(g: string, p: string) {
  const {demand: a, demandMul: m} = G[g], up = DATA.popInfo.types[p].upper;
  const base = ((a[p] || 0) + (a.all || 0) + (up ? a.upper || 0 : 0)) * (m[p] ?? 1) * (up ? m.upper ?? 1 : 1);
  return Math.max(0, base * (1 + agePct(g, AGE.v)));
}
export const gChip = (g: string, n?: number) => `<a class="chip" href="#g/${g}">${icon('goods', g, G[g]?.name || g)}${esc(G[g]?.name || g)}${n != null ? ` <span class="n">${fmt(n)}</span>` : ''}</a>`;
// compact: icon + amount, name in tooltip (for dense recipe lines)
const gIco = (g: string, n?: number) => `<a class="chip ico" href="#g/${g}" title="${esc(G[g]?.name || g)}">${icon('goods', g, G[g]?.name || g)}${n != null ? `<span class="n">${fmt(n)}</span>` : ''}</a>`;
export const bChip = (b: string) => `<a class="chip" href="#b/${b}">${icon('buildings', b, B[b].name)}${esc(B[b].name)}</a>`;
const uChip = (u: string) => `<span class="chip" title="${esc(U[u].age ? U[u].age.replace(/^age_\d_/, '').replace(/_/g, ' ') + ' age' : '')}">${icon('units', U[u].cat, U[u].name)}${esc(U[u].name)}</span>`;
// demand groups that aren't a single pop type get the game's generic icons
const PGROUP: Record<string, [string, string]> = {all: ['all_pops', 'All pops'], upper: ['strata', 'Upper strata']};
export const pName = (p: string) => PGROUP[p]?.[1] || P[p] || p;
export const pIcon = (p: string) => PGROUP[p] ? `<img class="ic" src="icons/misc/${PGROUP[p][0]}.png" alt="${esc(pName(p))}">` : icon('pops', p, pName(p));
const pChip = (p: string) => P[p] ? `<a class="chip" href="#p/${p}">${pIcon(p)}${esc(pName(p))}</a>` : `<span class="chip">${pIcon(p)}${esc(pName(p))}</span>`;

// ---- indexes ---------------------------------------------------------------
const producers: Record<string, Use[]> = {}, consumers: Record<string, Use[]> = {}, maint: Record<string, Use[]> = {}, demandUse: Record<string, string[]> = {};
for (const [bid, b] of Object.entries(B)) for (const r of b.recipes) {
  if (r.out) (producers[r.out] ??= []).push([bid, r]);
  for (const g in r.in) ((r.out ? consumers : maint)[g] ??= []).push([bid, r]);
}
const buildBy: Record<string, string[]> = {};  // construction demand id -> buildings
for (const [bid, b] of Object.entries(B)) if (b.build) (buildBy[b.build] ??= []).push(bid);
for (const [did, d] of Object.entries(D)) for (const g in d.in) (demandUse[g] ??= []).push(did);
const unitsBy: Record<string, string[]> = {};  // demand id -> visible unit types using it (hidden templates only if nothing else)
for (const [uid, u] of Object.entries(U)) for (const d of new Set(Object.values(u.dem))) (unitsBy[d] ??= []).push(uid);
for (const d in unitsBy) {
  const vis = unitsBy[d].filter(u => !U[u].hide);
  unitsBy[d] = (vis.length ? vis : unitsBy[d]).sort((a, b) => U[a].name.localeCompare(U[b].name));
}
const UNIT_CATS = new Set(['regiment_construction', 'regiment_maintenance', 'ship_construction', 'ship_maintenance', 'ship_repair']);
const chipList = (chips: string[], max = 8) => chips.length <= max ? chips.join('')
  : chips.slice(0, max).join('') + `<details style="display:inline"><summary class="tag more">+${chips.length - max} more</summary>${chips.slice(max).join('')}<button class="tag less">Show less</button></details>`;
// "Show less" at the end of an expanded list folds it back (Pops lists use it too)
addEventListener('click', e => {
  const d = (e.target as Element).closest?.('.less')?.closest('details');
  if (d) { d.open = false; d.querySelector('summary')!.scrollIntoView({block: 'nearest'}); }
});
// who uses a goods_demand entry: buildings (construction), unit types, or other script objects (laws, orders…)
const demandUsers = (d: string) => [...(buildBy[d] || []).map(bChip), ...(unitsBy[d] || []).map(uChip),
  ...(DREF[d] || []).map(r => `<span class="chip"><span class="tag">${esc(r.f.replace(/_/g, ' '))}</span>${esc(r.name)}</span>`)];

const DCAT: Record<string, string> = {
  building_construction: 'Building construction', building_maintenance: 'Upkeep',
  regiment_construction: 'Army recruitment', regiment_maintenance: 'Army upkeep',
  ship_construction: 'Ship construction', ship_maintenance: 'Ship upkeep', ship_repair: 'Ship repair',
  special_demands: 'Special demands', government_activities: 'Government activities',
};
const METHOD: Record<string, string> = {farming: 'Farming', mining: 'Mining', hunting: 'Hunting', gathering: 'Gathering', forestry: 'Forestry'};
const method = (m: string | null) => m ? METHOD[m] || m : '';
const pretty = (id: string) => id.replace(/_(construction|maintenance|repair|demands?|input)$/, '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

function recipeGroups(list: Use[]) {  // grouped under each building: inputs → output per line
  const by: Record<string, Recipe[]> = {};
  for (const [bid, r] of list) (by[bid] ??= []).push(r);
  return Object.entries(by).map(([bid, rs]) => `<div class="grp">${bChip(bid)}${rs.map(r =>
    `<div class="line rl"><span class="ins">${Object.entries(r.in).map(([g, n]) => gIco(g, n)).join('') || '<span class="none">no inputs</span>'}</span>${r.out ? `<span class="outp"><span class="arrow">→</span>${gIco(r.out, r.amt)}</span>` : ''}</div>`).join('')}</div>`).join('');
}

// ---- chain trees -----------------------------------------------------------
// ---- page filters (good pages only): age = what's available in that age, rec = recipe variant of the viewed good
const F: {on: boolean; g: string | null; rec: number | null} = {on: false, g: null, rec: null};
const obsoletedBy: Record<string, string[]> = {};
for (const [bid, b] of Object.entries(B)) if (b.obsolete) (obsoletedBy[b.obsolete] ??= []).push(bid);
// available in age A: unlocked by then and not already replaced by a newer tier that is also unlocked
const availB = (bid: string, A: number) => B[bid].age <= A && !(obsoletedBy[bid] || []).some(o => B[o].age <= A);
const okR = ([bid, r]: Use, A: number | null = AGE.v) => !A || (availB(bid, A) && (r.age || 1) <= A);
const matchesVariant = (r: Recipe, v: string[]) => v.every(i => i in r.in);
function prod(g: string, A?: number) {
  let ps = (producers[g] || []).filter(p => okR(p, A));
  if (F.on && g === F.g && F.rec != null) { const v = variants(g)[F.rec]; ps = ps.filter(([, r]) => matchesVariant(r, v)); }
  return ps;
}
const cons = (g: string) => (consumers[g] || []).filter(p => okR(p));
const minimalSets = (sets: string[][]) => sets.filter(s => !sets.some(o => o.length < s.length && o.every(i => s.includes(i))));
const distinctSets = (list: Use[]) => [...new Map(list.map(([, r]) => Object.keys(r.in).sort()).filter(s => s.length).map(s => [s.join('+'), s])).values()];
const variants = (g: string) => minimalSets(distinctSets(producers[g] || []));  // unfiltered, so the buttons stay stable

// recipe options for a good: distinct input sets, reduced to the minimal ones (alternatives);
// inputs only found in non-minimal sets are reported separately as "extra"
function inputOptions(g: string) {
  const sets = distinctSets(prod(g));
  const mins = minimalSets(sets);
  const core = new Set(mins.flat());
  return {mins, extra: [...new Set(sets.flat())].filter(i => !core.has(i))};
}
const isLeaf = (g: string) => G[g].cat === 'raw_material' || !prod(g).length;
// upgrade chains in tier order (longest chain first); single buildings come last
function orderB(bids: string[]) {
  const set = new Set(bids), chains: string[][] = [];
  for (const root of set) {
    const prev = B[root].obsolete;
    if (prev && set.has(prev)) continue;  // not the start of a chain
    const c = [root];
    for (let n; (n = (obsoletedBy[c.at(-1)!] || []).find(o => set.has(o) && !c.includes(o)));) c.push(n);
    chains.push(c);
  }
  return chains.sort((a, b) => +(b.length > 1) - +(a.length > 1) || b.length - a.length || B[a[0]].age - B[b[0]].age || B[a[0]].name.localeCompare(B[b[0]].name));
}
// small linked building icons; hover gives the building tooltip; a divider before standalone buildings
function bIcons(bids: string[]) {
  const chains = orderB(bids), link = (b: string) => `<a class="bi" href="#b/${b}">${icon('buildings', b, B[b].name)}</a>`;
  const multi = chains.filter(c => c.length > 1), solo = chains.filter(c => c.length === 1);
  return [...multi.map(c => c.map(link).join('')), solo.map(c => link(c[0])).join('')].filter(Boolean).join('<span class="bsep"></span>');
}
const key = (s: Iterable<string>) => [...s].sort().join('+');
const members = (t: string) => t.startsWith('G:') ? t.slice(2).split(',') : [t];
// Either groups: inputs that swap one-for-one ('G:a,b' tokens). Kept only if every combination
// they imply is a real recipe and nothing is lost; null if that fails.
function swapTok(sets: string[][]) {
  const K = new Set(sets.map(key)), all = [...new Set(sets.flat())];
  const up: Record<string, string> = Object.fromEntries(all.map(i => [i, i]));
  const find = (x: string): string => up[x] === x ? x : (up[x] = find(up[x]));
  for (const s of sets) for (const x of s) for (const y of all)  // x and y are swappable if trading one for the other gives another recipe
    if (!s.includes(y) && K.has(key([...s.filter(i => i !== x), y]))) up[find(y)] = find(x);
  const grp: Record<string, string[]> = {};
  for (const i of all) (grp[find(i)] ??= []).push(i);
  const tok = (i: string) => grp[find(i)].length > 1 ? 'G:' + [...grp[find(i)]].sort().join(',') : i;
  const expand = (t: string[]) => t.reduce((acc, x) => acc.flatMap(a => members(x).map(i => [...a, i])), [[]] as string[][]);
  const back = new Set(sets.flatMap(s => expand([...new Set(s.map(tok))])).map(key));
  return back.size === K.size && [...back].every(k => K.has(k)) ? tok : null;
}
// How a good is made, from every recipe that makes it (not just the minimal ones):
// "always" = inputs (or Either groups like Lumber / Leather) that every recipe uses;
// rows = buildings with the same remaining options, in upgrade order, each listing its recipes.
function recipeView(g: string) {
  const ps = prod(g);
  const setsOf = (rs: Use[]) => [...new Map(rs.map(([, r]) => [key(Object.keys(r.in)), Object.keys(r.in)])).values()].filter(s => s.length);
  // groups across all producers first; if that doesn't hold (jewelry: Pounamou's lone Gems vs the guild's
  // base + enhancement), find each building's own groups
  const global = swapTok(setsOf(ps)), id = (i: string) => i;
  const tokB = new Map([...new Set(ps.map(([b]) => b))].map(b => [b, global || swapTok(setsOf(ps.filter(([x]) => x === b))) || id]));
  const T = (b: string, s: string[]) => [...new Set(s.map(tokB.get(b)!))];
  const sets = ps.map(([b, r]) => T(b, Object.keys(r.in))).filter(s => s.length);
  const always = sets.length ? sets[0].filter(t => sets.every(s => s.includes(t))) : [];
  const byB = new Map<string, Map<string, string[]>>();
  for (const [bid, r] of ps) {
    const o = T(bid, Object.keys(r.in)).filter(t => !always.includes(t));
    if (!byB.has(bid)) byB.set(bid, new Map());
    byB.get(bid)!.set(key(o), o);
  }
  const groups = new Map<string, {opts: string[][]; bids: string[]}>();
  for (const [bid, opts] of byB) {
    const k = [...opts.keys()].sort().join('|');
    if (!groups.has(k)) groups.set(k, {opts: [...opts.values()].sort((a, b) => a.length - b.length || key(a).localeCompare(key(b))), bids: []});
    groups.get(k)!.bids.push(bid);
  }
  const order = orderB([...byB.keys()]).flat(), pos = (r: {bids: string[]}) => Math.min(...r.bids.map(b => order.indexOf(b)));
  const allB = new Set(byB.keys());
  const span = (x: string, i: string) => {  // building tag for an Either option not every building using that box can use
    const users = [...allB].filter(b => ps.some(([y, r]) => y === b && T(b, Object.keys(r.in)).includes(x)));
    const bs = users.filter(b => ps.some(([y, r]) => y === b && i in r.in));
    return bs.length < users.length ? bIcons(bs) : '';
  };
  return {always, rows: [...groups.values()].sort((a, b) => pos(a) - pos(b)), span, allB};
}
// panel titles explain themselves on hover
const TERMS: Record<string, string> = {
  'Always': 'Every recipe for this good uses these. The icons next to the title are the buildings that make it.',
  'Either': 'Use any one of these. If an option has building icons under it, only those buildings can use it.',
  'Plus, by building': 'Some buildings need more than the Always inputs. Each row shows buildings on the left and what they add on the right. "or" means the building can run either recipe. Buildings that need nothing extra are not listed.',
  'By age': 'Every pop\'s demand for this good changes by this much in each age.',
  'Modifiers': 'Changes how much every pop in your country wants this good while you have it. +100% means double.',
  'Culture & religion': 'Pops of these cultures or religions want this many times the normal amount. ×0 means they don\'t buy it at all. Clergy only means just their clergy.',
  'Where': 'Pop demand for this good is multiplied by where the pops live: winters, climate, terrain, or part of the world.',
  'Events': 'These events add demand for this good to a market for a while. The number is the extra amount bought.',
  'By building': 'No input is shared by every recipe, so each building\'s recipes are shown in full. Buildings on the same row use the same recipes. "or" means the building can run either recipe.',
};
const term = (t: string) => `<span class="term" data-tip="${esc(TERMS[t] || '')}">${t}</span>`;
function optsHtml(g: string) {
  const {always, rows, span, allB} = recipeView(g);
  if (!rows.length) return '';
  const PLUS = '<span class="arrow">+</span>';
  const either = (x: string) => `<span class="fx either"><span class="fl">${term('Either')}</span><span class="fr">${
    members(x).map(i => span(x, i) ? `<span class="em">${gChip(i)}<span class="bis">${span(x, i)}</span></span>` : gChip(i)).join('')}</span></span>`;
  // plain goods first, then Either boxes, joined with +
  const chips = (ts: string[]) => [...ts].sort((a, b) => +a.startsWith('G:') - +b.startsWith('G:')).map(x => x.startsWith('G:') ? either(x) : gChip(x)).join(PLUS);
  const head = (label: string) => `<span class="fl hd">${term(label)}<span class="bis">${bIcons([...allB])}</span></span>`;
  let out = always.length ? `<div class="fx">${head('Always')}<span class="fr">${chips(always)}</span></div>` : '';
  // a building whose only recipe is exactly the Always inputs adds nothing; its icon is already in the Always header
  const extra = rows.filter(r => r.opts.length > 1 || r.opts[0].length);
  if (extra.length) {
    const opt = (o: string[], many: boolean) => !o.length ? '<span class="none">nothing extra</span>'
      : `<span class="${many && o.length > 1 ? 'og' : 'og1'}">${always.length ? PLUS : ''}${chips(o)}</span>`;
    out += `<div class="fx">${always.length ? `<span class="fl">${term('Plus, by building')}</span>` : head('By building')}${extra.map(r =>
      `<span class="trow"><span class="tl">${bIcons(r.bids)}</span><span class="fr">${r.opts.map(o => opt(o, r.opts.length > 1)).join('<span class="or">or</span>')}</span></span>`).join('')}</div>`;
  }
  return out;
}

// upstream: every produced good in the dependency closure once, as a header + its recipe panels; raw materials listed last
function upChain(g: string) {
  if (isLeaf(g)) return '';
  const seen = new Set([g]), q = [g], rows: string[] = [], raw: string[] = [];
  while (q.length) {
    const x = q.shift()!;
    if (isLeaf(x)) { raw.push(x); continue; }
    const o = inputOptions(x);
    rows.push(`<div class="crow up">${gChip(x)}<span class="opts">${optsHtml(x)}</span></div>`);
    for (const i of [...new Set([...o.mins.flat(), ...o.extra])].sort()) if (!seen.has(i)) { seen.add(i); q.push(i); }
  }
  return rows.join('') + `<div class="crow up raw"><span class="hdr">Raw materials (RGO)</span><span class="opts"><div class="fx"><span class="fr">${raw.map(i => gChip(i)).join('')}</span></div></span></div>`;
}
// downstream: every good reachable by processing, once, as "good → outputs" (depth-limited)
function downChain(g: string, depth = 3) {
  const seen = new Set([g]), rows: string[] = [];
  let level = [g];
  for (let d = 0; d < depth && level.length; d++) {
    const next: string[] = [];
    for (const x of level) {
      // raw outputs (tools → fish via fishing villages etc.) are extraction inputs, not processing — skip them
      const outs = [...new Set(cons(x).map(([, r]) => r.out!))].filter(o => G[o].cat !== 'raw_material').sort((a, b) => G[a].name.localeCompare(G[b].name));
      if (!outs.length) continue;
      rows.push(`<div class="crow">${gChip(x)}<span class="arrow">→</span><span class="opts row">${outs.map(o => gChip(o)).join('')}</span></div>`);
      for (const o of outs) if (!seen.has(o)) { seen.add(o); next.push(o); }
    }
    level = next;
  }
  return rows.join('');
}

// ---- views -----------------------------------------------------------------
// filled cards render; empty ones only add their text to EMPTY, which route() shows as one line below everything
let EMPTY: string[] = [];
const keep = (list: Card[]) => { EMPTY.push(...list.filter(c => !c[0]).map(c => c[2])); return list.filter(c => c[0]); };
const cards = (list: Card[]) => `<div class="masonry">${keep(list).map(([body, h, , cls]) => `<section class="card${cls ? ' ' + cls : ''}">${h}${body}</section>`).join('')}</div>`;
export const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI'];
function filterBar(g: string) {
  const vs = variants(g);
  if (!vs.length) return '';
  const tip = (v: string[]) => esc(v.map(i => G[i].name).join(' + ')), ics = (v: string[]) => v.map(i => icon('goods', i, G[i].name)).join('');
  // a single recipe has nothing to filter, so it shows without a button
  return `<div class="popbar filters"><span class="flbl">Recipe</span><div class="row">${vs.length === 1 ? `<span class="rec" title="${tip(vs[0])}">${ics(vs[0])}</span>`
    : vs.map((v, k) => `<button class="rec${F.rec === k ? ' on' : ''}" data-f="rec" data-v="${k}" title="${tip(v)}">${ics(v)}</button>`).join('')}</div></div>`;
}
let keepScroll = false;
const filterQuery = () => F.rec != null ? `?rec=${F.rec}` : '';
// share every pop's demand for g changes by in age a (age modifiers apply only during their age)
export const agePct = (g: string, a: number | null) => a ? [...(DATA.demandMods[g] || []), ...(DATA.demandMods['*'] || [])]
  .filter(m => m.kind === 'age' && m.age === a).reduce((t, m) => t + m.pct!, 0) : 0;
const AGE_NOTE = (a: number) => `Age ${ROMAN[a]}: ${esc(DATA.ages[a])}`;

// upkeep users grouped by per-building amount, largest first
function upkeepGroups(g: string, ms: Use[]) {
  const by: Record<string, Set<string>> = {};
  for (const [b, r] of ms) (by[r.in[g]] ??= new Set()).add(b);
  return Object.entries(by).sort((a, b) => +b[0] - +a[0]).map(([n, bs]) =>
    `<div class="ugrp"><div class="who">${chipList([...bs].map(b => bChip(b)), 24)}</div>
    <div class="need"><span class="arrow">each needs →</span><a class="chip" href="#g/${g}">${icon('goods', g, G[g].name)}<span class="nm">${esc(G[g].name)}</span> <span class="n">${fmt(+n)}</span></a></div></div>`).join('');
}

// construction: how many buildings need this good to be built; CORE = needed by ≥20% of buildings (masonry, lumber, tools, glass)
const buildCost = (b: {build: string | null}) => b.build ? D[b.build] : undefined;
const BUILT = Object.values(B).filter(buildCost).length, conUse: Record<string, number> = {};
for (const b of Object.values(B)) for (const g in buildCost(b)?.in || {}) conUse[g] = (conUse[g] || 0) + 1;
const pct = (g: string) => Math.round(100 * (conUse[g] || 0) / BUILT);
const CORE = Object.keys(conUse).filter(g => pct(g) >= 20).sort((a, b) => conUse[b] - conUse[a]);
const feedsCore = (g: string) => CORE.filter(c => c !== g && (producers[c] || []).some(([, r]) => g in r.in));
// food value per unit, ranked against every other food good
const FOODS = Object.keys(G).filter(g => G[g].food).sort((a, b) => G[b].food! - G[a].food!);
const APPLE = '<img class="ic" src="icons/misc/food.png" alt="Food">';
function foodBar(g: string) {
  const f = G[g].food;
  if (!f) return '';
  const rank = FOODS.findIndex(o => G[o].food === f) + 1;  // ties share the best rank
  return `<div class="popbar"><span class="flbl">Food</span><div class="row"><span class="pd food" title="Each unit provides ${fmt(f)} food; food drives pop growth">
    <span class="fv">${APPLE}<span class="big">${fmt(f)}</span></span><b>#${rank} of ${FOODS.length} foods</b></span></div></div>`;
}
function conBar(g: string) {
  if (!conUse[g]) return '';
  return `<div class="popbar"><span class="flbl">Construction</span><div class="row"><span class="pd${CORE.includes(g) ? ' top' : ''}"
    title="Needed to construct ${conUse[g]} of ${BUILT} building types"><span class="big">${pct(g)}%</span><b>${conUse[g]} building${conUse[g] === 1 ? '' : 's'}</b></span></div></div>`;
}
function conNote(g: string) {
  const f = feedsCore(g);
  return (CORE.includes(g) ? `<div class="cnote">Core construction material — needed to build ${conUse[g]} of ${BUILT} building types, so its price feeds directly into building costs.</div>` : '')
    + (f.length ? `<div class="cnote">Input for construction material${f.length > 1 ? 's' : ''}: ${f.map(c => gChip(c)).join('')}</div>` : '');
}

// pop classes that buy this good, biggest consumer first and highlighted
function popBar(g: string) {
  const x = G[g], f = 1 + agePct(g, AGE.v);  // the chosen age scales every pop's demand
  const d = Object.entries(x.demand).map(([p, n]) => [p, Math.max(0, n * f)] as [string, number]).sort((a, b) => b[1] - a[1]);
  const m = Object.entries(x.demandMul).filter(([, n]) => n).sort((a, b) => b[1] - a[1]);
  if (!d.length && !m.length) return '';
  const pd = (p: string, txt: string, cls: string, tip: string) => `<span class="pd${cls}" title="${esc(pName(p) + tip)}">${pIcon(p)}<b>${txt}</b></span>`;
  return `<div class="popbar"><span class="flbl">Pop demand</span><div class="row">${
    d.map(([p, n], i) => i === 0 && d.length > 1 ? pd(p, `+${fmt(n)}`, ' top', `: +${fmt(n)} — biggest consumer`) : pd(p, `+${fmt(n)}`, '', `: +${fmt(n)}`)).join('')}${
    m.map(([p, n]) => pd(p, `×${fmt(n)}`, ' mul', `: demand ×${fmt(n)}`)).join('')}</div></div>`;
}

// ---- what changes pop demand ------------------------------------------------
export const KIND: Record<string, string> = {
  government_reforms: 'Government reform', religious_aspects: 'Religious aspect', societal_values: 'Societal value',
  industry_types: 'Promote Industry', modifier: 'Modifier', culture_groups: 'Culture group', cultures: 'Culture',
  religion_groups: 'Religion group', religions: 'Religion', events: 'Event', decisions: 'Decision', on_action: 'Game event',
};
export const signed = (n: number, unit = '') => `${n > 0 ? '+' : n < 0 ? '−' : '±'}${fmt(Math.abs(n))}${unit}`;
export const pctTxt = (p: number) => signed(Math.round(p * 100), '%');
export const trig = (t: {kind: string; name: string; tag?: string}) => `${t.tag ? `<span class="tag">${esc(t.tag)}</span>` : `<span class="tag">${esc(KIND[t.kind] || t.kind)}</span>`} ${esc(t.name)}`;
const COND = {only: 'Only in', winter: 'Winter', climate: 'Climate', topography: 'Terrain', continent: 'Continent', sub_continent: 'Subcontinent',
  region: 'Region', disease: 'Disease', literacy: 'Literacy', market_unavailability: 'Unavailable'};
function demandShifts(g: string) {
  const mods = [...(DATA.demandMods[g] || []), ...(DATA.demandMods['*'] || []).map(m => ({...m, all: true}))];
  const ages = mods.filter(m => m.kind === 'age').sort((a, b) => a.age! - b.age!);
  const pcts = mods.filter(m => m.pct != null && m.kind !== 'age').sort((a, b) => b.pct! - a.pct!);
  const muls = mods.filter(m => m.mul != null);
  const events = Object.entries(DATA.tempDemand).filter(([d]) => D[d]?.in[g]).flatMap(([d, ts]) => ts.map(t => ({...t, amt: D[d].in[g] * t.scale})))
    .sort((a, b) => (a.tag || '~').localeCompare(b.tag || '~') || a.name.localeCompare(b.name));
  const cls = (n: number, base = 0) => n > base ? 'up' : n < base ? 'down' : '';
  const out: string[] = [];
  if (ages.length) out.push(`<div class="dsec">${term('By age')}<div class="ages">${ages.map(a =>
    `<span class="ag${a.age === AGE.v ? ' cur' : ''}" title="Age ${ROMAN[a.age!]}: ${esc(DATA.ages[a.age!])}"><b>${ROMAN[a.age!]}</b><span class="${cls(a.pct!)}">${pctTxt(a.pct!)}</span></span>`).join('')}</div></div>`);
  if (pcts.length) out.push(`<div class="dsec">${term('Modifiers')}${pcts.map(m => `<div class="dm"><span class="v ${cls(m.pct!)}">${pctTxt(m.pct!)}</span><span>${
    `<span class="tag">${esc(KIND[m.kind] || m.kind)}</span> ${esc(m.name)}${m.side ? ` <i>(leaning ${esc(m.side)})</i>` : ''}${'all' in m ? ' <i>(every good)</i>' : ''}`
    }${m.by?.length ? `<div class="by">from ${m.by.map(trig).join(', ')}</div>` : ''}</span></div>`).join('')}</div>`);
  if (muls.length) {
    const groups = new Map<string, typeof muls>();
    for (const m of muls) { const k = `${m.mul}|${m.clergy ? 1 : 0}`; groups.set(k, [...(groups.get(k) || []), m]); }
    out.push(`<div class="dsec">${term('Culture & religion')}${[...groups.values()].sort((a, b) => b[0].mul! - a[0].mul!).map(ms =>
      `<div class="dm"><span class="v ${cls(ms[0].mul!, 1)}">×${fmt(ms[0].mul!)}</span><span>${ms[0].clergy ? `${pIcon('clergy')} <i>clergy only:</i> ` : ''}${
        ms.map(m => `${esc(m.name)} <span class="kd">${esc(KIND[m.kind])}</span>`).join(', ')}</span></div>`).join('')}</div>`);
  }
  const c = G[g].cond;
  if (c) out.push(`<div class="dsec">${term('Where')}${Object.entries(COND).filter(([k]) => c[k as keyof typeof c]).map(([k, label]) => {
    const v = c[k as keyof typeof c]!;
    const txt = Array.isArray(v) ? v.map(esc).join(', ') : typeof v === 'number' ? `×${fmt(v)}`
      : Object.entries(v).map(([w, n]) => `${esc(w)} <span class="${cls(n, 1)}">×${fmt(n)}</span>`).join(' · ');
    return `<div class="dm wh"><span class="v">${esc(label)}</span><span>${txt}</span></div>`;
  }).join('')}</div>`);
  if (events.length) out.push(`<div class="dsec">${term('Events')}${chipList(events.map(e =>
    `<div class="dm ev"><span class="v up">${signed(e.amt)}</span><span>${trig(e)}${e.months ? ` <i>for ${e.months} months</i>` : ''}</span></div>`), 10)}</div>`);
  return out.join('');
}

// what the header's age means for this good: pop demand shift, and whether anything can make it yet
function ageNote(g: string) {
  const a = AGE.v;
  if (!a) return '';
  const p = agePct(g, a), ps = producers[g] || [];
  return (p ? `<div class="cnote">${AGE_NOTE(a)} — every pop's demand <span class="${p > 0 ? 'up' : 'down'}">${pctTxt(p)}</span></div>` : '')
    + (ps.length && !ps.some(x => okR(x)) ? `<div class="cnote">No building can make it yet in Age ${ROMAN[a]}.</div>` : '');
}

function goodView(g: string) {
  const x = G[g];
  const ps = prod(g), cs = cons(g), ms = (maint[g] || []).filter(p => okR(p)), ds = demandUse[g] || [];
  const meta = [x.cat === 'raw_material' ? `Raw material — ${method(x.method)}` : 'Produced good',
    `Base price ${fmt(x.price)}`, x.slave ? 'Slave good' : ''].filter(Boolean);

  let made = x.cat === 'raw_material'
    ? `<div class="rec"><span class="tag">RGO</span>&nbsp;Extracted from locations whose raw material is ${esc(x.name)} (${esc(method(x.method))})</div>` : '';
  made += recipeGroups(ps);

  const pops = Object.entries(x.demand).map(([p, n]) =>
    `<tr><td>${pChip(p)}</td><td class="n">+${fmt(Math.max(0, n * (1 + agePct(g, AGE.v))))}</td></tr>`).join('');
  const muls = Object.entries(x.demandMul).map(([p, n]) =>
    `<tr><td>${pChip(p)}</td><td class="n">×${fmt(n)}</td></tr>`).join('');

  const demCard = (filter: (d: string) => boolean) => {
    const byCat: Record<string, string[]> = {};
    for (const d of ds.filter(filter)) (byCat[D[d].cat] ??= []).push(d);
    return Object.entries(byCat).map(([c, list]) => `<details ${list.length < 8 ? 'open' : ''}><summary>${esc(DCAT[c] || c)} (${list.length})</summary>
      ${list.map(d => {
        const who = demandUsers(d);
        return `<div class="rec">${who.length ? chipList(who) : `<span>${esc(pretty(d))}</span>`}<span class="arrow">needs</span>${gChip(g, D[d].in[g])}</div>`;
      }).join('')}</details>`).join('');
  };
  const unitDem = demCard(d => UNIT_CATS.has(D[d].cat)), dem = demCard(d => !UNIT_CATS.has(D[d].cat));

  return `<div class="title lg">${icon('goods', g, x.name)}<div><h2>${esc(x.name)}</h2><div class="meta">${meta.map(m => `<span>${esc(m)}</span>`).join('')}</div>${conNote(g)}${ageNote(g)}</div>${foodBar(g)}${conBar(g)}${popBar(g)}${filterBar(g)}</div>
  ${cards([
    [upChain(g), `<h4 class="in">Upstream<small>what it takes to make ${esc(x.name)}</small></h4>`, 'Raw material, extracted by RGOs.', 'big'],
    [downChain(g), `<h4 class="out">Downstream<small>what ${esc(x.name)} becomes</small></h4>`, 'Not processed into any other good.'],
    [upkeepGroups(g, ms), '<h4 class="gold">Building upkeep<small>amount is per building</small></h4>', 'Not used as building upkeep.'],
    [made, '<h4 class="out">Produced by</h4>', 'No building produces this.'],
    [recipeGroups(cs), '<h4 class="in">Input for production</h4>', 'Not an input for any production method.'],
    [pops || muls || x.food ? `${pops || muls ? `<table class="pops">${pops}${muls}</table>` : ''}
      ${x.food ? `<div class="rec">${APPLE}&nbsp;Provides ${fmt(x.food)} food per unit</div>` : ''}` : '', '<h4 class="pop">Consumed by pops</h4>', 'No direct pop demand.'],
    [demandShifts(g), '<h4 class="pop">What changes demand</h4>', 'Nothing changes its demand.'],
    [unitDem, '<h4 class="in">Army &amp; navy (recruit, upkeep, repair)</h4>', 'Not used by any unit.'],
    [dem, '<h4 class="gold">Construction &amp; other demand</h4>', 'None.'],
  ])}`;
}

function buildingView(bid: string) {
  const b = B[bid];
  const prod = b.recipes.filter(r => r.out), up = b.recipes.filter(r => !r.out);
  const outs = [...new Set(prod.map(r => r.out!))];
  const replaces = b.obsolete && B[b.obsolete] ? bChip(b.obsolete) : '';
  const replacedBy = Object.entries(B).filter(([, o]) => o.obsolete === bid).map(([k]) => bChip(k)).join('');
  const meta = [CATS[b.cat] || b.cat, b.pop ? `Employs ${P[b.pop] || b.pop}` : '', b.foreign ? 'Can be built abroad' : ''].filter(Boolean);
  const later = AGE.v && !availB(bid, AGE.v) ? (b.age > AGE.v ? `Unlocks in Age ${ROMAN[b.age]} (${esc(DATA.ages[b.age])}).`
    : `Replaced by ${(obsoletedBy[bid] || []).filter(o => B[o].age <= AGE.v!).map(o => esc(B[o].name)).join(', ')} by Age ${ROMAN[AGE.v]}.`) : '';
  const restrict = (later ? `<div class="cnote">${later}</div>` : '') + reqLines(b).map(([k, v]) => `<div class="cnote"><span class="tag">${esc(k)}</span>${esc(v)} only</div>`).join('')
    + (b.event ? `<div class="cnote">${EVENT_NOTE}</div>` : '');
  const cost = buildCost(b), build = cost ? Object.entries(cost.in).map(([g, n]) => gChip(g, n)).join('') : '';
  return `<div class="title lg">${icon('buildings', bid, b.name)}<div><h2>${esc(b.name)}</h2><div class="meta">${meta.map(m => `<span>${esc(m)}</span>`).join('')}</div>${restrict}</div></div>
  ${cards([
    [recipeGroups(prod.map(r => [bid, r])), '<h4 class="out">Production methods</h4>', 'Produces no goods.'],
    [outs.map(o => {
      const cs = [...new Set((consumers[o] || []).map(([k]) => k))];
      const pd = Object.keys(G[o].demand);
      const us = [...new Set((demandUse[o] || []).flatMap(d => unitsBy[d] || []))];
      const other = (demandUse[o] || []).filter(d => !unitsBy[d]).length;
      return `<div class="grp">${gChip(o)}
        ${cs.length ? `<div class="line"><span class="arrow">buildings</span>${chipList(cs.map(bChip))}</div>` : ''}
        ${pd.length ? `<div class="line"><span class="arrow">pops</span>${pd.map(p => p === 'all' ? '<span class="tag">all pops</span>' : p === 'upper' ? '<span class="tag">upper strata</span>' : pChip(p)).join('')}</div>` : ''}
        ${us.length ? `<div class="line"><span class="arrow">units</span>${chipList(us.map(uChip))}</div>` : ''}
        ${other ? `<div class="line"><a class="tag" href="#g/${o}">+${other} construction / upkeep / other demands →</a></div>` : ''}</div>`;
    }).join(''), '<h4 class="pop">Output is used by</h4>', '—'],
    [up.map(r => `<div class="rec">${r.name ? `<div class="rname">${esc(r.name)}</div>` : ''}${Object.entries(r.in).map(([g, n]) => gChip(g, n)).join('') || '<span class="none">none</span>'}</div>`).join(''), '<h4 class="gold">Upkeep</h4>', 'No goods upkeep.'],
    [build + (replaces ? `<div class="rec"><span class="arrow">Replaces</span>${replaces}</div>` : '')
      + (replacedBy ? `<div class="rec"><span class="arrow">Replaced by</span>${replacedBy}</div>` : ''), '<h4 class="gold">Construction</h4>', 'No goods cost listed.'],
    ...outs.map((o): Card => [downChain(o), `<h4 class="out">Downstream<small>what ${esc(G[o].name)} becomes</small></h4>`, `${esc(G[o].name)} is not processed into any other good.`]),
  ])}`;
}

function overview() {
  return `<div class="overview"><h2>Production Chains</h2>
  <p class="meta">Pick a good or building on the left, or search. Every icon is clickable. Data extracted from the installed game files.</p>
  <section class="card"><h4 class="gold">How to read it</h4>
  <div class="rec">${gChip('wool', 1)}<span class="arrow">→</span>${bChip('cloth_guild')}<span class="arrow">→</span>${gChip('cloth', 1)}</div>
  <p class="meta">Inputs (amount per building level) → building → output. Raw materials come from location RGOs; produced goods come from buildings.</p></section></div>`;
}

// ---- sidebar / routing -----------------------------------------------------
function sidebar() {
  const grp: Record<string, string[]> = {};
  for (const [g, x] of Object.entries(G)) {
    const k = x.cat === 'produced' ? 'Produced goods' : x.food ? 'Food' : `Raw — ${method(x.method)}`;
    (grp[k] ??= []).push(g);
  }
  const order = ['Produced goods', 'Food', ...Object.keys(grp).filter(k => k.startsWith('Raw')).sort()];
  let h = `<h3 title="Share of building types that need this good to be built">Construction materials</h3><div class="grid">${Object.keys(conUse).filter(g => pct(g) >= 5)
    .sort((a, b) => conUse[b] - conUse[a]).map(g => `<a href="#g/${g}" data-k="g/${g}" title="${esc(G[g].name)} — needed to build ${conUse[g]} of ${BUILT} building types">${icon('goods', g, G[g].name)}<span class="pct">${pct(g)}%</span></a>`).join('')}</div>`;
  h += order.filter(k => grp[k]).map(k => `<h3>${k}</h3><div class="grid">${grp[k].sort(k === 'Food' ? (a, b) => G[b].food! - G[a].food! : (a, b) => G[a].name.localeCompare(G[b].name))
    .map(g => `<a href="#g/${g}" data-k="g/${g}" title="${esc(G[g].name)}${k === 'Food' ? ` — ${fmt(G[g].food)} food` : ''}">${icon('goods', g, G[g].name)}${k === 'Food' ? `<span class="pct food">${fmt(G[g].food)}</span>` : ''}</a>`).join('')}</div>`).join('');
  const bg: Record<string, string[]> = {};
  for (const [bid, b] of Object.entries(B)) if (b.recipes.some(r => r.out)) (bg[CATS[b.cat] || b.cat] ??= []).push(bid);
  h += `<h3>Producing buildings</h3>` + Object.keys(bg).sort().map(c => `<details><summary>${esc(c)} (${bg[c].length})</summary><div class="blist sm">${bg[c].sort((a, b) => B[a].name.localeCompare(B[b].name))
    .map(b => `<a href="#b/${b}" data-k="b/${b}">${icon('buildings', b, B[b].name)}${esc(B[b].name)}</a>`).join('')}</div></details>`).join('');
  return h;
}

// distribute cards (in priority order) into N columns, each card going to the currently shortest column,
// so short cards fill the space under other short cards. A 'big' card (upstream) gets a column 1.6x as wide.
const COL = 340, GAP = 16, BIG = 1.6;
function layoutMasonry(root: HTMLElement) {
  for (const m of root.querySelectorAll<HTMLElement>('.masonry')) {
    const cards = [...m.querySelectorAll<HTMLElement>(':scope > .card, :scope > .mcol > .card')];
    const extra = cards.some(c => c.classList.contains('big')) ? (BIG - 1) * COL : 0;
    const n = Math.max(1, Math.min(cards.length, Math.floor((m.clientWidth + GAP - extra) / (COL + GAP))));
    const cols = Array.from({length: n}, () => Object.assign(document.createElement('div'), {className: 'mcol'}));
    m.replaceChildren(...cols);
    for (const c of cards) {
      const col = cols.reduce((a, b) => b.offsetHeight < a.offsetHeight ? b : a);
      if (c.classList.contains('big') && n > 1) col.style.flexGrow = String(BIG);
      col.append(c);
    }
  }
}

function route(side: HTMLElement, main: HTMLElement) {
  const [path, query = ''] = location.hash.slice(1).split('?');
  const [t, id] = path.split('/');
  const qs = new URLSearchParams(query);
  EMPTY = [];
  // the recipe filter comes from the URL (?rec=); the age is the global one from the header
  if (t === 'g') F.rec = qs.has('rec') ? +qs.get('rec')! : null;
  F.on = t === 'g'; F.g = t === 'g' ? id : F.g;
  const body = t === 'g' && G[id] ? goodView(id) : t === 'b' && B[id] ? buildingView(id) : overview();
  main.innerHTML = `<div class="view${keepScroll ? '' : ' enter'}">${body}${EMPTY.length ? `<div class="empty-note">${EMPTY.map(e => `<span>${e}</span>`).join('')}</div>` : ''}</div>`;
  layoutMasonry(main);
  if (!keepScroll) main.scrollTop = 0;
  keepScroll = false;
  side.querySelectorAll('.on').forEach(e => e.classList.remove('on'));
  const cur = side.querySelector(`[data-k="${t}/${id}"]`);
  if (cur) { cur.classList.add('on'); cur.closest('details')?.setAttribute('open', ''); }
}

// renders into the page's sidebar and main panes; returns a cleanup function
export function mountProduction(side: HTMLElement, main: HTMLElement) {
  side.innerHTML = sidebar();
  const onClick = (e: MouseEvent) => {
    const t = e.target as Element;
    const h = t.closest('section.card > h4');
    if (h) return h.parentElement!.classList.toggle('shut');
    const b = t.closest<HTMLElement>('button[data-f]');
    if (!b) return;
    const v = +b.dataset.v!;
    F.rec = F.rec === v ? null : v;  // click the active one again to clear
    keepScroll = true;
    location.hash = `g/${F.g}` + filterQuery();
  };
  let resizeT: ReturnType<typeof setTimeout>;
  const onResize = () => { clearTimeout(resizeT); resizeT = setTimeout(() => layoutMasonry(main), 100); };
  const onHash = () => route(side, main);
  const onAge = () => { keepScroll = true; route(side, main); };
  main.addEventListener('click', onClick);
  addEventListener('resize', onResize);
  addEventListener('hashchange', onHash);
  addEventListener('agechange', onAge);
  route(side, main);
  return () => { main.removeEventListener('click', onClick); removeEventListener('resize', onResize); removeEventListener('hashchange', onHash); removeEventListener('agechange', onAge); };
}

// ---- search ----------------------------------------------------------------
export const searchNames = [...Object.values(G).map(x => x.name), ...Object.values(B).map(b => b.name), ...Object.values(P)];
export function searchGo(raw: string) {
  const q = raw.trim().toLowerCase();
  const g = Object.keys(G).find(k => G[k].name.toLowerCase() === q) || Object.keys(G).find(k => G[k].name.toLowerCase().includes(q));
  const b = !g && (Object.keys(B).find(k => B[k].name.toLowerCase() === q) || Object.keys(B).find(k => B[k].name.toLowerCase().includes(q)));
  const p = Object.keys(P).find(k => P[k].toLowerCase() === q);
  if (p) location.hash = `p/${p}`; else if (g) location.hash = `g/${g}`; else if (b) location.hash = `b/${b}`;
}

// ---- tooltip content: rich cards for goods / buildings ------------------------
const tRow = (label: string, v: string | number | null, ic = '') => `<div class="tr">${ic}<span>${label}</span>${v != null ? `<span class="v">${v}</span>` : ''}</div>`;
const tHead = (ic: string, name: string, sub?: string) => `<div class="th">${ic}<div><b>${esc(name)}</b>${sub ? `<i>${esc(sub)}</i>` : ''}</div></div>`;
function goodTip(g: string) {
  const x = G[g], ps = producers[g] || [], cs = consumers[g] || [];
  const top = Object.entries(x.demand).sort((a, b) => b[1] - a[1])[0];
  return tHead(icon('goods', g, x.name), x.name, x.cat === 'raw_material' ? `Raw material — ${method(x.method)}` : 'Produced good')
    + `<div class="tb">${tRow('Base price', fmt(x.price))}
    ${x.food ? tRow('Food per unit', fmt(x.food), APPLE) : ''}
    ${conUse[g] ? tRow('Needed to construct', `${conUse[g]} buildings (${pct(g)}%)`) : ''}
    ${top ? tRow(`Biggest pop consumer: ${esc(pName(top[0]))}`, '+' + fmt(top[1]), pIcon(top[0])) : ''}
    ${tRow('Made by', [x.cat === 'raw_material' && 'RGO', ps.length && `${new Set(ps.map(p => p[0])).size} buildings`].filter(Boolean).join(' + ') || '—')}
    ${tRow('Input for', `${new Set(cs.map(p => p[0])).size} buildings`)}</div>`
    + (CORE.includes(g) ? '<div class="tn">Core construction material — its price feeds into building costs.</div>' : '');
}
// "Nation: Muscovy or Russia" lines from build.py's identity requirements
const reqLines = (b: {req: [string, string][]}) => Object.entries(b.req.reduce((m, [k, v]) => ((m[k] ??= []).push(v), m), {} as Record<string, string[]>)).map(([k, vs]) => [k, vs.join(' or ')]);
const EVENT_NOTE = 'Not built through normal construction — granted by events or decisions';
function buildingTip(bid: string) {
  const b = B[bid], outs = [...new Set(b.recipes.filter(r => r.out).map(r => r.out!))];
  return tHead(icon('buildings', bid, b.name), b.name, CATS[b.cat] || b.cat)
    + `<div class="tb">${b.pop ? tRow(`Employs ${esc(P[b.pop] || b.pop)}`, null, icon('pops', b.pop, P[b.pop] || b.pop)) : ''}
    ${tRow('Available from', `Age ${ROMAN[b.age]} — ${esc(DATA.ages[b.age] || '')}`)}
    ${outs.length ? tRow('Produces', outs.map(o => icon('goods', o, G[o]?.name || o)).join('')) : ''}
    ${reqLines(b).map(([k, v]) => tRow(`<span class="req">${esc(k)}</span>`, esc(v))).join('')}
    ${tRow('Production methods', b.recipes.length)}
    ${b.obsolete && B[b.obsolete] ? tRow('Replaces', esc(B[b.obsolete].name)) : ''}
    ${obsoletedBy[bid]?.length ? tRow('Replaced by', obsoletedBy[bid].map(o => esc(B[o].name)).join(', ')) : ''}</div>`
    + (b.event ? `<div class="tn">${EVENT_NOTE}.</div>` : '');
}
// rich tooltip for goods / building links, '' for anything else
export function linkTip(el: Element) {
  const h = el.getAttribute('href') || '';
  if (h.startsWith('#g/') && G[h.slice(3)]) return goodTip(h.slice(3));
  if (h.startsWith('#b/') && B[h.slice(3)]) return buildingTip(h.slice(3));
  return '';
}
