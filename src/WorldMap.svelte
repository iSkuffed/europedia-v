<script lang="ts">
  // The world map at the 1337 start, with the game's map modes: political, culture, religion, raw goods,
  // population, development, settlements, topography, vegetation, climate; rivers and country names drawn over them.
  // Colours are the game's: its named colours and map-mode defines, the water and gradients matched to screenshots.
  import { DATA } from './lib/data';
  import { loadNations, type NationData } from './lib/nations';
  import { loadWorld, loadMapInfo, loadRivers, seaDistance, WORLD_SCALE, type MapInfo } from './lib/world';
  import MapCanvas, { type Raster, type View } from './MapCanvas.svelte';

  const G = DATA.goods;
  let N = $state<NationData>(), M = $state<Raster>(), I = $state<MapInfo>(), R = $state<Path2D[]>();
  loadNations().then(d => N = d);
  loadWorld().then(m => M = m);
  loadMapInfo().then(d => I = d);

  const MODES = [['political', 'Political', 'political'], ['culture', 'Culture', 'culture'], ['religion', 'Religion', 'location_religion'],
    ['goods', 'Raw goods', 'raw_material'], ['pop', 'Population', 'population'], ['dev', 'Development', 'development'], ['rank', 'Settlements', 'country_rank'],
    ['topo', 'Topography', 'topography'], ['veg', 'Vegetation', 'vegetation'], ['climate', 'Climate', 'climate']] as const;
  type Mode = typeof MODES[number][0];
  const saved = JSON.parse(localStorage.getItem('worldmap') ?? '{}');
  let mode = $state<Mode>(MODES.some(m => m[0] === saved.mode) ? saved.mode : 'political');
  let rivers = $state<boolean>(saved.rivers ?? true), names = $state<boolean>(saved.names ?? true);
  let good = $state<string | null>(null);
  let pan = $state<{cx: number; cy: number; s: number} | null>(saved.pan ?? null);
  $effect(() => localStorage.setItem('worldmap', JSON.stringify({mode, rivers, names, pan})));
  $effect(() => { if (rivers && !R) loadRivers().then(r => R = r); });

  let W = $state(0), innerHeight = $state(800);
  const H = $derived(Math.max(420, innerHeight - 120));
  const fit = $derived(M ? {s: Math.max(W / M.w, H / M.h), cx: M.w / 2, cy: M.h / 2} : {s: 1, cx: 0, cy: 0});  // the whole world, filling the frame
  const view = $derived.by((): View => { const {cx, cy, s} = pan ?? fit; return {s, x0: cx - W / s / 2, y0: cy - H / s / 2}; });
  let hover = $state<{x: number; y: number; i: number} | null>(null), picked = $state<number | null>(null);

  // raster position of a location (x unwrapped near `near` when given)
  const lx = (i: number) => N!.locs[i][2] / WORLD_SCALE, ly = (i: number) => (8192 - N!.locs[i][3]) / WORLD_SCALE;

  // ---- colours ---------------------------------------------------------------------------------------------
  const hex = (s: string) => [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16));
  const mix = (a: number[], b: number[], t: number) => a.map((v, k) => Math.round(v + (b[k] - v) * t));
  const hsv = (h: number, s: number, v: number) => [5, 3, 1].map(n => { const k = (n + h * 6) % 6; return Math.round(255 * (v - v * s * Math.max(0, Math.min(k, 4 - k, 1)))); });
  const WASTE = hex('#3a3833'), FREE = hex('#57554d'), DIM = hex('#2a2e33');
  // the game lights its flat map-mode colours over the terrain, which warms and lifts them; a fixed tint stands in
  const lit = (c: number[]) => mix(c, hex('#b4966a'), 0.28);
  // NMapColors MAP_COLOR_MIN .. MAX (defines/graphic/00_graphics.txt): black, dark red, gold, green, bright green
  const GRAD = [hsv(0, .85, .015), hsv(0, .85, .34), hsv(.13, .95, .75), hsv(.31, .9, .6), hsv(.31, 1, 1)];
  const grad = (t: number) => { const f = Math.min(1, Math.max(0, t)) * 4, k = Math.min(3, Math.floor(f)); return lit(mix(GRAD[k], GRAD[k + 1], f - k)); };
  // population on the game's log scale: 1,000 people at the bottom, x4.7934 a step (the legend's 4,793 / 22,977 / 110K / 527K)
  const POP_STOPS = [0, 1, 2, 3, 4].map(k => 1000 * 527.96 ** (k / 4));
  const popT = (p: number) => p > 1000 ? Math.log(p / 1000) / Math.log(527.96) : 0;
  const RANK_NAME = ['Rural', 'Town', 'City', 'Megalopolis'];
  // water by distance from land (half raster px): the shallows' cyan glow down to the open ocean; 255 = off the map
  const SEA_STOPS: [number, string][] = [[0, '#64ccd9'], [4, '#4cb4d8'], [10, '#3592c8'], [20, '#2b74b2'], [40, '#2a62a8'], [80, '#2b4f92']];
  const SHALLOW = hex('#64ccd9'), OFFMAP = hex('#2a2520');
  const seaPal = new Uint8ClampedArray(256 * 3);
  for (let d = 0; d < 255; d++) {
    const j = SEA_STOPS.findIndex(s => s[0] > d), [a, b] = j < 0 ? [SEA_STOPS.at(-1)!, SEA_STOPS.at(-1)!] : [SEA_STOPS[j - 1], SEA_STOPS[j]];
    seaPal.set(mix(hex(a[1]), hex(b[1]), b[0] > a[0] ? (d - a[0]) / (b[0] - a[0]) : 0), d * 3);
  }
  seaPal.set(OFFMAP, 255 * 3);
  const sea = $derived(M ? {d: seaDistance(M), pal: seaPal} : undefined);
  const devMax = $derived(I?.locs.dev ? Math.max(...I.locs.dev) : 42);
  // numbers as the game's legend and map labels write them: 4,793 / 110K / 3.717M
  const gameNum = (n: number) => n >= 1e6 ? (Math.floor(n / 1e3) / 1e3).toFixed(3) + 'M' : n >= 1e5 ? Math.floor(n / 1e3) + 'K' : Math.floor(n).toLocaleString('en');

  const colourOf = $derived.by(() => {
    if (!N || !I) return null;
    const n = N, info = I, m = mode, g = good;
    const set = (k: 'culture' | 'religion' | 'topo' | 'veg' | 'climate') => (i: number) => info.sets[k][info.locs[k][i]]?.[1] ?? FREE;
    const political = (i: number) => n.countries[n.locs[i][4]]?.color ?? FREE;
    if (m === 'political') return political;
    if (m === 'goods') return (i: number) => { const c = lit(info.goods[n.locs[i][1]] ?? FREE); return g && n.locs[i][1] !== g ? mix(c, DIM, 0.8) : c; };
    if (m === 'pop') return (i: number) => grad(popT(info.locs.pop[i] * 1000));
    if (m === 'dev') return (i: number) => grad((info.locs.dev?.[i] ?? 0) / devMax);
    if (m === 'rank') return (i: number) => lit(info.ranks[n.locs[i][5]][1]);
    return set(m);
  });
  const palette = $derived.by(() => {
    if (!N || !colourOf) return null;
    const n = N.locs.length + 2, P = new Uint8ClampedArray(n * 9), oid = new Int32Array(n), owners = new Map<string, number>();
    const put = (code: number, col: number[], b1: number, b2: number) => {
      P.set(col, code * 9); P.set(mix(col, [0, 0, 0], b1), code * 9 + 3); P.set(mix(col, [0, 0, 0], b2), code * 9 + 6);
    };
    put(0, SHALLOW, 0.25, 0); put(1, WASTE, 0, 0); oid[0] = -2; oid[1] = -3;
    N.locs.forEach((l, i) => {
      oid[i + 2] = l[4] ? owners.get(l[4]) ?? (owners.set(l[4], owners.size + 1), owners.size) : -1 - i;
      put(i + 2, colourOf(i), 0.55, mode === 'political' ? 0.12 : 0.2);
    });
    return {P, oid};
  });

  // ---- what's drawn over the colours -----------------------------------------------------------------------
  // country names: over the land joined to the capital (not colonies or exclaves), sized to its extent,
  // biggest first, skipped where they'd overlap
  const labels = $derived.by(() => {
    if (!N || !M) return [];
    const n = N, mw = M.w, out: {t: string; pop: number; x: number; y: number; w: number; h: number}[] = [];
    for (const c of Object.values(n.countries)) {
      if (!c.locs.length) continue;
      const pts = c.locs.map(i => [lx(i), ly(i)]), ref = pts[c.cap != null ? Math.max(0, c.locs.indexOf(c.cap)) : 0][0];
      for (const p of pts) { if (p[0] - ref > mw / 2) p[0] -= mw; else if (ref - p[0] > mw / 2) p[0] += mw; }
      // ponytail: O(n²) flood fill per country, fine for the largest (China, ~1700 locations)
      const seen = new Uint8Array(pts.length), stack = [pts.indexOf(pts.find(p => p[0] === ref)!)], core: number[][] = [];
      seen[stack[0]] = 1;
      while (stack.length) {
        const a = pts[stack.pop()!]; core.push(a);
        pts.forEach((b, j) => { if (!seen[j] && Math.abs(a[0] - b[0]) < 25 && Math.abs(a[1] - b[1]) < 25) { seen[j] = 1; stack.push(j); } });
      }
      const xs = core.map(p => p[0]), ys = core.map(p => p[1]);
      const w = Math.max(...xs) - Math.min(...xs) + 8, h = Math.max(...ys) - Math.min(...ys) + 8;
      out.push({t: c.name, pop: Object.values(c.pops).reduce((a, b) => a + b, 0) * 1000, x: xs.reduce((a, b) => a + b, 0) / xs.length, y: ys.reduce((a, b) => a + b, 0) / ys.length, w, h});
    }
    return out;
  });
  // the population map mode labels countries with their total population, as the game does
  const shownLabels = $derived(labels.map(l => { const t = mode === 'pop' ? gameNum(l.pop) : l.t; return {t, x: l.x, y: l.y, size: Math.min(l.w / (t.length * 0.62), l.h * 0.55, 60)}; })
    .sort((a, b) => b.size - a.size));
  // goods icons, loaded as they're needed; each load repaints
  const imgs = new Map<string, HTMLImageElement>();
  let loaded = $state(0);
  const gimg = (g: string) => {
    let im = imgs.get(g);
    if (!im) { im = new Image(); im.onload = () => loaded++; im.src = `icons/goods/${g}.png`; imgs.set(g, im); }
    return im.complete && im.naturalWidth ? im : null;
  };
  const goodsRank = $derived(N && mode === 'goods' ? N.locs.map((l, i) => i).filter(i => G[N!.locs[i][1]])
    .sort((a, b) => (N!.locs[b][1] === good ? 1e6 : 0) + G[N!.locs[b][1]].price - (N!.locs[a][1] === good ? 1e6 : 0) - G[N!.locs[a][1]].price) : []);

  const paint = $derived.by(() => {
    const riv = rivers ? R : undefined, lab = names && mode !== 'goods' ? shownLabels : [], icons = goodsRank, mw = M?.w ?? 4096, g = good;
    void loaded;
    return (ctx: CanvasRenderingContext2D, v: View, dpr: number) => {
      const k = v.s * dpr, cw = ctx.canvas.width, ch = ctx.canvas.height;
      const shifts = [-1, 0, 1].map(j => j * mw).filter(o => (o - v.x0) * k < cw && (o + mw - v.x0) * k > 0);
      if (riv) {
        // in full map units; the narrow ones fade in as you zoom
        ctx.lineCap = ctx.lineJoin = 'round';
        const widths = [0.7, 1.1, 1.7, 2.6];
        for (const o of shifts) {
          ctx.setTransform(k / WORLD_SCALE, 0, 0, k / WORLD_SCALE, (o - v.x0) * k, -v.y0 * k);
          riv.forEach((p, w) => {
            const alpha = Math.min(1, Math.max(0, (v.s - [1.2, 0.7, 0.35, 0][w]) / 0.5));
            if (!alpha) return;
            ctx.globalAlpha = alpha;
            ctx.strokeStyle = '#3a8bd6';
            ctx.lineWidth = widths[w] * Math.min(2, Math.max(0.6, Math.sqrt(v.s))) * dpr * WORLD_SCALE / k;
            ctx.stroke(p);
          });
        }
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
      }
      if (icons.length) {
        const cell = 22 * dpr, sz = 18 * dpr, taken = new Set<number>();
        for (const i of icons) {
          for (const o of shifts) {
            const x = (lx(i) + o - v.x0) * k, y = (ly(i) - v.y0) * k;
            if (x < 0 || y < 0 || x > cw || y > ch) continue;
            const key = Math.floor(x / cell) * 100000 + Math.floor(y / cell);
            if (taken.has(key)) continue;
            taken.add(key);
            const im = gimg(N!.locs[i][1]);
            if (!im) continue;
            ctx.globalAlpha = g && N!.locs[i][1] !== g ? 0.35 : 1;
            ctx.drawImage(im, x - sz / 2, y - sz / 2, sz, sz);
          }
        }
        ctx.globalAlpha = 1;
      }
      if (lab.length) {
        const boxes: number[][] = [];
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
        for (const l of lab) {
          const px = l.size * v.s * 0.8;
          if (px < 10) break;  // sorted by size: the rest are smaller
          const fs = Math.min(px, 26) * dpr;
          ctx.font = `600 ${fs}px "Noto Serif", Georgia, serif`;
          const tw = ctx.measureText(l.t).width;
          for (const o of shifts) {
            const x = (l.x + o - v.x0) * k, y = (l.y - v.y0) * k;
            const b = [x - tw / 2, y - fs / 2, x + tw / 2, y + fs / 2];
            if (b[0] < 0 || b[2] > cw || b[1] < 0 || b[3] > ch || boxes.some(q => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])) continue;
            boxes.push(b);
            ctx.lineWidth = Math.max(2, fs / 6); ctx.strokeStyle = '#000a'; ctx.strokeText(l.t, x, y);
            ctx.fillStyle = '#f3ead2'; ctx.fillText(l.t, x, y);
          }
        }
      }
    };
  });

  // ---- side panel ------------------------------------------------------------------------------------------
  // what's on screen, for the legend: locations whose centre is in view, counted once the map has been
  // still for a moment (recounting 21k locations every frame of a pan made it stutter)
  let settled = $state<View | null>(null);
  $effect(() => { const v = view, t = setTimeout(() => settled = v, 250); return () => clearTimeout(t); });
  const inView = $derived.by(() => {
    if (!N || !M || !W || !settled) return [] as number[];
    const {x0, y0, s} = settled, x1 = x0 + W / s, y1 = y0 + H / s, mw = M.w;
    return N.locs.map((l, i) => i).filter(i => { const y = ly(i); if (y < y0 || y > y1) return false; const x = lx(i); return [x - mw, x, x + mw].some(xx => xx >= x0 && xx <= x1); });
  });
  const tally = (key: (i: number) => string | number, weight: (i: number) => number) => {
    const t = new Map<string | number, number>();
    for (const i of inView) { const k = key(i); if (k !== -1 && k !== '') t.set(k, (t.get(k) ?? 0) + weight(i)); }
    return [...t.entries()].sort((a, b) => b[1] - a[1]);
  };
  const pop = (i: number) => I!.locs.pop[i];
  const people = (n: number) => n >= 1e6 ? (n / 1e6).toFixed(2) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(Math.round(n));
  type Legend = {title: string; unit: string; rows: {col: string; name: string; v: number; href?: string}[]};
  const legend = $derived.by((): Legend | null => {
    if (!N || !I) return null;
    const n = N, info = I;
    if (mode === 'political') return {title: 'Largest in view', unit: 'locations', rows: tally(i => n.locs[i][4], () => 1).slice(0, 12)
      .map(([t, v]) => ({col: `rgb(${(n.countries[t as string]?.color ?? FREE).join(',')})`, name: n.countries[t as string]?.name ?? String(t), v, href: `#n/${t}`}))};
    if (mode === 'culture' || mode === 'religion') return {title: 'Biggest in view, by pops', unit: 'people', rows: tally(i => info.locs[mode as 'culture'][i], pop).slice(0, 12)
      .map(([k, v]) => ({col: `rgb(${info.sets[mode as 'culture'][k as number][1].join(',')})`, name: info.sets[mode as 'culture'][k as number][0], v: v * 1000}))};
    if (mode === 'topo' || mode === 'veg' || mode === 'climate') {
      const t = new Map(tally(i => info.locs[mode as 'topo'][i], () => 1));
      return {title: 'In view', unit: 'locations', rows: info.sets[mode].map(([nm, c], k) => ({col: `rgb(${c.join(',')})`, name: nm, v: t.get(k) ?? 0})).filter(r => r.v)};
    }
    if (mode === 'rank') { const t = new Map(tally(i => n.locs[i][5], () => 1)); return {title: 'In view', unit: 'locations', rows: info.ranks.map(([nm, c], k) => ({col: `rgb(${lit(c).join(',')})`, name: nm, v: t.get(k) ?? 0}))}; }
    if (mode === 'pop') return {title: 'People per location', unit: '', rows: POP_STOPS.map((p, k) => ({col: `rgb(${grad(k / 4).join(',')})`, name: gameNum(p), v: -1}))};
    if (mode === 'dev') return {title: 'Development', unit: '', rows: [0, 1, 2, 3, 4].map(k => ({col: `rgb(${grad(k / 4).join(',')})`, name: String(Math.round(devMax * k / 4)), v: -1}))};
    return null;
  });
  const goodsInView = $derived(N && mode === 'goods' ? tally(i => N!.locs[i][1], () => 1).filter(([g]) => G[g as string]) as [string, number][] : []);

  // one location, for the hover card and the picked panel
  const about = (i: number) => {
    const l = N!.locs[i], c = N!.countries[l[4]], s = (k: 'culture' | 'religion' | 'topo' | 'veg' | 'climate') => I?.sets[k][I.locs[k][i]]?.[0];
    return {name: l[0], owner: c?.name, tag: l[4], area: N!.areas[l[6]], good: G[l[1]]?.name, rank: RANK_NAME[l[5]],
      culture: s('culture'), religion: s('religion'), topo: s('topo'), veg: s('veg'), climate: s('climate'), pop: I ? Math.round(I.locs.pop[i] * 1000) : 0, dev: I?.locs.dev?.[i]};
  };
