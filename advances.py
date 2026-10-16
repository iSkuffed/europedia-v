"""Extract research advances into public/advances.json (+ 40px icons in public/icons/advances/).
Usage: python3 -I advances.py [game_dir]

EU5 has no "research category": an advance belongs to an age (age = ...) and optionally to an age *focus* (for = adm | dip | mil),
the specialisation a country picks in the age-start event (events/ages.txt: set_age_preference). `for` advances only appear to
countries that picked that focus; the rest are open to all. Who can get an advance comes from its potential / allow blocks and
the top-level government / country_type keys, turned into structured clauses (see `norm`). Scripted triggers are expanded."""
import sys, os, json, subprocess, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eu5lib import *

# ---- advances ------------------------------------------------------------------------------------------------
adv = {}
for f in sorted(glob.glob(f'{C}/advances/*.txt')):
    for k, v in items(rd(f)):
        if isinstance(v, list):
            adv[k] = (os.path.basename(f), v)

ST = {}  # scripted triggers


def has_param(b):  # $PARAM$ placeholders: the trigger can't be expanded without its arguments
    return any(('$' in x[0] if x[0] else False) or (has_param(x[2]) if isinstance(x[2], list) else '$' in str(x[2])) for x in b)


for f in glob.glob(f'{C}/scripted_triggers/*.txt'):
    for k, v in items(rd(f)):
        if isinstance(v, list) and not has_param(v):
            ST[k] = v

# ---- trigger blocks -> clauses ------------------------------------------------------------------------------------
TL = {'tag': 'Country', 'culture': 'Culture', 'culture_group': 'Culture group', 'language': 'Language', 'religion': 'Religion',
      'religion_group': 'Religion group', 'region': 'Region', 'area': 'Area', 'sub_continent': 'Sub-continent', 'continent': 'Continent',
      'capital': 'Capital', 'government': 'Government', 'reform': 'Reform', 'subject_type': 'Subject type', 'status': 'Status',
      'estate': 'Estate', 'societal': 'Societal value', 'dlc': 'DLC', 'rank': 'Rank', 'institution': 'Institution',
      'advance': 'Advance', 'country_type': 'Country type', 'other': ''}
CAT = {'tag': 'country', 'culture': 'culture', 'culture_group': 'culture', 'language': 'culture', 'religion': 'religion',
       'religion_group': 'religion', 'region': 'region', 'area': 'region', 'sub_continent': 'region', 'continent': 'region', 'capital': 'region'}
GEO = ('region', 'area', 'sub_continent', 'continent')
# trigger key -> (type, via the capital)
KEYS = {'has_or_had_tag': ('tag', 0), 'tag': ('tag', 0), 'original_tag': ('tag', 0),
        'has_culture_group': ('culture_group', 0), 'merged_culture_group_contains_culture': ('culture', 0),
        'has_accepted_culture': ('culture', 0), 'has_primary_or_accepted_culture': ('culture', 0), 'culture.language': ('language', 0),
        'religion.group': ('religion_group', 0), 'region': ('region', 0), 'area': ('area', 0), 'sub_continent': ('sub_continent', 0),
        'continent': ('continent', 0), 'original_capital.region': ('region', 1), 'original_capital.area': ('area', 1),
        'capital.region': ('region', 1), 'capital.area': ('area', 1), 'government_type': ('government', 0), 'has_reform': ('reform', 0),
        'is_subject_type': ('subject_type', 0), 'country_has_estate': ('estate', 0), 'has_societal_value': ('societal', 0),
        'has_dlc': ('dlc', 0), 'country_rank': ('rank', 0), 'has_embraced_institution': ('institution', 0),
        'has_unlocked_advance_trigger': ('advance', 0), 'government': ('government', 0), 'country_type': ('country_type', 0)}
SCOPES = {'culture': 'culture', 'religion': 'religion', 'capital': 'capital', 'original_capital': 'capital'}
SKIPK = {'text', 'value', 'always', 'limit', 'hidden_trigger', 'trigger_if', 'trigger_else_if', 'trigger_else'}
known_other = collections.Counter()


def ref(v):  # "culture:turkish" -> "turkish"
    return v.split(':', 1)[1] if isinstance(v, str) and ':' in v else v


