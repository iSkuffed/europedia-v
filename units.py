"""Extract every land unit type and the combat rules around it into public/units.json (+ icons in public/icons/units/).
Usage: python3 -I units.py [game_dir]      Contract: src/lib/units.ts (UnitsData).

Land units only (in_game/common/unit_types, navy files skipped). Stats are RESOLVED: every stat line is additive through the
copy_from chain plus the unit category's base value (levies/readme.txt). Not inherited through copy_from: hide, buildable, levy,
is_special, upgrades_to, country/location potentials are taken from the nearest unit in the chain that has them.
Left out: hide = yes (category bases and the a_age_N_* templates) and the `*_base` parents (not buildable, not a levy, copied by
another unit). Kept: levy units, and non-buildable event units (conquistadors, farari).
`who` = AND of country_potential, location_potential, location_trigger and, for levy units, the levy's country_allow /
allowed_culture / allow (scripted triggers expanded). It uses advances.py's clause shape (type + ids + names, any/all as `parts`),
which src/lib/fit.ts scopes."""
import sys, os, json, subprocess, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eu5lib import *

# ---- trigger blocks -> who clauses: copied from advances.py (importing it would re-run its whole extraction) -----------
# Additions for unit triggers: owner / location scopes are flattened into the country, dominant_culture / dominant_religion
# read like culture / religion, `modifier:x` conditions become text.
ST = {}  # scripted triggers


def has_param(b):  # $PARAM$ placeholders: the trigger can't be expanded without its arguments
    return any(('$' in x[0] if x[0] else False) or (has_param(x[2]) if isinstance(x[2], list) else '$' in str(x[2])) for x in b)


for f in glob.glob(f'{C}/scripted_triggers/*.txt'):
    for k, v in items(rd(f)):
        if isinstance(v, list) and not has_param(v):
            ST[k] = v

TL = {'tag': 'Country', 'culture': 'Culture', 'culture_group': 'Culture group', 'language': 'Language', 'religion': 'Religion',
      'religion_group': 'Religion group', 'region': 'Region', 'area': 'Area', 'sub_continent': 'Sub-continent', 'continent': 'Continent',
      'capital': 'Capital', 'government': 'Government', 'reform': 'Reform', 'subject_type': 'Subject type', 'status': 'Status',
      'estate': 'Estate', 'societal': 'Societal value', 'dlc': 'DLC', 'rank': 'Rank', 'institution': 'Institution',
      'advance': 'Advance', 'country_type': 'Country type', 'other': ''}
GEO = ('region', 'area', 'sub_continent', 'continent')
KEYS = {'has_or_had_tag': ('tag', 0), 'tag': ('tag', 0), 'original_tag': ('tag', 0),
        'has_culture_group': ('culture_group', 0), 'merged_culture_group_contains_culture': ('culture', 0),
        'has_accepted_culture': ('culture', 0), 'has_primary_or_accepted_culture': ('culture', 0), 'culture.language': ('language', 0),
        'dominant_culture': ('culture', 0), 'dominant_religion': ('religion', 0),
        'religion.group': ('religion_group', 0), 'region': ('region', 0), 'area': ('area', 0), 'sub_continent': ('sub_continent', 0),
        'continent': ('continent', 0), 'original_capital.region': ('region', 1), 'original_capital.area': ('area', 1),
        'capital.region': ('region', 1), 'capital.area': ('area', 1), 'government_type': ('government', 0), 'has_reform': ('reform', 0),
        'is_subject_type': ('subject_type', 0), 'country_has_estate': ('estate', 0), 'has_societal_value': ('societal', 0),
        'has_dlc': ('dlc', 0), 'country_rank': ('rank', 0), 'has_embraced_institution': ('institution', 0),
        'has_unlocked_advance_trigger': ('advance', 0), 'government': ('government', 0), 'country_type': ('country_type', 0)}