</script>

<svelte:window bind:innerHeight />

{#snippet card(i: number)}
  {@const a = about(i)}
  <b>{a.name}</b><span class="sub">{a.area}{a.rank !== 'Rural' ? ` · ${a.rank}` : ''}</span>
  <dl>
    <dt>Owner</dt><dd>{#if a.owner}<span class="fl"><img src="flags/{a.tag}.png" alt="" onerror={e => (e.currentTarget as HTMLElement).remove()}></span>{a.owner}{:else}Unowned{/if}</dd>
    {#if a.pop}<dt>Pops</dt><dd>{a.pop.toLocaleString('en')}</dd>{/if}
    {#if a.dev}<dt>Development</dt><dd>{a.dev}</dd>{/if}
    {#if a.culture}<dt>Culture</dt><dd>{a.culture}</dd>{/if}
    {#if a.religion}<dt>Religion</dt><dd>{a.religion}</dd>{/if}
    {#if a.good}<dt>Produces</dt><dd><img class="ic" src="icons/goods/{N!.locs[i][1]}.png" alt="">{a.good}</dd>{/if}
    {#if a.topo}<dt>Terrain</dt><dd>{a.topo}{a.veg ? `, ${a.veg}` : ''}</dd>{/if}
    {#if a.climate}<dt>Climate</dt><dd>{a.climate}</dd>{/if}
  </dl>
{/snippet}

<div class="layout worldmap">
  <aside>
    <h3>Map modes</h3>
    <div class="modes">
      {#each MODES as [m, label, ic]}<button class:on={mode === m} onclick={() => mode = m}><img src="icons/mapmodes/{ic}.webp" alt="">{label}</button>{/each}
    </div>
    <div class="toggles">
      <label class="tgl"><input type="checkbox" bind:checked={rivers}><img src="icons/mapmodes/rivers.webp" alt="">Rivers</label>
      <label class="tgl"><input type="checkbox" bind:checked={names} disabled={mode === 'goods'}>Country names</label>
    </div>

    {#if mode === 'goods'}
      <h3>Raw goods in view</h3>
      <div class="gpick">
        {#each goodsInView as [g, n] (g)}<button class:on={good === g} onclick={() => good = good === g ? null : g} title="{G[g].name}: {n} locations in view"><img src="icons/goods/{g}.png" alt="">{n}</button>{/each}
      </div>
      <p class="meta">Pick a good to light up where it's produced.</p>
    {:else if legend}
      <h3>{legend.title}</h3>
      <ul class="wlegend">
        {#each legend.rows as r (r.name)}
          <li><i style="background:{r.col}"></i>{#if r.href}<a href={r.href}>{r.name}</a>{:else}<span>{r.name}</span>{/if}{#if r.v >= 0}<b>{legend.unit === 'people' ? people(r.v) : r.v}</b>{/if}</li>
        {:else}<li class="meta">Nothing in view.</li>{/each}
      </ul>
    {/if}

    {#if picked != null && N}
      <h3>Location</h3>
      <div class="wpick">{@render card(picked)}
        {#if N.locs[picked][4]}<a class="chip" href="#n/{N.locs[picked][4]}">Open {N.countries[N.locs[picked][4]]?.name}</a>{/if}</div>
    {/if}
    <p class="meta">The 1 April 1337 start. Drag to move, scroll to zoom, click a location for its details.</p>
  </aside>
  <main>
    {#if M && palette}
      <MapCanvas {M} P={palette.P} oid={palette.oid} {sea} {fit} {H} bind:W bind:pan {paint} resetTitle="Whole world"
        onhover={h => hover = h} onpick={i => picked = i >= 0 ? i : null}>
        {#snippet children(v: View)}
          {#if picked != null}<span class="wmark" style="left:{(lx(picked) - v.x0) * v.s}px;top:{(ly(picked) - v.y0) * v.s}px"></span>{/if}
          {#if hover}<div class="wtip" style="left:{Math.min(hover.x + 16, W - 260)}px;top:{Math.min(hover.y + 16, H - 200)}px">{@render card(hover.i)}</div>{/if}
        {/snippet}
      </MapCanvas>
    {:else}
      <div class="nmap" style="height:{H}px"><p class="meta" style="padding:20px">Loading the map…</p></div>
    {/if}
  </main>
</div>
