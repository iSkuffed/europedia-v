// Nations at the 1337 start (public/nations.json, written by build.py) and what their land suggests.
import { DATA } from './data';
import { popDemand } from './production';

export interface Nation {
  name: string; cap: number | null; locs: number[]; color: [number, number, number] | null;
  pops: Record<string, number>;  // starting pops in thousands, by type
  culture: string | null; religion: string | null; rank: string;
  over: [string, string] | null;  // overlord tag, subject type
}
// location: name, raw good, map x, map z (north is bigger), owner tag, rank (0 rural / 1 town / 2 city), area index
export type Loc = [string, string, number, number, string, number, number];
export interface NationData { locs: Loc[]; areas: string[]; countries: Record<string, Nation> }

let cache: Promise<NationData> | undefined;
export const loadNations = () => cache ??= fetch('nations.json').then(r => r.json());

// public/unique.json (unique.py): reforms, privileges, laws, units, advances... locked to a few tags
export interface Unique { kind: string; id: string; name: string; desc?: string; shared?: string[]; estate?: string; law?: string; age?: string; gated?: boolean; mods: [string, string][] }
let uniqueCache: Promise<Record<string, Unique[]>> | undefined;
export const loadUnique = () => uniqueCache ??= fetch('unique.json').then(r => r.ok ? r.json() : {});

// public/map.png: one pixel per 8x8 map units, red * 256 + green = 0 water, 1 wasteland, i + 2 = locs[i]
export const MAP_SCALE = 8;
let mapCache: Promise<{w: number; h: number; c: Uint16Array}> | undefined;
export const loadMap = () => mapCache ??= fetch('map.png').then(r => r.blob())
  .then(b => createImageBitmap(b, {colorSpaceConversion: 'none', premultiplyAlpha: 'none'})).then(bm => {
    const cv = document.createElement('canvas'), w = cv.width = bm.width, h = cv.height = bm.height;
    const ctx = cv.getContext('2d', {willReadFrequently: true})!;
    ctx.drawImage(bm, 0, 0);
    const d = ctx.getImageData(0, 0, w, h).data, c = new Uint16Array(w * h);
    for (let i = 0; i < c.length; i++) c[i] = d[4 * i] * 256 + d[4 * i + 1];
    return {w, h, c};
  });

const {goods: G, buildings: B} = DATA;
const W = 16384;  // the map wraps east-west
export const dist = (a: Loc, b: Loc) => { const dx = Math.abs(a[2] - b[2]); return Math.hypot(Math.min(dx, W - dx), a[3] - b[3]); };
export const UPPER = ['nobles', 'clergy', 'burghers'];

export const subjectsOf = (N: NationData, tag: string) => Object.keys(N.countries).filter(t => N.countries[t].over?.[0] === tag);

// raw goods -> what you can make from them. A recipe is in reach when you have most of its inputs;
// goods you can fully make count as "have" for the next tier, with the amount of their scarcest input.
export interface Reach { share: number; building: string; missing: string[] }
function reachFrom(rgo: Record<string, number>) {
  const amt: Record<string, number> = {...rgo}, reach: Record<string, Reach> = {};
  const have = {has: (g: string) => g in amt, add: (g: string, n: number) => amt[g] = Math.max(amt[g] ?? 0, n)};
  for (let grew = true; grew;) {
    grew = false;
    for (const [bid, b] of Object.entries(B)) {
      if (b.event) continue;
      for (const r of b.recipes) {
        if (!r.out || have.has(r.out) || G[r.out]?.cat !== 'produced') continue;
        const ins = Object.keys(r.in), missing = ins.filter(g => !have.has(g));
        if (!ins.length) continue;
        const share = 1 - missing.length / ins.length;
        if (share > (reach[r.out]?.share ?? 0)) reach[r.out] = {share, building: bid, missing};
        if (!missing.length) { have.add(r.out, Math.min(...ins.map(g => amt[g]))); grew = true; }
      }
    }
  }
  return {amt, reach};
}

