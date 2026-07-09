import re
from copy import deepcopy


# --------------------------------------------
# Default metadata template
# --------------------------------------------

DEFAULT_METADATA = {

    # Universal
    "imports": [],
    "functions": [],
    "classes": [],
    "exports": [],

    # CSS
    "selectors": [],
    "ids": [],
    "css_classes": [],
    "variables": [],
    "animations": [],
    "media_queries": [],

    # HTML
    "elements": [],

    # Relationship Builder Phase 2
    "calls": [],
    "dom_references": [],
    "event_listeners": [],
    "class_ops": [],
    "module_symbol_usage": [],
    "forms": [],
    "assets": [],

    # Semantic HTML attributes
    "data_attributes": [],
    "roles": [],
    "aria_attributes": [],

    # CSS advanced
    "variable_uses": [],
    "selector_specificity": [],
    "pseudo_selectors": [],
    "themes": [],

    # Future
    "relationships": [],
    "dependencies": [],
    "references": [],
    "warnings": [],
}


# --------------------------------------------
# Fresh metadata
# --------------------------------------------

def empty_metadata():

    """
    Returns a fresh metadata dictionary.
    """

    return deepcopy(DEFAULT_METADATA)


# --------------------------------------------
# Remove duplicates
# --------------------------------------------

def unique(items):

    return list(dict.fromkeys(items))


# --------------------------------------------
# Clean every metadata list
# --------------------------------------------

def clean_metadata(metadata):

    for key, value in metadata.items():

        if not isinstance(value, list):
            continue

        # Some metadata lists contain dictionaries, which can't be
        # deduplicated using dict.fromkeys() because dictionaries are unhashable.
        if value and isinstance(value[0], dict):

            seen = set()
            cleaned = []

            for item in value:

                marker = tuple(sorted((k, repr(v)) for k, v in item.items()))

                if marker not in seen:
                    seen.add(marker)
                    cleaned.append(item)

            metadata[key] = cleaned

        else:
            metadata[key] = unique(value)

    return metadata


# --------------------------------------------
# Merge metadata dictionaries
# --------------------------------------------

def merge_metadata(base, incoming):

    for key, value in incoming.items():

        if key not in base:

            base[key] = []

        if isinstance(value, list):

            base[key].extend(value)

    return clean_metadata(base)


# --------------------------------------------
# Safe regex helper
# --------------------------------------------

def regex(pattern, text, flags=0):

    try:

        return re.findall(pattern, text, flags)

    except re.error:

        return []


# --------------------------------------------
# Remove HTML comments
# --------------------------------------------

def strip_html_comments(content):

    return re.sub(

        r"<!--.*?-->",

        "",

        content,

        flags=re.DOTALL,

    )


# --------------------------------------------
# Remove JS comments
# --------------------------------------------

def strip_js_comments(content):

    content = re.sub(

        r"/\*.*?\*/",

        "",

        content,

        flags=re.DOTALL,

    )

    content = re.sub(

        r"//.*?$",

        "",

        content,

        flags=re.MULTILINE,

    )

    return content


# --------------------------------------------
# Remove CSS comments
# --------------------------------------------

def strip_css_comments(content):

    return re.sub(

        r"/\*.*?\*/",

        "",

        content,

        flags=re.DOTALL,

    )


# --------------------------------------------
# Check if string is a URL
# --------------------------------------------

def is_url(path):

    return path.startswith(("http://", "https://"))