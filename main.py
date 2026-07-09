from core.repository import scan_repository
from core.indexer import build_index
from core.graph import (
    build_graph,
    find_function,
    find_class,
    find_selector,
    find_id,
    find_css_class,
    find_variable,
    find_animation,
    imports_of,
    files_importing,
)
from core.relationship import Relation, RelationshipBuilder


SEPARATOR = "=" * 60


# ----------------------------------------
# Generic print helpers
# ----------------------------------------

def print_header(title):
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)


def print_section(title):
    print()
    print_header(title)


def print_named_index(title, mapping):
    """Print a name -> file mapping.

    Used for functions, classes, selectors, ids, css classes, variables,
    animations, media queries, and html elements. It's generic on purpose:
    if the graph ever indexes a new kind of entity, this function does not
    need to change - just call it with the new mapping.
    """

    print_section(title)

    if not mapping:
        print("(none found)")
        return

    width = min(max(len(name) for name in mapping), 40)

    for name in sorted(mapping):
        print(f"{name:<{width}} -> {mapping[name]}")


def print_multi_index(title, mapping):
    """Print a name -> [files] mapping.

    Unlike the other symbol indexes (functions, classes, selectors, etc.),
    which map a name to a single defining file, graph.elements maps an
    HTML tag to every file that contains it - so it needs a join instead
    of a straight lookup.
    """

    print_section(title)

    if not mapping:
        print("(none found)")
        return

    width = min(max(len(name) for name in mapping), 40)

    for name in sorted(mapping):
        files = ", ".join(dict.fromkeys(mapping[name]))
        print(f"{name:<{width}} -> {files}")


def print_relationship_map(title, mapping, arrow):
    """Print a name -> [related names] mapping.

    IMPORT GRAPH (file -> imports) and REVERSE IMPORTS (module -> importers)
    are the exact same shape of data, just with the arrow pointing the other
    way, so they share this one implementation instead of two near-identical
    functions.
    """

    print_section(title)

    if not mapping:
        print("(none found)")
        return

    for key in sorted(mapping):
        related = mapping[key]

        print(key)

        if related:
            for item in related:
                print(f"  {arrow} {item}")
        else:
            print("  (none)")

        print()


# ----------------------------------------
# Formatting helpers
# ----------------------------------------

def format_size(num_bytes):
    """Human-readable file size: '512 B', '12.4 KB', '8.6 MB', '1.3 GB'."""

    size = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]

    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


# ----------------------------------------
# REPOSITORY section
# ----------------------------------------

def print_repository_summary(index):
    files = index.files

    print_header("REPOSITORY")

    if not files:
        print("(no files found)")
        return

    total_files = len(files)
    total_lines = sum(f.lines for f in files)
    total_size = sum(f.size for f in files)

    print(f"Total Files      : {total_files:,}")
    print(f"Total Lines      : {total_lines:,}")
    print(f"Total Size       : {format_size(total_size)}")

    # Language breakdown is fully dynamic - no hardcoded language list.
    # Any new language the parsers/indexer ever produce (Rust, Go, Vue,
    # whatever) shows up here automatically, with zero changes to main.py.
    language_counts = {}
    for f in files:
        language_counts[f.language] = language_counts.get(f.language, 0) + 1

    print()
    print("Language Breakdown")
    print("-" * 60)

    for language in sorted(language_counts):
        print(f"  {language:<20}: {language_counts[language]:,}")

    # Highlights - biggest / busiest files at a glance.
    largest_file = max(files, key=lambda f: f.size)
    most_functions_file = max(files, key=lambda f: len(f.functions))
    most_imports_file = max(files, key=lambda f: len(f.imports))
    most_classes_file = max(files, key=lambda f: len(f.classes))

    print()
    print("Highlights")
    print("-" * 60)
    print(
        f"  Largest File     : {largest_file.path} "
        f"({format_size(largest_file.size)}, {largest_file.lines:,} lines)"
    )
    print(
        f"  Most Functions   : {most_functions_file.path} "
        f"({len(most_functions_file.functions):,} functions)"
    )
    print(
        f"  Most Imports     : {most_imports_file.path} "
        f"({len(most_imports_file.imports):,} imports)"
    )
    print(
        f"  Most Classes     : {most_classes_file.path} "
        f"({len(most_classes_file.classes):,} classes)"
    )


# ----------------------------------------
# GRAPH section
# ----------------------------------------

def graph_nodes(graph):
    """Every distinct file/module that appears anywhere in the import
    graph, either as an importer or as something imported."""

    nodes = set(graph.imports.keys())

    for imported in graph.imports.values():
        nodes.update(imported)

    return nodes


def graph_edges(graph):
    """Total number of import relationships (directed edges)."""

    return sum(len(imported) for imported in graph.imports.values())


