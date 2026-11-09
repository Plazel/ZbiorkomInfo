#!/usr/bin/env python3
"""The notices of every city translated into the page's other languages – free, on the build's own machine, with no service
and no key: Argos Translate's open models (argos-net.com, MIT/CC0), run with CTranslate2 and SentencePiece. Every model goes
through English (Polish → English → German). Hourly, after the notices themselves (bvg_utrudnienia.py, utrudnienia_miast.py).

For each group of cities and each language the page shows: data/tl/<group>_<language>.json
    {"s": source language, "d": language, "m": {line of the source: its translation}}
The lines are those the page translates (index.html: mtStrs): each line of a notice's title and text without its "• " and its
[heading] brackets, and the words before a list of suspended stops. A line translated once is kept (the file of the run
before), so only new notices take the models' time.
Stop names of the city and the links ([text](url)) are not translated: set aside before and put back after; a line whose
names did not come back whole is left out (the page shows it in the original).
Sources: data/alerts_*.json (the build's), ZTM Gdańsk's notices through the site's worker (/alerts), the GTFS-RT service
alerts of Warszawa, Łódź (zbiorkom.live) and Kraków (ZTP).
Usage: python3 tlumacz_komunikaty.py [data folder]   (needs: pip install ctranslate2 sentencepiece "sacremoses<0.2"; pip install --no-deps argostranslate)"""
import json, os, re, sys, unicodedata, urllib.request, zipfile

UA = {'User-Agent': 'ZbiorkomInfo/1.0 (rozklady; github.com/Plazel/ZbiorkomInfo)'}
LANGS = ['pl', 'en', 'de', 'sk', 'cs']
MODELS = {('pl', 'en'): 'pl_en-1_9', ('cs', 'en'): 'cs_en-1_9_6', ('de', 'en'): 'de_en-1_3',
          ('en', 'pl'): 'en_pl-1_9', ('en', 'de'): 'en_de-1_3', ('en', 'sk'): 'en_sk-1_9', ('en', 'cs'): 'en_cs-1_9_6'}
MODEL_DIR = os.environ.get('ARGOS_CT2_DIR', os.path.expanduser('~/.cache/argos-ct2'))
WORKER = 'https://divine-limit-0a3b.latka1500.workers.dev/alerts'
# group: (source language, the areas of its stops in index.json, where its notices come from)
GROUPS = {
    'tri': ('pl', ['gda', 'sop', 'gdy', 'wej', 'oth'], [('worker', WORKER)]),
    'waw': ('pl', ['waw'], [('rt', 'https://api.zbiorkom.live/api6-open/warsaw/gtfsRealtime/default/serviceAlerts')]),
    'ldz': ('pl', ['ldz'], [('rt', 'https://api.zbiorkom.live/api6-open/lodz/gtfsRealtime/default/serviceAlerts')]),
    'krk': ('pl', ['krk'], [('rt', 'https://gtfs.ztp.krakow.pl/ServiceAlerts_A.pb'), ('rt', 'https://gtfs.ztp.krakow.pl/ServiceAlerts_T.pb')]),
    'ber': ('de', ['ber'], [('json', 'alerts_ber.json')]),
    'prg': ('cs', ['prg'], [('json', 'alerts_prg.json')]),
    'poz': ('pl', ['poz'], [('json', 'alerts_poz.json')]),
    'byd': ('pl', ['byd'], [('json', 'alerts_byd.json')]),
    'ns': ('pl', ['ns', 'kmx', 'km'], [('json', 'alerts_ns.json')]),
    'wej': ('pl', ['gda', 'sop', 'gdy', 'wej', 'oth'], [('json', 'alerts_wej.json')]),
}


def get(u, raw=False):
    b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=300).read()
    return b if raw else b.decode('utf-8', 'replace')