SCOPES = {'culture': 'culture', 'religion': 'religion', 'capital': 'capital', 'original_capital': 'capital',
          'owner': 'country', 'location': 'country', 'dominant_culture': 'culture', 'dominant_religion': 'religion'}
SKIPK = {'text', 'value', 'always', 'limit', 'hidden_trigger', 'trigger_if', 'trigger_else_if', 'trigger_else'}


def ref(v):  # "culture:turkish" -> "turkish"
    return v.split(':', 1)[1] if isinstance(v, str) and ':' in v else v


def atom(t, i, cap=0, nm=None):
    return ('atom', t, str(i), nm or (re.sub(r'^d\d+_', '', str(i)).replace('_', ' ').title() if t == 'dlc' else name(str(i))), cap)


def other(text):
    return ('atom', 'other', text, text, 0)


def tr(b, scope='country', depth=0):  # trigger block -> node
    kids = []
    for k, o, v in b:
        if k is None or k in SKIPK:
            continue
        lst = isinstance(v, list)
        if k in ('AND', 'and') and lst:
            kids.append(tr(v, scope, depth))
        elif k in ('OR', 'NOR', 'NAND') and lst:
            n = ('or', [tr([x], scope, depth) for x in v])
            kids.append(n if k == 'OR' else ('not', n))
        elif k == 'NOT' and lst:
            kids.append(('not', tr(v, scope, depth)))
        elif k in ('custom_description', 'custom_tooltip') and lst:
            n, t = tr(v, scope, depth), get(v, 'text')
            kids.append(n if norm(n) or t not in loc else other(text(loc[t])))
        elif lst and k in SCOPES:
            kids.append(tr(v, SCOPES[k], depth))
        elif lst and k == 'has_unlocked_advance_trigger' and isinstance(get(v, 'type'), str):
            kids.append(atom('advance', get(v, 'type')))
        elif lst and k == 'current_age_or_later' and isinstance(get(v, 'age'), str):
            kids.append(other(f'{name(get(v, "age"))} or later'))
        elif lst:  # unknown block: its plain conditions as text
            kids.append(other(human(k) + (': ' + '; '.join(f'{human(kk)} {name(ref(vv))}' for kk, _, vv in v if kk and isinstance(vv, str)) if any(isinstance(x[2], str) for x in v) else ' …')))
        elif o == '!=':  # government_type != x
            kids.append(('not', leaf(k, '=', v, scope, depth)))
        else:
            kids.append(leaf(k, o, v, scope, depth))
    return ('and', kids)


def leaf(k, o, v, scope, depth):
    neg = v == 'no'
    if k == 'exists' and v in ('capital', 'government_type') or (k == 'num_locations' and o == '>' and v == '0'):  # always true for a real country
        return ('and', [])
    if k == 'has_variable' and isinstance(v, str) and v.startswith('unlocked_advance_'):
        return atom('advance', v[17:])
    if scope == 'religion' and k == 'has_tag':
        return atom('religion_group', ref(v))
    flip = lambda n: ('not', n) if neg else n
    if isinstance(v, str) and (k in KEYS or k in ('culture', 'religion', 'capital', 'original_capital')) and re.match(r'(root|scope:|this|prev)|.*\.', v, re.I):
        return other(human(k) + f' {o} {v}')  # relative to another scope (culture = root.dominant_culture): no fixed id
    if k in ST and v in ('yes', 'no') and depth < 6:
        return flip(tr(ST[k], scope, depth + 1))
    if scope == 'culture' and k in ('has_culture_group', 'merged_culture_group_contains_culture', 'language'):
        return atom({'has_culture_group': 'culture_group', 'language': 'language'}.get(k, 'culture'), ref(v))
    if scope == 'religion' and k in ('group', 'religion_group'):
        return atom('religion_group', ref(v))
    if k in ('culture', 'religion'):
        return atom(k, ref(v))
    if k in ('capital', 'original_capital'):
        return atom('capital', ref(v))
    if k == 'is_subject':
        return flip(atom('status', 'subject', nm='Subject'))
    if k == 'has_tribal_government':
        return flip(atom('government', 'tribe'))
    if k.startswith('modifier:'):
        return flip(other(name(k[9:])))
    if k in KEYS and isinstance(v, str):
        t, c = KEYS[k]
        return atom(t, ref(v), c or (1 if scope == 'capital' and t in GEO else 0))
    return other(human(k) + (f' {o} {name(ref(v))}' if isinstance(v, str) and v != 'yes' else ''))


