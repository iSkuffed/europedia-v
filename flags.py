"""Render a 120x80 flag PNG per country tag from EU5's coat-of-arms script.

    python3 -I flags.py              # every tag in public/nations.json -> public/flags/<TAG>.png
    python3 -I flags.py MOS NOV ...  # only these tags
    python3 -I flags.py --out /tmp/x MOS NOV   # write elsewhere

Pure Python compositing + ImageMagick (`magick`) for DDS decoding and PNG encoding.
Game files are read-only; nothing outside public/flags/ is written.
"""
import collections
import glob
import json
import math
import multiprocessing
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pdx import parse, get, num  # noqa: E402

GAME = os.path.expanduser('~/.local/share/Steam/steamapps/common/Europa Universalis V/game/main_menu')
COA_DIR = GAME + '/common/coat_of_arms/coat_of_arms/'
GFX = GAME + '/gfx/coat_of_arms/'
OUT_W, OUT_H = 120, 80
SS = 2                      # supersample factor (rendered at 2x, then averaged down)
W, H = OUT_W * SS, OUT_H * SS
MIPS = (384, 192, 96, 48, 24, 12)  # decoded texture widths (all 3:2)
SETUP = GAME + '/setup/'
GOV_ATOMS = {'coa_def_monarchy_trigger': 'monarchy', 'coa_def_republic_trigger': 'republic',
             'coa_def_theocracy_trigger': 'theocracy'}


# ---------------------------------------------------------------- script loading

def read_script(path):
    """parse() a script file; keeps the colour-space keyword (pdx.parse drops it) and @[expr] values."""
    text = open(path, encoding='utf-8-sig').read()
    text = re.sub(r'\b(rgb|hsv360|hsv|hex)\s*\{', r'{ \1 ', text)
    exprs = []

    def stash(m):
        exprs.append(m.group(1))
        return ' @__e%d ' % (len(exprs) - 1)
    text = re.sub(r'@\[([^\]\n]*)\]', stash, text)
    return parse(text), exprs


def resolve_vars(block, env, exprs):
    """Replace '@name' / '@[expr]' scalars in-place-ish (returns a new block); top-level '@x = v' defs fill env."""
    def sub(v):
        if isinstance(v, list):
            return [(k, o, sub(x)) for k, o, x in v]
        if isinstance(v, str) and v.startswith('@'):
            if v.startswith('@__e'):
                e = exprs[int(v[4:])]
                e = re.sub(r'[A-Za-z_]\w*', lambda m: repr(env.get(m.group(0), 0.0)) if m.group(0) in env else m.group(0), e.replace('@', ''))
                try:
                    return repr(float(eval(e, {'__builtins__': {}}, {})))
                except Exception:
                    return '0'
            return env.get(v[1:], v)
        return v
    out = []
    for k, o, v in block:
        v = sub(v)
        if k and k.startswith('@'):
            f = num(v)
            if f is not None:
                env[k[1:]] = f
            continue
        out.append((k, o, v))
    return out


def load_coas():
    env, coas = {}, {}
    order = ['pre_scripted_countries_formable', 'pre_scripted_countries', '00_subs', '00_subs_usa',
             'pre_scripted_countries_usa', 'pre_scripted_countries_japanese_clans']
    for name in order + [os.path.basename(p)[:-4] for p in sorted(glob.glob(COA_DIR + '*.txt'))]:
        p = COA_DIR + name + '.txt'
        if not os.path.exists(p):
            continue
        block, exprs = read_script(p)
        local = dict(env)
        for k, _, v in resolve_vars(block, local, exprs):
            if k and isinstance(v, list):
                coas.setdefault(k, v)  # first definition wins
        env.update({k: v for k, v in local.items() if k not in env})
    return coas


def load_colors():
    cols = {}
    for p in sorted(glob.glob(GAME + '/common/named_colors/*.txt')):
        block, _ = read_script(p)
        for k, _, v in block:
            if isinstance(v, list):
                for name, _, c in v:
                    if name and isinstance(c, list):
                        cols.setdefault(name, parse_color(c, {}))
    return cols


def hsv2rgb(h, s, v):
    h = (h % 1.0) * 6
    i = int(h)
    f = h - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]


