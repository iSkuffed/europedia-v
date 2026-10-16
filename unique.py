"""Extract game content unique to a country (tag-locked) into public/unique.json.
Usage: python3 -I unique.py [game_dir]

An item is unique to a tag when its potential/allow-style condition requires `tag = X` / `has_or_had_tag = X`
(directly, or in an OR of such). NOT/NOR/trigger_if are never read, so exclusions never count. More than MAXTAGS
tags -> not unique, skipped. Items with no tag of their own but unlocked only by tag-locked advances are credited
to those advances' tags (gated)."""
import sys, os, glob, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdx import parse, get, items, num

GAME = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/.local/share/Steam/steamapps/common/Europa Universalis V/game')
C, MM = f'{GAME}/in_game/common', f'{GAME}/main_menu/common'
OUT = os.path.dirname(os.path.abspath(__file__))
MAXTAGS = 8
TAG = re.compile(r'^[A-Z][A-Z0-9]{2}$')


def rd(f):
    return parse(open(f, encoding='utf-8-sig').read())


def load(d):  # top-level objects of every .txt in in_game/common/<d>: {id: block}
    out = {}
    for f in sorted(glob.glob(f'{C}/{d}/*.txt')):
        for k, v in items(rd(f)):
            if isinstance(v, list):
                out[k] = v
    return out


# ---- localisation (copied from build.py) ----------------------------------------------------------------
def load_loc():
    loc = {}
    line = re.compile(r'^\s*([\w.\-]+):\d*\s+"(.*)"\s*(#.*)?$')
    for f in sorted(glob.glob(f'{GAME}/**/localization/english/**/*.yml', recursive=True)):
        for l in open(f, encoding='utf-8-sig', errors='replace'):
            m = line.match(l)
            if m:
                loc.setdefault(m.group(1), m.group(2))
    return loc


loc = load_loc()


def resolve(t, depth=0):  # expand $other_key$ references
    if depth > 5:
        return t
    return re.sub(r'\$([\w.]+)(?:\|[^$]*)?\$', lambda m: resolve(loc[m.group(1)], depth + 1) if m.group(1) in loc else m.group(0), t)


def human(k):
    return k.replace('_', ' ').capitalize()


def text(s):  # loc string -> plain text: drop formatting, resolve the few runtime calls we can
    s = resolve(s).replace('\\n', '\n')
    s = re.sub(r"\[Show\w*Adjective\w*\('(\w+)'\)\]", lambda m: loc.get(m.group(1) + '_ADJ', human(m.group(1))), s)
    s = re.sub(r"\[Show\w*?Name\w*\('(\w+)'\)\]", lambda m: text(loc[m.group(1)]) if m.group(1) in loc else human(m.group(1)), s)
    s = re.sub(r"\[(?:GetCountry\('\w+'\)|ROOT\.GetCountry)\.GetGovernment\.GetEstateName\w*\('(\w+)'\)\]",
               lambda m: text(loc[m.group(1)]) if m.group(1) in loc else human(m.group(1)), s)
    s = re.sub(r"\[GetCountry\('(\w+)'\)\.GetName\w*\]", lambda m: loc.get(m.group(1), m.group(1)), s)
    s = re.sub(r'\[[\w.\x27()]*GetRulerTitle\]', 'ruler', s)
    s = re.sub(r'\[[\w.\x27()]*GetFlavorRank\]', 'realm', s)
    s = re.sub(r'\[(\w+)(?:\|\w+)?\]', lambda m: text(loc[m.group(1)]).lower() if m.group(1) in loc else m.group(1).replace('_', ' '), s)
    s = re.sub(r'\[[^\]]*\]', '', s)  # unresolvable runtime text
    s = re.sub(r'#\w+\s?|#!|@\w+!\s?|\$\w+\$', '', s)
    s = re.sub(r'[ \t]+([,.;:])', r'\1', s)
    return re.sub(r'[ \t]{2,}', ' ', s).strip()