def norm(n):  # node -> list of clauses, ANDed. empty = no restriction
    if n[0] == 'atom':
        c = {'type': n[1], 'ids': [n[2]], 'names': [n[3]]}
        if n[4]:
            c['cap'] = 1
        return [c]
    if n[0] == 'and':
        return [c for x in n[1] for c in norm(x)]
    if n[0] == 'not':
        s = norm(n[1])
        if len(s) == 1:
            c = dict(s[0])
            if c.get('not'):
                del c['not']
            else:
                c['not'] = 1
            return [c]
        return [{'type': 'all', 'parts': s, 'not': 1}] if s else []
    subs = [norm(x) for x in n[1]]  # or: any empty branch makes it always true
    if not subs or any(not s for s in subs):
        return []
    parts = [s[0] if len(s) == 1 else {'type': 'all', 'parts': s} for s in subs]
    # absorption: (X or (X and Y)) is X
    parts = [p for p in parts if not (p['type'] == 'all' and not p.get('not') and any(q != p and q in p['parts'] for q in parts))]
    if len(parts) == 1:
        return [parts[0]]
    if len({(p['type'], p.get('cap', 0)) for p in parts}) == 1 and not any(p.get('not') or 'parts' in p for p in parts):
        c = {'type': parts[0]['type'], 'ids': [], 'names': []}
        for p in parts:
            for i, nm in zip(p['ids'], p['names']):
                if i not in c['ids']:
                    c['ids'].append(i)
                    c['names'].append(nm)
        if parts[0].get('cap'):
            c['cap'] = 1
        return [c]
    flat = []
    for p in parts:
        flat += [q for q in (p['parts'] if p['type'] == 'any' and not p.get('not') else [p]) if q not in flat]
    return [{'type': 'any', 'parts': flat}]


def ctext(c, top=True):
    t, no = c['type'], 'not ' if c.get('not') else ''
    if 'parts' in c:
        s = (' or ' if t == 'any' else ' and ').join(ctext(p, False) for p in c['parts'])
        return no + (f'({s})' if len(c['parts']) > 1 or no else s)
    ns = c['names']
    s = ', '.join(ns[:4]) + (f' +{len(ns) - 4}' if len(ns) > 4 else '')
    if t == 'other':
        return no + s
    lab = f'capital in {TL[t].lower()}' if c.get('cap') else (TL[t] if top and not no else TL[t].lower())
    return f'{no}{lab}: {s}'


# ---- unit types ---------------------------------------------------------------------------------------------------
UT = {}  # id -> (file, block); navy files out
for f in sorted(glob.glob(f'{C}/unit_types/*.txt')):
    if 'navy' in f or f.endswith('readme.txt'):
        continue
    for k, v in items(rd(f)):
        if isinstance(v, list) and k.startswith('a_'):
            UT[k] = (os.path.basename(f), v)

CATS = {k: v for k, v in load('unit_categories').items() if k.startswith('army_')}
STATS = ('max_strength', 'combat_power', 'initiative', 'combat_speed', 'frontage', 'flanking_ability', 'secure_flanks_defense',
         'movement_speed', 'strength_damage_done', 'strength_damage_taken', 'morale_damage_done', 'morale_damage_taken', 'bombard_efficiency')


