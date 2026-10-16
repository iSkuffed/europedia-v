"""Extract every estate privilege into public/privileges.json: modifiers, effects, who can get it (potential), what
enacting needs (allow), when it can be revoked, how it is unlocked, and which privileges it excludes/needs.
Usage: python3 -I privileges.py [game_dir]

"Who" items are {type, kind, ids, names, not?, text} with type in tag / culture / religion / region / government /
unlock / other; an OR of mixed kinds becomes {type:'any', any:[items]}, unknown block triggers {type:'other', all:[items]}.
Empty `who` = everyone. Scripted triggers are expanded by name where possible; the rest are kept as 'other' items."""
import sys, os, re, glob, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eu5lib import *

ESTATE_MOD = re.compile(r'_estate_(power|target_satisfaction)$')
SCRIPTED = {}
for f in sorted(glob.glob(f'{C}/scripted_triggers/*.txt')):
    for k, v in items(rd(f)):
        if isinstance(v, list):
            SCRIPTED[k] = v
unresolved = {}


def pref(v):
    return v.split(':', 1)[1] if isinstance(v, str) and ':' in v else v


def nm(t, v):
    v = pref(v)
    return loc.get(v, v) if t == 'tag' else name(v)


def op_text(op):
    return {'=': '', '?=': '', '>': 'above ', '>=': 'at least ', '<': 'below ', '<=': 'at most ', '!=': 'not '}.get(op, '')


def num_text(v):
    x = val(v) if isinstance(v, str) else None
    if x is None:
        return str(v)
    return f'{g(x * 100, 1)}%' if abs(x) <= 1 and '.' in str(v) else g(x, 2)


def subst(block, args):  # fill $param$ in a scripted trigger body
    out = []
    for k, op, v in block:
        f = lambda s: re.sub(r'\$(\w+)\$', lambda m: args.get(m.group(1), m.group(0)), s) if isinstance(s, str) else s
        out.append((f(k), op, subst(v, args) if isinstance(v, list) else f(v)))
    return out


def mk(type, kind, ids, neg=False, **kw):
    ids = ids if isinstance(ids, list) else [ids]
    names = [nm(type, i) for i in ids]
    it = {'type': type, 'kind': kind, 'ids': [pref(i) for i in ids], 'names': names}
    if neg:
        it['not'] = True
    it.update(kw)
    it['text'] = ('Not ' if neg else '') + (f'{kind}: ' if kind else '') + ', '.join(names)
    return it


def txt(t, neg=False, type='other', kind='', **kw):  # free-text item
    it = {'type': type, 'kind': kind, 'text': ('Not: ' if neg else '') + t}
    if neg:
        it['not'] = True
    it.update(kw)
    return it


def types_of(it):
    out = {it['type']} if it['type'] not in ('any',) else set()
    for s in it.get('any', []) + it.get('all', []):
        out |= types_of(s)
    return out


GEO = {'region': 'region', 'area': 'area', 'sub_continent': 'sub-continent', 'continent': 'continent'}
CULT = {'has_culture_group': 'culture group', 'culture_group': 'culture group'}
SCOPES = {'culture': 'culture', 'religion': 'religion', 'capital': 'capital', 'owner': 'owner', 'ruler': 'ruler'}


def conds_of(block, neg=False, scope=None, depth=0):
    """AND of the conditions in a trigger block -> list of items."""
    out = []
    for k, op, v in block:
        out += leaf(k, op, v, neg, scope, depth)
    return out


def tag_items(vs, neg, scope):
    return [mk('tag', 'country', vs, neg)]


def key_label(k):  # "estate_power(estate_type:crown_estate)" -> Estate power (Crown)
    m = re.fullmatch(r'(\w+)[(:](?:\w+:)?(\w+)\)?', k)
    return f'{human(m.group(1))} ({name(m.group(2))})' if m else human(k)


