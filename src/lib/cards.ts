// Hover cards for estate privileges (links to #e/<id>), government reforms ([data-reform]) and advances (a.adv to #r/<id>):
// the game's art, name, modifiers, who can get it and the description, in the app tooltip.
import { esc, ROMAN } from './production';

type Mod = [string, string];
interface PrivLite { id: string; name: string; estateName: string; desc?: string; whoText: string; groups: { kind: string; when?: string; mods: Mod[]; estate: Mod[] }[] }
interface Reform { name: string; desc?: string; mods: Mod[]; major?: boolean }

let privCache: Promise<{ privileges: PrivLite[]; reforms: { id: string; name: string }[] }> | undefined;
export const loadPrivileges = (): Promise<{ privileges: PrivLite[]; reforms: { id: string; name: string }[] }> => privCache ??= fetch('privileges.json').then(r => r.json());
interface AdvLite { id: string; name: string; age: number; icon?: string; mods?: Mod[]; unlocks?: [string, string, string][]; whoText?: string }
// public/advances.json (advances.py); typed in Research.svelte
let advCache: Promise<any> | undefined;
export const loadAdvances = () => advCache ??= fetch('advances.json').then(r => r.json()).then(d => {
  A = Object.fromEntries((d.advances as AdvLite[]).map(a => [a.id, a])); AGES = d.ages; return d;
});
let refCache: Promise<Record<string, Reform>> | undefined;
export const loadReforms = () => refCache ??= fetch('reforms.json').then(r => r.ok ? r.json() : {});

// filled once loaded, so the (synchronous) tooltip can read them
let P: Record<string, PrivLite> = {}, R: Record<string, Reform> = {}, A: Record<string, AdvLite> = {}, AGES: Record<string, string> = {};
export function preloadCards() {
  loadPrivileges().then(d => P = Object.fromEntries(d.privileges.map(p => [p.id, p])));
  loadReforms().then(d => R = d);
}

const rows = (mods: Mod[]) => mods.map(([l, v]) => `<div class="tr"><span>${esc(l)}</span><span class="v">${esc(v)}</span></div>`).join('');
const head = (src: string, title: string, sub: string) =>
  `<div class="th"><img class="tart" src="${src}" alt=""><div><b>${esc(title)}</b><i>${esc(sub)}</i></div></div>`;
const note = (s?: string) => s ? `<div class="tn">${esc(s)}</div>` : '';

export function cardTip(el: Element): string {
  const ra = el.closest('a.adv[href^="#r/"]');
  if (ra) {
    const v = A[decodeURIComponent(ra.getAttribute('href')!.slice(3))];
    if (!v) return '';
    return `<div class="th">${v.icon ? `<img class="ic" src="icons/advances/${v.icon}.png" alt="">` : ''}<div><b>${esc(v.name)}</b><i>Age ${ROMAN[v.age]}: ${esc(AGES[v.age] ?? '')}</i></div></div>`
      + (v.mods?.length ? `<div class="tb">${rows(v.mods)}</div>` : '')
      + (v.unlocks?.length ? `<div class="tt"><span class="tw">Unlocks</span> ${esc(v.unlocks.map(u => u[2]).join(', '))}</div>` : '') + (v.whoText ? `<div class="tt"><span class="tw">Only for</span> ${esc(v.whoText)}</div>` : '');
  }
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