def atom(t, i, cap=0, nm=None):
    return ('atom', t, str(i), nm or (re.sub(r'^d\d+_', '', str(i)).replace('_', ' ').title() if t == 'dlc' else name(str(i))), cap)


def other(text):
    known_other[text] += 1
    return ('atom', 'other', text, text, 0)


def tr(b, scope='country', depth=0):  # trigger block -> node
    kids = []
    for k, o, v in b:
        if k is None or k in SKIPK:
            continue
        lst = isinstance(v, list)
        if k == 'AND' and lst:
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
        else:
            kids.append(leaf(k, o, v, scope, depth))
    return ('and', kids)


def leaf(k, o, v, scope, depth):
    neg = v == 'no'
    if (k == 'exists' and v == 'capital') or (k == 'num_locations' and o == '>' and v == '0'):  # always true for a real country
        return ('and', [])
    if k == 'has_variable' and isinstance(v, str) and v.startswith('unlocked_advance_'):
        return atom('advance', v[17:])
    if scope == 'religion' and k == 'has_tag':
        return atom('religion_group', ref(v))
    flip = lambda n: ('not', n) if neg else n
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
        flat += p['parts'] if p['type'] == 'any' and not p.get('not') else [p]
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


def cats(c, neg=False):  # categories of the clauses that actually restrict (positive ones)
    neg = neg != bool(c.get('not'))
    if 'parts' in c:
        return set().union(*(cats(p, neg) for p in c['parts']))
    return set() if neg else {CAT.get(c['type'], 'other')}


def clauses(*blocks):
    return [c for b in blocks if isinstance(b, list) for c in norm(tr(b))]


# ---- advances -> records -----------------------------------------------------------------------------------------
PLAIN = {'age', 'icon', 'requires', 'depth', 'research_cost', 'for', 'content_priority', 'starting_technology_level', 'allow_children',
         'country_type', 'government', 'in_tree_of'}
flagkeys = collections.Counter()
ICONS = f'{GAME}/main_menu/gfx/interface/advance'
IC_OUT = f'{OUT}/public/icons/advances'
os.makedirs(IC_OUT, exist_ok=True)
conv = set()


def build(aid, fname, b):
    a = {'id': aid, 'name': name(aid)}
    if (d := desc(aid)):
        a['desc'] = d
    ag = get(b, 'age')
    a['age'] = int(re.match(r'age_(\d)', ag).group(1)) if ag else 0
    if (fo := get(b, 'for')):
        a['focus'] = fo
    if isinstance(c := get(b, 'research_cost'), str) and val(c) is not None:
        a['cost'] = val(c)
    if (r := [v for k, _, v in b if k == 'requires' and isinstance(v, str)]):
        a['requires'] = r
    if (ic := get(b, 'icon') or aid) and os.path.exists(f'{ICONS}/{ic}.dds'):
        a['icon'] = ic
        conv.add(ic)
    un, mods = [], mods_of(b)
    for k, _, v in b:
        if not isinstance(v, str) or not k:
            continue
        if k.startswith('unlock_'):
            un.append([k[7:], v, name(v)])
        elif k not in PLAIN and k not in DEF and k not in SKIP_IN_MOD and k != 'pure_tooltip_entry':  # boolean abilities (may_explore...)
            flagkeys[k] += 1
            mods.append([mod_label(k), mod_value(k, v)])
    if un:
        a['unlocks'] = un
    if mods:
        a['mods'] = mods
    for k, _, v in b:
        if k == 'modifier_while_progressing' and isinstance(v, list) and (mm := mods_of(v)):
            a['during'] = mm
    # who can get it: potential + government / country_type; req = what a country must have to research it (allow)
    extra = [(k, '=', v) for k in ('government', 'country_type') if isinstance(v := get(b, k), str)]
    if (who := clauses(get(b, 'potential'), extra)):
        a['who'] = who
        a['whoText'] = '; '.join(ctext(c) for c in who)
        a['uniq'] = sorted(set().union(*(cats(c) for c in who))) or ['other']
    if (req := clauses(get(b, 'allow'))):
        a['req'] = req
        a['reqText'] = '; '.join(ctext(c) for c in req)
    a['file'] = re.sub(r'\.txt$', '', fname)
    return a


out = [build(k, f, b) for k, (f, b) in adv.items()]

