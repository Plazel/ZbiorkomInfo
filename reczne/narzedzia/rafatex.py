"""RAFATEX timetables (rafatex.pl, PDF): Szczawnik – Muszyna – Krynica-Zdrój – Nowy Sącz, both ways.
Usage: python3 rafatex.py rafatex-krynica-ns.pdf rafatex-ns-krynica.pdf -> prints JSON trips [{days, dir, st: [[stop name, 'HH:MM']]}]"""
import json, re, sys, collections
import pdfplumber

TIME = re.compile(r'^\d{1,2}:\d{2}$')
CODE = re.compile(r'^[DS67,+]+$')


def days_of(code):
    """D every weekday: school days (w) and school-free weekdays (f); S school days only (w); 6 Saturdays, 7 Sundays and
    holidays (+: also the main holidays)"""
    d = ''
    if 'D' in code or 'S' in code: d += 'w'
    if 'D' in code: d += 'f'
    if '6' in code: d += 's'
    if '7' in code: d += 'h'
    return d


def parse(path):
    trips = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            for w in words: w['text'] = re.sub(r'\(cid:(\d+)\)', lambda m: chr(int(m.group(1))), w['text']).strip()
            # a stop name run together with the first time after it ("Batorego12:18"): split them
            for w in list(words):
                m = re.match(r'^(.*\D)(\d{1,2}:\d{2})$', w['text'])
                if m:
                    words.append(dict(w, text=m.group(2), x0=w['x1'] - 17)); w['text'] = m.group(1); w['x1'] = w['x1'] - 18
            lines = []   # words grouped into rows (tops within 4 pt of each other)
            for w in sorted(words, key=lambda w: w['top']):
                if lines and w['top'] - lines[-1][0]['top'] < 4: lines[-1].append(w)
                else: lines.append([w])
            lines = [sorted(v, key=lambda w: w['x0']) for v in lines]
            block = None
            for ws in lines:
                if ws and ws[0]['text'].startswith('Przystanki'):
                    cols = [((w['x0'] + w['x1']) / 2, w['text']) for w in ws[1:] if CODE.match(w['text'])]
                    block = {'cols': cols, 'stops': []}; trips_b = [[] for _ in cols]
                    block['trips'] = trips_b; trips.append(block); continue
                if not block: continue
                times = [w for w in ws if TIME.match(w['text'])]
                if not times: continue
                name = ' '.join(w['text'] for w in ws if not TIME.match(w['text']) and w['x1'] < times[0]['x0'])
                for w in times:
                    c = (w['x0'] + w['x1']) / 2
                    k = min(range(len(block['cols'])), key=lambda i: abs(block['cols'][i][0] - c))
                    h, m = w['text'].split(':')
                    block['trips'][k].append([name, '%02d:%s' % (int(h), m)])
    out = []
    for b in trips:
        for (x, code), st in zip(b['cols'], b['trips']):
            if len(st) >= 2: out.append({'days': days_of(code), 'code': code, 'st': st})
    return out


if __name__ == '__main__':
    res = {}
    for p in sys.argv[1:]: res[p] = parse(p)
    json.dump(res, sys.stdout, ensure_ascii=False)