def chain(uid):  # [unit, parent, grandparent...]
    out = []
    while uid and uid in UT and uid not in out:
        out.append(uid)
        uid = get(UT[uid][1], 'copy_from')
    return out


def own(uid, key):  # nearest value of a plain key along the chain
    for u in chain(uid):
        v = get(UT[u][1], key)
        if v is not None:
            return v


def stat(uid, key):  # additive: own line + parents' + category base
    s = sum(val(v) or 0 for u in chain(uid) for k, _, v in UT[u][1] if k == key and isinstance(v, str))
    return s + (val(get(CATS[own(uid, 'category')], key)) or 0)


def combat_of(uid):  # additive `combat` block along the chain
    r = {}
    for u in chain(uid):
        for k, _, v in get(UT[u][1], 'combat') or []:
            r[k] = r6(r.get(k, 0) + val(v))
    return {k: v for k, v in r.items() if v}


def r6(x):  # 6 decimals, whole numbers as ints (smaller JSON)
    x = round(x, 6) + 0.0
    return int(x) if x == int(x) else x


copied = {get(b, 'copy_from') for _, b in UT.values()}


def keep(uid):
    b = UT[uid][1]
    if get(b, 'hide') == 'yes':  # category bases and the a_age_N_* templates
        return False
    if get(b, 'buildable') == 'no' and get(b, 'levy') != 'yes' and uid in copied:  # pure base parent (a_order_knights_base ...)
        return False
    return True


# ---- levies, unlocking advances -------------------------------------------------------------------------------------
LEVY = load('levies')
levies_of = collections.defaultdict(list)  # unit -> [levy blocks]
for lid, lb in LEVY.items():
    if isinstance(u := get(lb, 'unit'), str):
        levies_of[u].append((lid, lb))

ADV = load('advances')
unlock = collections.defaultdict(list)
for aid, ab in ADV.items():
    for k, _, v in ab:
        if k == 'unlock_unit' and isinstance(v, str):
            unlock[v].append(aid)
        elif k == 'unlock_levy' and isinstance(v, str) and v in LEVY and isinstance(get(LEVY[v], 'unit'), str):
            unlock[get(LEVY[v], 'unit')].append(aid)


def levy_node(lb):
    kids = []
    if isinstance(ca := get(lb, 'country_allow'), list):
        kids.append(tr(ca))
    cults = [v for k, _, v in lb if k == 'allowed_culture' and isinstance(v, str)]
    if cults:
        kids.append(('or', [atom('culture', c) for c in cults]))
    if isinstance(al := get(lb, 'allow'), list):
        kids.append(tr(al))
    return ('and', kids)


def who_of(uid):
    kids = []
    for key in ('country_potential', 'location_potential', 'location_trigger'):
        for u in chain(uid):  # nearest unit in the chain that has the block
            if isinstance(bl := get(UT[u][1], key), list):
                kids.append(tr(bl))
                break
    if get(UT[uid][1], 'levy') == 'yes' and levies_of.get(uid):
        kids.append(('or', [levy_node(lb) for _, lb in levies_of[uid]]))
    return [c for i, c in enumerate(norm(('and', kids))) if c not in norm(('and', kids))[:i]]  # drop repeats


# ---- icons: in_game/gfx/unit_illustrations picks the art by priority among entries whose trigger passes ------------------
ILL = {}
for f in [f'{GAME}/in_game/gfx/unit_illustrations/00_unit_illustrations.txt', *glob.glob(f'{GAME}/dlc/*/in_game/gfx/unit_illustrations/*.txt')]:
    if not f.endswith('readme.txt'):
        ILL.update({k: v for k, v in items(rd(f)) if isinstance(v, list)})


def art_file(tex):
    for d in (f'{GAME}/main_menu', f'{GAME}/in_game', *glob.glob(f'{GAME}/dlc/*/main_menu'), *glob.glob(f'{GAME}/dlc/*/in_game')):
        if os.path.exists(p := f'{d}/{tex}'):
            return p