# ---- the notices, as the page reads them (index.html: alertsJSON, alertsBVG, alertsRT with mdPlain, the worker's /alerts)
def md_plain(t):
    t = re.sub(r'~~[\s\S]*?~~', '', t or '')
    t = re.sub(r'\*\*|__|(^|\s)_(?=\S)|(?<=\S)_(?=\s|$)', lambda m: m.group(1) or '', t, flags=re.M)
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def pb_fields(b, i=0, end=None):
    """the fields of a protocol-buffer message: (number, wire type, value or (start, end))"""
    end = len(b) if end is None else end
    while i < end:
        k = 0; s = 0
        while True:
            x = b[i]; i += 1; k |= (x & 127) << s; s += 7
            if x < 128: break
        f, w = k >> 3, k & 7
        if w == 0:
            v = 0; s = 0
            while True:
                x = b[i]; i += 1; v |= (x & 127) << s; s += 7
                if x < 128: break
            yield f, w, v
        elif w == 2:
            n = 0; s = 0
            while True:
                x = b[i]; i += 1; n |= (x & 127) << s; s += 7
                if x < 128: break
            yield f, w, (i, i + n); i += n
        elif w == 1: i += 8
        elif w == 5: i += 4
        else: return


def rt_alerts(u):
    b = get(u, raw=True); out = []
    def tr(a, c):
        t = pl = ''
        for f, w, v in pb_fields(b, a, c):
            if f == 1 and w == 2:
                x = lg = ''
                for f3, w3, v3 in pb_fields(b, *v):
                    if w3 != 2: continue
                    if f3 == 1: x = b[v3[0]:v3[1]].decode('utf-8', 'replace')
                    elif f3 == 2: lg = b[v3[0]:v3[1]].decode('utf-8', 'replace')
                if not t or lg == 'pl':
                    if lg == 'pl': pl = x
                    t = x
        return pl or t
    for f, w, v in pb_fields(b):
        if f != 2 or w != 2: continue
        for f2, w2, v2 in pb_fields(b, *v):
            if f2 != 5 or w2 != 2: continue
            title = text = ''
            for f3, w3, v3 in pb_fields(b, *v2):
                if w3 != 2: continue
                if f3 == 10: title = tr(*v3)
                elif f3 == 11: text = md_plain(tr(*v3))
            if not title or re.match(r'^Ogólny tekst|^Komunikat$', title, re.I):
                t = text.split('\n')[0]; title = t[:137] + '…' if len(t) > 140 else t
                if title == text: text = ''
            if title: out.append((title, text))
    return out


def notices(data, src):
    res = []
    for kind, u in src:
        try:
            if kind == 'json': res += [(a.get('title') or '', a.get('text') or '') for a in json.load(open(os.path.join(data, u), encoding='utf-8')).get('alerts', [])]
            elif kind == 'worker': res += [(a.get('title') or '', a.get('text') or '') for a in json.loads(get(u))]
            else: res += rt_alerts(u)
        except Exception as e:
            print('tłumaczenia: %s – brak (%s)' % (u, e))
    return res


# ---- the lines the page looks up (index.html: mtStrs, alNorm, AL_LIST_RE)
AL_LIST_RE = re.compile(r'^(.*?\b(?:zawiesza się obsługę|zawieszone zostaje funkcjonowanie|zawieszona zostaje obsługa|wyłącza się z obsługi|nieczynne będą|'
                        r'nie będą obsługiwane|nie będą obsługiwane przez autobusy|nie będą obsługiwane przez tramwaje)\s+przystank[^\W\d_]*)\s*:?\s*(.+?)\.?\s*$', re.I)
def al_norm(t): return re.sub(r'[\s  ]+', ' ', unicodedata.normalize('NFC', t or '')).strip()


def strs(t):
    out = []
    for l in (t or '').split('\n'):
        body = re.sub(r'^\s*(?:•\s*)?', '', l)
        if not re.search(r'[A-Za-zÀ-ž]{3}', body): continue
        hd = re.match(r'^\[(.+)\]$', body); out.append(hd.group(1) if hd else body)
        m = AL_LIST_RE.match(al_norm(l))
        if m: out.append(m.group(1))
    return out


