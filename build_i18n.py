#!/usr/bin/env python3
"""Writes the interface translations (i18n_src.py) into index.html, between the I18N markers.
Usage: python build_i18n.py"""
import json, os, re
from i18n_src import ROWS, WEEKDAYS, PHRASES

HERE = os.path.dirname(os.path.abspath(__file__))
LANGS = ['en', 'de', 'sk', 'cs']
D = {l: {} for l in LANGS}
for row in ROWS:
    pl = row[0]
    for i, l in enumerate(LANGS):
        D[l][pl] = row[i + 1]
PH = {l: [[p[0], p[i + 1]] for p in PHRASES] for i, l in enumerate(LANGS)}
js = 'const I18N=' + json.dumps({'d': D, 'wd': WEEKDAYS, 'ph': PH}, ensure_ascii=False, separators=(',', ':')) + ';'
p = os.path.join(HERE, 'index.html')
s = open(p, encoding='utf-8').read()
s = re.sub(r'/\*I18N\*/.*?/\*/I18N\*/', lambda m: '/*I18N*/' + js + '/*/I18N*/', s, flags=re.S)
open(p, 'w', encoding='utf-8').write(s)
print('I18N:', len(ROWS), 'phrases')
