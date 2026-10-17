"""Extract EU5 production data into src/data.json for the app.
Usage: python3 -I build.py [game_dir]"""
import sys, os, glob, json, re, itertools, colorsys, subprocess
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

# modifier keys that make room for a pop type or move pops between types
POP_KEY = re.compile(r'(local|global)_(\w+?)_(?:(city|rural)_)?desired_pop(_scaled)?$|(local|global)_pop_(promotion|demotion)_speed(_modifier)?$|local_tribal_promotion$'
                     r'|(local|global)_(\w+_pop|population)_growth$|(local|global|total)_population_capacity(_modifier)?$|(local|global)_food_capacity(_modifier)?$'
                     r'|cap_maximum_population_growth_at_zero$')
pop_keys = lambda blk: {k: 1 if x == 'yes' else val(x) for k, x in leaves(blk) if POP_KEY.match(k) and (x == 'yes' or val(x) is not None)}
pop_static = {k: m for f, k, v in tree(f'{MM}/static_modifiers') if k != 'location_base_values' and (m := pop_keys(v))}

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
                elif bk == 'modifier' and (bv in static_mods or bv in pop_static):
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

# ---- pops: social classes, where they come from, what makes room for them -------------------
def text(s):  # concept text: [pops|e] -> pops, [ShowPopTypeName('burghers')] -> Burghers
    s = re.sub(r"\[Show\w*?Name\w*\('(\w+)'\)\]", lambda m: pops.get(m.group(1)) or name(m.group(1), m.group(1)), resolve(s))
    s = re.sub(r'\[(\w+)(?:\|\w+)?\]', lambda m: clean(loc.get(m.group(1), m.group(1).replace('_', ' '))).lower(), s)
    return clean(re.sub(r'\[[^\]]*\]', '…', s))


mod_name = lambda k: text(loc[f'MODIFIER_TYPE_NAME_{k}']) if f'MODIFIER_TYPE_NAME_{k}' in loc else k.replace('_', ' ').capitalize()
estates = load('estates')
pop_types = {}
for p, v in load('pop_types').items():
    est = next((k for k, _, b in v if k and k.endswith('_estate') and b == []), None)
    pop_types[p] = {
        'desc': text(loc.get(f'{p}_desc', '')), 'estate': est and name(est, est),
        'upper': get(v, 'upper') == 'yes', 'cap': get(v, 'has_cap') == 'yes', 'power': num(get(v, 'power_per_pop')),
        'tax': num(get(estates.get(est) or [], 'tax_per_pop')), 'food': num(get(v, 'pop_food_consumption')) or 0,
        'promoteTo': [x for k, _, x in v if k == 'promote_to'],
        'promo': num(get(v, 'promotion_factor')), 'migration': num(get(v, 'migration_factor')),
        'assim': num(get(v, 'assimilation_conversion_factor')),
        'literacy': [[mod_name(k), val(x)] for k, x in items(get(v, 'literacy_impact') or [])],
        'share': [[mod_name(k), val(x)] for k, x in items(get(v, 'pop_percentage_impact') or [])],
    }

ranks = []
for k, v in load('location_ranks').items():
    allow = get(v, 'allow') or []
    ranks.append({'id': k, 'name': name(k, k), 'mods': pop_keys(get(v, 'rank_modifier') or []),
                  'minPop': next((num(x) for kk, op, x in allow if kk == 'population' and op == '>='), None)})
base = {}
for f, k, v in tree(f'{MM}/static_modifiers'):
    if k == 'location_base_values':
        base = pop_keys(v)
pop_sources = [{'kind': 'building_types', 'id': k, 'mods': m} for k, v in load('building_types').items() if (m := pop_keys(v))]
# the comment above a static modifier says how the game scales it ("multiplies with prosperity in location (0 to 1)")
notes = {m.group(2): ' '.join(l.lstrip('# ').strip() for l in m.group(1).splitlines() if l.strip('# '))
         for f in glob.glob(f'{MM}/static_modifiers/*.txt') for m in re.finditer(r'((?:^#.*\n)+)(\w+)\s*=\s*\{', open(f, encoding='utf-8-sig').read(), re.M)}