# ---- translation
class Engine:
    def __init__(self):
        import ctranslate2
        from argostranslate.tokenizer import BPETokenizer, SentencePieceTokenizer   # (the package's tokenizers only: no stanza, no torch)
        self.ct2, self.BPE, self.SP, self.m = ctranslate2, BPETokenizer, SentencePieceTokenizer, {}

    def model(self, pair):
        if pair not in self.m:
            name = MODELS[pair]; d = os.path.join(MODEL_DIR, name)
            if not os.path.exists(os.path.join(d, 'model', 'model.bin')):
                os.makedirs(MODEL_DIR, exist_ok=True); z = os.path.join(MODEL_DIR, name + '.zip')
                with open(z, 'wb') as o: o.write(get('https://argos-net.com/v1/translate-%s.argosmodel' % name, raw=True))
                with zipfile.ZipFile(z) as f:
                    for n in f.namelist():   # (the archive's folder dropped: <name>/model/…)
                        p = n.split('/', 1)[1] if '/' in n else ''
                        if not p or n.endswith('/'): continue
                        os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
                        with open(os.path.join(d, p), 'wb') as o: o.write(f.read(n))
                os.remove(z)
            sp = os.path.join(d, 'sentencepiece.model')   # (the Czech models: BPE with Moses' tokenizer instead)
            tok = self.SP(sp) if os.path.exists(sp) else self.BPE(os.path.join(d, 'bpe.model'), pair[0], pair[1])
            self.m[pair] = (self.ct2.Translator(os.path.join(d, 'model'), device='cpu', inter_threads=os.cpu_count() or 2), tok)
        return self.m[pair]

    def run(self, pair, texts):
        if not texts: return []
        t, sp = self.model(pair)
        r = t.translate_batch([sp.encode(x) for x in texts], beam_size=3, max_batch_size=24, max_decoding_length=512)
        return [re.sub(r'\s+', ' ', sp.decode(x.hypotheses[0]).replace('▁', ' ')).strip() for x in r]


ABBR = re.compile(r'(?:^|[\s(])(?:ul|al|Al|Ul|pl|Pl|os|Os|godz|ks|św|im|nr|ok|tj|in|r|dn|tzw|ww|pn|pd|wsch|zach|str|Str|St|Dw|Bhf|Nr|č|ul|tř|nám|sídl|Hbf|S|U)\.$')
def sentences(x):
    """a line in sentences (a model translates a sentence at a time best); not after an abbreviation ("ul. Długa")"""
    out, last = [], 0
    for m in re.finditer(r'[.!?](?=\s+["„(]?[A-ZÀ-Ž0-9])', x):
        if ABBR.search(x[:m.end()]) or re.search(r'\d\.$', x[:m.end()]): continue
        out.append(x[last:m.end()].strip()); last = m.end()
    out.append(x[last:].strip())
    return [s for s in out if s]


def guard(x, names_re):
    """the stop names, links and short bold names set aside as ZQ1, ZQ2…"""
    keep = []
    def put(v): keep.append(v); return 'ZQ%d' % len(keep)
    x = re.sub(r'\[[^\]\n]+\]\(https?://[^)\s]+\)', lambda m: put(m.group(0)), x)
    # (bold: a short bold span set aside and translated by itself, "**Ersatzverkehr**" → "**Replacement service**" – a stop name or a
    # number in it kept as it is, "**302**", "**Přezletice,Kocanda**"; a longer bold phrase translated without its marks: the models
    # break "**" apart)
    def bold(m):
        t = m.group(1)
        if len(t.split()) > 3 or len(t) > 40: return t
        if not re.search(r'[^\W\d_]{3}', t) or (names_re and names_re.fullmatch(t)) or re.search(r'\d|\w,\w', t): return put('**%s**' % t)   # ("Přezletice,Kocanda": PID's names of stops beyond Prague)
        return put(('B', t))
    x = re.sub(r'\*\*\s*(.+?)\s*\*\*', bold, x)
    if names_re: x = names_re.sub(lambda m: put(m.group(0)), x)
    return x, keep