def name(id, *cands):
    for c in (id, f'{id}.title', *cands):
        if c in loc and (t := text(loc[c])):
            return t
    return human(id)


def desc(id, *cands):
    for c in (f'{id}_desc', f'{id}.desc', *cands):
        if c in loc and (t := text(loc[c])):
            return t


# ---- modifiers: definitions, script values, formatting ------------------------------------------------------
DEF = {k: {d[0]: d[2] for d in v if d[0] and not isinstance(d[2], list)}
       for f in glob.glob(f'{MM}/modifier_type_definitions/*.txt') for k, v in items(rd(f))}
SV = {}
for path in (f'{MM}/script_values', f'{C}/script_values'):
    for f in sorted(glob.glob(f'{path}/*.txt')):
        for k, v in items(rd(f)):
            if num(v) is not None:
                SV[k] = num(v)
val = lambda v: num(v) if num(v) is not None else SV.get(v)
mod_cov = {'named': 0, 'raw': 0}
raw_keys = {}


def mod_label(k):
    for key in (f'MODIFIER_TYPE_NAME_{k}', f'game_concept_{k}'):  # game_concept_*: unit combat stats
        if key in loc and (t := text(loc[key])):
            mod_cov['named'] += 1
            return t
    mod_cov['raw'] += 1
    raw_keys[k] = raw_keys.get(k, 0) + 1
    return human(k)


def g(x, nd):  # number without trailing zeros
    return f'{round(x, nd):g}'


def mod_value(k, v, pct=False):
    d = DEF.get(k, {})
    if pct:
        d = {'percent': 'yes'}
    if d.get('boolean') == 'yes' or v in ('yes', 'no'):
        return 'Yes' if v == 'yes' else 'No'
    x = val(v)
    if x is None:
        return human(v) if re.fullmatch(r'\w+', v) else v
    sign = '+' if x > 0 else ''
    if d.get('percent') == 'yes':
        return f'{sign}{g(x * 100, 2)}%'
    if d.get('already_percent') == 'yes':
        return f'{sign}{g(x, 2)}%'
    return f'{sign}{g(x, int(d.get("decimals", 2)))}'


SKIP_IN_MOD = {'scale', 'value', 'multiply', 'add'}


def condition_text(block):  # why a conditional modifier block applies: its custom_tooltip text, else "conditional"
    for k, _, v in block:
        if k == 'text' and isinstance(v, str) and v in loc:
            return text(loc[v])
        if isinstance(v, list) and (t := condition_text(v)):
            return t


def mods_of(block, top=True, out=None, why=None):
    """modifier [label, value] pairs: scalar keys in *_modifier blocks; at top level only known modifier keys.
    Blocks with a potential_trigger only apply sometimes: their labels get a "(reason)" suffix."""
    out = [] if out is None else out
    sub = get(block, 'potential_trigger')
    if isinstance(sub, list):
        why = condition_text(sub) or 'conditional'
        why = re.sub(r'^The following bonus can be gained from the (.*?) decision:?$', r'via \1 decision', why).rstrip(':')
    sfx = f' ({why})' if why else ''
    for k, _, v in block:
        if k is None or k in SKIP_IN_MOD:
            continue
        if isinstance(v, list):
            if k == 'modifier' or k.endswith('_modifier'):
                mods_of(v, False, out, why)
        elif k == 'pure_tooltip_entry':  # a bare tooltip line, e.g. "Unlocks fondaco rights"
            out.append([(text(loc[v]) if v in loc else human(v)) + sfx, 'Yes'])
        elif (not top) or k in DEF:
            out.append([mod_label(k) + sfx, mod_value(k, v)])
    return out


# ---- tag restriction ----------------------------------------------------------------------------------------
TAGKEYS = ('tag', 'has_or_had_tag')
GATE = re.compile(r'^(has_variable|has_global_variable|has_unlocked_\w+)$')


