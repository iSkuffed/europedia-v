"""Extract EU5 production data into data.js for index.html.
Usage: python3 -I build.py [game_dir]"""
import sys, os, glob, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdx import parse, get, items, num

GAME = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/.local/share/Steam/steamapps/common/Europa Universalis V/game')
C = f'{GAME}/in_game/common'
OUT = os.path.dirname(os.path.abspath(__file__))


def load(d):
    out = {}
    for f in sorted(glob.glob(f'{C}/{d}/*.txt')):
        for k, v in items(parse(open(f, encoding='utf-8-sig').read())):
            if isinstance(v, list):
                out[k] = v
    return out


def load_loc():
    loc = {}
    line = re.compile(r'^\s*([\w.\-]+):\d*\s+"(.*)"\s*(#.*)?$')
    for f in glob.glob(f'{GAME}/**/localization/english/**/*.yml', recursive=True):
        for l in open(f, encoding='utf-8-sig', errors='replace'):
            m = line.match(l)
            if m:
                loc.setdefault(m.group(1), m.group(2))
    return loc


goods_raw = load('goods')
loc = load_loc()
GOODS = set(goods_raw)
POPS = list(load('pop_types'))


def clean(s):  # strip loc formatting like [..] / #b ..#! / $refs$
    s = re.sub(r"\[Show\w*Adjective\w*\('(\w+)'\)\]", lambda m: loc.get(m.group(1) + '_ADJ', m.group(1).title()), s)
    s = re.sub(r'#\w+\s?|#!', '', s)
    return s.strip()


def resolve(text, depth=0):  # expand $other_key$ references
    if depth > 5:
        return text
    return re.sub(r'\$([\w.]+)(?:\|[^$]*)?\$', lambda m: resolve(loc[m.group(1)], depth + 1) if m.group(1) in loc else m.group(0), text)


def name(key, *cands):
    for c in cands:
        v = resolve(loc.get(c, ''))
        if v and '$' not in v:
            return clean(v)
    return key.replace('_', ' ').title()


def amounts(block):
    return {k: num(v) for k, v in items(block) if k in GOODS and num(v) is not None}


def recipe(rid, b):
    r = {'id': rid, 'in': amounts(b), 'cat': get(b, 'category')}
    if rid in loc:
        r['name'] = clean(loc[rid])
    if get(b, 'produced'):
        r['out'] = get(b, 'produced')
        r['amt'] = num(get(b, 'output')) or 0
    return r


goods = {}
for gid, b in goods_raw.items():
    goods[gid] = {
        'name': name(gid, gid, f'goods_{gid}'),
        'cat': get(b, 'category', 'raw_material'),
        'method': get(b, 'method', 'farming') if get(b, 'category', 'raw_material') == 'raw_material' else None,
        'food': num(get(b, 'food')),
        'price': num(get(b, 'default_market_price', '1')),
        'demand': {k: num(v) for k, v in items(get(b, 'demand_add') or [])},
        'demandMul': {k: num(v) for k, v in items(get(b, 'demand_multiply') or [])},
        'slave': get(b, 'is_slaves') == 'yes',
    }

pms = load('production_methods')
demands = {k: {'cat': get(b, 'category'), 'in': amounts(b)} for k, b in load('goods_demand').items()}
pop_demand = demands.pop('pop_demand', None)

buildings = {}
# who may build it: identity conditions (nation, culture, religion, government, place) in the potential/allow
# blocks; anything under NOT/NOR or a conditional trigger_if is skipped so we never state the opposite
REQ = {'has_or_had_tag': 'Nation', 'tag': 'Nation', 'culture': 'Culture', 'has_culture': 'Culture',
       'has_culture_group': 'Culture group', 'religion': 'Religion', 'has_religion': 'Religion',
       'religion_group': 'Religion group', 'government_type': 'Government', 'has_reform': 'Government reform',
       'region': 'Region', 'this': 'Location', 'owns': 'Location'}
SKIP = {'NOT', 'NOR', 'trigger_if', 'trigger_else_if', 'trigger_else', 'limit', 'if', 'else_if', 'else'}


def requirements(b):
    out = []
    def walk(block):
        for k, _, v in block or []:
            if isinstance(v, list):
                if k not in SKIP:
                    walk(v)
            elif k in REQ and isinstance(v, str) and (k not in ('this', 'owns') or v.startswith('location:')):
                if k in ('this', 'owns', 'region') and not re.match(r'(location|region):', v):
                    continue
                key = v.split(':', 1)[-1]
                if re.fullmatch(r'[\w]+', key) and key not in ('ROOT', 'root', 'prev', 'this', 'owner'):
                    r = [REQ[k], name(key, key)]
                    if r not in out:
                        out.append(r)
    for blk in ('country_potential', 'location_potential', 'potential', 'allow'):
        walk(get(b, blk))
    if sum(r[0] == 'Government' for r in out) >= 4:  # per-government variants, i.e. any government
        out = [r for r in out if r[0] != 'Government']
    return out


def event_only(b):  # allow = { always = no } (directly or inside a custom_tooltip) means never buildable normally
    allow = get(b, 'allow') or []
    return any(k == 'always' and v == 'no' for k, _, v in allow) or any(
        k == 'custom_tooltip' and isinstance(v, list) and get(v, 'always') == 'no' for k, _, v in allow)


