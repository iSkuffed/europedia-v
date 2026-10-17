// The world map tab's data: public/world.png (the location raster at 4x4 map units a pixel), public/mapinfo.json
// (per-location terrain, culture, religion, pops; written by build.py) and public/rivers.json (rivers.py).
import type { Raster } from '../MapCanvas.svelte';

export const WORLD_SCALE = 4;
let worldCache: Promise<Raster> | undefined;
export const loadWorld = () => worldCache ??= fetch('world.png').then(r => r.blob())
  .then(b => createImageBitmap(b, {colorSpaceConversion: 'none', premultiplyAlpha: 'none'})).then(bm => {
    const cv = document.createElement('canvas'), w = cv.width = bm.width, h = cv.height = bm.height;
    const ctx = cv.getContext('2d', {willReadFrequently: true})!;
    ctx.drawImage(bm, 0, 0);
    const d = ctx.getImageData(0, 0, w, h).data, c = new Uint16Array(w * h);
    for (let i = 0; i < c.length; i++) c[i] = d[4 * i] * 256 + d[4 * i + 1];
    return {w, h, c};
  });

type Set_ = [string, [number, number, number]][];
export interface MapInfo {
  sets: Record<'topo' | 'veg' | 'climate' | 'culture' | 'religion', Set_>;
  locs: Record<'topo' | 'veg' | 'climate' | 'culture' | 'religion', number[]> & {pop: number[]; harbor: number[]};
}
let infoCache: Promise<MapInfo> | undefined;
export const loadMapInfo = () => infoCache ??= fetch('mapinfo.json').then(r => r.json());

// rivers as one Path2D per width class (1 narrowest .. 4), in full map units (16384 x 8192, y down)
let riverCache: Promise<Path2D[]> | undefined;
export const loadRivers = () => riverCache ??= fetch('rivers.json').then(r => r.json()).then((d: {lines: number[][]}) => {
  const paths = [1, 2, 3, 4].map(() => new Path2D());
  for (const [w, x0, y0, ...rest] of d.lines) {
    const p = paths[Math.min(4, Math.max(1, w)) - 1];
    let x = x0, y = y0;
    p.moveTo(x + .5, y + .5);
    for (let k = 0; k < rest.length; k += 2) p.lineTo((x += rest[k]) + .5, (y += rest[k + 1]) + .5);
  }
  return paths;
});
