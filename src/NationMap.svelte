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
  const view = $derived.by(() => {
    const {cx, cy, s} = pan ?? fit;
    return {s, x0: cx - W / s / 2, y0: cy - H / s / 2};
  });
  // zoom by f keeping the map point under screen (px, py) still; from the whole world's width to 24 px per map pixel
  function zoom(f: number, px = W / 2, py = H / 2) {
    const s = Math.min(24, Math.max((M?.w ? W / M.w : 0.3), view.s * f)), mx = view.x0 + px / view.s, my = view.y0 + py / view.s;
    pan = {s, cx: mx - px / s + W / s / 2, cy: my - py / s + H / s / 2};
  }
  let drag: {x: number; y: number; cx: number; cy: number; moved: boolean} | null = null, justDragged = false;
  let grabbing = $state(false);
  function wheel(node: HTMLElement) {  // a non-passive listener so the page doesn't scroll under the map
    const on = (e: WheelEvent) => {
      e.preventDefault();
      const r = node.getBoundingClientRect();
      zoom(Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0015)), e.clientX - r.left, e.clientY - r.top);
    };
    node.addEventListener('wheel', on, {passive: false});
    return {destroy: () => node.removeEventListener('wheel', on)};
  }
  const toPx = (i: number) => [(rx(i) - view.x0) * view.s, (ry(i) - view.y0) * view.s];

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

  // redraw at screen resolution (borders stay one pixel thin at any zoom), at most once a frame
  $effect(() => {
    if (!M || !canvas || !W) return;
    const m = M, cv = canvas, {P, oid} = palette, {x0, y0, s} = view, w = W, h = H;
    const raf = requestAnimationFrame(() => {
      const dpr = devicePixelRatio || 1, cw = Math.round(w * dpr), ch = Math.round(h * dpr), k = s * dpr;
      if (cv.width !== cw || cv.height !== ch) { cv.width = cw; cv.height = ch; }
      const cols = new Int32Array(cw);
      for (let x = 0; x < cw; x++) cols[x] = ((Math.floor(x0 + x / k) % m.w) + m.w) % m.w;
      const codes = new Uint16Array(cw * ch);
      for (let y = 0; y < ch; y++) {
        const my = Math.floor(y0 + y / k);
        if (my < 0 || my >= m.h) continue;  // off the map: water (0)
        const row = my * m.w, o = y * cw;
        for (let x = 0; x < cw; x++) codes[o + x] = m.c[row + cols[x]];
      }
      const img = new ImageData(cw, ch), d = img.data, last = cw * (ch - 1);
      for (let p = 0; p < cw * ch; p++) {
        const code = codes[p], r = p % cw < cw - 1 ? codes[p + 1] : code, b = p < last ? codes[p + cw] : code;
        let o = code * 9;
        if (code > 1) {
          if ((r !== code && oid[r] !== oid[code]) || (b !== code && oid[b] !== oid[code])) o += 3;  // country border
          else if (r !== code || b !== code) o += 6;  // location border
        } else if (code === 0 && (r > 0 || b > 0)) o += 3;  // coast
        d[4 * p] = P[o]; d[4 * p + 1] = P[o + 1]; d[4 * p + 2] = P[o + 2]; d[4 * p + 3] = 255;
      }
      cv.getContext('2d')!.putImageData(img, 0, 0);
    });
    return () => cancelAnimationFrame(raf);
  });

  // icons on your land and on the highlighted good, where they fit: one per 18px cell, highlighted first, pricier goods win
  const ranked = $derived.by(() => {  // candidates best first; only their positions change with the view
    const rank = (i: number) => (N.locs[i][1] === sel ? 2e6 : 0) + (mine.has(N.locs[i][4]) ? 1e6 : 0) + G[N.locs[i][1]].price;
    return N.locs.map((l, i) => i).filter(i => G[N.locs[i][1]] && (mine.has(N.locs[i][4]) || N.locs[i][1] === sel)).sort((a, b) => rank(b) - rank(a));
  });
  const icons = $derived.by(() => {
    if (!W) return [];
    const taken = new Set<string>(), out: {i: number; x: number; y: number; dim: boolean}[] = [];
    for (const i of ranked) {
      const [x, y] = toPx(i);
      if (!(x > 6 && y > 6 && x < W - 6 && y < H - 6)) continue;
      const key = `${Math.floor(x / 18)},${Math.floor(y / 18)}`;
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

<div class="nmap" bind:clientWidth={W} style="height:{H}px" use:wheel>
  <canvas bind:this={canvas} style="width:{W}px;height:{H}px" class:grabbing
    onpointerdown={e => { if (e.button) return; drag = {x: e.clientX, y: e.clientY, cx: view.x0 + W / view.s / 2, cy: view.y0 + H / view.s / 2, moved: false}; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); }}
    onpointermove={e => {
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) > 4) { drag.moved = grabbing = true; hover = null; }
        if (drag.moved) { pan = {s: view.s, cx: drag.cx - dx / view.s, cy: drag.cy - dy / view.s}; return; }
      }
      const h = locAt(e); hover = h && h.i >= 0 ? h : null;
    }}
    onpointerup={() => { justDragged = !!drag?.moved; drag = null; grabbing = false; }} onpointercancel={() => { drag = null; grabbing = false; }} onmouseleave={() => hover = null}
    onclick={e => { if (justDragged) return; const h = locAt(e); const g = h && h.i >= 0 ? N.locs[h.i][1] : ''; if (G[g]) sel = sel === g ? null : g; }}></canvas>
  <div class="mzoom">
    <button onclick={() => zoom(1.5)} title="Zoom in (or use the mouse wheel)">+</button>
    <button onclick={() => zoom(1 / 1.5)} title="Zoom out">−</button>
    <button onclick={() => pan = null} disabled={!pan} title="Back to {c.name}">⟲</button>
  </div>
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
