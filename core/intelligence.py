"""Repository Intelligence layer.

Analyze RepositoryIndex, DependencyGraph, RelationshipGraph and Query Engine
and produce repository-level insights useful to AI agents.

All detectors return structured dictionaries with at least:
  - value: detection result (string or structured)
  - confidence: float (0.0-1.0)
  - evidence: list of strings describing why the detector made the judgement

Detectors are conservative and explain when information is incomplete.
"""
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import os

from core.indexer import RepositoryIndex
from core.graph import DependencyGraph
from core.relationship import RelationshipGraph
from core import queries


def _file_set(index: RepositoryIndex) -> set:
    return set(f.path for f in (index.files or []))


def detect_architecture(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """Detect high-level architecture style (MVC, MVVM, Layered, Component-based, Monolith, Unknown).

    Returns {architecture: str, confidence: float, evidence: [str,...]}
    """
    files = _file_set(index)
    evidence: List[str] = []
    scores = defaultdict(float)

    # Heuristics
    # Component-based: many UI components (React/Vue/.vue files or many capitalized functions)
    component_hits = []
    for f in index.files:
        p = f.path.lower()
        if p.endswith(".vue") or p.endswith(".jsx") or p.endswith(".tsx"):
            component_hits.append(f.path)
        # functions starting with capital letter likely components
        for name in (f.functions or []):
            if name and name[0].isupper():
                component_hits.append(f.path)
                break
    if component_hits:
        scores["Component-based"] += min(0.6, 0.15 * len(set(component_hits)))
        evidence.append(f"Detected possible component files: {len(set(component_hits))} files")

    # MVC: presence of 'models', 'views', 'controllers' directories or Django/Flask-like structure
    mvc_dirs = [d for d in files if os.path.normpath("/models/") in os.path.normpath(d).replace('\\\\','/') or "/models/" in d]
    controllers = [d for d in files if "/controllers/" in d or "controller" in os.path.basename(d).lower()]
    templates = [d for d in files if "/templates/" in d or d.endswith(".html")]
    if mvc_dirs or controllers:
        scores["MVC"] += 0.6
        evidence.append(f"Found model/controller patterns: models({len(mvc_dirs)}), controllers({len(controllers)})")
    if templates:
        scores["MVC"] += 0.2
        evidence.append(f"Found template-like files (.html or templates/): {len(templates)}")

    # MVVM: presence of 'viewmodel' naming or directories or many two-way bindings in UI (data- attributes)
    vm_hits = [f.path for f in index.files if "/viewmodel" in f.path.lower() or "viewmodel" in f.path.lower()]
    data_attrs_count = sum(len(f.get("data_attributes") or []) if isinstance(f, dict) else 0 for f in [])
    # limited detector; look for 'viewmodel' names
    if vm_hits:
        scores["MVVM"] += 0.7
        evidence.append(f"Found viewmodel-like files: {len(vm_hits)}")

    # Layered: directory patterns 'services', 'data', 'domain', 'api'
    layer_patterns = ["/services/", "/service/", "/data/", "/domain/", "/api/", "/core/"]
    layer_hits = set()
    for p in files:
        for pat in layer_patterns:
            if pat in p.lower():
                layer_hits.add(p)
    if layer_hits:
        scores["Layered"] += min(0.6, 0.1 * len(layer_hits))
        evidence.append(f"Files in layer-like directories: {len(layer_hits)}")

    # Monolith: few directories, high coupling (many import edges among many files)
    node_count = len(graph.imports)
    edge_count = sum(len(v) for v in graph.imports.values())
    coupling = 0.0
    if node_count:
        coupling = edge_count / node_count
    if node_count > 0 and coupling > 3.0:
        scores["Monolith"] += 0.6
        evidence.append(f"High coupling: {edge_count} import edges across {node_count} nodes (avg {coupling:.1f})")

    # Unknown if nothing decisive
    if not scores:
        return {"architecture": "Unknown", "confidence": 0.0, "evidence": ["No decisive patterns detected."]}

    # pick best score
    best = max(scores.items(), key=lambda kv: kv[1])
    total = sum(scores.values())
    confidence = min(1.0, best[1])

    return {"architecture": best[0], "confidence": float(confidence), "evidence": evidence}


def detect_frameworks(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """Detect frameworks present in the repository.

    Returns mapping framework -> {confidence, evidence:list}
    """
    files = _file_set(index)
    results = {}

    # helper to record
    def note(name, conf, ev):
        results[name] = {"confidence": float(conf), "evidence": ev}

    # collect filenames and simple name checks
    filenames = files
    lower = {p.lower() for p in filenames}

    # package.json presence indicates Node ecosystem
    if any(os.path.basename(p).lower() == "package.json" for p in filenames):
        note("Node", 0.7, ["package.json present"]) 

    # React: look for 'react' imports or JSX/TSX files
    react_evidence = []
    for f in index.files:
        if f.path.endswith(('.jsx', '.tsx')):
            react_evidence.append(f.path)
        # scan imports for 'react'
        for imp in getattr(f, 'imports', []) or []:
            if isinstance(imp, str) and 'react' in imp.lower():
                react_evidence.append(f.path)
    if react_evidence:
        note('React', 0.9, react_evidence)

    # Vue: .vue files or imports of 'vue'
    vue_evidence = [f.path for f in index.files if f.path.endswith('.vue')]
    for f in index.files:
        for imp in getattr(f, 'imports', []) or []:
            if isinstance(imp, str) and 'vue' in imp.lower():
                vue_evidence.append(f.path)
    if vue_evidence:
        note('Vue', 0.85, list(set(vue_evidence)))

    # Next.js: presence of 'next' in package.json or 'pages/' directory or next.config.js
    next_evidence = []
    if any(os.path.basename(p).lower() == 'next.config.js' for p in filenames):
        next_evidence.append('next.config.js')
    if any('/pages/' in p.lower() or p.lower().startswith('pages/') for p in filenames):
        next_evidence.append('pages/ directory')
    # package.json check: look for file presence but not content here
    if any(os.path.basename(p).lower() == 'package.json' for p in filenames):
        # cannot read package.json content here without parsing files; still indicate low-confidence
        next_evidence.append('package.json present (inspect dependencies for "next")')
    if next_evidence:
        note('Next.js', 0.6, next_evidence)

    # Express: imports of 'express' or usage of express.Router
    express_evidence = []
    for f in index.files:
        for imp in getattr(f, 'imports', []) or []:
            if isinstance(imp, str) and 'express' in imp.lower():
                express_evidence.append(f.path)
        # look for call patterns in calls metadata
        for call in getattr(f, 'calls', []) or []:
            callee = call.get('callee') if isinstance(call, dict) else None
            if callee and (callee.endswith('.get') or callee.endswith('.post') or callee.endswith('.use')):
                express_evidence.append(f.path)
    if express_evidence:
        note('Express', 0.85, list(set(express_evidence)))

    # Flask / FastAPI / Django: Python frameworks
    flask_evidence = []
    fastapi_evidence = []
    django_evidence = []
    for f in index.files:
        if f.path.endswith('.py'):
            for imp in getattr(f, 'imports', []) or []:
                if isinstance(imp, str):
                    if 'flask' in imp.lower():
                        flask_evidence.append(f.path)
                    if 'fastapi' in imp.lower():
                        fastapi_evidence.append(f.path)
                    if 'django' in imp.lower():
                        django_evidence.append(f.path)
            # decorators metadata may show route decorators - check those via queries.find_references? use f.decorators
            # indexer stores decorators in f.decorators
            if getattr(f, 'decorators', None):
                decs = f.decorators
                for d in decs:
                    for name in d.get('decorators', []) if isinstance(d, dict) else []:
                        if '.route' in name or 'flask' in name:
                            flask_evidence.append(f.path)
                        if 'app.get' in name or 'fastapi' in name:
                            fastapi_evidence.append(f.path)
    if flask_evidence:
        note('Flask', 0.9, list(set(flask_evidence)))
    if fastapi_evidence:
        note('FastAPI', 0.9, list(set(fastapi_evidence)))
    if django_evidence:
        note('Django', 0.95, list(set(django_evidence)))

    # Static Website: many HTML files and few server-side files
    html_count = sum(1 for f in index.files if f.path.endswith('.html'))
    js_count = sum(1 for f in index.files if f.path.endswith(('.js', '.jsx', '.ts', '.tsx')))
    py_count = sum(1 for f in index.files if f.path.endswith('.py'))
    if html_count > 0 and js_count == 0 and py_count == 0:
        note('Static Website', 0.95, [f"{html_count} HTML files and no JS/Python detected"]) 

    # Node generic
    if any(p.endswith('.js') for p in files):
        if 'Node' not in results:
            note('Node', 0.6, ['JS files present'])

    return results


def detect_routes(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> List[Dict]:
    """Detect web routes / endpoints in repository.

    Returns list of {method, path, handler, source_file, confidence, evidence}
    """
    routes = []

    for f in index.files:
        # JavaScript/Node - look for express-like calls
        if f.path.endswith(('.js', '.ts')):
            for call in (f.calls or []):
                if not isinstance(call, dict):
                    continue
                method = None
                callee = call.get('callee')
                method_name = call.get('method_name') or call.get('callee')
                obj = call.get('object_name')
                # callee may be 'app.get' or method_name 'get'
                if isinstance(callee, str) and ('.get' in callee or '.post' in callee or '.put' in callee or '.delete' in callee):
                    # extract method from callee
                    if '.get' in callee:
                        method = 'GET'
                    elif '.post' in callee:
                        method = 'POST'
                    elif '.put' in callee:
                        method = 'PUT'
                    elif '.delete' in callee:
                        method = 'DELETE'
                    handler = call.get('caller')
                    routes.append({
                        'method': method,
                        'path': None,
                        'handler': handler,
                        'source_file': f.path,
                        'confidence': 0.5,
                        'evidence': [f"Detected call callee={callee} in {f.path}"]
                    })
                elif isinstance(method_name, str) and method_name.lower() in {'get','post','put','delete','use'}:
                    handler = call.get('caller')
                    routes.append({
                        'method': method_name.upper(),
                        'path': None,
                        'handler': handler,
                        'source_file': f.path,
                        'confidence': 0.4,
                        'evidence': [f"Detected method name={method_name} in call metadata in {f.path}"]
                    })
        # Python - Flask / FastAPI
        if f.path.endswith('.py'):
            # decorators stored at metadata['decorators'] via parser
            decs = getattr(f, 'decorators', None)
            if decs:
                for entry in decs:
                    func = entry.get('function')
                    for dec in entry.get('decorators', []) or []:
                        if isinstance(dec, str) and ('.route' in dec or '.get' in dec or '.post' in dec or 'app.route' in dec or 'fastapi' in dec or 'router.' in dec):
                            method = None
                            if '.get' in dec:
                                method = 'GET'
                            elif '.post' in dec:
                                method = 'POST'
                            elif '.put' in dec:
                                method = 'PUT'
                            elif '.delete' in dec:
                                method = 'DELETE'
                            routes.append({
                                'method': method,
                                'path': None,  # parser does not capture decorator args
                                'handler': func,
                                'source_file': f.path,
                                'confidence': 0.6,
                                'evidence': [f"Decorator {dec} on function {func} in {f.path}"]
                            })
    return routes


def detect_components(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> List[Dict]:
    """Detect components (React, Vue, reusable HTML components).

    Returns list of {name, file, kind, confidence, evidence}
    """
    components = []

    # React/Vue components via filenames and symbol names
    for f in index.files:
        # Vue single-file components
        if f.path.endswith('.vue'):
            components.append({
                'name': os.path.splitext(os.path.basename(f.path))[0],
                'file': f.path,
                'kind': 'vue',
                'confidence': 0.9,
                'evidence': [f".vue file: {f.path}"]
            })
        # React components hinted by JSX/TSX extension or capitalized function/class names
        if f.path.endswith(('.jsx', '.tsx')):
            # pick exported functions/classes that are capitalized
            for name in (f.functions or []) + (f.classes or []):
                if name and name[0].isupper():
                    components.append({
                        'name': name,
                        'file': f.path,
                        'kind': 'react',
                        'confidence': 0.85,
                        'evidence': [f"Capitalized symbol {name} in {f.path}"]
                    })
        # HTML custom elements (dash in tag name)
        for el in (f.elements or []):
            tag = el.get('tag')
            if tag and '-' in tag:
                comp_name = tag
                components.append({
                    'name': comp_name,
                    'file': f.path,
                    'kind': 'web-component',
                    'confidence': 0.7,
                    'evidence': [f"Custom element <{tag}> found in {f.path}"]
                })
        # JS files: capitalized functions/classes
        if f.path.endswith(('.js', '.ts')):
            for name in (f.functions or []) + (f.classes or []):
                if name and name[0].isupper():
                    components.append({
                        'name': name,
                        'file': f.path,
                        'kind': 'component',
                        'confidence': 0.6,
                        'evidence': [f"Capitalized symbol {name} in {f.path}"]
                    })

    # deduplicate by (name,file)
    seen = set()
    unique = []
    for c in components:
        key = (c['name'], c['file'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    return unique


def detect_entry_points(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> List[Dict]:
    """Detect likely entry points (main.py, app.py, server.js, index.js, main.ts, index.html).

    Returns list of {file, confidence, evidence}
    """
    files = _file_set(index)
    candidates = [
        ('main.py', 0.9),
        ('app.py', 0.85),
        ('server.js', 0.9),
        ('index.js', 0.8),
        ('main.ts', 0.8),
        ('index.html', 0.8),
        ('src/main.ts', 0.8),
    ]
    results = []
    for name, base_conf in candidates:
        matches = [p for p in files if p.lower().endswith('/' + name) or p.lower().endswith(name)]
        for m in matches:
            # boost confidence if file imports many modules or constructs app/server
            conf = base_conf
            ev = [f"Found file {m}"]
            # check for heavy imports
            idx_file = next((f for f in index.files if f.path == m), None)
            if idx_file and len(idx_file.imports) > 3:
                conf = min(1.0, conf + 0.1)
                ev.append(f"Imports >3 modules ({len(idx_file.imports)})")
            results.append({'file': m, 'confidence': conf, 'evidence': ev})
    return results


def detect_configuration(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> List[Dict]:
    """Detect configuration files and their purposes.

    Returns list of {path, type, purpose, confidence, evidence}
    """
    files = _file_set(index)
    results = []

    def add_if_exists(pattern, ftype, purpose, conf=0.9):
        for p in files:
            b = os.path.basename(p).lower()
            if b == pattern or p.lower().endswith('/' + pattern):
                results.append({'path': p, 'type': ftype, 'purpose': purpose, 'confidence': conf, 'evidence': [f"Found {pattern}"]})

    add_if_exists('package.json', 'package_manifest', 'Node/npm project manifest', 0.95)
    add_if_exists('requirements.txt', 'requirements', 'Python dependencies (pip)', 0.95)
    add_if_exists('pyproject.toml', 'pyproject', 'Python project config (PEP 517/518)', 0.95)
    add_if_exists('tsconfig.json', 'tsconfig', 'TypeScript compiler config', 0.9)
    # vite/webpack/rollup
    for p in files:
        nb = os.path.basename(p).lower()
        if nb.startswith('vite.config'):
            results.append({'path': p, 'type': 'vite_config', 'purpose': 'Vite build tool config', 'confidence': 0.95, 'evidence': [f"Found {nb}"]})
        if nb.startswith('webpack.config'):
            results.append({'path': p, 'type': 'webpack_config', 'purpose': 'Webpack build tool config', 'confidence': 0.95, 'evidence': [f"Found {nb}"]})
        if nb == 'dockerfile' or nb.startswith('dockerfile.'):
            results.append({'path': p, 'type': 'dockerfile', 'purpose': 'Docker image build', 'confidence': 0.95, 'evidence': [f"Found {nb}"]})
        if nb.startswith('docker-compose'):
            results.append({'path': p, 'type': 'docker_compose', 'purpose': 'Docker compose deployment', 'confidence': 0.95, 'evidence': [f"Found {nb}"]})
        if nb.startswith('.env'):
            results.append({'path': p, 'type': 'env', 'purpose': 'Environment variables file', 'confidence': 0.9, 'evidence': [f"Found {nb}"]})
        if nb == 'nginx.conf' or 'nginx' in p.lower():
            results.append({'path': p, 'type': 'nginx', 'purpose': 'nginx configuration', 'confidence': 0.9, 'evidence': [f"Found {nb}"]})
        if '.github/workflows/' in p.replace('\\', '/'):
            results.append({'path': p, 'type': 'github_actions', 'purpose': 'CI/CD workflow', 'confidence': 0.9, 'evidence': [f"Found workflow {p}"]})

    # dedupe by path
    seen = set()
    unique = []
    for r in results:
        if r['path'] in seen:
            continue
        seen.add(r['path'])
        unique.append(r)

    return unique


def detect_build_system(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """Detect build system/tooling (npm, pnpm, yarn, Vite, Webpack, Rollup, Maven, Gradle, Cargo).

    Returns mapping name -> {confidence, evidence}
    """
    files = _file_set(index)
    results = {}

    # package-lock.json -> npm, yarn.lock -> yarn, pnpm-lock.yaml -> pnpm
    for p in files:
        b = os.path.basename(p).lower()
        if b == 'package-lock.json':
            results['npm'] = {'confidence': 0.95, 'evidence': [p]}
        if b == 'yarn.lock':
            results['yarn'] = {'confidence': 0.95, 'evidence': [p]}
        if b == 'pnpm-lock.yaml' or b == 'pnpm-lock.yaml':
            results['pnpm'] = {'confidence': 0.95, 'evidence': [p]}
        if b.startswith('vite.config'):
            results['Vite'] = {'confidence': 0.9, 'evidence': [p]}
        if b.startswith('webpack.config'):
            results['Webpack'] = {'confidence': 0.9, 'evidence': [p]}
        if b.startswith('rollup.config'):
            results['Rollup'] = {'confidence': 0.9, 'evidence': [p]}
        if b == 'pom.xml':
            results['Maven'] = {'confidence': 0.95, 'evidence': [p]}
        if b == 'build.gradle' or b == 'build.gradle.kts':
            results['Gradle'] = {'confidence': 0.95, 'evidence': [p]}
        if b == 'cargo.toml' or b == 'cargo.lock' or b == 'cargo.toml':
            results['Cargo'] = {'confidence': 0.95, 'evidence': [p]}

    return results


def detect_package_manager(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """Detect package managers used in the repository (npm, pnpm, yarn, pip, pipenv, poetry).

    Returns mapping manager -> {confidence, evidence}
    """
    files = _file_set(index)
    results = {}
    for p in files:
        b = os.path.basename(p).lower()
        if b == 'package-lock.json':
            results['npm'] = {'confidence': 0.98, 'evidence': [p]}
        if b == 'yarn.lock':
            results['yarn'] = {'confidence': 0.98, 'evidence': [p]}
        if b == 'pnpm-lock.yaml':
            results['pnpm'] = {'confidence': 0.98, 'evidence': [p]}
        if b == 'requirements.txt':
            results['pip'] = {'confidence': 0.95, 'evidence': [p]}
        if b == 'poetry.lock' or b == 'pyproject.toml':
            results['poetry'] = {'confidence': 0.9, 'evidence': [p]}
        if b == 'pipfile' or b == 'pipfile.lock':
            results['pipenv'] = {'confidence': 0.9, 'evidence': [p]}
    return results


def detect_testing_framework(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """Detect testing frameworks (pytest, unittest, Jest, Vitest, Mocha, Cypress, Playwright).

    Returns mapping framework -> {confidence, evidence}
    """
    files = _file_set(index)
    results = {}
    lower = {p.lower() for p in files}

    # pytest: presence of pytest.ini, conftest.py, tests/ folder, test_*.py
    if any(os.path.basename(p).lower() == 'pytest.ini' for p in files) or any(p.endswith('conftest.py') for p in files) or any('/tests/' in p.lower() or p.lower().startswith('tests/') for p in files):
        results['pytest'] = {'confidence': 0.9, 'evidence': ['pytest.ini or tests/ or conftest.py present']}
    # unittest: presence of tests and no pytest markers is ambiguous; lower confidence
    if any(p.endswith('_test.py') or p.startswith('test_') for p in [os.path.basename(p) for p in files]):
        results.setdefault('unittest', {'confidence': 0.5, 'evidence': []})
        results['unittest']['evidence'].append('test_*.py found')
    # Jest / Vitest / Mocha: presence of jest.config.*, vitest.config.*, cypress, playwright
    if any('jest.config' in os.path.basename(p).lower() for p in files) or any(p.lower().endswith('.spec.js') or p.lower().endswith('.test.js') for p in files):
        results['Jest'] = {'confidence': 0.9, 'evidence': ['jest config or *.test.js/*.spec.js present']}
    if any('vitest.config' in os.path.basename(p).lower() for p in files):
        results['Vitest'] = {'confidence': 0.9, 'evidence': ['vitest config present']}
    if any('cypress' in p.lower() for p in files):
        results['Cypress'] = {'confidence': 0.9, 'evidence': ['cypress directory or files present']}
    if any('playwright' in p.lower() for p in files):
        results['Playwright'] = {'confidence': 0.9, 'evidence': ['playwright files present']}

    return results


def detect_deployment(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """Detect deployment platforms and primitives (Docker, Vercel, Netlify, Railway, Render, GitHub Pages, Nginx).

    Returns mapping platform -> {confidence, evidence}
    """
    files = _file_set(index)
    results = {}
    for p in files:
        b = os.path.basename(p).lower()
        if b == 'dockerfile' or b.startswith('dockerfile'):
            results['Docker'] = {'confidence': 0.95, 'evidence': [p]}
        if 'vercel.json' in b or 'vercel' in p.lower():
            results['Vercel'] = {'confidence': 0.9, 'evidence': [p]}
        if 'netlify' in b or 'netlify.toml' in b:
            results['Netlify'] = {'confidence': 0.9, 'evidence': [p]}
        if 'railway' in p.lower():
            results['Railway'] = {'confidence': 0.7, 'evidence': [p]}
        if 'render' in p.lower():
            results['Render'] = {'confidence': 0.7, 'evidence': [p]}
        if 'gh-pages' in p.lower() or 'github.io' in p.lower():
            results['GitHub Pages'] = {'confidence': 0.6, 'evidence': [p]}
        if 'nginx' in p.lower() or b == 'nginx.conf':
            results['Nginx'] = {'confidence': 0.9, 'evidence': [p]}
        if '.github/workflows' in p.replace('\\', '/'):
            # check for deploy-like jobs by filename or later inspection (best-effort)
            results.setdefault('GitHub Actions', {'confidence': 0.8, 'evidence': []})
            results['GitHub Actions']['evidence'].append(p)
    return results


def detect_project_structure(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
    max_items: int = 50,
) -> Dict[str, List[str]]:
    """Infer the high-level project structure by grouping files into common folders.

    Returns mapping of section -> list of example file paths.
    Sections: src, public, components, controllers, models, views, services, utils, tests, config
    """
    files = [f.path for f in (index.files or [])]
    lower = [p.lower() for p in files]

    def pick(patterns):
        matches = [p for p in files if any(p.lower().find(pat) != -1 for pat in patterns)]
        return sorted(matches)[:max_items]

    structure = {
        "src": pick(["/src/", "src/", "app/", "/app/"]),
        "public": pick(["/public/", "/static/", "/assets/", "/public_html/"]),
        "components": pick(["/components/", "/component/", ".jsx", ".tsx", ".vue"]),
        "controllers": pick(["/controllers/", "controller.", "/controller/"]),
        "models": pick(["/models/", "/model/"]),
        "views": pick(["/views/", "/templates/", ".html"]),
        "services": pick(["/services/", "/service/"]),
        "utils": pick(["/utils/", "util.", "/helpers/", "/helper/"]),
        "tests": pick(["/tests/", "/test/", "test_"]),
        "config": pick(["package.json", "pyproject.toml", "requirements.txt", "vite.config", "webpack.config", "Dockerfile", "docker-compose"]),
    }

    # also include counts/evidence
    evidence = {k: len(v) for k, v in structure.items()}
    return {"structure": structure, "counts": evidence}


def summarize_repository(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """Return a compact repository summary useful to seed prompts for the AI.

    Keys:
      language, framework, architecture, entry_points, major_features,
      test_framework, deployment, build, package_manager
    """
    # language: dominant language by file counts
    lang_counts = {}
    for f in index.files:
        lang = (f.language or "").lower()
        if not lang:
            continue
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    dominant_language = max(lang_counts.items(), key=lambda kv: kv[1])[0] if lang_counts else None

    frameworks = detect_frameworks(index, graph, relationships)
    framework = None
    framework_conf = 0.0
    framework_evidence = []
    if frameworks:
        # pick top-scoring framework
        sorted_fw = sorted(frameworks.items(), key=lambda kv: kv[1].get("confidence", 0.0), reverse=True)
        framework, meta = sorted_fw[0]
        framework_conf = meta.get("confidence", 0.0)
        framework_evidence = meta.get("evidence", [])

    arch = detect_architecture(index, graph, relationships)

    entry_points = detect_entry_points(index, graph, relationships)
    entry_files = [e.get('file') for e in entry_points]

    routes = detect_routes(index, graph, relationships)
    route_paths = [r.get('path') or r.get('handler') for r in routes]

    components = detect_components(index, graph, relationships)
    component_list = [c.get('name') for c in components]

    testing = detect_testing_framework(index, graph, relationships) or {}
    test_framework = None
    if testing:
        test_framework = max(testing.items(), key=lambda kv: kv[1].get('confidence', 0))[0]

    deployment = detect_deployment(index, graph, relationships) or {}
    deployment_top = None
    if deployment:
        deployment_top = max(deployment.items(), key=lambda kv: kv[1].get('confidence', 0))[0]

    buildsys = detect_build_system(index, graph, relationships) or {}
    build_top = None
    if buildsys:
        build_top = max(buildsys.items(), key=lambda kv: kv[1].get('confidence', 0))[0]

    pkg = detect_package_manager(index, graph, relationships) or {}
    pkg_top = None
    if pkg:
        pkg_top = max(pkg.items(), key=lambda kv: kv[1].get('confidence', 0))[0]

    # major features: heuristics based on filenames and directories
    tokens = [
        "auth", "login", "user", "dashboard", "admin", "profile", "blog", "post", "search", "checkout",
        "payment", "cart", "chat", "comment", "analytics", "report",
    ]
    feature_hits = defaultdict(int)
    for f in index.files:
        path = f.path.lower()
        for t in tokens:
            if t in path:
                feature_hits[t] += 1
    major_features = [k for k, v in sorted(feature_hits.items(), key=lambda kv: kv[1], reverse=True) if v > 0]

    profile = {
        "language": dominant_language,
        "framework": framework,
        "framework_confidence": framework_conf,
        "framework_evidence": framework_evidence,
        "architecture": arch.get('architecture') if isinstance(arch, dict) else None,
        "architecture_confidence": arch.get('confidence') if isinstance(arch, dict) else None,
        "entry_points": entry_files,
        "routes": route_paths,
        "components": component_list,
        "major_features": major_features,
        "test_framework": test_framework,
        "deployment": deployment_top,
        "build": build_top,
        "package_manager": pkg_top,
    }

    return profile


def build_repository_profile(
    index: RepositoryIndex,
    graph: DependencyGraph,
    relationships: RelationshipGraph,
) -> Dict:
    """High-level composite repository profile used to seed AI prompts.

    Returns a dictionary with structure:
      {
        "summary": {...},
        "structure": {...},
        "frameworks": {...},
        "routes": [...],
        "components": [...],
        "configuration": [...],
        "build_system": {...},
        "package_manager": {...},
        "testing": {...},
        "deployment": {...},
      }
    """
    summary = summarize_repository(index, graph, relationships)
    structure = detect_project_structure(index, graph, relationships)
    frameworks = detect_frameworks(index, graph, relationships)
    routes = detect_routes(index, graph, relationships)
    components = detect_components(index, graph, relationships)
    configuration = detect_configuration(index, graph, relationships)
    build_system = detect_build_system(index, graph, relationships)
    package_manager = detect_package_manager(index, graph, relationships)
    testing = detect_testing_framework(index, graph, relationships)
    deployment = detect_deployment(index, graph, relationships)

    profile = {
        "summary": summary,
        "structure": structure,
        "frameworks": frameworks,
        "routes": routes,
        "components": components,
        "configuration": configuration,
        "build_system": build_system,
        "package_manager": package_manager,
        "testing": testing,
        "deployment": deployment,
    }

    return profile

# End of intelligence module