def tidy(y):
    """the models' spacing put right: "115 , 183" → "115, 183", "( x )" → "(x)", "** x**" → "**x**" """
    y = re.sub(r'\s+([,.;:!?)\]])', r'\1', y); y = re.sub(r'([(\[„])\s+', r'\1', y)
    y = re.sub(r'\*\*\s*(.+?)\s*\*\*', r'**\1**', y)
    y = re.sub(r'\b([SUP]) \+ ([SUR])\b', r'\1+\2', y); y = re.sub(r'(?<=[^\W\d_.]|\.) / (?=[^\W\d_])', '/', y)   # ("S+U", "P+R", "Mollstr./Prenzlauer Allee")
    return re.sub(r'\s{2,}', ' ', y).strip()


def unguard(y, keep):
    for i in range(len(keep), 0, -1):
        if y.count('ZQ%d' % i) != 1: return None
        y = y.replace('ZQ%d' % i, keep[i - 1])
    return None if re.search(r'ZQ\d', y) else y


def names_re_of(data, areas):
    try: st = json.load(open(os.path.join(data, 'index.json'), encoding='utf-8'))['stops']
    except Exception: return None
    A = set(areas); N = {v[0] for v in st.values() if v[4] in A and v[0] and len(v[0]) >= 4}
    # (a name of several words anywhere; a one-word name only inside a sentence: "Dworzec" opening a sentence is a word)
    alt = lambda L: '|'.join(re.escape(n) for n in sorted(L, key=len, reverse=True))
    M = [n for n in N if ' ' in n]; S = [n for n in N if ' ' not in n]
    parts = ([r'(?<![^\W_])(?:%s)(?![^\W_])' % alt(M)] if M else []) + ([r'(?:(?<=[^\s.!?:] )|(?<=[(„"]))(?:%s)(?![^\W_])' % alt(S)] if S else [])
    return re.compile('|'.join(parts)) if parts else None


def translate_lines(eng, src, dsts, lines, names_re):
    """{dst: {line: translation}} for the lines given; through English"""
    G = {x: guard(x, names_re) for x in lines}
    sent = {x: sentences(G[x][0]) for x in lines}
    bolds = {k[1] for x in lines for k in G[x][1] if isinstance(k, tuple)}
    uniq = sorted({s for v in sent.values() for s in v} | bolds)
    en = dict(zip(uniq, eng.run((src, 'en'), uniq))) if src != 'en' else {s: s for s in uniq}
    res = {}
    for d in dsts:
        if d == 'en': tgt = en
        elif d == src: continue
        else:
            u2 = sorted(set(en.values())); tgt0 = dict(zip(u2, eng.run(('en', d), u2))); tgt = {s: tgt0[en[s]] for s in uniq}
        out = {}
        for x in lines:
            keep = [('**%s**' % tgt[k[1]].strip(' .')) if isinstance(k, tuple) else k for k in G[x][1]]
            y = unguard(' '.join(tgt[s] for s in sent[x]), keep)
            if y: out[x] = y
        res[d] = out
    return res


def main(data):
    eng = None; os.makedirs(os.path.join(data, 'tl'), exist_ok=True)
    for g, (src, areas, sources) in GROUPS.items():
        lines = sorted({s for t, x in notices(data, sources) for s in strs(t) + strs(x)})
        dsts = [d for d in LANGS if d != src]
        old = {}
        for d in dsts:
            try: old[d] = json.load(open(os.path.join(data, 'tl', '%s_%s.json' % (g, d)), encoding='utf-8')).get('m', {})
            except Exception: old[d] = {}
        need = [x for x in lines if any(x not in old[d] for d in dsts)]
        new = {d: {} for d in dsts}
        if need:
            if eng is None: eng = Engine()
            new = translate_lines(eng, src, dsts, need, names_re_of(data, areas))
        for d in dsts:
            m = {x: tidy(new[d].get(x) or old[d].get(x)) for x in lines if new[d].get(x) or old[d].get(x)}
            p = os.path.join(data, 'tl', '%s_%s.json' % (g, d))
            if m != old[d] or not os.path.exists(p):
                json.dump({'s': src, 'd': d, 'm': m}, open(p, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        print('tłumaczenia %s: %d linii, %d nowych' % (g, len(lines), len(need)))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
