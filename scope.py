"""Per-country facts for the "viewing as" nation scope -> public/scope.json, as game ids so they match `who` items.
Usage: python3 -I scope.py [game_dir]

{ "names": {id: display name}, "countries": { TAG: { "name": display name, "c": culture, "cg": [culture groups], "lang": language, "r": religion, "rg": religion group,
         "gov": government type (setup, else start.json), "over": overlord tag or absent,
         "cap": [continent, sub-continent, region, area] of the capital,
         "geo": [every continent / sub-continent / region / area the country owns land in] } }
All at the 1337 start."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eu5lib import *

SETUP, MAP = f'{GAME}/main_menu/setup/1337', f'{GAME}/in_game/map_data'

geo_of = {}  # location -> [continent, sub-continent, region, area]
def walk(b, path):
    for k, _, v in b:
        if isinstance(v, list):
            walk(v, path + [k])
        elif k is None and len(path) >= 4:
            geo_of[v] = path[:4]
walk(rd(f'{MAP}/definitions.txt'), [])

cultures, religions = load('cultures'), load('religions')
lang_of = {}  # dialect or language -> language
for f in sorted(glob.glob(f'{C}/languages/*.txt')):
    for k, v in items(rd(f)):
        if isinstance(v, list):
            lang_of[k] = k
            for d, dv in items(get(v, 'dialects') or []):
                lang_of[d] = k

official = {}  # tag -> (culture, religion) as the game sets them
for f in glob.glob(f'{GAME}/in_game/setup/countries/*.txt'):
    for k, v in items(rd(f)):
        if isinstance(v, list):
            official[k] = (get(v, 'culture_definition'), get(v, 'religion_definition'))

over = {}
for a, b in re.findall(r'dependency\s*=\s*\{\s*first\s*=\s*(\w+)\s+second\s*=\s*(\w+)', open(f'{SETUP}/12_diplomacy.txt', encoding='utf-8-sig').read()):
    over[b] = a

start = json.load(open(f'{OUT}/public/start.json'))['countries']  # start.py: the save knows governments the setup files leave to includes
out = {}
for tag, _, b in get(get(rd(f'{SETUP}/10_countries.txt'), 'countries'), 'countries'):
    if not isinstance(b, list):
        continue
    locs = [x for k, _, v in b if k and k.startswith('own_') and isinstance(v, list) for _, _, x in v if x in geo_of]
    if not locs:
        continue
    c, r = official.get(tag, (None, None))
    cb, rb = cultures.get(c) or [], religions.get(r) or []
    e = {'name': name(tag, tag), 'c': c, 'cg': [x for _, _, x in get(cb, 'culture_groups') or []], 'lang': lang_of.get(get(cb, 'language')),
         'r': r, 'rg': get(rb, 'group'), 'gov': get(get(b, 'government') or [], 'type') or start.get(tag, {}).get('gov')}
    if tag in over:
        e['over'] = over[tag]
    cap = get(b, 'capital')
    if cap in geo_of:
        e['cap'] = geo_of[cap]
    e['geo'] = sorted({g for l in locs for g in geo_of[l]})
    out[tag] = {k: v for k, v in e.items() if v}

ids = {x for e in out.values() for k in ('c', 'cg', 'lang', 'r', 'rg', 'gov', 'geo') for x in ([e[k]] if isinstance(e.get(k), str) else e.get(k, []))}
with open(f'{OUT}/public/scope.json', 'w', encoding='utf-8') as fh:  # + display names, for data that only kept names (building requirements)
    json.dump({'names': {i: name(i) for i in sorted(ids)}, 'countries': out}, fh, separators=(',', ':'), sort_keys=True)
print(f'scope.json: {len(out)} countries')