def passes(block, u):  # trigger vs a unit type; anything that needs the viewer's culture (scope:culture) does not pass
    for k, _, v in block:
        if k == 'OR':
            ok = any(passes([x], u) for x in v)
        elif k == 'AND':
            ok = passes(v, u)
        elif k == 'NOT':
            ok = not passes(v, u)
        elif k == 'unit_category':
            ok = v == u['cat_id']
        elif k in ('min_age', 'max_age'):
            n = int(re.match(r'age_(\d)', v).group(1))
            ok = u['age'] >= n if k == 'min_age' else u['age'] <= n
        elif k == 'has_gfx_tag':
            ok = v in u['tags']
        elif k == 'is_unit_type':
            ok = v == u['id']
        elif k == 'scope:culture':
            ok = False
        else:
            raise SystemExit(f'unit_illustrations: unhandled trigger {k}')
        if not ok:
            return False
    return True


def illustration(u):
    best = None
    for ek, eb in ILL.items():
        tex, pri = get(eb, 'texture'), num(get(eb, 'priority')) or 0
        if (art := art_file(tex)) and passes(get(eb, 'trigger') or [], u) and (best is None or (pri, ek) > (best[0], best[1])):
            best = (pri, ek, art)
    return best and best[2]


# ---- units --------------------------------------------------------------------------------------------------------
ICON_DIR = f'{OUT}/public/icons/units'
os.makedirs(ICON_DIR, exist_ok=True)
units, n_icon, icon_new = [], 0, 0
for uid, (fname, b) in UT.items():
    if not keep(uid):
        continue
    cat_id = own(uid, 'category')
    age = int(re.match(r'age_(\d)', own(uid, 'age')).group(1))
    levy = get(b, 'levy') == 'yes'
    buildable = get(b, 'buildable') == 'yes' or (get(b, 'buildable') is None and not levy)
    u = {'id': uid, 'name': name(uid)}
    if (d := desc(uid)):
        u['desc'] = d
    u.update(cat=cat_id[5:], age=age, levy=levy, buildable=buildable, str=r6(stat(uid, 'max_strength')), cp=r6(stat(uid, 'combat_power')),
             init=r6(stat(uid, 'initiative')), speed=r6(stat(uid, 'combat_speed')), front=r6(stat(uid, 'frontage')),
             flank=r6(stat(uid, 'flanking_ability')), secure=r6(stat(uid, 'secure_flanks_defense')), move=r6(stat(uid, 'movement_speed')),
             sdd=r6(stat(uid, 'strength_damage_done')), sdt=r6(stat(uid, 'strength_damage_taken')),
             mdd=r6(stat(uid, 'morale_damage_done')), mdt=r6(stat(uid, 'morale_damage_taken')),
             taken=r6(val(get(CATS[cat_id], 'damage_taken'))))
    if stat(uid, 'bombard_efficiency'):
        u['bombard'] = r6(stat(uid, 'bombard_efficiency'))
    u['terrain'] = combat_of(uid)
    u['combinedArms'] = get(CATS[cat_id], 'exclude_from_combined_arms') != 'yes'
    if isinstance(up := get(b, 'upgrades_to') or get(b, 'upgrades_to_only'), str):
        u['upgrades'] = up
    who = who_of(uid)
    u['who'], u['whoText'] = who, '; '.join(ctext(c) for c in who)
    if uid in unlock:
        u['unlock'] = [{'id': a, 'name': name(a)} for a in dict.fromkeys(unlock[uid])]
    u['unique'] = fname != '2_unlocked_through_tech.txt'
    tags = [v for k, _, v in (own(uid, 'gfx_tags') or []) if k is None]
    if (art := illustration({'id': uid, 'cat_id': cat_id, 'age': age, 'tags': tags})):
        dst = f'{ICON_DIR}/{uid}.webp'
        if not os.path.exists(dst):
            subprocess.run(['magick', art, '-resize', '320x', '-strip', '-quality', '80', dst], check=True)
            icon_new += 1
        u['icon'] = uid
        n_icon += 1
    units.append(u)

