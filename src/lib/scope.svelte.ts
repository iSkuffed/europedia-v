// The nation the user is "viewing as", shared by every page and remembered between visits. null = Global view.
// ctx arrives once public/scope.json has loaded; pages hide what fits(x.who, ctx) says that country can't have.
import type { Ctx } from './fit';
interface ScopeData { names: Record<string, string>; countries: Record<string, Omit<Ctx, 'tag'> & { name: string }> }
let cache: Promise<ScopeData> | undefined;
export const loadScope = (): Promise<ScopeData> => cache ??= fetch('scope.json').then(r => r.json());

export const SCOPE = $state<{ tag: string | null; name: string; ctx: Ctx | null; names: Record<string, string> }>({ tag: null, name: '', ctx: null, names: {} });
export function setScope(tag: string | null) {
  SCOPE.tag = tag; SCOPE.ctx = null;
  if (tag) localStorage.setItem('scope', tag); else localStorage.removeItem('scope');
  if (tag) loadScope().then(d => {
    const c = d.countries[tag];
    if (SCOPE.tag !== tag) return;
    if (!c) return setScope(null);  // a tag from an older data set
    SCOPE.name = c.name; SCOPE.names = d.names; SCOPE.ctx = { tag, ...c };
    dispatchEvent(new Event('scopechange'));  // for the string-rendered Production page
  });
  else dispatchEvent(new Event('scopechange'));
}
const saved = localStorage.getItem('scope');
if (saved) setScope(saved);
