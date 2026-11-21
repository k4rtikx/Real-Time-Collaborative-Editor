import os, re, sys

root = r'c:\code\Real-Time-Collaborative-Editor'
template_dirs = [
    os.path.join(root, 'frontend', 'templates'),
    os.path.join(root, 'documents', 'templates'),
]

# Collect all url names AND their namespaces from urls.py files
url_names = set()          # bare names like 'login'
namespaced_names = set()   # namespaced like 'accounts:login'

for dirpath, _, files in os.walk(root):
    if 'venv' in dirpath or '__pycache__' in dirpath:
        continue
    for fn in files:
        if fn != 'urls.py':
            continue
        path = os.path.join(dirpath, fn)
        with open(path, encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Extract app_name
        ns_match = re.search(r'app_name\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        namespace = ns_match.group(1) if ns_match else None

        for m in re.finditer(r"name=['\"]([^'\"]+)['\"]", content):
            name = m.group(1)
            url_names.add(name)
            if namespace:
                namespaced_names.add(f"{namespace}:{name}")

all_defined = url_names | namespaced_names

# Also add names from root urls.py without namespace
all_defined.add('health_check')
all_defined.add('home')
all_defined.add('homepage')
all_defined.add('room')

# Collect url refs from templates
template_refs = set()
for tdir in template_dirs:
    for dirpath, _, files in os.walk(tdir):
        for fn in files:
            if not fn.endswith('.html'):
                continue
            with open(os.path.join(dirpath, fn), encoding='utf-8', errors='replace') as f:
                content = f.read()
            for m in re.finditer(r"""{%\s*url\s+['"]([^'"]+)['"]""", content):
                template_refs.add(m.group(1))

missing = template_refs - all_defined
if missing:
    print('MISSING URL names (in template but not defined):', sorted(missing))
    sys.exit(1)
else:
    print(f'OK: All {len(template_refs)} template URL references are defined.')
    print('References found:', sorted(template_refs))
