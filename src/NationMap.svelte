<script lang="ts">
  // A small map around a nation: its land in its colour, neighbours muted, raw-good icons where they fit,
  // the capital, and the "near" radius. Drawn from public/map.png (one pixel = 8x8 map units).
  import { DATA } from './lib/data';
  import { loadMap, MAP_SCALE, type NationData } from './lib/nations';
  import MapCanvas, { type View } from './MapCanvas.svelte';

  let { N, tag, mine, radius, sel = $bindable(null) }: { N: NationData; tag: string; mine: Set<string>; radius: number; sel: string | null } = $props();
  const G = DATA.goods;
  let M = $state<Awaited<ReturnType<typeof loadMap>>>();
  loadMap().then(m => M = m);
  let W = $state(0);
  const H = $derived(Math.round(W * 0.66));
  let hover = $state<{x: number; y: number; i: number} | null>(null);

  const rx = (i: number) => N.locs[i][2] / MAP_SCALE, ry = (i: number) => (8192 - N.locs[i][3]) / MAP_SCALE;
  const c = $derived(N.countries[tag]);
  // fitted view: the nation's land plus the near radius around the capital, with a margin
  const fit = $derived.by(() => {
    const own = [...mine].flatMap(t => N.countries[t].locs), r = radius / MAP_SCALE;
    const xs = own.map(rx), ys = own.map(ry);
    if (c.cap != null) xs.push(rx(c.cap) - r, rx(c.cap) + r), ys.push(ry(c.cap) - r, ry(c.cap) + r);
    let [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const m = 0.08 * Math.max(x1 - x0, y1 - y0, 40);
    x0 -= m; x1 += m; y0 -= m; y1 += m;
    return {s: Math.min(W / (x1 - x0), H / (y1 - y0)) || 1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2};
  });
  // the user's pan / zoom (centre in map pixels, screen px per map pixel); null = the fitted view
  let pan = $state<{cx: number; cy: number; s: number} | null>(null);
  $effect(() => { tag; radius; pan = null; });
  const toPx = (i: number, v: View) => [(rx(i) - v.x0) * v.s, (ry(i) - v.y0) * v.s];

  const hex = (s: string) => [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16));
  const mix = (a: number[], b: number[], t: number) => a.map((v, k) => Math.round(v + (b[k] - v) * t));
  const SEA = hex('#142231'), WASTE = hex('#34332f'), FREE = hex('#4b4a43'), BG = hex('#262b33'), GOLD = hex('#f0c75a');

  // colour per map code (0 water, 1 wasteland, i + 2 = locs[i]) at offsets 0 / 3 / 6: plain, country border
  // (or coast for water), location border; and an owner id per code so borders only show between countries
  const palette = $derived.by(() => {
    const n = N.locs.length + 2, P = new Uint8ClampedArray(n * 9), oid = new Int32Array(n), owners = new Map<string, number>();
    const own = c.color ?? [200, 170, 90];
    const put = (code: number, col: number[], b1: number, b2: number) => {
      P.set(col, code * 9); P.set(mix(col, [0, 0, 0], b1), code * 9 + 3); P.set(mix(col, [0, 0, 0], b2), code * 9 + 6);
    };
    put(0, SEA, 0.35, 0); put(1, WASTE, 0, 0); oid[0] = -2; oid[1] = -3;
    N.locs.forEach((l, i) => {
      oid[i + 2] = l[4] ? owners.get(l[4]) ?? (owners.set(l[4], owners.size + 1), owners.size) : -1;
      const oc = N.countries[l[4]]?.color;
      let col = l[4] === tag ? own : mine.has(l[4]) ? mix(own, [0, 0, 0], 0.3) : l[4] ? mix(oc ?? FREE, BG, 0.75) : FREE;
      if (sel) col = l[1] === sel ? mix(col, GOLD, 0.75) : mix(col, [0, 0, 0], 0.35);
      put(i + 2, col, 0.6, 0.18);
    });
    return {P, oid};
  });

  // icons on your land and on the highlighted good, where they fit: one per 18px cell, highlighted first, pricier goods win
  const ranked = $derived.by(() => {  // candidates best first; only their positions change with the view
    const rank = (i: number) => (N.locs[i][1] === sel ? 2e6 : 0) + (mine.has(N.locs[i][4]) ? 1e6 : 0) + G[N.locs[i][1]].price;
    return N.locs.map((l, i) => i).filter(i => G[N.locs[i][1]] && (mine.has(N.locs[i][4]) || N.locs[i][1] === sel)).sort((a, b) => rank(b) - rank(a));
  });
  const iconsIn = (view: View) => {
    const taken = new Set<string>(), out: {i: number; x: number; y: number; dim: boolean}[] = [];
    for (const i of ranked) {
      const [x, y] = toPx(i, view);
      if (!(x > 6 && y > 6 && x < W - 6 && y < H - 6)) continue;
      const key = `${Math.floor(x / 18)},${Math.floor(y / 18)}`;
      if (taken.has(key)) continue;
      taken.add(key);
      out.push({i, x, y, dim: !!sel && N.locs[i][1] !== sel});
    }
    return out;
  };

</script>

{#if M}
<MapCanvas {M} P={palette.P} oid={palette.oid} {fit} {H} bind:W bind:pan resetTitle="Back to {c.name}"
  onhover={h => hover = h} onpick={i => { const g = i >= 0 ? N.locs[i][1] : ''; if (G[g]) sel = sel === g ? null : g; }}>
  {#snippet children(view: View)}
    {#if c.cap != null}
      {@const [cx, cy] = toPx(c.cap, view)}
      <svg width={W} height={H}><circle cx={cx} cy={cy} r={radius / MAP_SCALE * view.s} /></svg>
      {#each iconsIn(view) as e (e.i)}<img class="mi" class:dim={e.dim} class:cap={e.i === c.cap} src="icons/goods/{N.locs[e.i][1]}.png" alt="" style="left:{e.x}px;top:{e.y}px">{/each}
      <span class="star" style="left:{cx}px;top:{cy}px" title="Capital: {N.locs[c.cap][0]}">★</span>
    {/if}
    {#if hover}
      {@const l = N.locs[hover.i]}
      <div class="mtip" style="left:{hover.x}px;top:{hover.y}px"><b>{l[0]}</b>{#if G[l[1]]}<span>{G[l[1]].name}</span>{/if}<i>{l[4] ? N.countries[l[4]]?.name : 'Unowned'}</i></div>
    {/if}
  {/snippet}
</MapCanvas>
{:else}<div class="nmap" style="height:{H}px"></div>{/if}
