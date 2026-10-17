<script lang="ts">
  // Part-to-whole donut: the biggest five shares plus "Other", with a legend. Colours are the dataviz
  // categorical slots, checked against the card background; `order` pins a colour to each key
  // (pop classes), otherwise colours go by size. Values are thousands of people.
  let { title, parts, order, label = (k: string) => k, iconOf }: {
    title: string; parts: Record<string, number>; order?: string[]; label?: (k: string) => string; iconOf?: (k: string) => string;
  } = $props();
  const SLOTS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9'], OTHER = '#6b7280';
  const R = 42, W = 14;  // ring radius and width in the 100×100 box

  const segs = $derived.by(() => {
    const all = Object.entries(parts).filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]);
    const total = all.reduce((s, e) => s + e[1], 0);
    const shown = all.length <= 6 ? all : all.slice(0, 5);
    const rest = all.slice(shown.length);
    const out = shown.map(([k, n], i) => ({k, name: label(k), n, color: SLOTS[order ? order.indexOf(k) : i] ?? OTHER}));
    if (rest.length) out.push({k: '', name: `Other (${rest.length})`, n: rest.reduce((s, e) => s + e[1], 0), color: OTHER});
    let a = 0;
    return {total, count: all.length, list: out.map(s => ({...s, f: s.n / total, a0: a, a1: a += s.n / total}))};
  });
  // arc from fraction a0 to a1, clockwise from 12 o'clock
  const pt = (f: number) => [50 + R * Math.sin(2 * Math.PI * f), 50 - R * Math.cos(2 * Math.PI * f)].map(v => v.toFixed(2)).join(' ');
  const arc = (a0: number, a1: number) => `M ${pt(a0)} A ${R} ${R} 0 ${a1 - a0 > 0.5 ? 1 : 0} 1 ${pt(a1)}`;
  const pct = (f: number) => f >= 1 ? '100%' : f > 0.99 ? Math.min(99.9, f * 100).toFixed(1) + '%' : f >= 0.1 ? Math.round(f * 100) + '%' : f >= 0.001 ? (f * 100).toFixed(1) + '%' : '<0.1%';
  const people = (k: number) => k >= 1000 ? (k / 1000).toFixed(2) + 'M' : k >= 1 ? Math.round(k) + 'k' : Math.round(k * 1000).toLocaleString('en');
</script>

<figure class="donut">
  <figcaption>{title}</figcaption>
  <svg viewBox="0 0 100 100" role="img" aria-label="{title}: {segs.list.map(s => `${s.name} ${pct(s.f)}`).join(', ')}">
    {#each segs.list as s (s.k)}
      {#if segs.list.length === 1}<circle cx="50" cy="50" r={R} stroke={s.color} stroke-width={W} fill="none" data-tip="{s.name}: {people(s.n)} people, 100%" />
      {:else}<path d={arc(s.a0, s.a1)} stroke={s.color} stroke-width={W} fill="none" data-tip="{s.name}: {people(s.n)} people, {pct(s.f)}" />{/if}
    {/each}
    <!-- 2px gaps in the surface colour between slices -->
    {#if segs.list.length > 1}{#each segs.list as s (s.k)}<line x1="50" y1={50 - R - W / 2 - 1} x2="50" y2={50 - R + W / 2 + 1} transform="rotate({s.a0 * 360} 50 50)" class="gap" />{/each}{/if}
    <text x="50" y="47" class="tot">{segs.count}</text><text x="50" y="60" class="sub">{(segs.count === 1 ? title.replace(/(ss)es$|s$/, "$1") : title).toLowerCase()}</text>
  </svg>
  <ul>
    {#each segs.list as s (s.k)}
      <li data-tip="{s.name}: {people(s.n)} people"><i style="background:{s.color}"></i>{#if iconOf && s.k}{@html iconOf(s.k)}{/if}<span class="nm">{s.name}</span><b>{pct(s.f)}</b></li>
    {/each}
  </ul>
</figure>

<style>
  .donut { margin: 0; min-width: 0; }
  figcaption { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: var(--dim); margin-bottom: 4px; }
  svg { display: block; width: 120px; height: 120px; margin: 0 auto 6px; overflow: visible; }
  path, circle { cursor: default; transition: stroke-width .12s; }
  path:hover, circle:hover { stroke-width: 18px; }
  .gap { stroke: #171e27; stroke-width: 1.5; pointer-events: none; }
  .tot { fill: var(--text); font-size: 16px; font-weight: 600; text-anchor: middle; dominant-baseline: central; }
  .sub { fill: var(--dim); font-size: 7px; letter-spacing: .5px; text-anchor: middle; dominant-baseline: central; }
  ul { list-style: none; margin: 0; padding: 0; font-size: 13px; }
  li { display: flex; align-items: center; gap: 6px; padding: 1px 0; }
  li i { flex: none; width: 10px; height: 10px; border-radius: 2px; }
  li :global(img.ic) { width: 18px; height: 18px; }
  .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li b { color: var(--dim); font-weight: 500; font-variant-numeric: tabular-nums; }
</style>
