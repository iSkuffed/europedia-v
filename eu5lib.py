"""Shared helpers for the extractors (unique.py, ...): game paths, script loading, localisation,
modifier labels and values, and tag conditions. Import with `from eu5lib import *`."""
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
    s = re.sub(r"\[GetCharacter\('(\w+)'\)\.GetName\w*\]", lambda m: m.group(1).replace('_', ' ').title(), s)  # kublai_khan -> Kublai Khan
    s = re.sub(r"\[GetUniqueInternationalOrganization\('(\w+)'\)\.GetName\w*\]", lambda m: text(loc[m.group(1)]) if m.group(1) in loc else human(m.group(1)), s)
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
