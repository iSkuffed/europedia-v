<script lang="ts" module>
  export type Raster = {w: number; h: number; c: Uint16Array};  // red*256+green per pixel: 0 water, 1 wasteland, i + 2 = locs[i]
  export type View = {s: number; x0: number; y0: number};       // screen px per raster pixel, top-left corner in raster pixels
</script>

<script lang="ts">
  // The location map: a colour per map code drawn over the location raster at screen resolution (borders stay one
  // pixel thin at any zoom), with drag to pan, wheel / buttons to zoom and hover / click on a location.
  // `paint` draws on the canvas afterwards (rivers, names); `children` lays HTML over it. `sea` shades open water
  // per raster pixel (an index into its 3-byte palette; 255 is beyond the map's top and bottom).
  import type { Snippet } from 'svelte';

  let { M, P, oid, sea, fit, H, W = $bindable(0), pan = $bindable(null), paint, onhover, onpick, resetTitle = 'Back', children }: {
    M: Raster; P: Uint8ClampedArray; oid: Int32Array; sea?: {d: Uint8Array; pal: Uint8ClampedArray}; fit: {s: number; cx: number; cy: number}; H: number; W?: number;
    pan?: {cx: number; cy: number; s: number} | null; paint?: (ctx: CanvasRenderingContext2D, v: View, dpr: number) => void;
    onhover?: (h: {i: number; x: number; y: number} | null) => void; onpick?: (i: number) => void; resetTitle?: string; children?: Snippet<[View]>;
  } = $props();
  let canvas = $state<HTMLCanvasElement>();

  const view = $derived.by((): View => {
    const {cx, cy, s} = pan ?? fit;
    return {s, x0: cx - W / s / 2, y0: cy - H / s / 2};
  });
  // zoom by f keeping the map point under screen (px, py) still; from the whole world's width to 24 px per raster pixel
  function zoom(f: number, px = W / 2, py = H / 2) {
    const s = Math.min(24, Math.max(W / M.w, view.s * f)), mx = view.x0 + px / view.s, my = view.y0 + py / view.s;
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

  // Colours as one 32-bit word each (little-endian ABGR), so a pixel is one write instead of four.
  const word = (rgb: ArrayLike<number>, i: number) => (0xff000000 | rgb[i + 2] << 16 | rgb[i + 1] << 8 | rgb[i]) >>> 0;
  const P32 = $derived.by(() => { const w = new Uint32Array(P.length / 3); for (let i = 0; i < w.length; i++) w[i] = word(P, i * 3); return w; });
  const sea32 = $derived.by(() => { if (!sea) return undefined; const w = new Uint32Array(256); for (let i = 0; i < 256; i++) w[i] = word(sea.pal, i * 3); return w; });

  // While the map is being dragged or zoomed it is drawn at no more than MOVING_PX pixels (the browser scales the canvas up),
  // then redrawn at full resolution once it has been still for a moment. A 4K screen has four times the pixels of 1080p,
  // and every one of them is computed here on the CPU; at 1080p this changes nothing.
  const MOVING_PX = 2e6;
  let moving = $state(false), still: ReturnType<typeof setTimeout>;
  $effect(() => { view; moving = true; clearTimeout(still); still = setTimeout(() => moving = false, 150); return () => clearTimeout(still); });
  let buf: {cw: number; ch: number; img: ImageData; px: Uint32Array; codes: Uint16Array; sd: Uint8Array} | undefined;  // reused between frames

  // redraw at most once a frame
  $effect(() => {
    if (!canvas || !W) return;
    const m = M, mc = m.c, mw = m.w, mh = m.h, cv = canvas, pal = P32, ids = oid, shd = sea?.d, sp = sea32, {x0, y0, s} = view, w = W, h = H, after = paint, quick = moving;
    const raf = requestAnimationFrame(() => {
      const dpr = devicePixelRatio || 1, full = w * h * dpr * dpr, q = quick && full > MOVING_PX ? Math.sqrt(MOVING_PX / full) : 1;
      const cw = Math.round(w * dpr * q), ch = Math.round(h * dpr * q), k = s * dpr * q;
      if (cv.width !== cw || cv.height !== ch) { cv.width = cw; cv.height = ch; }
      if (buf?.cw !== cw || buf.ch !== ch) { const img = new ImageData(cw, ch); buf = {cw, ch, img, px: new Uint32Array(img.data.buffer), codes: new Uint16Array(cw * ch), sd: new Uint8Array(cw * ch)}; }
      const {img, px, codes, sd} = buf;
      const cols = new Int32Array(cw);
      for (let x = 0; x < cw; x++) cols[x] = ((Math.floor(x0 + x / k) % mw) + mw) % mw;
      for (let y = 0; y < ch; y++) {
        const my = Math.floor(y0 + y / k), o = y * cw;
        if (my < 0 || my >= mh) { codes.fill(0, o, o + cw); sd.fill(255, o, o + cw); continue; }  // off the map: water (0)
        const row = my * mw;
        for (let x = 0; x < cw; x++) codes[o + x] = mc[row + cols[x]];
        if (shd) for (let x = 0; x < cw; x++) sd[o + x] = shd[row + cols[x]];
      }
      // palette words 3 * code + 0 / 1 / 2: plain, country border (coast for water), location border
      for (let y = 0, p = 0; y < ch; y++) {
        const lastRow = y === ch - 1;
        for (let x = 0; x < cw; x++, p++) {
          const code = codes[p], r = x < cw - 1 ? codes[p + 1] : code, b = lastRow ? code : codes[p + cw];
          let o = code * 3;
          if (code > 1) {
            if ((r !== code && ids[r] !== ids[code]) || (b !== code && ids[b] !== ids[code])) o += 1;
            else if (r !== code || b !== code) o += 2;
          } else if (code === 0 && (r > 0 || b > 0)) o += 1;
          else if (sp && code === 0) { px[p] = sp[sd[p]]; continue; }
          px[p] = pal[o];
        }
      }
      const ctx = cv.getContext('2d')!;
      ctx.putImageData(img, 0, 0);
      if (after) { ctx.save(); after(ctx, {x0, y0, s}, dpr * q); ctx.restore(); }
    });
    return () => cancelAnimationFrame(raf);
  });

  function locAt(e: MouseEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    const my = Math.floor(view.y0 + y / view.s), mx = ((Math.floor(view.x0 + x / view.s) % M.w) + M.w) % M.w;
    return {x, y, i: (my >= 0 && my < M.h ? M.c[my * M.w + mx] : 0) - 2};
  }
</script>

<div class="nmap" bind:clientWidth={W} style="height:{H}px" use:wheel>
  <canvas bind:this={canvas} style="width:{W}px;height:{H}px" class:grabbing
    onpointerdown={e => { if (e.button) return; drag = {x: e.clientX, y: e.clientY, cx: view.x0 + W / view.s / 2, cy: view.y0 + H / view.s / 2, moved: false}; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); }}
    onpointermove={e => {
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) > 4) { drag.moved = grabbing = true; onhover?.(null); }
        if (drag.moved) { pan = {s: view.s, cx: drag.cx - dx / view.s, cy: Math.max(0, Math.min(M.h, drag.cy - dy / view.s))}; return; }
      }
      const h = locAt(e); onhover?.(h.i >= 0 ? h : null);
    }}
    onpointerup={() => { justDragged = !!drag?.moved; drag = null; grabbing = false; }} onpointercancel={() => { drag = null; grabbing = false; }} onmouseleave={() => onhover?.(null)}
    onclick={e => { if (!justDragged) onpick?.(locAt(e).i); }}></canvas>
  <div class="mzoom">
    <button onclick={() => zoom(1.5)} title="Zoom in (or use the mouse wheel)">+</button>
    <button onclick={() => zoom(1 / 1.5)} title="Zoom out">−</button>
    <button onclick={() => pan = null} disabled={!pan} title={resetTitle}>⟲</button>
  </div>
  {#if W}{@render children?.(view)}{/if}
</div>
