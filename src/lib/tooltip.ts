// EU5-style tooltip for the whole app: links get a rich card from `linkTip`,
// anything with a title / data-tip gets its text in the same frame.
import { esc } from './production';

export function initTooltips(linkTip: (el: Element) => string) {
  const tip = Object.assign(document.createElement('div'), {id: 'tip'});
  document.body.append(tip);
  const tipFor = (el: HTMLElement) => linkTip(el) || (el.dataset.tip ? `<div class="tt">${esc(el.dataset.tip)}</div>` : '');
  const place = (e: MouseEvent) => {
    const r = tip.getBoundingClientRect(), x = e.clientX + 18, y = e.clientY + 18;
    tip.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + 'px';
    tip.style.top = Math.max(8, y + r.height > innerHeight ? e.clientY - r.height - 12 : y) + 'px';
  };
  let tipEl: HTMLElement | null = null;
  document.addEventListener('mouseover', e => {
    const t = e.target as HTMLElement;
    // a goods/building/privilege link or reform card wins over the name-only title on its own icon
    const el = t.closest<HTMLElement>('a[href^="#g/"], a[href^="#b/"], a[href^="#e/"], [data-reform]') || t.closest<HTMLElement>('[title], [data-tip]');
    if (t !== el && t.title) { t.dataset.tip = t.title; t.removeAttribute('title'); }
    if (el === tipEl) return;  // still on the same entry: keep the tooltip exactly as first shown
    tipEl = el;
    if (el?.title) { el.dataset.tip = el.title; el.removeAttribute('title'); }  // suppress the native tooltip
    const html = el && tipFor(el);
    if (!html) { tip.style.display = 'none'; return; }
    // measure at the left edge so the natural size isn't squeezed by the viewport, then lock it
    Object.assign(tip.style, {display: 'block', width: '', left: '0px', top: '0px'});
    tip.innerHTML = html;
    tip.style.width = tip.getBoundingClientRect().width + 'px';
    place(e);
  });
  document.addEventListener('mousemove', e => { if (tip.style.display !== 'none') place(e); });
  addEventListener('hashchange', () => { tip.style.display = 'none'; tipEl = null; });
}