def leaf(k, op, v, neg, scope, depth):
    if k is None:
        return conds_of(v, neg, scope, depth) if isinstance(v, list) else []
    if k in ('tag', 'has_or_had_tag') and isinstance(v, str):
        return [mk('tag', 'country', v, neg)]
    if k in ('AND',):
        return conds_of(v, neg, scope, depth)
    if k in ('NOT', 'NOR') and isinstance(v, list):  # none of the children may hold
        return conds_of(v, not neg, scope, depth)
    if k in ('OR', 'NAND') and isinstance(v, list):
        subs = [conds_of([c], False, scope, depth) for c in v]
        subs = [s for s in subs if s]
        flat = [s[0] for s in subs if len(s) == 1]
        if k == 'OR' and not neg and len(flat) == len(subs) == len(v) and len({(s['type'], s['kind'], s.get('not')) for s in flat}) == 1 and 'ids' in flat[0]:
            names = [n for s in flat for n in s['names']]
            return [dict(flat[0], ids=[i for s in flat for i in s['ids']], names=names,
                         text=('Not ' if flat[0].get('not') else '') + (f"{flat[0]['kind']}: " if flat[0]['kind'] else '') + ', '.join(names))]
        if not subs:
            return []
        sub = [s[0] if len(s) == 1 else {'type': 'other', 'kind': '', 'all': s, 'text': ' and '.join(x['text'] for x in s)} for s in subs]
        it = {'type': 'any', 'kind': '', 'any': sub, 'text': ('None of: ' if neg else 'Any of: ') + '; '.join(s['text'] for s in sub)}
        if neg:
            it['not'] = True
        return [it]
    if k in ('trigger_if', 'trigger_else_if', 'trigger_else', 'if', 'else_if', 'else') and isinstance(v, list):
        lim = get(v, 'limit')
        body = [x for x in v if x[0] != 'limit']
        s, c = (conds_of(lim, False, scope, depth) if isinstance(lim, list) else []), conds_of(body, neg, scope, depth)
        if not c:
            return []
        t = ('If ' + ' and '.join(x['text'] for x in s) + ': ' if s else ('Otherwise: ' if k.endswith('else') else '')) + ' and '.join(x['text'] for x in c)
        return [{'type': 'other', 'kind': '', 'all': s + c, 'text': t}]
    if k == 'custom_tooltip' or k == 'custom_description':
        t = get(v, 'text') if isinstance(v, list) else v
        if isinstance(t, str):
            inner = [x for x in conds_of([y for y in v if y[0] != 'text'], neg, scope, depth)] if isinstance(v, list) else []
            ty = 'unlock' if any(x['type'] == 'unlock' for x in inner) else 'other'
            return [txt(text(loc[t]) if t in loc else human(t.replace('.tt', '').replace('_tt', '')), neg, ty, all=inner)]
        return []
    if k == 'has_unlocked_estate_privilege_trigger':
        return [txt('Must be unlocked first (advance, decision or event)', neg, 'unlock', 'unlock', unlocks=pref(get(v, 'type')) if isinstance(v, list) else None)]
    if k in SCOPES and isinstance(v, list):  # culture ?= { ... } / capital ?= { ... }
        subs = conds_of(v, neg, SCOPES[k], depth)
        for s in subs:
            if SCOPES[k] == 'capital' and s['type'] == 'region':
                s['kind'] = 'capital in ' + s['kind']
                s['text'] = ('Not ' if s.get('not') else '') + s['kind'] + ': ' + ', '.join(s['names'])
        return subs
    if k == 'culture' and isinstance(v, str):
        return [mk('culture', 'culture', v, neg)]
    if k in CULT and isinstance(v, str):
        return [mk('culture', 'culture group', v, neg)]
    if k in ('religion', 'religion.group', 'group') and isinstance(v, str) and (k != 'group' or scope == 'religion'):
        grp = k != 'religion' and v.startswith('religion_group:') or k != 'religion'
        if '.' in v:
            return [txt('Same religion group as own' if grp else 'Same religion as own', neg, 'religion', 'religion')]
        return [mk('religion', 'religion group' if grp else 'religion', v, neg)]
    if k == 'has_religion' and isinstance(v, str):
        return [mk('religion', 'religion', v, neg)]
    if k in GEO and isinstance(v, str):
        return [mk('region', GEO[k], v, neg)]
    if k == 'capital.region' and isinstance(v, str):
        return [mk('region', 'capital in region', v, neg)]
    if k == 'owns' and isinstance(v, str):
        return [mk('region', 'owns', v, neg)]
    if k == 'government_type' and isinstance(v, str):
        return [mk('government', 'government', v, neg)]
    if k == 'has_tribal_government':
        return [txt('Tribal government', neg ^ (v == 'no'), 'government')]
    if k == 'has_reform' and isinstance(v, str):
        return [mk('government', 'reform', v, neg)]
    if k in ('has_law', 'succession_law', 'parliament_type', 'has_policy') and isinstance(v, str):
        return [mk('government', {'has_law': 'law', 'succession_law': 'succession law', 'parliament_type': 'parliament', 'has_policy': 'policy'}[k], v, neg)]
    if k == 'has_advance' and isinstance(v, str):
        return [mk('other', 'advance', v, neg)]
    if k == 'has_estate_privilege' and isinstance(v, str):
        it = mk('other', 'privilege', v, neg)
        it['priv'] = pref(v)
        return [it]
    if k == 'has_variable' and isinstance(v, str):
        return [txt(f'Needs event or decision flag: {human(v)}', neg, 'unlock', 'flag')]
    m = re.fullmatch(r'(religion|culture)(?:_group)?_percentage_in_country\((?:root\.|\w+:)?(\w+)\)', k or '')
    if m and isinstance(v, str):
        return [txt(f'{name(m.group(2))} {op_text(op)}{num_text(v)} of the population', neg, m.group(1), 'share')]
    if k == 'always':
        return [txt('Cannot be revoked', False, 'other', 'never')] if v == 'no' else []
    if k in ('is_alive', 'exists'):
        return []
    if k == 'any_overlord_or_above' and isinstance(v, list):
        tg = [x for x in conds_of(v, False, scope, depth) if x['type'] == 'tag']
        if tg:
            return [mk('tag', 'subject of', [i for x in tg for i in x['ids']], neg)]
    if k in ('dominant_religion', 'dominant_culture') and isinstance(v, str):
        t = k.split('_')[1]
        return [mk(t, 'dominant ' + t, v, neg)]
    m = re.fullmatch(r'(religion|culture)(_group)?_(percentage|population)_in_country', k) if isinstance(v, list) else None
    if m:
        what = get(v, 'religion') or get(v, 'culture') or get(v, 'religion_group') or get(v, 'culture_group') or get(v, 'target')
        cmp = [(o, x) for kk, o, x in v if kk == 'value'][:1]
        o, x = cmp[0] if cmp else ('>', '0')
        amt = (num_text(x) + ' of the population') if m.group(3) == 'percentage' else f'{num_text(x)}k population'
        return [txt(f'{name(pref(what))} {op_text(o)}{amt}'.replace('population population', 'population'), neg, m.group(1), 'share')]
    if k in SCRIPTED and isinstance(v, (str, list)):
        if depth < 4:
            args = {a: b for a, _, b in v if a and isinstance(b, str)} if isinstance(v, list) else {}
            body = subst(SCRIPTED[k], args)
            inner = conds_of([x for x in body if x[0] in ('limit', 'custom_description', 'custom_tooltip', None) or True], neg, scope, depth + 1)
            if inner:
                return [{'type': 'other', 'kind': human(k), 'all': inner, 'text': f'{human(k)} ({" and ".join(x["text"] for x in inner)})', 'trigger': k}] if len(inner) > 1 else inner
        unresolved[k] = unresolved.get(k, 0) + 1
        return [txt(human(k), neg, 'other', 'trigger', trigger=k)]
    if isinstance(v, list):  # unknown block: keep its readable contents
        inner = conds_of(v, neg, scope, depth)
        label = loc.get(k[2:], k[2:]) if re.fullmatch(r'c:[A-Z][A-Z0-9]{2}', k) else human(re.sub(r'^(any|every|random)_', '', k))
        if inner:
            return [{'type': 'other', 'kind': label, 'all': inner, 'text': f'{label}: ' + ' and '.join(x['text'] for x in inner)}]
        unresolved[k] = unresolved.get(k, 0) + 1
        return []
    # comparison / unknown leaf
    unresolved[k] = unresolved.get(k, 0) + 1
    label = key_label(k)
    pct = k.startswith(('estate_power', 'religious_unity', 'average_control', 'estate_satisfaction'))
    vs = str(v)
    if num(v) is not None:
        vs = num_text(v) if pct else g(num(v), 2)
    elif isinstance(v, str) and '(' in v:
        vs = key_label(v)
    elif isinstance(v, str) and pref(v) in loc:
        vs = name(pref(v))
    elif isinstance(v, str):
        vs = human(pref(v))
    return [txt(f'{label} {op_text(op) or "is "}{vs}', neg, 'other', 'condition')]


