"""Extract EU5 production data into src/data.json for the app.
Usage: python3 -I build.py [game_dir]"""
import sys, os, glob, json, re, itertools
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
        r['name'] = clean(resolve(loc[rid]))
    if get(b, 'produced'):
        r['out'] = get(b, 'produced')
        r['amt'] = num(get(b, 'output')) or 0
    return r


def combine(rs):  # one method per slot -> one recipe with summed inputs and output
    assert len({r.get('out') for r in rs}) == 1, [r['id'] for r in rs]
    r = {'id': '+'.join(r['id'] for r in rs), 'parts': [r['id'] for r in rs], 'in': {}, 'cat': rs[0]['cat'],
         'name': ' + '.join(r.get('name', r['id']) for r in rs)}
    for x in rs:
        for g, n in x['in'].items():
            r['in'][g] = round(r['in'].get(g, 0) + n, 4)
    if 'out' in rs[0]:
        r['out'], r['amt'] = rs[0]['out'], round(sum(x['amt'] for x in rs), 4)
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
    def refs(block):
        for k, _, v in block or []:
            if isinstance(v, list):
                yield from refs(v)
            elif k is None:
                yield v
    # each methods block is a slot; the building runs one method from every slot at once
    # (jewelry: gold/silver/copper base + ivory/amber/gems/pearls enhancement), so slots combine
    slots = [[recipe(k, v) for k, v in items(v)] if k == 'unique_production_methods'
             else [recipe(r, pms[r]) for r in refs(v) if r in pms]
             for k, _, v in b if k in ('unique_production_methods', 'possible_production_methods')]
    slots = [s for s in slots if s]
    recs = slots[0] if len(slots) == 1 else [combine(rs) for rs in itertools.product(*slots)] if slots else []
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
        a = [unlock_age[i] for i in r.get('parts', [r['id']]) if i in unlock_age]
        if a:
            r['age'] = max(a)
ages = {}
for k in load('age'):
    if age_no(k):
        ages[age_no(k)] = name(k, k)

pops = {p: name(p, p, f'pop_type_{p}', f'{p}_pop') for p in POPS}
cats = {c: name(c, c) for c in {b['cat'] for b in buildings.values() if b['cat']}}

# ---- what changes pop demand for a good ----------------------------------------------
# modifiers: global_<good>_pop_demand (+%) from ages, reforms, institutions, event modifiers...;
# goods_demand_modifier blocks (x multiplier) on cultures / religions; Promote Industry; and
# temporary market demand that events add (add_temporary_demand).
MM = f'{GAME}/main_menu/common'


def tree(path):  # (file, key, block) for top-level objects in every .txt under path
    for f in sorted(glob.glob(f'{path}/**/*.txt', recursive=True)):
        for k, v in items(parse(open(f, encoding='utf-8-sig').read())):
            if isinstance(v, list):
                yield f, k, v


def leaves(block):
    for k, _, v in block:
        if isinstance(v, list):
            yield from leaves(v)
        elif k:
            yield k, v


SV = {}
for path in (f'{MM}/script_values', f'{C}/script_values'):
    for f in glob.glob(f'{path}/*.txt'):
        for k, v in items(parse(open(f, encoding='utf-8-sig').read())):
            if num(v) is not None:
                SV[k] = num(v)
val = lambda v: num(v) if num(v) is not None else SV.get(v)
POP_MOD = re.compile(r'global_(\w+)_pop_demand$')
demand_mods = {}  # good ('*' = every good) -> [{kind, id, name, pct | mul, clergy?, by?}]


def add_mod(g, m):
    lst = demand_mods.setdefault(g, [])
    if m not in lst:
        lst.append(m)


static_mods = {}  # static modifier id -> {good: pct}
for f, k, v in tree(f'{MM}/static_modifiers'):
    for lk, lv in leaves(v):
        m = POP_MOD.match(lk)
        g = m.group(1) if m else '*' if lk == 'global_pop_demand' else None
        if g and (g == '*' or g in GOODS) and val(lv) is not None:
            static_mods.setdefault(k, {})[g] = val(lv)

# who applies those static modifiers (events, decisions, ...), and every temporary demand an event adds
appliers, temp_demand = {}, {}


def script_text(t):  # event titles: [ShowGoodsName('maize')] -> Maize, other runtime text -> "…"
    t = re.sub(r"\[Show\w*?Name\w*\('(\w+)'\)\]", lambda m: name(m.group(1), m.group(1), f'goods_{m.group(1)}'), t)
    return re.sub(r'\[[^\]]*\]', '…', t)


def title(folder, k, v):
    t = get(v, 'title')
    out = {'name': script_text(clean(resolve(loc[t]))) if isinstance(t, str) and t in loc else name(k, k)}
    if not re.search(r'\w', out['name'].replace('…', '')):  # title is all runtime text
        out['name'] = f'Untitled event ({k})'
    m = re.match(r'flavor_([a-z]{3})[._]', k)  # flavor_eng.21 -> an England event
    if folder == 'events' and m and m.group(1).upper() in loc:
        out['tag'] = clean(loc[m.group(1).upper()])
    return out