def cond(k, v):  # tags a single condition limits to, or None (no information)
    if k in TAGKEYS:
        return {v} if isinstance(v, str) and TAG.match(v) else None
    if k == 'OR' and isinstance(v, list):
        parts = [cond(kk, vv) for kk, _, vv in v if kk is not None]
        if parts and all(p is not None for p in parts):
            return set().union(*parts)
        return None
    if (k is None or k == 'AND') and isinstance(v, list):
        return restr(v)
    return None


def restr(block):  # AND of the conditions
    r = None
    for k, _, v in block:
        c = cond(k, v)
        if c is not None:
            r = c if r is None else r & c
    return r


def gated(block):  # a variable / unlock gate somewhere outside NOT/NOR
    for k, _, v in block:
        if k in ('NOT', 'NOR'):
            continue
        if k and GATE.match(k) or (isinstance(v, list) and gated(v)):
            return True
    return False


def conds(block, keys):
    """-> (tags | None, gated) from the condition blocks `keys` of an item."""
    r, gt = None, False
    for k, _, v in block:
        if k in keys and isinstance(v, list):
            c = restr(v)
            if c is not None:
                r = c if r is None else r & c
            gt = gt or gated(v)
    return r, gt


# ---- output -------------------------------------------------------------------------------------------------
OUTD = {}
kind_count = {}
CONDS = ('potential', 'allow')


def emit(kind, id, tags, block, label=None, d=None, estate=None, gt=False, mods=None, extra=None):
    if not tags or len(tags) > MAXTAGS:
        return
    e = {'kind': kind, 'id': id, 'name': label or name(id)}
    if d or desc(id):
        e['desc'] = d or desc(id)
    if extra:
        e.update(extra)
    if estate:
        e['estate'] = estate
    if gt:
        e['gated'] = True
    e['mods'] = mods_of(block) if mods is None else mods
    for t in sorted(tags):
        x = dict(e)
        if len(tags) > 1:
            x['shared'] = sorted(tags - {t})
        x = {k: x[k] for k in ('kind', 'id', 'name', 'desc', 'shared', 'estate', 'law', 'age', 'gated', 'mods') if k in x}
        OUTD.setdefault(t, []).append(x)
    kind_count[kind] = kind_count.get(kind, 0) + 1


# ---- advances first: they unlock units / reforms / privileges / laws, which makes those unique too ---------------
UNLOCK = {'unlock_unit': 'unit', 'unlock_government_reform': 'reform', 'unlock_estate_privilege': 'privilege',
          'unlock_law': 'law', 'unlock_policy': 'policy', 'unlock_building': 'building', 'unlock_levy': 'levy',
          'unlock_casus_belli': 'casus belli', 'unlock_chivalric_order': 'chivalric order',
          'unlock_production_method': 'production method', 'unlock_subject_type': 'subject type'}
unlockers = {}  # id -> [tags of each unlocking advance, or None when that advance is not tag-locked]
advances = {}
for f in sorted(glob.glob(f'{C}/advances/*.txt')):
    for k, v in items(rd(f)):
        if isinstance(v, list):
            advances[k] = v
adv_tags = {}
for aid, b in advances.items():
    t, gt = conds(b, CONDS)
    adv_tags[aid] = t
    for k, v in items(b):
        if k in UNLOCK and isinstance(v, str):
            unlockers.setdefault(v, []).append(t)


def unlocked_tags(id):  # tags when every unlocker of `id` is tag-locked
    u = unlockers.get(id)
    if u and all(x is not None for x in u):
        return set().union(*u)


def tags_for(id, b, keys, allow_unlock=True):
    t, gt = conds(b, keys)
    if t is None and allow_unlock and (t := unlocked_tags(id)):
        gt = True
    return t, gt


for aid, b in advances.items():
    t = adv_tags[aid]
    if not t:
        continue
    mods = mods_of(b)
    for k, v in items(b):
        if k in UNLOCK and isinstance(v, str):
            mods.append([f'Unlocks {UNLOCK[k]}', name(v)])
    emit('advance', aid, t, b, mods=mods, extra={'age': name(get(b, 'age'))} if get(b, 'age') else None)

