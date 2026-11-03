#!/usr/bin/env python3
"""Krynica-Zdrój's stops named without "-Zdrój" ("Krynica Czarny Potok Gondola"): there is only one Krynica in the area, so
the shorter name is enough on the page and in the guide's announcements. The railway station and the stop at it keep the
town's full name ("Krynica-Zdrój", "Krynica-Zdrój Dworzec PKP"), as do the operator (MPGK Krynica-Zdrój) and the area.
Then the names of a street's stops split as in Bydgoszcz: the street apart from the place on it ("Krynica Kraszewskiego -
Szpital", "Muszyna Kościuszki - Pętla"): where several stops of a town share the street (or the stop on it has its own
name), and those listed in SPLIT.
Done on the data written by build.py (the names inside the build stay as in the sources).
Usage: python3 krynica_nazwy.py [data folder]   (build.py calls apply())"""
import json, os, re, sys

OLD, NEW = 'Krynica-Zdrój', 'Krynica'
RX = re.compile(r'Krynica-Zdrój (?!Dworzec PKP)(?=\w)')
KEEP_KEYS = {'op'}   # (the operator: its own name)
EXTRA_TOWNS = {'Krynica', 'Mochnaczka Niżna', 'Wierchomla Wielka', 'Wojkowa'}
SPLIT = {'Krynica Szkolna Gimnazjum': 2, 'Krynica Jastrzębia ZAiKS': 2, 'Krynica Zdrojowa Bank': 2, 'Krynica Słotwiny Arena': 2, 'Krynica Zawodzie Pętla': 2}   # name: words before " - "
NUM = re.compile(r'\s(I|II|III)$')


def splits(names):
    """name -> name with " - " between the street (with the town) and the place on it"""
    A = {n for n in names if not re.search(r'\s(I|II|PKP)$', n)} | EXTRA_TOWNS
    towns = {x for x in A if x.endswith(' Zdrój') or not any(' '.join(x.split()[:k]) in A for k in range(1, len(x.split())))}
    base = {NUM.sub('', n) for n in names}   # (Jastrzębik I and II: one stop for this)
    mp = {}
    for n in names:
        if n.endswith('PKP') or ' - ' in n: continue
        w = n.split()
        if n in SPLIT: mp[n] = ' '.join(w[:SPLIT[n]]) + ' - ' + ' '.join(w[SPLIT[n]:]); continue
        t = max((k for k in range(1, len(w)) if ' '.join(w[:k]) in towns), default=None)
        if t is None or len(w) - t < 2: continue
        best = None
        for k in range(t + 1, len(w)):
            pre = ' '.join(w[:k])
            if NUM.match(' ' + ' '.join(w[k:])): continue
            if sum(1 for m in base if m.startswith(pre + ' ') or m == pre) >= 2: best = k
        if best: mp[n] = ' '.join(w[:best]) + ' - ' + ' '.join(w[best:])
    return mp


def fix(v, f, key=None):
    if isinstance(v, str): return v if key in KEEP_KEYS else f(v)
    if isinstance(v, list): return [fix(x, f) for x in v]
    if isinstance(v, dict): return {f(k): fix(x, f, k) for k, x in v.items()}
    return v


def apply(out, log=print):
    _apply(out, lambda v: RX.sub(NEW + ' ', v) if OLD in v else v, (OLD,))
    idx = json.load(open(os.path.join(out, 'index.json'), encoding='utf-8'))
    mp = splits(sorted({s[0].replace(' - ', ' ') for s in idx['stops'].values() if s[4] == 'km'}))   # (run again: from the names before the split)
    if mp:   # (also inside other texts: "Kurs do: …", the variants' descriptions)
        rx = re.compile('(' + '|'.join(re.escape(k) for k in sorted(mp, key=len, reverse=True)) + r')(?![\w])')
        _apply(out, lambda v: rx.sub(lambda m: mp[m.group(1)], v) if any(t in v for t in ('Krynica', 'Muszyna', 'Tylicz')) else v, ('Krynica', 'Muszyna', 'Tylicz'))
    log('Krynica i Muszyna: %d nazw z „ - ”' % len(mp))
    return mp


def _apply(out, f, words):
    n = 0
    for root, _, files in os.walk(out):
        for fn in files:
            if not fn.endswith('.json'): continue
            p = os.path.join(root, fn)
            s = open(p, encoding='utf-8').read()
            if not any(w in s for w in words): continue
            j = json.loads(s); j2 = fix(j, f)
            if j2 != j: json.dump(j2, open(p, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':')); n += 1
    return n


if __name__ == '__main__':
    apply(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