for bid, b in load('building_types').items():
    recs = [recipe(k, v) for k, v in items(get(b, 'unique_production_methods') or [])]
    def refs(block):
        for k, _, v in block or []:
            if isinstance(v, list):
                yield from refs(v)
            elif k is None:
                yield v
    recs += [recipe(r, pms[r]) for r in refs(get(b, 'possible_production_methods')) if r in pms]
    cd = get(b, 'construction_demand')
    buildings[bid] = {
        'name': name(bid, bid, f'building_type_{bid}', f'building_{bid}'),
        'cat': get(b, 'category'),
        'pop': get(b, 'pop_type'),
        'obsolete': get(b, 'obsolete'),
        'recipes': recs,
        'build': cd if isinstance(cd, str) else None,
        'foreign': get(b, 'is_foreign') == 'yes',
        'req': requirements(b),
        'event': event_only(b),
    }

# units: demand fields resolve own -> copy_from chain -> unit category
ucats = load('unit_categories')
utypes = load('unit_types')


def ufield(uid, key, depth=0):
    u = utypes.get(uid)
    if not u or depth > 20:
        return None
    if get(u, key) is not None:
        return get(u, key)
    return ufield(get(u, 'copy_from'), key, depth + 1)


units = {}
for uid, u in utypes.items():
    cat = ufield(uid, 'category')
    cb = ucats.get(cat, [])
    dem = {k: ufield(uid, f'{k}_demand') or get(cb, f'{k}_demand') for k in ('maintenance', 'construction', 'repair')}
    dem['repair'] = dem['repair'] or dem['construction']
    units[uid] = {'name': name(uid, uid), 'cat': cat, 'hide': get(u, 'hide') == 'yes',
                  'age': ufield(uid, 'age'), 'dem': {k: v for k, v in dem.items() if v in demands}}

# any other script object pointing at a goods_demand via a *_demand key (laws, reforms, orders...)
demand_refs = {}
SKIP = {'building_types', 'unit_types', 'unit_categories', 'goods_demand', 'goods', 'production_methods'}


def scan(block, folder, owner):
    for k, _, v in block:
        if isinstance(v, list):
            scan(v, folder, owner)
        elif k and k.endswith('_demand') and v in demands:
            refs = demand_refs.setdefault(v, [])
            if (folder, owner) not in [(r['f'], r['id']) for r in refs]:
                refs.append({'f': folder, 'id': owner, 'name': name(owner, owner)})


for d in sorted(os.listdir(C)):
    if d in SKIP or not os.path.isdir(f'{C}/{d}'):
        continue
    for k, v in load(d).items():
        scan(v, d, k)

# ages: buildings / production methods unlocked by advances (no unlock advance = available from the start)
def age_no(a):
    m = re.match(r'age_(\d+)', a or '')
    return int(m.group(1)) if m else None


unlock_age = {}
for adv in load('advances').values():
    n = age_no(get(adv, 'age'))
    if n is None:
        continue
    for k, v in items(adv):
        if k in ('unlock_building', 'unlock_production_method') and isinstance(v, str):
            unlock_age[v] = min(n, unlock_age.get(v, n))
for bid, b in buildings.items():
    b['age'] = unlock_age.get(bid, 1)
    for r in b['recipes']:
        if r['id'] in unlock_age:
            r['age'] = unlock_age[r['id']]
ages = {}
for k in load('age'):
    if age_no(k):
        ages[age_no(k)] = name(k, k)

pops = {p: name(p, p, f'pop_type_{p}', f'{p}_pop') for p in POPS}
cats = {c: name(c, c) for c in {b['cat'] for b in buildings.values() if b['cat']}}

data = {'ages': ages, 'units': units, 'demandRefs': demand_refs, 'goods': goods, 'buildings': buildings, 'demands': demands, 'pops': pops, 'cats': cats,
        'icons': {d: sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(OUT, 'icons', d)))
                  for d in ('goods', 'buildings', 'pops', 'units') if os.path.isdir(os.path.join(OUT, 'icons', d))}}

with open(os.path.join(OUT, 'data.js'), 'w') as f:
    f.write('const DATA = ' + json.dumps(data, separators=(',', ':')) + ';\n')

n_rec = sum(len(b['recipes']) for b in buildings.values())
print(f'{len(units)} units, {len(demand_refs)} demands referenced elsewhere')
print(f'{len(goods)} goods, {len(buildings)} buildings, {n_rec} recipes, {len(demands)} demands, '
      f'{len(loc)} loc keys')
assert goods['cloth']['cat'] == 'produced'
assert any(r.get('out') == 'cloth' and 'wool' in r['in'] for r in buildings['cloth_guild']['recipes'])
assert units['a_houfnice']['dem'] == {'maintenance': 'artillery_maintenance', 'construction': 'artillery_construction',
                                      'repair': 'artillery_construction'}, units['a_houfnice']
assert buildings['furniture_workshop']['age'] == 4 and buildings['furniture_guild' if 'furniture_guild' in buildings else 'cloth_guild']['age'] == 1
assert ['Nation', 'Muscovy'] in buildings['bolshoi_theater']['req'] and buildings['bolshoi_theater']['event']