# ---- government reforms -----------------------------------------------------------------------------------------
for rid, b in load('government_reforms').items():
    t, gt = tags_for(rid, b, CONDS)
    emit('reform', rid, t, b, gt=gt)

# ---- estate privileges --------------------------------------------------------------------------------------------
for f in sorted(glob.glob(f'{C}/estate_privileges/*.txt')):
    for pid, b in items(rd(f)):
        if isinstance(b, list):
            t, gt = tags_for(pid, b, CONDS)
            est = get(b, 'estate')
            emit('privilege', pid, t, b, estate=name(est) if est else None, gt=gt)

# ---- laws and their policies ----------------------------------------------------------------------------------------
LAW_ATTR = {'potential', 'allow', 'locked', 'custom_tags', 'law_religion_group', 'law_gov_group', 'law_country_group',
            'law_category', 'international_organization_modifier', 'country_modifier', 'estate_preferences'}
for f in sorted(glob.glob(f'{C}/laws/*.txt')):
    for lid, lb in items(rd(f)):
        if not isinstance(lb, list):
            continue
        lt, lgt = tags_for(lid, lb, CONDS)
        lg = get(lb, 'law_country_group')
        if isinstance(lg, str) and TAG.match(lg):
            lt = {lg} if lt is None else lt & {lg}
        if lt:
            emit('law', lid, lt, lb, gt=lgt, mods=[])
        for pid, pb in items(lb):
            if not isinstance(pb, list) or pid in LAW_ATTR:
                continue
            pt, pgt = conds(pb, CONDS)
            pt = lt if pt is None else (pt if lt is None else pt & lt)
            if pt is None and (pt := unlocked_tags(pid)):
                pgt = True
            emit('policy', pid, pt, pb, gt=lgt or pgt, extra={'law': name(lid)})

# ---- unit types -------------------------------------------------------------------------------------------------------
units = {}
for f in sorted(glob.glob(f'{C}/unit_types/*.txt')):
    for k, v in items(rd(f)):
        if isinstance(v, list):
            units[k] = v
replaces = {}
for uid, b in units.items():
    up = get(b, 'upgrades_to')
    if isinstance(up, str):
        replaces.setdefault(up, []).append(uid)
UNIT_STATS = {'morale_damage_taken', 'strength_damage_taken', 'morale_damage_done', 'strength_damage_done', 'supply_weight',
              'attrition_loss', 'movement_speed', 'max_strength', 'combat_speed', 'initiative', 'frontage', 'combat_power',
              'flanking_ability', 'secure_flanks_defense', 'transport_capacity', 'maritime_presence', 'crew_size',
              'blockade_capacity', 'cannons', 'hull_size', 'anti_piracy_warfare', 'food_storage_per_strength',
              'food_consumption_per_strength'}
# combat stats have no modifier definition; the fraction-like ones read as percentages
UNIT_PCT = {'morale_damage_taken', 'strength_damage_taken', 'morale_damage_done', 'strength_damage_done', 'movement_speed',
            'attrition_loss'}
for uid, b in units.items():
    t, gt = tags_for(uid, b, ('country_potential',))
    if not t:
        continue
    cat = get(b, 'category')
    cp = uid
    while cat is None and (cp := get(units.get(cp, []), 'copy_from')) in units:  # category comes from the template
        cat = get(units[cp], 'category')
    mods = []
    if cat:
        mods.append(['Category', name(cat)])
    if (src := get(b, 'copy_from')) and src != uid:
        mods.append(['Based on', name(src)])
    if (up := get(b, 'upgrades_to')):
        mods.append(['Upgrades to', name(up)])
    if (rp := [r for r in replaces.get(uid, []) if r != uid]):
        mods.append(['Upgrades from', ', '.join(name(r) for r in rp)])
    mods += [[mod_label(k), mod_value(k, v, k in UNIT_PCT)] for k, v in items(b) if (k in UNIT_STATS or k in DEF) and isinstance(v, str)]
    emit('unit', uid, t, b, gt=gt, mods=mods, extra={'age': name(get(b, 'age'))} if get(b, 'age') else None)