def summary(items_):
    return '; '.join(i['text'] for i in items_) if items_ else ''


# ---- unlock sources: advances, decisions, events ----------------------------------------------------------------------
UNLOCK_SRC = {}  # privilege id -> [{kind, id, name, age?, tags?}]
adv = {}
for f in sorted(glob.glob(f'{C}/advances/*.txt')):
    for k, v in items(rd(f)):
        if isinstance(v, list):
            adv[k] = v
for aid, b in adv.items():
    for k, v in items(b):
        if k == 'unlock_estate_privilege' and isinstance(v, str):
            t, _ = conds(b, ('potential', 'allow'))
            e = {'kind': 'advance', 'id': aid, 'name': name(aid)}
            if get(b, 'age'):
                e['age'] = name(get(b, 'age'))
            if t:
                e['tags'] = sorted(t)
            UNLOCK_SRC.setdefault(v, []).append(e)


def effect_types(block, out):
    for k, _, v in block:
        if k == 'unlock_estate_privilege_effect' and isinstance(v, list):
            if isinstance(get(v, 'type'), str):
                out.add(get(v, 'type'))
        if isinstance(v, list):
            effect_types(v, out)


for kind, pat, tkeys in (('decision', f'{C}/decisions/*.txt', ('potential', 'allow')), ('event', f'{GAME}/in_game/events/**/*.txt', ('trigger',))):
    for f in sorted(glob.glob(pat, recursive=True)):
        if 'unlock_estate_privilege_effect' not in open(f, encoding='utf-8-sig', errors='replace').read():
            continue
        for k, v in items(rd(f)):
            if not isinstance(v, list):
                continue
            found = set()
            effect_types(v, found)
            for p in found:
                t, _ = conds(v, tkeys)
                fm = re.search(r'flavor_(?:decisions_)?([A-Za-z]{3})\.txt$', f)  # flavor files are per country: heuristic tag
                if not t and fm and fm.group(1).upper() in loc:
                    t = {fm.group(1).upper()}
                e = {'kind': kind, 'id': k, 'name': name(k, f'{k}.t') if kind == 'event' else name(k)}
                if t:
                    e['tags'] = sorted(t)
                UNLOCK_SRC.setdefault(p, []).append(e)

