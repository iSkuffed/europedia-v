// Does a `who` condition list (privileges.py / advances.py) let a given country have the thing? 'maybe' = the data
// can't tell (unlocks, events, reforms it could adopt, free-text conditions), so a scoped page keeps it.

// public/scope.json (scope.py): a country's culture, religion, government and land, as game ids
export interface Ctx { tag: string; c?: string; cg?: string[]; lang?: string; r?: string; rg?: string; gov?: string; over?: string; cap?: string[]; geo?: string[] }
export interface WhoItem { type: string; kind?: string; ids?: string[]; not?: boolean | number; cap?: number; any?: WhoItem[]; all?: WhoItem[]; parts?: WhoItem[] }  // parts: advances.py's any/all
export type Fit = 'yes' | 'no' | 'maybe';

const has = (ids: string[] | undefined, xs: (string | undefined)[] | undefined) => !!ids && !!xs && xs.some(x => x && ids.includes(x));
const yn = (b: boolean): Fit => b ? 'yes' : 'no';

function one(it: WhoItem, c: Ctx): Fit {
  const k = it.kind ?? '';
  switch (it.type) {
    case 'any': {
      const fs = (it.any ?? it.parts ?? []).map(x => item(x, c));
      return fs.includes('yes') ? 'yes' : fs.length && fs.every(f => f === 'no') ? 'no' : 'maybe';
    }
    case 'all': return fits(it.all ?? it.parts, c);
    case 'tag': return k === 'subject of' ? yn(has(it.ids, [c.over])) : yn(has(it.ids, [c.tag]));
    case 'culture': return k === 'culture group' ? yn(has(it.ids, c.cg)) : yn(has(it.ids, [c.c]));
    case 'culture_group': return yn(has(it.ids, c.cg));
    case 'language': return yn(has(it.ids, [c.lang]));
    case 'religion': return k === 'religion group' ? yn(has(it.ids, [c.rg])) : k === 'religion' || !k ? yn(has(it.ids, [c.r])) : 'maybe';
    case 'religion_group': return yn(has(it.ids, [c.rg]));
    // ids may be any map level, so test against all of them: the capital's when the condition is about the capital
    case 'region': case 'area': case 'sub_continent': case 'continent':
      return yn(has(it.ids, it.cap || k.startsWith('capital') ? c.cap : c.geo));
    case 'government': return k === 'reform' ? 'maybe' : yn(has(it.ids, [c.gov]));
    case 'status': return it.ids?.length === 1 && it.ids[0] === 'subject' ? yn(!!c.over) : 'maybe';
    default: return 'maybe';  // unlock, other, reform, estate, societal, subject_type, dlc, ...
  }
}

const item = (it: WhoItem, c: Ctx): Fit => {
  const f = one(it, c);
  return !it.not ? f : f === 'yes' ? 'no' : f === 'no' ? 'yes' : 'maybe';
};

export function fits(who: WhoItem[] | undefined, c: Ctx): Fit {
  let out: Fit = 'yes';
  for (const it of who ?? []) {
    const f = item(it, c);
    if (f === 'no') return 'no';
    if (f === 'maybe') out = 'maybe';
  }
  return out;
}