for k, m in pop_static.items():  # starving, overpopulation, river, capital... (applied by the game itself, or by events)
    n = f'STATIC_MODIFIER_NAME_{k}'
    nm = text(loc[n]) if n in loc else name(k, k)
    e = {'kind': 'modifier', 'id': k, 'name': nm[:1].upper() + nm[1:], 'mods': m, 'by': appliers.get(k, [])}
    if notes.get(k) and not set(notes[k]) <= set('#-= '):
        e['note'] = notes[k]
    pop_sources.append(e)
for d in sorted(os.listdir(C)):
    if not os.path.isdir(f'{C}/{d}') or d in ('building_types', 'location_ranks', 'pop_types', 'goods', 'production_methods'):
        continue
    for k, v in load(d).items():
        if m := pop_keys(v):
            e = {'kind': d, 'id': k, 'name': text(loc[k]) if k in loc else name(k, k), 'mods': m}
            if d == 'advances' and get(v, 'age'):
                e['age'] = age_no(get(v, 'age'))
            if d in ('advances', 'laws', 'estate_privileges') and (m := re.match(r'([a-z]{3})_', k)) and m.group(1).upper() in loc:  # hun_strengthened_towns -> Hungary only
                e['tag'] = clean(loc[m.group(1).upper()])
            pop_sources.append(e)
defines = open(f'{GAME}/loading_screen/common/defines/00_defines.txt', encoding='utf-8-sig').read()
define = lambda k: float(re.search(rf'\b{k}\s*=\s*([\d.]+)', defines).group(1))
pop_info = {'food': {k: define(k) for k in ('FOOD_SURPLUS_POP_GROWTH', 'FOOD_STORAGE_POP_GROWTH', 'STARVING_ON_FOOD_DEMAND')},
            'types': pop_types,
            'text': {k: text(loc[f'game_concept_{k}_desc']) for k in ('population_growth', 'population_capacity')}, 'ranks': ranks[::-1], 'base': base, 'sources': pop_sources,
            'modNames': {k: mod_name(k) for s in [base, *[r['mods'] for r in ranks], *[s['mods'] for s in pop_sources]] for k in s}}
mod_types = {k: v for f, k, v in tree(f'{MM}/modifier_type_definitions')}
pop_info['pct'] = sorted(k for k in pop_info['modNames'] if get(mod_types.get(k, []), 'percent') == 'yes')

# conditions that scale a good's pop demand (winter, climate, region...) or limit it to one area
COND = ('winter', 'climate', 'topography', 'continent', 'sub_continent', 'region')
for gid, b in goods_raw.items():
    cond = {c: {name(k, k): num(x) for k, x in items(get(b, f'{c}_demand_modifier') or [])} for c in COND}
    cond = {c: x for c, x in cond.items() if x}
    only = [name(x, x) for k, _, x in b if k and k.startswith('demand_only_in_')]
    if only:
        cond['only'] = only
    for k in ('disease', 'market_unavailability'):
        if num(get(b, f'{k}_demand_modifier')):
            cond[k] = num(get(b, f'{k}_demand_modifier'))
    if num(get(b, 'literacy_demand_factor')):
        cond['literacy'] = num(get(b, 'literacy_demand_factor'))
    if cond:
        goods[gid]['cond'] = cond

# ---- nations at the 1337 start: owned locations, their raw goods and map positions -> public/nations.json
SETUP, MAP = f'{GAME}/main_menu/setup/1337', f'{GAME}/in_game/map_data'
setup = lambda f: parse(open(f'{SETUP}/{f}', encoding='utf-8-sig').read())
pos = {m[0]: (round(float(m[1])), round(float(m[2]))) for m in re.findall(
    r'id=(\w+)\s*position=\{ ([\d.]+) [-\d.]+ ([\d.]+)', open(f'{GAME}/in_game/gfx/map/map_objects/generated_locators_city.txt').read())}
tmpl = {k: v for k, _, v in parse(open(f'{MAP}/location_templates.txt', encoding='utf-8-sig').read())}
area_of = {}
def walk(b, path):
    for k, _, v in b:
        if isinstance(v, list):
            walk(v, path + [k])
        elif k is None and len(path) >= 4:
            area_of[v] = path[3]  # continent > sub-continent > region > area > province > location
walk(parse(open(f'{MAP}/definitions.txt', encoding='utf-8-sig').read()), [])
ranks = {k: get(v, 'rank') for k, _, v in get(setup('07_cities_and_buildings.txt'), 'locations') or [] if isinstance(v, list) and get(v, 'rank')}
loc_pops = {k: [(get(d, 'type'), get(d, 'culture'), get(d, 'religion'), num(get(d, 'size')) or 0) for x, _, d in v if x == 'define_pop']
            for k, _, v in get(setup('06_pops.txt'), 'locations') or [] if isinstance(v, list)}  # location -> [(type, culture, religion, thousands)]
