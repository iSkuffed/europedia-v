<script lang="ts">
  // A small map around a nation: its land in its colour, neighbours muted, raw-good icons where they fit,
  // the capital, and the "near" radius. Drawn from public/map.png (one pixel = 8x8 map units).
  import { DATA } from './lib/data';
  import { loadMap, MAP_SCALE, type NationData } from './lib/nations';

  let { N, tag, mine, radius, sel = $bindable(null) }: { N: NationData; tag: string; mine: Set<string>; radius: number; sel: string | null } = $props();
  const G = DATA.goods;
  let M = $state<Awaited<ReturnType<typeof loadMap>>>();
  loadMap().then(m => M = m);
  let W = $state(0);
  const H = $derived(Math.round(W * 0.66));
  let canvas = $state<HTMLCanvasElement>();
  let hover = $state<{x: number; y: number; i: number} | null>(null);

  const rx = (i: number) => N.locs[i][2] / MAP_SCALE, ry = (i: number) => (8192 - N.locs[i][3]) / MAP_SCALE;
  const c = $derived(N.countries[tag]);
  // view: the nation's land plus the near radius around the capital, with a margin, fitted to the canvas
  const view = $derived.by(() => {
    const own = [...mine].flatMap(t => N.countries[t].locs), r = radius / MAP_SCALE;
    const xs = own.map(rx), ys = own.map(ry);
    if (c.cap != null) xs.push(rx(c.cap) - r, rx(c.cap) + r), ys.push(ry(c.cap) - r, ry(c.cap) + r);
    let [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const m = 0.08 * Math.max(x1 - x0, y1 - y0, 40);
    x0 -= m; x1 += m; y0 -= m; y1 += m;
    const s = Math.min(W / (x1 - x0), H / (y1 - y0)) || 1;
    return {s, x0: (x0 + x1) / 2 - W / s / 2, y0: (y0 + y1) / 2 - H / s / 2};
  });
  const toPx = (i: number) => [(rx(i) - view.x0) * view.s, (ry(i) - view.y0) * view.s];

  const hex = (s: string) => [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16));
  const mix = (a: number[], b: number[], t: number) => a.map((v, k) => Math.round(v + (b[k] - v) * t));
  const SEA = hex('#142231'), WASTE = hex('#34332f'), FREE = hex('#4b4a43'), BG = hex('#262b33'), GOLD = hex('#f0c75a');

  $effect(() => {
    if (!M || !canvas || !W) return;
    const dpr = devicePixelRatio || 1, cw = Math.round(W * dpr), ch = Math.round(H * dpr), k = view.s * dpr;
    canvas.width = cw; canvas.height = ch;
    // colour and owner per map code (0 water, 1 wasteland, i + 2 = locs[i])
    const own = c.color ?? [200, 170, 90], owners = new Map<string, number>(), oid = new Int32Array(N.locs.length + 2);
    const pal = [SEA, WASTE, ...N.locs.map((l, i) => {
      oid[i + 2] = l[4] ? owners.get(l[4]) ?? (owners.set(l[4], owners.size + 1), owners.size) : -1;
      const oc = N.countries[l[4]]?.color;
      let col = l[4] === tag ? own : mine.has(l[4]) ? mix(own, [0, 0, 0], 0.3) : l[4] ? mix(oc ?? FREE, BG, 0.75) : FREE;
      if (sel) col = l[1] === sel ? mix(col, GOLD, 0.75) : mix(col, [0, 0, 0], 0.35);
      return col;
    })];
    oid[0] = -2; oid[1] = -3;
    const codes = new Int32Array(cw * ch);
    for (let y = 0; y < ch; y++) {
      const my = Math.floor(view.y0 + y / k), row = (my < 0 || my >= M.h) ? -1 : my * M.w;
      for (let x = 0; x < cw; x++) {
        const mx = ((Math.floor(view.x0 + x / k) % M.w) + M.w) % M.w;
        codes[y * cw + x] = row < 0 ? 0 : M.c[row + mx];
      }
    }
    const img = new ImageData(cw, ch), d = img.data;
    for (let p = 0; p < cw * ch; p++) {
      const code = codes[p], r = p % cw < cw - 1 ? codes[p + 1] : code, b = p < cw * (ch - 1) ? codes[p + cw] : code;
      let col = pal[code] ?? WASTE;
      if (code > 1 && ((r !== code && oid[r] !== oid[code]) || (b !== code && oid[b] !== oid[code]))) col = mix(col, [0, 0, 0], 0.6);  // country border
      else if (code > 1 && (r !== code || b !== code)) col = mix(col, [0, 0, 0], 0.18);  // location border
      else if (code === 0 && (r > 0 || b > 0)) col = mix(col, [0, 0, 0], 0.35);  // coast
      d[4 * p] = col[0]; d[4 * p + 1] = col[1]; d[4 * p + 2] = col[2]; d[4 * p + 3] = 255;
    }
    canvas.getContext('2d')!.putImageData(img, 0, 0);
  });

  // icons on your land and on the highlighted good, where they fit: one per 18px cell, highlighted first, pricier goods win
  const icons = $derived.by(() => {
    if (!W) return [];
    const taken = new Set<string>(), out: {i: number; x: number; y: number; dim: boolean}[] = [];
    const cand = N.locs.map((l, i) => i).filter(i => G[N.locs[i][1]] && (mine.has(N.locs[i][4]) || N.locs[i][1] === sel) && (() => { const [x, y] = toPx(i); return x > 6 && y > 6 && x < W - 6 && y < H - 6; })());
    const rank = (i: number) => (N.locs[i][1] === sel ? 2e6 : 0) + (mine.has(N.locs[i][4]) ? 1e6 : 0) + G[N.locs[i][1]].price;
    for (const i of cand.sort((a, b) => rank(b) - rank(a))) {
      const [x, y] = toPx(i), key = `${Math.floor(x / 18)},${Math.floor(y / 18)}`;
      if (taken.has(key)) continue;
      taken.add(key);
      out.push({i, x, y, dim: !!sel && N.locs[i][1] !== sel});
    }
    return out;
  });

  function locAt(e: MouseEvent) {
    if (!M) return null;
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    const my = Math.floor(view.y0 + y / view.s), mx = ((Math.floor(view.x0 + x / view.s) % M.w) + M.w) % M.w;
    const code = my >= 0 && my < M.h ? M.c[my * M.w + mx] : 0;
    return {x, y, i: code - 2};
  }