# ---- combat-relevant modifiers --------------------------------------------------------------------------------------
LAND_POWER = {f'army_{c}_power' for c in ('light_infantry', 'heavy_infantry', 'light_cavalry', 'heavy_cavalry', 'artillery', 'auxiliary')}
COMBAT_KEYS = {'military_tactics', 'discipline', 'land_morale', 'land_morale_modifier', 'land_morale_recovery', 'army_initiative',
               'combat_speed_modifier', 'possible_frontage_modifier', 'combined_bonus_per_type', 'levy_combat_efficiency_modifier',
               'correct_box_chance', 'commander_combat_bonus'} | LAND_POWER


def combat_mods(b):  # {key: value} of the combat modifiers among a block's plain lines
    return {k: r6(val(v)) for k, _, v in b if k in COMBAT_KEYS and isinstance(v, str) and val(v) is not None}


# generic advances: no potential / country_type / government restriction, no age focus (adm / dip / mil: a country picks one per
# age), and an allow that is at most an institution. Everyone ends up with these.
# focus advances (for = adm/dip/mil) that are otherwise generic go to focusMods[focus], cumulative per age the same way.
ageMods, skipped = {n: collections.Counter() for n in range(1, 7)}, []
focusMods = {f: {n: collections.Counter() for n in range(1, 7)} for f in ('adm', 'dip', 'mil')}
for aid, ab in ADV.items():
    m = combat_mods(ab)
    ag = get(ab, 'age')
    if not m or not ag:
        continue
    extra = [(k, '=', v) for k in ('government', 'country_type') if isinstance(v := get(ab, k), str)]
    why = ('restricted' if norm(('and', [tr(p) for p in (get(ab, 'potential'), extra) if isinstance(p, list)])) else
           'allow' if any(c['type'] != 'institution' for c in norm(tr(get(ab, 'allow') or []))) else None)
    if why:
        skipped.append((aid, why))
        continue
    for n in range(int(re.match(r'age_(\d)', ag).group(1)), 7):
        for k, x in m.items():
            (focusMods[get(ab, 'for')] if get(ab, 'for') else ageMods)[n][k] += x
ageMods = {n: {k: r6(x) for k, x in sorted(c.items())} for n, c in ageMods.items()}
focusMods = {f: {n: {k: r6(x) for k, x in sorted(c.items())} for n, c in ages.items()} for f, ages in focusMods.items()}

traits = []
for fn in ('00_ruler', '01_general'):  # ruler traits count: a ruler can lead the army
    for tid, tb in items(rd(f'{C}/traits/{fn}.txt')):
        if isinstance(tb, list) and isinstance(mb := get(tb, 'modifier'), list) and (m := combat_mods(mb)):
            traits.append({'id': tid, 'name': name(tid), 'kind': fn[3:], 'mods': m})


def static(fn, ids):  # numeric modifier lines of static_modifiers/<fn>.txt blocks
    sm = {k: v for k, v in items(rd(f'{MM}/static_modifiers/{fn}.txt')) if isinstance(v, list)}
    return {i: {k: r6(val(v)) for k, _, v in sm[i] if isinstance(v, str) and val(v) is not None} for i in ids}


gen = static('character', ['general_adm', 'general_dip', 'general_mil'])
sub = static('subunit', ['is_army_levy', 'is_army_regular'])
loc_base = static('location', ['location_base_values'])['location_base_values']

BASE_KEYS = ('military_tactics', 'combined_arms_max_threshold', 'combined_arms_min_percent_for_bonus', 'combined_bonus_per_type',
             'land_morale_recovery', 'experience_decay', 'discipline', 'land_morale', 'land_morale_modifier')
