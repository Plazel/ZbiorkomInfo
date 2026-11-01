"""Road routes between consecutive stops ("legs") again for the stops moved since they were found (e.g. placed by hand
with narzedzia/przystanki-krynica.html): a leg whose end is more than 15 m from its stop is routed anew (drogi.road_legs);
where routing fails the old leg is kept. Both reczne/krynica_muszyna.json and reczne/km_dodatkowe.json.
Usage: python3 legs_odswiez.py"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, ROOT)
from drogi import road_legs, dist

PATHS = [os.path.join(ROOT, 'reczne', f) for f in ('krynica_muszyna.json', 'km_dodatkowe.json')]
F = [json.load(open(p, encoding='utf-8')) for p in PATHS]
pos = {}
for D in F:
    for k, v in D['stops'].items(): pos.setdefault(k, [v[2], v[3]])
todo = {}
for i, D in enumerate(F):
    for key, pts in (D.get('legs') or {}).items():
        a, b = key.split(' ')
        if a in pos and b in pos and pts and (dist(pts[0], pos[a]) > 15 or dist(pts[-1], pos[b]) > 15): todo.setdefault((a, b), []).append(i)
print('odcinki do przeliczenia:', len(todo))
if todo:
    new, odd = road_legs(set(todo), {s: pos[s] for pr in todo for s in pr}, log=print)
    for pr, files in todo.items():
        if pr in new:
            for i in files: F[i]['legs']['%s %s' % pr] = [[round(x, 5), round(y, 5)] for x, y in new[pr]]
    print('przeliczone: %d, bez zmian (nie udało się): %d' % (len(new), len(todo) - len(new)))
    for i, p in enumerate(PATHS): json.dump(F[i], open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