n_new = 0
for ic in sorted(conv):
    p = f'{IC_OUT}/{ic}.png'
    if not os.path.exists(p):
        subprocess.run(['magick', f'{ICONS}/{ic}.dds', '-resize', '40x40', '-strip', '-define', 'png:compression-level=9', p], check=True)
        n_new += 1

AGES = {1: 'traditions', 2: 'renaissance', 3: 'discovery', 4: 'reformation', 5: 'absolutism', 6: 'revolutions'}
ages = {n: name(f'age_{n}_{s}') for n, s in AGES.items()}
focus = {k: loc.get(f'ages_of_eu.{k}', k) for k in ('adm', 'dip', 'mil')}
path = f'{OUT}/public/advances.json'
with open(path, 'w', encoding='utf-8') as fh:
    # descriptions are half the text and only the detail page shows them: they go in their own file
    lean = [{k: v for k, v in a.items() if k not in ('desc', 'file')} for a in out]
    json.dump({'ages': ages, 'focus': focus, 'advances': lean}, fh, separators=(',', ':'), ensure_ascii=False)
with open(f'{OUT}/public/advance_text.json', 'w', encoding='utf-8') as fh:
    json.dump({a['id']: a['desc'] for a in out if a.get('desc')}, fh, separators=(',', ':'), ensure_ascii=False)

if __name__ == '__main__':
    n = lambda t: norm(tr(parse(t)))
    assert n('has_or_had_tag = BYZ') == [{'type': 'tag', 'ids': ['BYZ'], 'names': [name('BYZ')]}]
    assert n('OR = { has_or_had_tag = BYZ has_or_had_tag = ROM }')[0]['ids'] == ['BYZ', 'ROM']
    assert n('NOT = { culture = { has_culture_group = culture_group:italian_group } }')[0]['not'] == 1
    assert n('OR = { culture = culture:a culture = { merged_culture_group_contains_culture = culture:a } }')[0]['ids'] == ['a']
    assert n('OR = { has_or_had_tag = TUR has_reform = government_reform:anatolian_beylik }')[0]['type'] == 'any'
    assert n('capital = { region = region:x }')[0].get('cap') == 1
    assert 'not' not in n('NOT = { NOT = { tag = AAA } }')[0]
    print('size', os.path.getsize(path), 'bytes;', len(out), 'advances; icons', len(conv), f'({n_new} newly converted)')
    print('icon dir', sum(os.path.getsize(f'{IC_OUT}/{f}') for f in os.listdir(IC_OUT)), 'bytes,', len(os.listdir(IC_OUT)), 'files')
    cn = collections.Counter
    print('per age:', {ages[a]: sum(1 for x in out if x['age'] == a) for a in ages})
    print('per focus:', dict(cn(x.get('focus', 'general') for x in out)))
    print('per age x focus:', {a: dict(cn(x.get('focus', 'general') for x in out if x['age'] == a)) for a in ages})
    print('universal:', sum(1 for x in out if 'who' not in x), 'restricted:', sum(1 for x in out if 'who' in x))
    print('restricted by category (an advance can count in several):', dict(cn(c for x in out for c in x.get('uniq', []))))
    print('who clause types:', dict(cn(c['type'] for x in out for c in x.get('who', [])).most_common()))
    print('allow clauses:', sum(1 for x in out if 'req' in x), dict(cn(c['type'] for x in out for c in x.get('req', [])).most_common()))
    print('unlock kinds:', dict(cn(u[0] for x in out for u in x.get('unlocks', [])).most_common()))
    print('flag-style modifier keys (not in the modifier definitions):', flagkeys.most_common(30))
    print('unsummarisable (other) atoms:', len(known_other), known_other.most_common(40))
    print('modifier labels:', mod_cov, 'raw keys:', sorted(raw_keys.items(), key=lambda x: -x[1])[:15])
    nm = cn()
    for x in out:
        for c in x.get('who', []) + x.get('req', []):
            for i, s in zip(c.get('ids', []), c.get('names', [])):
                if s == human(i) and c['type'] != 'other':
                    nm[(c['type'], i)] += 1
    print('names that fell back to the raw id:', len(nm), nm.most_common(25))
    for i in ('written_alphabet', 'innovativeness', 'unlock_cakradonya', 'fratricide_succesion_advance'):
        print(json.dumps(next(x for x in out if x['id'] == i), ensure_ascii=False))
