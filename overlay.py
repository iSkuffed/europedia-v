"""Merge the base game and its DLC folders into one tree at .game/, so the extractors see DLC content (advances, privileges,
reforms, buildings, units, laws...) as if it were part of the base game. Directories that exist in more than one source are
merged; everything else is a symlink back into the install. DLC files use `INJECT:name = {...}` to add content to an existing
base object; those blocks are spliced into the target here, so the extractors never see the prefix. Usage: python3 overlay.py [path/to/Europa Universalis V/game]"""
import sys, os, glob, re, shutil

GAME = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/.local/share/Steam/steamapps/common/Europa Universalis V/game')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.game')
dlcs = [d for d in sorted(glob.glob(f'{GAME}/dlc/*')) if os.path.isdir(d)]
conflicts = []


def merge(srcs, dst):
    os.makedirs(dst)
    names = {}
    for s in srcs:
        for n in os.listdir(s):
            if s in dlcs and not os.path.isdir(os.path.join(s, n)):
                continue  # a DLC's own manifest/thumbnail files, not content
            names.setdefault(n, []).append(os.path.join(s, n))
    for n, paths in names.items():
        dirs = [p for p in paths if os.path.isdir(p)]
        if len(dirs) > 1:
            merge(dirs, os.path.join(dst, n))
        else:
            if len(paths) > 1:  # same file in base and DLC: the DLC one wins
                conflicts.append(os.path.relpath(paths[-1], GAME))
            os.symlink(paths[-1], os.path.join(dst, n))


def top_blocks(t):  # [(key, start, body_start, end)] for every top-level `key = { ... }`, skipping comments and strings
    out, depth, last, i = [], 0, 0, 0
    while i < len(t):
        c = t[i]
        if c == '#':
            i = t.find('\n', i) if t.find('\n', i) >= 0 else len(t)
        elif c == '"':
            i = t.find('"', i + 1) if t.find('"', i + 1) >= 0 else len(t)
        elif c == '{':
            if depth == 0:
                m = re.search(r'([\w:.\-]+)\s*=\s*$', t[last:i])
                key, start, body = (m.group(1), last + m.start(1), i + 1) if m else (None, i, i + 1)
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                out.append((key, start, body, i))
                last = i + 1
        i += 1
    return out


def read(p):
    return open(p, encoding='utf-8-sig').read()


def write(p, text):  # replace the symlink with a real, patched file
    os.unlink(p)
    open(p, 'w', encoding='utf-8').write(text)


def inject():
    n = 0
    for d in dlcs:
        for f in glob.glob(f'{d}/**/common/**/*.txt', recursive=True):
            t = read(f)
            inj = [b for b in top_blocks(t) if b[0] and b[0].startswith(('INJECT:', 'TRY_INJECT:'))]
            if not inj:
                continue
            rel = os.path.relpath(f, d)
            for key, start, body, end in inj:
                name = key.split(':', 1)[1]
                for g in glob.glob(f'{OUT}/{os.path.dirname(rel)}/*.txt'):
                    gt = read(g)
                    hit = [b for b in top_blocks(gt) if b[0] == name]
                    if hit:
                        write(g, gt[:hit[0][3]] + t[body:end] + gt[hit[0][3]:])
                        n += 1
                        break
                else:
                    sys.exit(f'overlay: no target for {key} from {rel}')
            for key, start, body, end in sorted(inj, key=lambda b: -b[1]):
                t = t[:start] + t[end + 1:]
            write(f'{OUT}/{rel}', t)
    return n


if os.path.lexists(OUT):
    shutil.rmtree(OUT)
merge([GAME, *dlcs], OUT)  # game/dlc itself stays a plain link (art lookups glob it)
injected = inject()
print(f'merged {len(dlcs)} DLC folders into {OUT}; {len(conflicts)} files overridden by a DLC, {injected} INJECT blocks spliced' + (f' ({", ".join(conflicts[:5])})' if conflicts else ''))