cbv = get(rd(f'{C}/auto_modifiers/country.txt'), 'country_base_values')
base = {k: r6(val(v)) for k, _, v in cbv if k in BASE_KEYS and isinstance(v, str)}

dfn = rd(f'{GAME}/loading_screen/common/defines/00_defines.txt')
defines = {k: r6(num(v)) for k, v in items(get(dfn, 'NCombat')) if num(v) is not None}
for ns, k in (('NUnit', 'LAND_MORALE'), ('NLocation', 'MIN_FRONTAGE_AFTER_TERRAIN'), ('NAI', 'AVERAGE_FRONTAGE')):
    defines[k] = r6(num(get(get(dfn, ns), k)))

# ---- terrain ------------------------------------------------------------------------------------------------------
WATER = {'is_lake', 'is_deep_ocean', 'can_have_ice', 'can_freeze_over'}


def terrain(d, land):
    out = []
    for k, v in load(d).items():
        if not land(k, v):
            continue
        lm = get(v, 'location_modifier') or []
        out.append({'id': k, 'name': name(k), 'dice': int(num(get(v, 'defender')) or 0), 'front': int(num(get(lm, 'local_frontage_allowed')) or 0)})
    return out


# wasteland variants are impassable (game_concepts: corridors "contrary to wastelands, still can be traversed"): left out
topography = terrain('topography', lambda k, v: not WATER & {x[0] for x in v} and 'wasteland' not in k and k not in ('ocean', 'narrows', 'atoll'))
vegetation = terrain('vegetation', lambda k, v: True)


def front_in(b):
    for k, _, v in b:
        if k == 'local_frontage_allowed':
            return num(v)
        if isinstance(v, list) and (x := front_in(v)) is not None:
            return x


ranks = [{'id': k, 'name': name(k), 'front': int(front_in(v) or 0)} for k, v in load('location_ranks').items()]
ranks.sort(key=lambda r: r['front'], reverse=True)  # rural 0, town -1, city -2, megalopolis -3

data = {'units': units, 'topography': topography, 'vegetation': vegetation, 'ranks': ranks, 'baseFrontage': int(loc_base['local_frontage_allowed']),
        'defines': defines, 'traits': traits, 'ageMods': ageMods, 'focusMods': focusMods, 'general': {k[8:]: v for k, v in gen.items()},
        'levyMods': sub['is_army_levy'], 'regularMods': sub['is_army_regular'], 'base': base}
path = f'{OUT}/public/units.json'
with open(path, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, separators=(',', ':'), ensure_ascii=False)

if __name__ == '__main__':
    cn = collections.Counter
    print(f'units.json: {os.path.getsize(path)} bytes, {len(units)} units')
    print('by category:', dict(cn(u['cat'] for u in units)))
    print('levies:', sum(u['levy'] for u in units), 'buildable:', sum(u['buildable'] for u in units), 'unique:', sum(u['unique'] for u in units),
          'with who:', sum(bool(u['who']) for u in units), 'with unlock:', sum('unlock' in u for u in units))
    print(f'icons: {n_icon} units have art ({icon_new} newly converted), {len({u["icon"] for u in units if "icon" in u})} icon files')
    print('no icon:', [u['id'] for u in units if 'icon' not in u])
    print('topography:', [t['id'] for t in topography], 'vegetation:', [t['id'] for t in vegetation])
    print('ranks:', ranks)
    print('generic advances skipped for ageMods (combat mods):', cn(w.split()[0] for _, w in skipped))
    print('traits:', len(traits), 'defines:', len(defines))
    print('who types:', dict(cn(c['type'] for u in units for c in u['who']).most_common()))
    print('traits by kind:', dict(cn(t['kind'] for t in traits)))
    for f in focusMods:
        print('focusMods', f, {n: m for n, m in focusMods[f].items() if n in (1, 2, 4, 6)})
    for n in (1, 3, 6):
        print('ageMods', n, ageMods[n])