for root, folder_of in ((f'{GAME}/in_game/events', lambda f: 'events'),
                        (C, lambda f: os.path.relpath(f, C).split(os.sep)[0])):
    for f, k, v in tree(root):
        folder = folder_of(f)
        if folder in ('goods_demand', 'goods', 'building_types', 'production_methods') or '/debug/' in f:
            continue
        who = None
        def find(block):
            for bk, _, bv in block:
                if isinstance(bv, list):
                    if bk == 'add_temporary_demand':
                        t = get(bv, 'type', '')
                        d = t.split(':', 1)[-1]
                        if d in demands:
                            yield 'temp', d, bv
                    else:
                        yield from find(bv)
                elif bk == 'modifier' and bv in static_mods:
                    yield 'mod', bv, None
        for kind, x, bv in find(v):
            who = who or {'kind': folder, 'id': k, **title(folder, k, v)}
            if kind == 'mod':
                if who not in appliers.setdefault(x, []):
                    appliers[x].append(who)
            else:
                e = dict(who, months=val(get(bv, 'months')), scale=val(get(bv, 'scale')) or 1)
                if e not in temp_demand.setdefault(x, []):
                    temp_demand[x].append(e)

for mid, gs in static_mods.items():
    for g, pct in gs.items():
        add_mod(g, {'kind': 'modifier', 'id': mid, 'name': name(mid, f'STATIC_MODIFIER_NAME_{mid}', mid), 'pct': pct, 'by': appliers.get(mid, [])})

# modifier blocks on ages, reforms, religious aspects, institutions, societal values...
for d in sorted(os.listdir(C)):
    if not os.path.isdir(f'{C}/{d}') or d in ('industry_types', 'goods', 'goods_demand', 'building_types', 'production_methods'):
        continue
    for k, v in load(d).items():
        # societal values: left_modifier / right_modifier apply when leaning to that side ("Serfdom vs Free Subjects")
        sides = [(sk, sv) for sk, _, sv in v if sk in ('left_modifier', 'right_modifier')] if d == 'societal_values' else [(None, v)]
        for side, blk in sides:
            for lk, lv in leaves(blk):
                m = POP_MOD.match(lk)
                g = m.group(1) if m else '*' if lk == 'global_pop_demand' else None
                if g and (g == '*' or g in GOODS) and val(lv) is not None:
                    e = {'kind': d, 'id': k, 'name': name(k, k), 'pct': val(lv)}
                    if d == 'age':
                        e['age'] = age_no(k)
                    if side:
                        parts = e['name'].split(' vs ')
                        e['side'] = parts[side == 'right_modifier'] if len(parts) == 2 else side.split('_')[0]
                    add_mod(g, e)

# Promote Industry: every good in the industry gets global_<good>_pop_demand = pop_demand
for k, v in load('industry_types').items():
    pd = val(get(v, 'pop_demand'))
    for g in [x for x, _, _ in get(v, 'goods') or [] if x] + [vv for kk, _, vv in get(v, 'goods') or [] if kk is None]:
        if g in GOODS and pd:
            add_mod(g, {'kind': 'industry_types', 'id': k, 'name': name(k, k, f'industry_{k}'), 'pct': pd})

# x multipliers on every pop (or just clergy) of a culture / culture group / religion / religion group
for d in ('culture_groups', 'cultures', 'religion_groups', 'religions'):
    for k, v in load(d).items():
        for key, clergy in (('goods_demand_modifier', False), ('clergy_goods_demand_modifier', True)):
            for g, n in amounts(get(v, key) or []).items():
                add_mod(g, {'kind': d, 'id': k, 'name': name(k, k), 'mul': n, 'clergy': clergy})

data = {'demandMods': demand_mods, 'tempDemand': temp_demand, 'ages': ages, 'units': units, 'demandRefs': demand_refs, 'goods': goods, 'buildings': buildings, 'demands': demands, 'pops': pops, 'cats': cats,
        'icons': {d: sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(OUT, 'public', 'icons', d)))
                  for d in ('goods', 'buildings', 'pops', 'units') if os.path.isdir(os.path.join(OUT, 'public', 'icons', d))}}

with open(os.path.join(OUT, 'src', 'data.json'), 'w') as f:
    json.dump(data, f, separators=(',', ':'))

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
jg = buildings['jewelry_guild']['recipes']  # two slots: 3 bases x 4 enhancements
assert len(jg) == 12 and any(r['in'] == {'goods_gold': 0.5208, 'gems': 0.1042} and r['amt'] == 1.1 for r in jg), jg
assert any(m.get('mul') == 4 and m['id'] == 'andean_group' for m in demand_mods['potato'])
assert [m['pct'] for m in demand_mods['tobacco'] if m['kind'] == 'age'] == [-0.75, -0.75, -0.25, 0.5, 1.0, 1.5]
assert any(a['id'] == 'anglican_events.11' for m in demand_mods['fine_cloth'] if m['kind'] == 'modifier' for a in m['by'])