</script>

<div class="nmap" bind:clientWidth={W} style="height:{H}px">
  <canvas bind:this={canvas} style="width:{W}px;height:{H}px"
    onmousemove={e => { const h = locAt(e); hover = h && h.i >= 0 ? h : null; }} onmouseleave={() => hover = null}
    onclick={e => { const h = locAt(e); const g = h && h.i >= 0 ? N.locs[h.i][1] : ''; if (G[g]) sel = sel === g ? null : g; }}></canvas>
  {#if c.cap != null && W}
    {@const [cx, cy] = toPx(c.cap)}
    <svg width={W} height={H}><circle cx={cx} cy={cy} r={radius / MAP_SCALE * view.s} /></svg>
    {#each icons as e (e.i)}<img class="mi" class:dim={e.dim} class:cap={e.i === c.cap} src="icons/goods/{N.locs[e.i][1]}.png" alt="" style="left:{e.x}px;top:{e.y}px">{/each}
    <span class="star" style="left:{cx}px;top:{cy}px" title="Capital: {N.locs[c.cap][0]}">★</span>
  {/if}
  {#if hover}
    {@const l = N.locs[hover.i]}
    <div class="mtip" style="left:{hover.x}px;top:{hover.y}px"><b>{l[0]}</b>{#if G[l[1]]}<span>{G[l[1]].name}</span>{/if}<i>{l[4] ? N.countries[l[4]]?.name : 'Unowned'}</i></div>
  {/if}
</div>