# ---- formable countries (only the few whose own potential/allow names a tag) --------------------------------------------
for fid, b in load('formable_countries').items():
    t, gt = conds(b, CONDS)
    ft = get(b, 'tag')
    if t:
        emit('formable', fid, t, b, label=f'Form {name(ft)}' if ft else None, gt=gt,
             d=f'Lets {", ".join(sorted(t))} form {name(ft)}.' if ft else None,
             mods=[['Level', get(b, 'level')]] if get(b, 'level') else [])

# ---- other tag-locked player content ------------------------------------------------------------------------------------------
OTHER = {'cabinet_actions': 'cabinet action', 'decisions': 'decision', 'chivalric_orders': 'chivalric order',
         'heir_selections': 'heir selection', 'parliament_issues': 'parliament issue', 'parliament_types': 'parliament type',
         'town_rights': 'town right', 'bureaucracies': 'bureaucracy', 'societal_values': 'societal value',
         'expedition_types': 'expedition type', 'casus_belli': 'casus belli', 'subject_types': 'subject type',
         'country_interactions': 'country interaction'}
for folder, kind in OTHER.items():
    for oid, b in load(folder).items():
        t, gt = tags_for(oid, b, CONDS + ('trigger', 'possible', 'is_shown', 'can_use', 'available'))
        emit(kind, oid, t, b, gt=gt)

# ---- write + summary --------------------------------------------------------------------------------------------------------------
ORDER = ['reform', 'privilege', 'law', 'policy', 'unit', 'formable', 'advance']
for t in OUTD:
    OUTD[t].sort(key=lambda e: (ORDER.index(e['kind']) if e['kind'] in ORDER else len(ORDER), e['name']))
# only nations on the map in 1337 get a page; build.py writes that list (run it first)
START = json.load(open(f'{OUT}/public/nations.json', encoding='utf-8'))['countries']
OUTD = dict(sorted((t, v) for t, v in OUTD.items() if t in START))
path = f'{OUT}/public/unique.json'
with open(path, 'w', encoding='utf-8') as fh:
    json.dump(OUTD, fh, separators=(',', ':'), ensure_ascii=False)

if __name__ == '__main__':
    # restriction self-check: OR of tags, exclusions ignored, AND intersects, >MAXTAGS not an issue here
    r = lambda t: restr(parse(t))
    assert r('tag = A1B') == {'A1B'} and r('OR = { tag = AAA has_or_had_tag = BBB }') == {'AAA', 'BBB'}
    assert r('NOT = { tag = AAA }') is None and r('OR = { tag = AAA culture = x }') is None
    assert r('OR = { tag = AAA tag = BBB } tag = BBB') == {'BBB'}
    assert any(e['id'] == 'prikazi_reform' for e in OUTD['MOS'])
    print('size', os.path.getsize(path), 'bytes; tags covered', len(OUTD), '; entries', sum(map(len, OUTD.values())))
    print('items per kind (unique items, before fan-out to tags):', dict(sorted(kind_count.items(), key=lambda x: -x[1])))
    print('modifier labels:', mod_cov, f'-> {100 * mod_cov["named"] / max(1, sum(mod_cov.values())):.1f}% localised')
    print('top unlocalised modifier keys:', sorted(raw_keys.items(), key=lambda x: -x[1])[:25])
    for t in ('MOS', 'NOV', 'FRA', 'ENG', 'CAS', 'VEN'):
        print(f'\n===== {t} ({len(OUTD.get(t, []))})')
        for e in OUTD.get(t, []):
            print(json.dumps(e, ensure_ascii=False))