def rgb(kind, a, b, c):
    frac = any('.' in str(x) for x in (a, b, c))  # rgb { 0.36 0.13 0.28 } is 0-1, rgb { 92 33 71 } is 0-255
    a, b, c = float(a), float(b), float(c)
    if kind == 'rgb':
        return [round(x * 255) for x in (a, b, c)] if frac else [round(a), round(b), round(c)]
    h, s, v = (a / 360, b / 100, c / 100) if kind == 'hsv360' else (a, b, c)
    return [round(x * 255) for x in colorsys.hsv_to_rgb(h, s, v)]
colors = {m[0]: rgb(*m[1:]) for f in glob.glob(f'{MM}/named_colors/*.txt')
          for m in re.findall(r'(\w+)\s*=\s*(rgb|hsv360|hsv)\s*\{\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)', open(f, encoding='utf-8-sig').read())}
ccol, official = {}, {}  # official: tag -> (primary culture, religion) as the game sets them
for f in glob.glob(f'{GAME}/in_game/setup/countries/*.txt'):
    for k, _, v in parse(open(f, encoding='utf-8-sig').read()):
        if isinstance(v, list):
            official[k] = (get(v, 'culture_definition'), get(v, 'religion_definition'))
        c = isinstance(v, list) and get(v, 'color')
        if isinstance(c, str) and c in colors:
            ccol[k] = colors[c]
    nocomments = re.sub(r'#[^\n]*', '', open(f, encoding='utf-8-sig').read())  # "MLO = { #Milan" hid the colour
    for m in re.findall(r'^(\w+)\s*=\s*\{\s*color\s*=\s*(rgb|hsv360|hsv)\s*\{\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)', nocomments, re.M):
        ccol[m[0]] = rgb(*m[1:])  # inline colour
over = {}
for a, b, t in re.findall(r'dependency\s*=\s*\{\s*first\s*=\s*(\w+)\s+second\s*=\s*(\w+)\s+subject_type\s*=\s*(\w+)', open(f'{SETUP}/12_diplomacy.txt', encoding='utf-8-sig').read()):
    over[b] = [a, name(t, f'subject_type_{t}_name', t)]
L, idx, areas, countries = [], {}, [], {}
RANK = {'town': 1, 'city': 2}
def lidx(l):
    if l not in idx:
        a = area_of.get(l, '')
        if a not in areas:
            areas.append(a)
        idx[l] = len(L)
        L.append([name(l, l), get(tmpl.get(l, []), 'raw_material') or '', *pos[l], '', RANK.get(ranks.get(l), 0), areas.index(a)])
    return idx[l]
for tag, _, b in get(get(setup('10_countries.txt'), 'countries'), 'countries'):
    if not isinstance(b, list):
        continue
    locs = [x for k, _, v in b if k and k.startswith('own_') and isinstance(v, list) for _, _, x in v if x in pos]
    if not locs:
        continue
    for l in locs:
        L[lidx(l)][4] = tag
    tot, cul, rel = {}, {}, {}
    for t, c, r, n in (p for l in locs for p in loc_pops.get(l, [])):
        tot[t] = round(tot.get(t, 0) + n, 3); cul[c] = cul.get(c, 0) + n; rel[r] = rel.get(r, 0) + n
    top = lambda d: name(max(d, key=d.get), max(d, key=d.get)) if d else None
    by = lambda d: {name(k, k): round(n, 3) for k, n in sorted(d.items(), key=lambda x: -x[1]) if n}  # name -> thousands
    oc, orl = official.get(tag, (None, None))
    cap = get(b, 'capital')
    countries[tag] = {'name': name(tag, tag), 'cap': lidx(cap) if cap in pos else None, 'locs': [idx[l] for l in locs],
                      'color': ccol.get(tag), 'pops': tot, 'culture': name(oc, oc) if oc else top(cul), 'religion': name(orl, orl) if orl else top(rel),
                      'cul': by(cul), 'rel': by(rel),
                      'over': over.get(tag), 'rank': name(get(b, 'country_rank') or '', get(b, 'country_rank') or '')}
