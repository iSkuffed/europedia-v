"""Trace in_game/map_data/rivers.png into simplified polylines -> public/rivers.json.
Usage: python3 -I rivers.py [game_dir]
Format: {"w","h","lines":[[width 1-4, x0, y0, dx1, dy1, ...]]} in full-resolution map pixels (y down from the north edge)."""
import sys, os, re, json, time, zlib, struct

GAME = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/.local/share/Steam/steamapps/common/Europa Universalis V/game')
OUT = os.path.dirname(os.path.abspath(__file__))
TOL, MIN_LEN, MIN_RUN = 1.2, 4, 6
t0 = time.time()

# the PNG is 8-bit palette with filter 0 on every row, so inflating gives palette indices directly
d = open(f'{GAME}/in_game/map_data/rivers.png', 'rb').read()
o, idat, pal = 8, [], b''
while o < len(d):
    n, typ = struct.unpack('>I4s', d[o:o + 8])
    if typ == b'IHDR':
        W, H, depth, ctype = struct.unpack('>IIBB', d[o + 8:o + 18])
        assert (depth, ctype) == (8, 3), 'expected an 8-bit palette PNG'
    elif typ == b'PLTE':
        pal = d[o + 8:o + 8 + n]
    elif typ == b'IDAT':
        idat.append(d[o + 8:o + 8 + n])
    o += 12 + n
raw = zlib.decompress(b''.join(idat))
S = W + 1  # stride: filter byte + W indices
assert len(raw) == S * H and not any(raw[y * S] for y in range(H)), 'rows must use filter 0'

# palette index -> 1..4 river width, or 5 source / 6 flow-in / 7 split marker, 0 for background
BODY = [(0, 225, 255), (0, 200, 255), (0, 150, 255), (0, 100, 255), (0, 0, 255), (0, 0, 225), (0, 0, 200), (0, 0, 150),
        (0, 0, 100), (0, 85, 0), (0, 125, 0), (0, 158, 0), (24, 206, 0)]  # narrowest .. widest
WIDTH = [1, 1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4]
MARK = {(0, 255, 0): 5, (255, 0, 0): 6, (255, 252, 0): 7}
tbl = bytearray(256)
for i in range(len(pal) // 3):
    c = tuple(pal[3 * i:3 * i + 3])
    if c in MARK:
        tbl[i] = MARK[c]
    elif c in BODY:
        tbl[i] = WIDTH[BODY.index(c)]
m = raw.translate(bytes(tbl))
del raw
m += bytes(S + 1)  # padding so edge pixels can look at neighbours (negative indices land in it too)
pix = []
for r in re.finditer(rb'[\x01-\x07]+', m):
    pix.extend(range(r.start(), r.end()))
print(f'{len(pix)} river pixels, {time.time() - t0:.1f}s')

# neighbours: 4-way, plus a diagonal only when neither shared 4-neighbour is river (then it is not redundant)
nb = {}
for p in pix:
    e, w_, s_, n_ = m[p + 1], m[p - 1], m[p + S], m[p - S]
    a = [q for q, v in ((p + 1, e), (p - 1, w_), (p + S, s_), (p - S, n_)) if v]
    if not (e or s_) and m[p + S + 1]: a.append(p + S + 1)
    if not (w_ or s_) and m[p + S - 1]: a.append(p + S - 1)
    if not (e or n_) and m[p - S + 1]: a.append(p - S + 1)
    if not (w_ or n_) and m[p - S - 1]: a.append(p - S - 1)
    nb[p] = a
# a diagonal link must be mutual (the other pixel's check may have found a shared 4-neighbour)
for p, a in nb.items():
    a[:] = [q for q in a if p in nb[q]]
node = {p for p, a in nb.items() if len(a) != 2 or m[p] > 4}


def dp(pts, tol):  # Douglas-Peucker, iterative
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    st = [(0, len(pts) - 1)]
    while st:
        i, j = st.pop()
        (x1, y1), (x2, y2) = pts[i], pts[j]
        dx, dy = x2 - x1, y2 - y1
        L = (dx * dx + dy * dy) ** 0.5 or 1
        best, bk = -1, 0
        for k in range(i + 1, j):
            dist = abs(dy * (pts[k][0] - x1) - dx * (pts[k][1] - y1)) / L if (dx or dy) else abs(pts[k][0] - x1) + abs(pts[k][1] - y1)
            if dist > best:
                best, bk = dist, k
        if best > tol:
            keep[bk] = True
            st += [(i, bk), (bk, j)]
    return [p for p, k in zip(pts, keep) if k]


lines, npts, wcount = [], 0, [0] * 5


def emit(path):
    global npts
    if len(path) < MIN_LEN:
        return
    cl = [m[p] if m[p] <= 4 else 0 for p in path]  # markers inherit the neighbouring width
    last = 0
    for i, c in enumerate(cl):
        last = c or last
        cl[i] = last
    last = next((c for c in cl if c), 1)
    for i in range(len(cl) - 1, -1, -1):
        last = cl[i] = cl[i] or last
    runs = []  # [class, start, end] ; runs shorter than MIN_RUN take the previous run's class
    for i, c in enumerate(cl):
        if runs and runs[-1][0] == c:
            runs[-1][2] = i
        else:
            runs.append([c, i, i])
    k = 0
    while len(runs) > 1 and k < len(runs):
        if runs[k][2] - runs[k][1] + 1 < MIN_RUN:
            j = k - 1 if k else k + 1
            runs[j][0:3] = [runs[j][0], min(runs[j][1], runs[k][1]), max(runs[j][2], runs[k][2])]
            del runs[k]
            k = max(k - 1, 0)
            # merge equal neighbours
            while k + 1 < len(runs) and runs[k][0] == runs[k + 1][0]:
                runs[k][2] = runs[k + 1][2]
                del runs[k + 1]
        else:
            k += 1
    for c, a, b in runs:
        seg = [(p % S - 1, p // S) for p in path[a:b + 1 + (b + 1 < len(path))]]  # overlap one pixel so segments join
        if len(seg) < 2:
            continue
        s = dp(seg, TOL)
        row = [c, *s[0]]
        for (x0, y0), (x1, y1) in zip(s, s[1:]):
            row += [x1 - x0, y1 - y0]
        lines.append(row)
        npts += len(s)
        wcount[c] += 1


seen_edge, seen = set(), set()
for n0 in node:
    for q in nb[n0]:
        if q in seen or (q in node and (n0, q) in seen_edge):
            continue
        path, prev, cur = [n0, q], n0, q
        while cur not in node:
            seen.add(cur)
            a = nb[cur]
            nxt = a[0] if a[0] != prev else a[1]
            path.append(nxt)
            prev, cur = cur, nxt
        if len(path) == 2:
            seen_edge.update(((n0, q), (q, n0)))
        emit(path)
for p in pix:  # pure loops: degree-2 chains with no node
    if p not in seen and p not in node:
        path, prev, cur = [p], None, p
        while True:
            seen.add(cur)
            nxt = next((x for x in nb[cur] if x != prev and x not in seen), None)
            if nxt is None:
                break
            path.append(nxt)
            prev, cur = cur, nxt
        emit(path + [p])

with open(f'{OUT}/public/rivers.json', 'w') as f:
    json.dump({'w': W, 'h': H, 'lines': lines}, f, separators=(',', ':'))
size = os.path.getsize(f'{OUT}/public/rivers.json')
print(f'{len(lines)} lines, {npts} points, width classes {wcount[1:]}, {size} bytes, {time.time() - t0:.1f}s')
assert size < 1.9e6