def print_graph_summary(graph):
    print_header("GRAPH")

    metrics = [
        ("Functions", len(graph.functions)),
        ("Classes", len(graph.classes)),
        ("Selectors", len(graph.selectors)),
        ("IDs", len(graph.ids)),
        ("CSS Classes", len(graph.css_classes)),
        ("Variables", len(graph.variables)),
        ("Animations", len(graph.animations)),
        ("Media Queries", len(graph.media_queries)),
        ("Elements", len(graph.elements)),
        ("Import Nodes", len(graph_nodes(graph))),
        ("Import Edges", graph_edges(graph)),
        ("Reverse Imports", len(graph.reverse_imports)),
    ]

    for label, value in metrics:
        print(f"  {label:<15}: {value:,}")


def print_relationship_summary(relationship_graph):
    print_header("RELATIONSHIP SUMMARY")

    summary = relationship_graph.summary()

    print(f"Total Relationships : {len(relationship_graph):,}")
    print()

    for relation in Relation:
        print(f"{relation.value:<20}: {summary[relation.value]:,}")


def print_relationship_sample(relationship_graph, limit=12):
    print_header("RELATIONSHIP SAMPLE")

    if not relationship_graph:
        print("(none found)")
        return

    for index, relationship in enumerate(relationship_graph):
        if index >= limit:
            remaining = len(relationship_graph) - limit
            if remaining > 0:
                print(f"... {remaining:,} more relationships")
            break

        print(relationship.source)
        print(f"    {relationship.relation.value}")
        print(f"        {relationship.target}")
        print()


# ----------------------------------------
# INDEXES section
# ----------------------------------------

def print_indexes(graph):
    print_named_index("FUNCTION INDEX", graph.functions)
    print_named_index("CLASS INDEX", graph.classes)
    print_named_index("CSS SELECTORS", graph.selectors)
    print_named_index("HTML IDS", graph.ids)
    print_named_index("CSS CLASSES", graph.css_classes)
    print_named_index("VARIABLES", graph.variables)
    print_named_index("ANIMATIONS", graph.animations)
    print_named_index("MEDIA QUERIES", graph.media_queries)
    print_multi_index("HTML ELEMENTS", graph.elements)

    print_relationship_map("IMPORT GRAPH", graph.imports, "->")
    print_relationship_map("REVERSE IMPORTS", graph.reverse_imports, "<-")


# ----------------------------------------
# REPOSITORY HEALTH (reserved for future metrics)
# ----------------------------------------

def print_repository_health(index, graph):
    """Placeholder section.

    Once the Relationship Builder starts adding graph edges, this is where
    things like unused CSS variables, duplicate IDs, files without imports,
    files without functions, and function-count outliers will live. It's
    broken out as its own section now, with `index` and `graph` already
    wired in, so none of the surrounding structure has to change later -
    only the body of this function.
    """

    print_header("REPOSITORY HEALTH")
    print("(coming soon: unused CSS variables, duplicate IDs, files")
    print(" without imports, files without functions, largest function")
    print(" count)")


# ----------------------------------------
# QUERIES section
# ----------------------------------------

def _first_key(mapping):
    return next(iter(mapping), None)


def print_example_queries(graph):
    print_header("QUERIES")

    # (label, mapping to sample a real key from, the find_* function)
    single_key_queries = [
        ("find_function", graph.functions, find_function),
        ("find_class", graph.classes, find_class),
        ("find_selector", graph.selectors, find_selector),
        ("find_id", graph.ids, find_id),
        ("find_css_class", graph.css_classes, find_css_class),
        ("find_variable", graph.variables, find_variable),
        ("find_animation", graph.animations, find_animation),
    ]

    for name, mapping, finder in single_key_queries:
        sample = _first_key(mapping)

        if sample is None:
            print(f"{name}(...): (no data available)")
            print()
            continue

        print(f'Testing: {name}("{sample}")')
        print(f"  {finder(graph, sample)}")
        print()

    sample_module = _first_key(graph.reverse_imports)

    if sample_module is None:
        print("files_importing(...): (no data available)")
    else:
        print(f'Testing: files_importing("{sample_module}")')
        print(f"  {files_importing(graph, sample_module)}")


# ----------------------------------------
# Main
# ----------------------------------------

def main():
    repo = scan_repository("repos/website")
    index = build_index(repo)
    graph = build_graph(index)
    relationship_graph = RelationshipBuilder(index).build()

    print_repository_summary(index)
    print()
    print_graph_summary(graph)
    print()
    print_relationship_summary(relationship_graph)
    print()
    print_relationship_sample(relationship_graph)
    print_indexes(graph)
    print()
    print_repository_health(index, graph)
    print_example_queries(graph)


if __name__ == "__main__":
    main()