def parse_color(v, palette, names=None):
    """colour value -> (r,g,b) floats 0-1, or None. v: name string, 'colorN' reference, or [kind a b c] list."""
    if isinstance(v, str):
        if v in palette:
            return palette[v]
        return (names or NAMED).get(v)
    kind = v[0][2] if v and v[0][0] is None and v[0][2] in ('rgb', 'hsv', 'hsv360', 'hex') else 'rgb'
    n = [num(x) for k, _, x in v if k is None and num(x) is not None]
    if len(n) < 3:
        return None
    if kind == 'hsv360':
        return hsv2rgb(n[0] / 360, n[1] / 100, n[2] / 100)
    if kind == 'hsv':
        return hsv2rgb(*n[:3])
    if max(n[:3]) > 1.0:
        n = [x / 255 for x in n]
    return tuple(n[:3])


# ---------------------------------------------------------------- textures

_TEX_PATH = {}
for _d in ('patterns', 'colored_emblems', 'textured_emblems'):
    for _f in glob.glob(GFX + _d + '/*.dds'):
        _TEX_PATH[os.path.basename(_f)] = _f
_tex_cache = collections.OrderedDict()


def texture(name):
    """-> list of (w, h, bytes RGBA) per MIPS level, or None when the file is missing."""
    if name in _tex_cache:
        _tex_cache.move_to_end(name)
        return _tex_cache[name]
    path = _TEX_PATH.get(name)
    mips = None
    if path:
        cmd = ['magick', path + '[0]', '-depth', '8', '-filter', 'Box', '-resize', '384x256!']
        for w in MIPS[1:]:
            cmd += ['(', '-clone', '0', '-filter', 'Box', '-resize', '%dx%d!' % (w, w * 2 // 3), ')']
        cmd += ['rgba:-']
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        mips, off = [], 0
        for w in MIPS:
            h = w * 2 // 3
            mips.append((w, h, raw[off:off + w * h * 4]))
            off += w * h * 4
    _tex_cache[name] = mips
    if len(_tex_cache) > 120:
        _tex_cache.popitem(last=False)
    return mips


def pick_mip(mips, px_width):
    best = mips[0]
    for m in mips:          # smallest mip still at least as wide as the on-canvas size
        if m[0] >= px_width:
            best = m
    return best


# ---------------------------------------------------------------- canvas / drawing

class Canvas:
    def __init__(self):
        n = W * H
        self.r, self.g, self.b, self.a = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n  # premultiplied

    def rgba_bytes(self):
        out = bytearray()
        for i in range(W * H):
            a = self.a[i]
            if a <= 0:
                out += b'\0\0\0\0'
            else:
                out += bytes((min(255, int(self.r[i] / a * 255 + .5)), min(255, int(self.g[i] / a * 255 + .5)),
                              min(255, int(self.b[i] / a * 255 + .5)), min(255, int(a * 255 + .5))))
        return bytes(out)


def overlay(base, b):
    return 2 * base * b if b < 0.5 else 1 - 2 * (1 - base) * (1 - b)


class Coat:
    def __init__(self, block, ctx):
        self.block = block
        self.pal = {}
        for i in range(1, 6):
            v = get(block, 'color%d' % i)
            c = parse_color(v, {}) if v is not None else None
            if c:
                self.pal['color%d' % i] = c
        for i in range(2, 6):
            self.pal.setdefault('color%d' % i, self.pal.get('color1', (1.0, 0.0, 1.0)))
        self.pal.setdefault('color1', (1.0, 0.0, 1.0))
        pat = get(block, 'pattern')
        self.pattern = texture(pat) if pat else None

    def color(self, v, default='color1'):
        c = parse_color(v, self.pal) if v is not None else None
        return c or self.pal[default]

    def mask_weight(self, mips_px, lx, ly, mask):
        """Share of the pattern's colour channels in `mask` at local pixel (lx, ly)."""
        if not self.pattern:
            return 0.0
        w, h, d = mips_px
        i = (min(h - 1, int(ly / H * h)) * w + min(w - 1, int(lx / W * w))) * 4
        g, bl = d[i + 1] / 255, d[i + 2] / 255
        wt = {1: (1 - g) * (1 - bl), 2: g * (1 - bl), 3: bl}
        return sum(wt.get(m, 0.0) for m in mask)


def insts(block, defaults):
    out = [x for k, _, x in block if k == 'instance']
    return out or [[]] if defaults else out


def vec(block, key, default):
    v = get(block, key)
    if isinstance(v, list):
        n = [num(x) for k, _, x in v if k is None]
        if len(n) >= 2 and None not in n[:2]:
            return n[0], n[1]
    return default


def draw_coat(cv, name, T, clip, depth, colors_in, coas, stack=()):
    """Draw coat `name` with local->canvas map cx = T[0] + lx*T[2], cy = T[1] + ly*T[3]; colors_in overrides color1..3."""
    block = coas.get(name)
    if block is None or depth > 5 or name in stack:
        return False
    coat = Coat(block, None)
    for k, c in colors_in.items():
        coat.pal[k] = c
    ox, oy, kx, ky = T
    cx0, cy0 = max(clip[0], ox), max(clip[1], oy)
    cx1, cy1 = min(clip[2], ox + W * kx), min(clip[3], oy + H * ky)
    clip = (cx0, cy0, cx1, cy1)
    if cx1 <= cx0 or cy1 <= cy0:
        return True
    for key, _, val in block:
        if key == 'pattern' and coat.pattern:
            draw_pattern(cv, coat, T, clip)
        elif key in ('colored_emblem', 'textured_emblem'):
            draw_emblem(cv, coat, key == 'colored_emblem', val, T, clip)
        elif key == 'sub':
            parent = get(val, 'parent')
            ov = {}
            for i in (1, 2, 3):
                v = get(val, 'color%d' % i)
                if v is not None:
                    c = parse_color(v, coat.pal)
                    if c:
                        ov['color%d' % i] = c
            for inst in insts(val, True):
                sx, sy = vec(inst, 'scale', (1.0, 1.0))
                fx, fy = vec(inst, 'offset', (0.0, 0.0))
                T2 = (ox + fx * W * kx, oy + fy * H * ky, kx * sx, ky * sy)
                draw_coat(cv, parent, T2, clip, depth + 1, ov, coas, stack + (name,))
    return True


def draw_pattern(cv, coat, T, clip):
    ox, oy, kx, ky = T
    w, h, d = pick_mip(coat.pattern, W * kx)
    c1, c2, c3 = coat.pal['color1'], coat.pal['color2'], coat.pal['color3']
    for y in range(int(clip[1]), int(math.ceil(clip[3]))):
        if not 0 <= y < H:
            continue
        ly = (y + .5 - oy) / ky
        row = min(h - 1, max(0, int(ly / H * h))) * w
        for x in range(max(0, int(clip[0])), min(W, int(math.ceil(clip[2])))):
            lx = (x + .5 - ox) / kx
            i = (row + min(w - 1, max(0, int(lx / W * w)))) * 4
            a = d[i + 3] / 255
            if a <= 0:
                continue
            g, b = d[i + 1] / 255, d[i + 2] / 255
            p = y * W + x
            na = 1 - a
            cv.r[p] = cv.r[p] * na + a * ((c1[0] + (c2[0] - c1[0]) * g) * (1 - b) + c3[0] * b)
            cv.g[p] = cv.g[p] * na + a * ((c1[1] + (c2[1] - c1[1]) * g) * (1 - b) + c3[1] * b)
            cv.b[p] = cv.b[p] * na + a * ((c1[2] + (c2[2] - c1[2]) * g) * (1 - b) + c3[2] * b)
            cv.a[p] = cv.a[p] * na + a


def draw_emblem(cv, coat, colored, eb, T, clip):
    mips = texture(get(eb, 'texture') or '')
    if not mips:
        return
    cols = [coat.color(get(eb, 'color1'), 'color1'), None, None]
    cols[1] = coat.color(get(eb, 'color2'), 'color1') if get(eb, 'color2') is not None else cols[0]
    cols[2] = coat.color(get(eb, 'color3'), 'color1') if get(eb, 'color3') is not None else cols[0]
    c1, c2, c3 = cols
    mask = [int(num(x)) for k, _, x in (get(eb, 'mask') or []) if k is None and num(x) is not None]
    pat_mip = pick_mip(coat.pattern, W * T[2]) if (mask and coat.pattern) else None
    ox, oy, kx, ky = T
    for inst in insts(eb, True):
        px, py = vec(inst, 'position', (0.5, 0.5))
        sx, sy = vec(inst, 'scale', (1.0, 1.0))
        rot = math.radians(num(get(inst, 'rotation', '0')) or 0.0)
        if sx == 0 or sy == 0:
            continue
        cs, sn = math.cos(rot), math.sin(rot)
        mw, mh, md = pick_mip(mips, abs(sx) * W * kx)
        hx, hy = abs(sx) * W / 2, abs(sy) * H / 2
        ccx, ccy = px * W, py * H
        ex = abs(hx * cs) + abs(hy * sn)
        ey = abs(hx * sn) + abs(hy * cs)
        x0 = max(int(clip[0]), int(ox + (ccx - ex) * kx), 0)
        x1 = min(int(math.ceil(clip[2])), int(math.ceil(ox + (ccx + ex) * kx)) + 1, W)
        y0 = max(int(clip[1]), int(oy + (ccy - ey) * ky), 0)
        y1 = min(int(math.ceil(clip[3])), int(math.ceil(oy + (ccy + ey) * ky)) + 1, H)
        iw, ih = 1 / (sx * W), 1 / (sy * H)
        for y in range(y0, y1):
            ly = (y + .5 - oy) / ky
            for x in range(x0, x1):
                lx = (x + .5 - ox) / kx
                dx, dy = lx - ccx, ly - ccy
                u = (dx * cs + dy * sn) * iw + .5
                v = (-dx * sn + dy * cs) * ih + .5
                if not (0 <= u < 1 and 0 <= v < 1):
                    continue
                i = (int(v * mh) * mw + int(u * mw)) * 4
                a = md[i + 3] / 255
                if a <= 0.004:
                    continue
                if mask:
                    if not pat_mip:
                        continue
                    a *= coat.mask_weight(pat_mip, lx, ly, mask)
                    if a <= 0.004:
                        continue
                r, g, b = md[i] / 255, md[i + 1] / 255, md[i + 2] / 255
                if colored:
                    # base = lerp(lerp(c1,c2,R),c3,G); shade with an overlay blend against B
                    cr = overlay(c1[0] + (c2[0] - c1[0]) * r + (c3[0] - c1[0] - (c2[0] - c1[0]) * r) * g, b)
                    cg = overlay(c1[1] + (c2[1] - c1[1]) * r + (c3[1] - c1[1] - (c2[1] - c1[1]) * r) * g, b)
                    cb = overlay(c1[2] + (c2[2] - c1[2]) * r + (c3[2] - c1[2] - (c2[2] - c1[2]) * r) * g, b)
                else:
                    cr, cg, cb = r, g, b
                p = y * W + x
                na = 1 - a
                cv.r[p] = cv.r[p] * na + a * cr
                cv.g[p] = cv.g[p] * na + a * cg
                cv.b[p] = cv.b[p] * na + a * cb
                cv.a[p] = cv.a[p] * na + a


# ---------------------------------------------------------------- picking the coat per tag

def govtypes():
    """tag -> government type at the 1337 start (own block, else first include template that sets one)."""
    def gtype(block):
        g = get(block, 'government')
        return get(g, 'type') if isinstance(g, list) else None
    tmpl = {}
    out = {}
    top, _ = read_script(SETUP + '1337/10_countries.txt')
    for tag, _, b in get(get(top, 'countries'), 'countries'):
        if not isinstance(b, list):
            continue
        t = gtype(b)
        for k, _, inc in b:
            if t or k != 'include':
                continue
            if inc not in tmpl:
                p = SETUP + 'templates/%s.txt' % inc
                tmpl[inc] = gtype(read_script(p)[0]) if os.path.exists(p) else None
            t = tmpl[inc]
        out[tag] = t
    return out


def trigger_ok(t, gov=None):
    """Tiny 1337-start evaluator: government atoms from the setup data, other atoms false (so NOT of them true)."""
    if t is None:
        return True

    def ev(b, mode='AND'):
        res = []
        for k, _, v in b:
            if k in ('AND', 'OR', 'NOT', 'NOR', 'NAND') and isinstance(v, list):
                r = ev(v, 'OR' if k in ('OR', 'NOR') else 'AND')
                res.append(not r if k in ('NOT', 'NOR', 'NAND') else r)
            elif k is None:
                continue
            elif k in GOV_ATOMS:
                res.append((gov == GOV_ATOMS[k]) == (v == 'yes'))
            elif k.startswith('has_variable'):
                res.append(False)
            else:
                res.append(v == 'no')
        if not res:
            return True
        return any(res) if mode == 'OR' else all(res)
    return ev(t)


def pick_coa(tag, coas, fdefs, gov=None):
    """-> (coa name or None, how). how in 'flagdef', 'tag', ''."""
    best = None
    for k, _, e in fdefs.get(tag, []):
        if k != 'flag_definition':
            continue
        name = get(e, 'coa')
        if not isinstance(name, str) or name == 'list' or name not in coas:
            continue
        if not trigger_ok(get(e, 'trigger'), gov):
            continue
        pr = num(get(e, 'priority', '0')) or 0
        if best is None or pr > best[0]:
            best = (pr, name)
    if best:
        return best[1], 'flagdef' if best[1] != tag else 'tag'
    if tag in coas:
        return tag, 'tag'
    return None, ''


# ---------------------------------------------------------------- rendering

def render(tag, coa, coas, out_dir):
    cv = Canvas()
    draw_coat(cv, coa, (0.0, 0.0, 1.0, 1.0), (0, 0, W, H), 0, {}, coas)
    cmd = ['magick', '-size', '%dx%d' % (W, H), '-depth', '8', 'rgba:-', '-filter', 'Box', '-resize',
           '%dx%d!' % (OUT_W, OUT_H), '+dither', '-colors', '255', '-define', 'png:compression-level=9',
           'PNG8:%s/%s.png' % (out_dir, tag)]
    subprocess.run(cmd, input=cv.rgba_bytes(), check=True, capture_output=True)


_G = {}


def work(args):
    tag, coa, out_dir = args
    try:
        render(tag, coa, _G['coas'], out_dir)
        return tag, None
    except Exception as e:  # keep the batch going
        return tag, repr(e)


def main():
    argv = sys.argv[1:]
    out_dir = os.path.join(HERE, 'public', 'flags')
    if '--out' in argv:
        i = argv.index('--out')
        out_dir = argv[i + 1]
        del argv[i:i + 2]
    os.makedirs(out_dir, exist_ok=True)
    tags = argv or list(json.load(open(os.path.join(HERE, 'public', 'nations.json')))['countries'])
    NAMED.update(load_colors())
    coas = load_coas()
    fb, _ = read_script(GAME + '/common/flag_definitions/00_flag_definitions.txt')
    fdefs = {k: v for k, _, v in fb if k and isinstance(v, list)}
    govs = govtypes()
    jobs, missing, via = [], [], collections.Counter()
    for t in tags:
        coa, how = pick_coa(t, coas, fdefs, govs.get(t))
        if coa:
            jobs.append((t, coa, out_dir))
            via[how] += 1
        else:
            missing.append(t)
    _G['coas'] = coas
    errs = []
    done = 0
    with multiprocessing.get_context("fork").Pool(min(os.cpu_count() or 1, 14)) as pool:
        for tag, err in pool.imap_unordered(work, jobs, chunksize=4):
            done += 1
            if err:
                errs.append((tag, err))
            if done % 100 == 0:
                print('  %d/%d' % (done, len(jobs)), flush=True)
    print('tags %d: rendered %d (coa==tag %d, via flag_definitions %d), errors %d, no coa %d'
          % (len(tags), len(jobs) - len(errs), via['tag'], via['flagdef'], len(errs), len(missing)))
    for t, e in errs:
        print('ERR', t, e)
    print('NO COA:', ' '.join(missing))


NAMED = {}

if __name__ == '__main__':
    main()