// How much one pop of class p stands out as a buyer of good g against the other upper classes:
// fur is nobles 0.5 vs 0.05 per pop, so nobles get the cap of 3; goods every class buys alike give 0.
function tilt(g: string, p: string) {
  const d = UPPER.map(q => popDemand(g, q)), i = UPPER.indexOf(p), other = Math.max(...d.filter((_, j) => j !== i));
  const t = d[i] ? (other ? Math.min(3, d[i] / other - 1) : 3) : 0;
  return t < 0.25 ? 0 : t;
}

// each good's share of the value of everything you could make (amount x base price)
function valueShares(amt: Record<string, number>) {
  const total = Object.entries(amt).reduce((s, [g, n]) => s + n * G[g].price, 0) || 1;
  return Object.fromEntries(Object.entries(amt).map(([g, n]) => [g, n * G[g].price / total]));
}
let worldShares: Record<string, number> | undefined;  // the same for all land owned in 1337
function world(N: NationData) {
  if (!worldShares) {
    const rgo: Record<string, number> = {};
    for (const l of N.locs) if (l[4] && G[l[1]]) rgo[l[1]] = (rgo[l[1]] || 0) + 1;
    worldShares = valueShares(reachFrom(rgo).amt);
  }
  return worldShares;
}

export function analyse(N: NationData, tag: string, withSubjects: boolean) {
  const c = N.countries[tag];
  const mine = new Set([tag, ...(withSubjects ? subjectsOf(N, tag) : [])]);
  const locs = [...mine].flatMap(t => N.countries[t].locs);
  const rgo: Record<string, number> = {};
  for (const i of locs) { const g = N.locs[i][1]; if (G[g]) rgo[g] = (rgo[g] || 0) + 1; }
  const {amt, reach} = reachFrom(rgo);

  // specialties: goods that are a bigger part of what you can make than of what the world can make
  const mineShares = valueShares(amt), w = world(N);
  const spec = Object.keys(amt).map(g => ({g, lq: mineShares[g] / (w[g] || 1e-9)})).filter(x => x.lq > 1).sort((a, b) => b.lq - a.lq);
  // each class: your surplus of the goods its pops stand out as buyers of (share of your output above the
  // world's, weighted by how clearly they stand out), against how big those goods are worldwide. Only
  // surpluses count, so lacking some noble goods doesn't cancel a fur surplus; the floor keeps tiny
  // categories (burghers stand out only for pottery) from winning on noise.
  const classes = UPPER.map(p => {
    const supplied = Object.keys(amt).map(g => ({g, v: Math.max(0, mineShares[g] - (w[g] || 0)) * tilt(g, p) / 3})).filter(x => x.v > 0).sort((a, b) => b.v - a.v);
    const base = Object.keys(w).reduce((s, g) => s + w[g] * tilt(g, p) / 3, 0);
    const almost = Object.keys(G).filter(g => !(g in amt) && (reach[g]?.share ?? 0) >= 0.5 && tilt(g, p) > 0)
      .map(g => ({g, v: G[g].price * tilt(g, p)})).sort((a, b) => b.v - a.v);
    return {p, lean: supplied.reduce((s, x) => s + x.v, 0) / Math.max(0.05, base), supplied, almost};
  });

  // raw goods near the capital that you don't own, nearest first per good
  const capL = c.cap != null ? N.locs[c.cap] : null;
  const near = (radius: number) => {
    const by: Record<string, {n: number; best: Loc; d: number}> = {};
    if (!capL) return [];
    for (const l of N.locs) {
      if (mine.has(l[4]) || !G[l[1]]) continue;
      const d = dist(l, capL);
      if (d > radius) continue;
      const e = by[l[1]] ??= {n: 0, best: l, d};
      e.n++;
      if (d < e.d) { e.best = l; e.d = d; }
    }
    return Object.entries(by).map(([g, e]) => ({g, ...e, isNew: !rgo[g]}))
      .sort((a, b) => +b.isNew - +a.isNew || G[b.g].price - G[a.g].price || a.d - b.d);
  };
  return {c, mine, locs, rgo, amt, reach, classes, spec, near};
}