# ---- estates & privileges ----------------------------------------------------------------------------------------------
ESTATES = [{'id': k, 'name': name(k)} for k, v in load('estates').items()]
P = {}
for f in sorted(glob.glob(f'{C}/estate_privileges/*.txt')):
    if f.endswith('readme.txt'):
        continue
    for k, v in items(rd(f)):
        if isinstance(v, list):
            P[k] = v

ek = lambda es: {e['id']: e['name'] for e in ESTATES}.get(es, human(es or ''))


def effect_texts(block):
    out = []
    for k, _, v in block:
        if k == 'custom_tooltip':
            t = get(v, 'text') if isinstance(v, list) else v
            out.append(text(loc[t]) if t in loc else human(re.sub(r'\.?tt$', '', t).replace('_tt', '')))
        elif k in ('add_opinion', 'reverse_add_opinion') and isinstance(v, list):
            out.append(f'Opinion change with {name(get(v, "target", "").replace("c:", "")) if get(v, "target") else "target"}')
        elif isinstance(v, list):
            out += effect_texts(v)
    return out


def refs(items_, neg_ok):
    out = []
    for i in items_:
        if i.get('priv') and bool(i.get('not')) == neg_ok:
            out.append(i['priv'])
        out += refs(i.get('any', []) + i.get('all', []), neg_ok)
    return out


def strip_priv(items_):  # privilege cross-references have their own section
    return items_


