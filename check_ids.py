import re

with open('static/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

matches = re.findall(r'getElementById\(["\']([^"\']+)["\']\)', content)
print('IDs referenced in app.js:')
for m in sorted(set(matches)):
    print(' ', m)

with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

html_ids = re.findall(r'id=["\']([^"\']+)["\']', html)
print('\nIDs defined in index.html:')
for m in sorted(set(html_ids)):
    print(' ', m)

js_set = set(matches)
html_set = set(html_ids)
missing = js_set - html_set
print('\nIDs in JS but NOT in HTML (broken references):')
for m in sorted(missing):
    print(' ', m)
