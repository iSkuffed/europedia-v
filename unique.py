"""Extract game content unique to a country (tag-locked) into public/unique.json.
Usage: python3 -I unique.py [game_dir]

An item is unique to a tag when its potential/allow-style condition requires `tag = X` / `has_or_had_tag = X`
(directly, or in an OR of such). NOT/NOR/trigger_if are never read, so exclusions never count. More than MAXTAGS
tags -> not unique, skipped. Items with no tag of their own but unlocked only by tag-locked advances are credited
to those advances' tags (gated)."""
import sys, os, json, glob, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eu5lib import *  # paths, loc, modifier formatting, tag conditions


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

# card art for every reform (64x90, like privileges.py's): <icon or id>.dds, DLC ones under dlc/
ART = {os.path.basename(f)[:-4]: f for d in (GAME, *glob.glob(f'{GAME}/dlc/*'))
       for f in glob.glob(f'{d}/main_menu/gfx/interface/icons/government_reforms/illustrations/*.dds')}
os.makedirs(f'{OUT}/public/icons/reforms', exist_ok=True)
for rid, b in load('government_reforms').items():
    dst = f'{OUT}/public/icons/reforms/{rid}.webp'
    if not os.path.exists(dst):
        subprocess.run(['magick', ART.get(get(b, 'icon') or rid, ART['_default']), '-strip', '-quality', '88', dst], check=True)

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
