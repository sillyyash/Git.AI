from dataclasses import dataclass
from typing import Dict, List

from core.indexer import RepositoryIndex


# -------------------------------------------------
# Repository Knowledge Graph
# -------------------------------------------------

@dataclass
class DependencyGraph:

    # File -> imports
    imports: Dict[str, List[str]]

    # Reverse imports
    reverse_imports: Dict[str, List[str]]

    # Symbol indexes
    functions: Dict[str, str]
    classes: Dict[str, str]

    selectors: Dict[str, str]
    ids: Dict[str, str]
    css_classes: Dict[str, str]
    variables: Dict[str, str]
    animations: Dict[str, str]
    media_queries: Dict[str, str]

    # HTML tag -> files
    elements: Dict[str, List[str]]


# -------------------------------------------------
# Build Graph
# -------------------------------------------------

def build_graph(index: RepositoryIndex) -> DependencyGraph:

    imports = {}
    reverse_imports = {}

    functions = {}
    classes = {}

    selectors = {}
    ids = {}
    css_classes = {}
    variables = {}
    animations = {}
    media_queries = {}

    elements = {}

    for file in index.files:

        imports[file.path] = file.imports

        # ------------------------
        # Reverse imports
        # ------------------------

        for module in file.imports:

            reverse_imports.setdefault(module, []).append(file.path)

        # ------------------------
        # Functions
        # ------------------------

        for function in file.functions:

            functions[function] = file.path

        # ------------------------
        # Classes
        # ------------------------

        for cls in file.classes:

            classes[cls] = file.path

        # ------------------------
        # CSS Selectors
        # ------------------------

        for selector in getattr(file, "selectors", []):

            selectors[selector] = file.path

        # ------------------------
        # HTML IDs
        # ------------------------

        for html_id in getattr(file, "ids", []):

            ids[html_id] = file.path

        # ------------------------
        # CSS Classes
        # ------------------------

        for css_class in getattr(file, "css_classes", []):

            css_classes[css_class] = file.path

        # ------------------------
        # Variables
        # ------------------------

        for variable in getattr(file, "variables", []):

            variables[variable] = file.path

        # ------------------------
        # Animations
        # ------------------------

        for animation in getattr(file, "animations", []):

            animations[animation] = file.path

        # ------------------------
        # Media Queries
        # ------------------------

        for media in getattr(file, "media_queries", []):

            media_queries[media] = file.path

        # ------------------------
        # HTML Elements
        # ------------------------

        for element in getattr(file, "elements", []):

            tag = element.get("tag")

            if not tag:
                  continue

            files = elements.setdefault(tag, [])

            if file.path not in files:
                files.append(file.path)

    return DependencyGraph(

        imports=imports,
        reverse_imports=reverse_imports,

        functions=functions,
        classes=classes,

        selectors=selectors,
        ids=ids,
        css_classes=css_classes,
        variables=variables,
        animations=animations,
        media_queries=media_queries,

        elements=elements,
    )


# -------------------------------------------------
# Query Helpers
# -------------------------------------------------

def find_function(graph: DependencyGraph, name: str):
    return graph.functions.get(name)


def find_class(graph: DependencyGraph, name: str):
    return graph.classes.get(name)


def find_selector(graph: DependencyGraph, selector: str):
    return graph.selectors.get(selector)


def find_id(graph: DependencyGraph, html_id: str):
    return graph.ids.get(html_id)


def find_css_class(graph: DependencyGraph, css_class: str):
    return graph.css_classes.get(css_class)


def find_variable(graph: DependencyGraph, variable: str):
    return graph.variables.get(variable)


def find_animation(graph: DependencyGraph, animation: str):
    return graph.animations.get(animation)


def find_media_query(graph: DependencyGraph, media: str):
    return graph.media_queries.get(media)


def find_element(graph: DependencyGraph, tag: str):
    return graph.elements.get(tag, [])


def files_importing(graph: DependencyGraph, module: str):
    return graph.reverse_imports.get(module, [])


def imports_of(graph: DependencyGraph, file_path: str):
    return graph.imports.get(file_path, [])