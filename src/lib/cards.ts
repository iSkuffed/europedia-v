// Hover cards for estate privileges (links to #e/<id>) and government reforms ([data-reform]):
// the game's art, name, modifiers, who can get it and the description, in the app tooltip.
import { esc } from './production';

type Mod = [string, string];
interface PrivLite { id: string; name: string; estateName: string; desc?: string; whoText: string; groups: { kind: string; when?: string; mods: Mod[]; estate: Mod[] }[] }
interface Reform { name: string; desc?: string; mods: Mod[]; major?: boolean }

let privCache: Promise<{ privileges: PrivLite[] }> | undefined;
export const loadPrivileges = (): Promise<{ privileges: PrivLite[] }> => privCache ??= fetch('privileges.json').then(r => r.json());
let refCache: Promise<Record<string, Reform>> | undefined;
export const loadReforms = () => refCache ??= fetch('reforms.json').then(r => r.ok ? r.json() : {});

// filled once loaded, so the (synchronous) tooltip can read them
let P: Record<string, PrivLite> = {}, R: Record<string, Reform> = {};
export function preloadCards() {
  loadPrivileges().then(d => P = Object.fromEntries(d.privileges.map(p => [p.id, p])));
  loadReforms().then(d => R = d);
}

const rows = (mods: Mod[]) => mods.map(([l, v]) => `<div class="tr"><span>${esc(l)}</span><span class="v">${esc(v)}</span></div>`).join('');
const head = (src: string, title: string, sub: string) =>
  `<div class="th"><img class="tart" src="${src}" alt=""><div><b>${esc(title)}</b><i>${esc(sub)}</i></div></div>`;
const note = (s?: string) => s ? `<div class="tn">${esc(s)}</div>` : '';

export function cardTip(el: Element): string {
  const a = el.closest('a[href^="#e/"]'), rid = el.closest<HTMLElement>('[data-reform]')?.dataset.reform;
  if (a) {
    const p = P[decodeURIComponent(a.getAttribute('href')!.slice(3))];
    if (!p) return '';
    const body = p.groups.map(g => (g.when || g.kind !== 'country' ? `<div class="tg">${esc(g.when ?? 'In each location')}</div>` : '') + rows(g.mods) + rows(g.estate)).join('');
    return head(`icons/privileges/${p.id}.webp`, p.name, `${p.estateName} privilege`) + `<div class="tb">${body}</div>`
      + (p.whoText && p.whoText !== 'Everyone' ? `<div class="tt"><span class="tw">Who can get it</span> ${esc(p.whoText)}</div>` : '') + note(p.desc);
  }
  const r = rid && R[rid];
  if (!r) return '';
  return head(`icons/reforms/${rid}.webp`, r.name, r.major ? 'Major government reform' : 'Government reform')
    + (r.mods.length ? `<div class="tb">${rows(r.mods)}</div>` : '') + note(r.desc);
}
