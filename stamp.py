# The page's version: the time now into APP_BUILD in index.html and into version.json beside it (run before publishing);
# an open older page sees the newer number in version.json and updates itself.
import re, time, json
b = int(time.time())
p = 'index.html'; s = open(p, encoding='utf-8').read()
s, n = re.subn(r'const APP_BUILD=\d+;', f'const APP_BUILD={b};', s, count=1)
assert n == 1, 'APP_BUILD not found'
open(p, 'w', encoding='utf-8').write(s)
json.dump({'b': b}, open('version.json', 'w'))
print('APP_BUILD', b)