res = []
for pid, b in P.items():
    est = get(b, 'estate')
    pot = [x for k, _, x in b if k == 'potential' and isinstance(x, list)]
    alw = [x for k, _, x in b if k == 'allow' and isinstance(x, list)]
    rev = [x for k, _, x in b if k == 'can_revoke' and isinstance(x, list)]
    who = [i for x in pot for i in conds_of(x)]
    req = [i for x in alw for i in conds_of(x)]
    rvk = [i for x in rev for i in conds_of(x)]
    e = {'id': pid, 'name': name(pid), 'estate': est, 'estateName': ek(est)}
    d = desc(pid)
    if d:
        e['desc'] = d
    groups = []
    for k, _, x in b:
        if k.endswith('_modifier') and isinstance(x, list):
            pt = get(x, 'potential_trigger')
            body = [y for y in x if y[0] != 'potential_trigger']
            es = [y for y in body if y[0] and ESTATE_MOD.search(y[0])]
            ot = [y for y in body if not (y[0] and ESTATE_MOD.search(y[0]))]
            grp = {'kind': k[:-len('_modifier')]}
            if isinstance(pt, list):
                grp['when'] = summary(conds_of(pt)) or condition_text(pt) or 'conditional'
            grp['mods'], grp['estate'] = mods_of(ot), mods_of(es)
            if grp['mods'] or grp['estate']:
                groups.append(grp)
    e['groups'] = groups
    # short effect line for lists: the first plain country modifiers
    e['sum'] = [l if v == 'Yes' else f'{l} {v}' for gr in groups if not gr.get('when') for l, v in gr['mods']][:3]
    # unlock
    src = UNLOCK_SRC.get(pid, [])
    gated = any(i['type'] == 'unlock' for i in who) or any(i['type'] == 'unlock' for x in req for i in [x])
    if src:
        e['unlock'] = src
        if gated and all(s.get('tags') for s in src) and not any(i['type'] == 'tag' for i in who):
            tags = sorted({t for s in src for t in s['tags']})
            if len(tags) <= MAXTAGS:
                who.append(dict(mk('tag', 'unlocked for', tags), derived=True))
    e['who'], e['whoText'] = who, summary(who) or 'Everyone'
    if req:
        e['requires'] = req
    e['revoke'] = rvk
    e['canRevoke'] = not any(i.get('kind') == 'never' for i in rvk)
    c = sorted(set(refs(who, True) + refs(req, True)))
    n = sorted(set(refs(who, False) + refs(req, False) + refs(rvk, False)))
    if c:
        e['conflicts'] = c
    if n:
        e['needs'] = n
    for key, out in (('on_activate', 'onActivate'), ('on_deactivate', 'onDeactivate')):
        t = effect_texts(get(b, key) or [])
        if get(b, key) is not None:
            e[out] = t or ['Scripted effects']
    if get(b, 'months'):
        e['months'] = int(float(get(b, 'months')))
    e['types'] = sorted({t for i in who for t in types_of(i)})
    res.append(e)

# fix cross refs: has_estate_privilege inside the privileges' own text stays readable; drop refs to nothing
ids = set(P)
for e in res:
    for key in ('conflicts', 'needs'):
        if key in e:
            e[key] = [x for x in e[key] if x in ids]
            if not e[key]:
                del e[key]
    e['availability'] = (['tag'] if 'tag' in e['types'] else []) + [t for t in ('culture', 'religion', 'region') if t in e['types']] + (
        ['other'] if set(e['types']) & {'government', 'unlock', 'other'} else [])
    if not e['availability']:
        e['availability'] = ['all']

counts = {es['id']: sum(1 for e in res if e['estate'] == es['id']) for es in ESTATES}
out = {'estates': [dict(es, count=counts[es['id']]) for es in ESTATES if counts[es['id']]], 'privileges': res}
json.dump(out, open(f'{OUT}/public/privileges.json', 'w', encoding='utf-8'), separators=(',', ':'), ensure_ascii=False)

# ---- summary ----------------------------------------------------------------------------------------------------------
print(f'{len(res)} privileges -> public/privileges.json ({os.path.getsize(OUT + "/public/privileges.json") // 1024} KB)')
print('per estate:', {es['name']: counts[es['id']] for es in ESTATES if counts[es['id']]})
av = {}
for e in res:
    for a in e['availability']:
        av[a] = av.get(a, 0) + 1
print('availability (a privilege can count under several):', av)
print('universal:', sum(1 for e in res if not e['who']), ' restricted:', sum(1 for e in res if e['who']))
print('unresolved triggers/keys:', dict(sorted(unresolved.items(), key=lambda x: -x[1])))
print('modifier labels named/raw:', mod_cov, 'raw keys:', dict(raw_keys))

# card art: every privilege has a 64x90 picture named after it (DLC ones live under dlc/)
ART = {os.path.basename(f)[:-4]: f for f in glob.glob(f'{GAME}/main_menu/gfx/interface/icons/privileges/*.dds')
       + glob.glob(f'{GAME}/dlc/*/main_menu/gfx/interface/icons/privileges/*.dds')}
os.makedirs(f'{OUT}/public/icons/privileges', exist_ok=True)
for e in res:
    dst = f'{OUT}/public/icons/privileges/{e["id"]}.webp'
    if not os.path.exists(dst):
        subprocess.run(['magick', ART.get(e['id'], ART['_default']), '-strip', '-quality', '88', dst], check=True)
print('card art:', sum(e['id'] in ART for e in res), 'of', len(res))