for l in pos:  # every other land location with a raw good, unowned or not, so neighbours can be listed
    if get(tmpl.get(l, []), 'raw_material'):
        lidx(l)
# a 1/8-scale map of locations for the nation page (public/map.png, north up, x wraps): each pixel's
# red*256 + green is 0 for water, 1 for land with no entry above (wasteland), or i + 2 for locs[i]
dmap = parse(open(f'{MAP}/default.map', encoding='utf-8-sig').read())
water = {x for k in ('sea_zones', 'lakes') for _, _, x in get(dmap, k)}
mcode = {}
for f in glob.glob(f'{MAP}/named_locations/*.txt'):
    for k, _, v in parse(open(f, encoding='utf-8-sig').read()):
        mcode[bytes.fromhex(v.zfill(6))] = 0 if k in water else idx[k] + 2 if k in idx else 1
for MAP_SCALE, mfile in ((8, 'map.png'), (4, 'world.png')):  # world.png: same encoding at 1/4 scale for the Map tab
    raw = subprocess.run(['magick', f'{MAP}/locations.png', '-sample', f'{100 / MAP_SCALE}%', 'rgb:-'], capture_output=True, check=True).stdout
    px = bytearray(len(raw))
    for i in range(0, len(raw), 3):
        c = mcode.get(raw[i:i + 3], 1)
        px[i], px[i + 1] = c >> 8, c & 255
    mw, mh = 16384 // MAP_SCALE, 8192 // MAP_SCALE
    subprocess.run(['magick', '-size', f'{mw}x{mh}', '-depth', '8', 'rgb:-', '-strip', '-define', 'png:color-type=2', '-define', 'png:compression-level=9',
                    f'{OUT}/public/{mfile}'], input=bytes(px), check=True)
    mx, mz = L[countries['MOS']['cap']][2:4]
    near = [3 * (((8192 - mz) // MAP_SCALE + dy) * mw + mx // MAP_SCALE + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    assert countries['MOS']['cap'] + 2 in [px[o] * 256 + px[o + 1] for o in near], f'{mfile}: Moscow is not at its locator'
    assert os.path.getsize(f'{OUT}/public/{mfile}') < 1.9e6
assert countries['MOS']['name'] == 'Muscovy' and L[countries['MOS']['cap']][0] == 'Moscow' and L[countries['MOS']['cap']][5] == 2 and countries['FRA']['color'] and countries['PSK']['over'][0] == 'NOV'
def col(v):  # named colour, or an rgb/hsv literal parsed as a block of numbers
    if isinstance(v, str):
        return colors.get(v)
    if isinstance(v, list) and len(v) == 3:
        return rgb('rgb', *[x for _, _, x in v])
with open(f'{OUT}/public/nations.json', 'w') as f:
    rel_defs = load('religions')
    rel_colors = {name(k, k): '#%02x%02x%02x' % tuple(col(get(v, 'color'))) for k, v in rel_defs.items() if col(get(v, 'color'))}  # religion display name -> colour
    json.dump({'locs': L, 'areas': [name(a, a) for a in areas], 'countries': countries, 'relColors': rel_colors}, f, separators=(',', ':'), ensure_ascii=False)

# ---- map modes for the Map tab: per-location class indices + colour sets -> public/mapinfo.json
def color_of(d, key):
    c = col(get(d[key], 'color')) if key in d else None
    if c is None:
        print(f'warning: no colour for {key}')
    return c or [128, 128, 128]
def kind_set(d, used):  # entries as [display name, colour] in definition order, + key -> index
    keys = [k for k in d if k in used]
    return [[name(k, k), color_of(d, k)] for k in keys], {k: i for i, k in enumerate(keys)}
key_of = {i: k for k, i in idx.items()}
major = lambda d: max(d, key=d.get) if d else None
loc_cul, loc_rel = [], []
for i in range(len(L)):
    p = loc_pops.get(key_of[i], [])
    cs, rs = {}, {}
    for _, c, r, n in p:
        cs[c] = cs.get(c, 0) + n; rs[r] = rs.get(r, 0) + n
    t = tmpl.get(key_of[i], [])
    loc_cul.append(major(cs) or get(t, 'culture')); loc_rel.append(major(rs) or get(t, 'religion'))
sets, cls = {}, {}
for kind, d, field in (('topo', load('topography'), 'topography'), ('veg', load('vegetation'), 'vegetation'), ('climate', load('climates'), 'climate')):
    vals = [get(tmpl.get(key_of[i], []), field) for i in range(len(L))]
    sets[kind], ix = kind_set(d, set(d))
    cls[kind] = [ix.get(v, -1) for v in vals]
for kind, d, vals in (('culture', load('cultures'), loc_cul), ('religion', load('religions'), loc_rel)):
    sets[kind], ix = kind_set(d, set(vals))
    cls[kind] = [ix.get(v, -1) for v in vals]
cls['pop'] = [round(sum(p[3] for p in loc_pops.get(key_of[i], [])), 3) for i in range(len(L))]
cls['harbor'] = [round(float(get(tmpl.get(key_of[i], []), 'natural_harbor_suitability') or 0), 2) for i in range(len(L))]
# development is worked out by the game at start from rules (setup/14_development.txt), so it's read from the
# first autosave of a 1337 campaign (start.py's): the location keys in id order, then each location's block
SAVE = os.path.expanduser('~/.local/share/Steam/steamapps/compatdata/3450310/pfx/drive_c/users/steamuser/Documents/'
                          'Paradox Interactive/Europa Universalis V/save games/autosave_9e705812-68e4-452a-9476-e58419626384.eu5')
if os.path.exists(SAVE):
    import mmap
    with open(SAVE, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
        a = m.find(b'\t\tlocations={') + 13
        order = m[a:m.find(b'}', a)].decode().split()
        a = m.find(b'\nlocations={\n')
        blk = m[a:m.find(b'\n}', a + 1)].decode()
    dev = {}
    for chunk in re.split(r'\n\t\t(?=\d+=\{)', blk)[1:]:
        d = re.search(r'\n\t\t\tdevelopment=([\d.]+)', chunk)
        dev[order[int(chunk[:chunk.index('=')]) - 1]] = float(d.group(1)) if d else 0
    cls['dev'] = [round(dev.get(key_of[i], 0), 2) for i in range(len(L))]
    print('development: Stockholm', dev.get('stockholm'), 'max', max(cls['dev']), 'zero', cls['dev'].count(0))
else:
    print(f'warning: no save at {SAVE}, no development map mode')
goods_col = {g: colors[f'goods_{g}'] for g in {l[1] for l in L if l[1]} if f'goods_{g}' in colors}
rank_defs = load('location_ranks')
rank_col = [[name(k, k), col(get(rank_defs[k], 'color'))] for k in ('rural_settlement', 'town', 'city')]
with open(f'{OUT}/public/mapinfo.json', 'w') as f:
    json.dump({'sets': sets, 'locs': cls, 'goods': goods_col, 'ranks': rank_col}, f, separators=(',', ':'), ensure_ascii=False)
assert all(len(v) == len(L) for v in cls.values())
mos = countries['MOS']['cap']
print('mapinfo:', {k: len(v) for k, v in sets.items()}, 'missing:', {k: v.count(-1) for k, v in cls.items() if k not in ('pop', 'harbor')}, os.path.getsize(f'{OUT}/public/mapinfo.json'), 'bytes')
print('Moscow:', sets['culture'][cls['culture'][mos]][0], '/', sets['religion'][cls['religion'][mos]][0])
assert sets['culture'][cls['culture'][mos]][0] == 'Muscovite' and sets['religion'][cls['religion'][mos]][0] == 'Orthodoxy'
assert any(n == 'Mountains' for n, _ in sets['topo']), sets['topo']

data = {'popInfo': pop_info, 'demandMods': demand_mods, 'tempDemand': temp_demand, 'ages': ages, 'units': units, 'demandRefs': demand_refs, 'goods': goods, 'buildings': buildings, 'demands': demands, 'pops': pops, 'cats': cats,
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
assert pop_info['types']['peasants']['promoteTo'] == ['burghers', 'clergy', 'nobles', 'laborers', 'soldiers']
assert [r['id'] for r in pop_info['ranks']] == ['rural_settlement', 'town', 'city', 'megalopolis'] and pop_info['ranks'][2]['minPop'] == 30
assert pop_info['base']['local_nobles_desired_pop_scaled'] == 0.0025 and goods['camels']['cond']['only'][-1] == 'Western India'
assert any(s['id'] == 'overpopulation' for s in pop_info['sources']) and pop_info['food']['FOOD_SURPLUS_POP_GROWTH'] == 0.0015
assert 'local_population_growth' in pop_info['pct'] and 'local_population_capacity' not in pop_info['pct']
