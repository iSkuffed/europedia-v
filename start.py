"""Starting positions per country, read from a PLAIN-TEXT EU5 save made at the 1337 campaign start.

    python3 -I start.py [save.eu5]      -> public/start.json   (no text save found: message, exit 0, file untouched)

Schema (only tags present in public/nations.json):
  { "date": "<save date>", "setup": "<date that marks setup-time entries>",
    "countries": { TAG: {
        "gov": "monarchy",                       government.type                              [start]
        "privileges": [id, ...],                 implemented_privileges dated <setup>         [start, see drift]
        "laws": {law: policy},                   implemented_laws dated <setup>               [start; changed laws omitted]
        "reforms": [id, ...],                    implemented_reforms dated <setup>            [start]
        "values": [n, ...],                      societal_values in the order of top-level "axes"; null = unused axis (-999)  [as of save date]
        "estates": {estate_type: satisfaction},  0-1, only estates that exist                          [as of save date]
    } } }  (+ top-level "axes": [societal value names]; kept compact because jj refuses files over 2 MiB)
NOT available: estate power and crown power. The save does not store them (estate objects only carry
satisfaction / wealth_impact / gold); the engine recomputes them from pop political weight, privileges, laws,
control, legitimacy, advances.

Sources in the save: estate_manager.database.<id> (col 0 `id={`), countries.database.<id>.government.
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import Counter
from pdx import parse, get, items

HERE = os.path.dirname(os.path.abspath(__file__))
SAVES = os.path.expanduser('~/.local/share/Steam/steamapps/compatdata/3450310/pfx/drive_c/users/steamuser/'
                           'Documents/Paradox Interactive/Europa Universalis V/save games/')
DEFAULT = SAVES + 'SP_BYZ_1337_12_01_e9c1cb66-2afe-4f50-921f-cc8f81108fff.eu5'
OUT = f'{HERE}/public/start.json'
KV = re.compile(r'^\t(\w+)=([^{\s]+)$')
ID = re.compile(r'^(\d+)=\{$')


def stream(path):
    """-> (date, {estate id: fields}, {tag: (government block, estate-privilege cooldown estates)})"""
    date, estates, govs = '', {}, {}
    sect = cur = buf = gov = name = None
    ingov = in_cool = False
    cool = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if cur is None:                                     # between id blocks
                if line[0] not in '\t\n}':
                    m = ID.match(line)
                    if m and sect in ('estate_manager', 'countries'):
                        cur, buf, gov, ingov, name, cool, in_cool = m.group(1), {}, [], False, None, [], False
                    elif line.endswith('={\n'):
                        sect = line[:-3]
                        if sect == 'market_manager':
                            break
                elif sect == 'metadata' and not date and line.startswith('\tdate='):
                    date = line.split('=')[1].strip()
                continue
            if line[0] == '}':                                  # end of the id block
                if sect == 'estate_manager':
                    estates[cur] = buf
                elif name:
                    govs[name] = (parse(''.join(gov)) if gov else [], cool)
                cur = None
            elif sect == 'estate_manager':
                m = KV.match(line)
                if m:
                    buf[m.group(1)] = m.group(2)
            elif ingov:                                         # inside the government block
                gov.append(line)
                ingov = line != '\t}\n'
            elif line == '\tgovernment={\n':
                gov, ingov = ['x={\n'], True                    # wrap: parse() then yields [(x, block)]
            elif line.startswith('\tdefinition='):
                name = line.split('=')[1].strip()
            elif line.rstrip().endswith('estate_privilege={'):   # cooldowns: <estate>=<date until>
                in_cool = True
            elif in_cool:
                m = re.match(r'^\t*(\w+_estate)=', line)
                if m:
                    cool.append(m.group(1))
                else:
                    in_cool = False
    return date, estates, govs


def dated(entries, setup):
    """implemented_* list of {date,days,object} -> [object] setup-dated, count of later ones"""
    ok, late = [], 0
    for k, _, v in entries:
        if k is not None:
            continue
        if get(v, 'date') == setup:
            ok.append(get(v, 'object'))
        else:
            late += 1
    return ok, late


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    try:
        head = open(path, 'rb').read(400)
    except OSError:
        head = b''
    if not head.startswith(b'SAV0200') or b'metadata={' not in head:
        print(f'start.py: no plain-text EU5 save at {path}; leaving {OUT} untouched')
        return
    known = set(json.load(open(f'{HERE}/public/nations.json'))['countries'])
    date, estates, govs = stream(path)

    AXES = sorted({k for gov, _ in govs.values() for k, _ in items(get(get(gov, 'x') or [], 'societal_values') or [])})
    # setup date = the most common date over all implemented_privileges
    dates = Counter()
    for gov, _ in govs.values():
        g = get(get(gov, 'x') or [], 'implemented_privileges') or []
        dates.update(get(v, 'date') for k, _, v in g if k is None)
    setup = dates.most_common(1)[0][0]

    out, drift = {}, Counter()
    for tag, (gov, cool) in govs.items():
        g = get(gov, 'x')
        if tag not in known or not g:
            continue
        privs, late = dated(get(g, 'implemented_privileges') or [], setup)
        laws, late_laws = {}, 0
        for law, v in items(get(g, 'implemented_laws') or []):
            if get(v, 'date') == setup:
                laws[law] = get(v, 'object')
            else:
                late_laws += 1
        reforms, late_ref = dated(get(g, 'implemented_reforms') or [], setup)
        e = {}
        for et, eid in items(get(g, 'estates') or []):
            o = estates.get(eid, {})
            if o.get('existence') == 'yes':
                e[et] = round(float(o.get('satisfaction', 0.5)), 3)   # no field = never moved off the 50% default
        sv = dict(items(get(g, 'societal_values') or []))
        vals = [round(float(sv[a]), 1) if a in sv and float(sv[a]) > -999 else None for a in AXES]
        out[tag] = {'gov': get(g, 'type'), 'privileges': privs, 'laws': laws, 'reforms': reforms,
                    'values': vals, 'estates': e}
        drift['added_privileges'] += bool(late)
        drift['changed_laws'] += bool(late_laws)
        drift['changed_reforms'] += bool(late_ref)
        drift['privilege_cooldown_(possible_revocation)'] += bool(cool)
        drift['any_of_the_above'] += bool(late or late_laws or late_ref or cool)

    # display names for every id used (eu5lib reads argv[1] as the game dir, so hide the save path from it)
    argv, sys.argv = sys.argv, sys.argv[:1]
    from eu5lib import name, load, get as eget
    sys.argv = argv
    estate_of = {k: eget(v, 'estate') for k, v in load('estate_privileges').items()}  # privilege -> estate
    ids = {x for c in out.values() for x in (*c['privileges'], *c['laws'], *c['laws'].values(), *c['reforms'], *c['estates'], c.get('gov') or '') if x}
    ids |= set(estate_of.values()) - {None}
    names = {i: name(i, f'{i}_name', f'government_{i}') for i in sorted(ids)}
    json.dump({'date': date, 'setup': setup, 'axes': AXES, 'axisNames': [name(a).split(' vs ', 1) if ' vs ' in name(a) else a.split('_vs_') for a in AXES], 'names': names,
               'estateOf': {p: estate_of[p] for p in sorted({p for c in out.values() for p in c['privileges']}) if estate_of.get(p)}, 'countries': out}, open(OUT, 'w', encoding='utf-8'),
              separators=(',', ':'), ensure_ascii=False)
    n = len(out)
    print(f'save {date}, setup-date {setup}: {n} countries, avg {sum(len(c["privileges"]) for c in out.values()) / n:.1f} '
          f'privileges, {sum(1 for c in out.values() if c["privileges"])} with any')
    print('drift (countries):', dict(drift))
    for t in ('MOS', 'NOV', 'FRA', 'NAV'):
        print(t, json.dumps(out.get(t), ensure_ascii=False))


if __name__ == '__main__':
    main()
