import re

from core.parsers.parser_utils import empty_metadata, clean_metadata


# At-rules whose block bodies do NOT contain real selectors.
# (0%, 50%, "to", "from" in @keyframes; property names in @font-face, etc.)
# These blocks get skipped wholesale rather than scanned for selectors.
_SKIP_ATRULES = {
    "@keyframes",
    "@-webkit-keyframes",
    "@-moz-keyframes",
    "@-o-keyframes",
    "@font-face",
    "@page",
    "@counter-style",
    "@font-feature-values",
    "@property",
    "@namespace",
    "@charset",
    "@layer",      # CSS Cascade Layers
}


def _skip_block(content: str, i: int) -> int:
    """
    `i` points just past an opening '{'. Advance past the matching
    closing '}' (respecting nested braces and quoted strings) and
    return the index just after it.
    """
    depth = 1
    in_string = None
    n = len(content)

    while i < n and depth > 0:
        char = content[i]

        if in_string:
            if char == "\\":
                i += 2
                continue
            if char == in_string:
                in_string = None
        elif char in ("'", '"'):
            in_string = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

        i += 1

    return i


def _extract_selectors(content: str) -> list:
    """
    Lexically scan CSS and pull out real selectors only.

    Tracks brace depth, quoted strings, and parenthesis depth
    (url(...), gradients, etc.) one character at a time, so it never
    loses sync the way a regex-over-fragments approach can.

    - Text immediately before a '{' at "selector position" (i.e. not
      inside quotes/parens) is a candidate selector.
    - If that text is an at-rule in _SKIP_ATRULES (@keyframes,
      @font-face, ...), the whole block is skipped — its contents
      (percentages, property names) are never mistaken for selectors.
    - Other at-rules (@media, @supports, ...) are descended into,
      since real selectors can be nested inside them.
    - Plain '}' just closes whatever block we were in.
    """
    selectors = []
    buffer = []
    in_string = None
    paren_depth = 0
    i = 0
    n = len(content)

    while i < n:
        char = content[i]

        if in_string:
            buffer.append(char)
            if char == "\\":
                i += 1
                if i < n:
                    buffer.append(content[i])
                    i += 1
                continue
            if char == in_string:
                in_string = None
            i += 1
            continue

        if char in ("'", '"'):
            in_string = char
            buffer.append(char)
            i += 1
            continue

        if char == "(":
            paren_depth += 1
            buffer.append(char)
            i += 1
            continue

        if char == ")":
            paren_depth = max(0, paren_depth - 1)
            buffer.append(char)
            i += 1
            continue

        if paren_depth > 0:
            buffer.append(char)
            i += 1
            continue

        if char == "{":
            selector_text = "".join(buffer).strip()
            buffer = []

            if selector_text.startswith("@"):
                atrule_name = selector_text.split(None, 1)[0].lower()
                if atrule_name in _SKIP_ATRULES:
                    # skip the whole block; nothing inside is a real selector
                    i = _skip_block(content, i + 1)
                    continue
                # @media / @supports / @document / etc: descend, real
                # selectors may be nested inside
                i += 1
                continue

            if selector_text:
                for part in selector_text.split(","):

                    part = part.strip()

                    if not part:
                        continue
 
                    if part.startswith("@"):
                           continue

                    # Reject CSS declarations accidentally captured as selectors
                    # but keep pseudo-elements like ::before and ::after.
                    if re.match(r'^[A-Za-z-]+\s*:', part):
                        continue

                    selectors.append(part)

            i += 1
            continue

        if char == "}":
            buffer = []
            i += 1
            continue

        buffer.append(char)
        i += 1

    return selectors


def parse_css(content: str) -> dict:

    metadata = empty_metadata()

    # -----------------------------------
    # Remove CSS comments
    # -----------------------------------

    content = re.sub(
        r"/\*.*?\*/",
        "",
        content,
        flags=re.DOTALL,
    )

    # -----------------------------------
    # Imports
    # -----------------------------------

    metadata["imports"].extend(

        re.findall(
            r'@import\s+(?:url\()?["\']?(.*?)["\']?\)?;',
            content,
            flags=re.IGNORECASE,
        )

    )

    # -----------------------------------
    # CSS Variables
    # -----------------------------------

    metadata["variables"].extend(

        re.findall(
            r'(--[A-Za-z0-9_-]+)\s*:',
            content,
        )

    )

    # -----------------------------------
    # Animations
    # -----------------------------------

    metadata["animations"].extend(

        re.findall(
            r'@keyframes\s+([A-Za-z0-9_-]+)',
            content,
        )

    )

    # -----------------------------------
    # Media Queries
    # -----------------------------------

    metadata["media_queries"].extend(

        [
            q.strip()
            for q in re.findall(
                r'@media\s*([^{]+)',
                content,
                flags=re.IGNORECASE,
            )
        ]

    )

    # -----------------------------------
    # Selectors (lexer-based — see _extract_selectors)
    # -----------------------------------

    metadata["selectors"].extend(_extract_selectors(content))

    # -----------------------------------
    # CSS Classes
    # -----------------------------------

    for selector in metadata["selectors"]:

        metadata["css_classes"].extend(

            re.findall(
                r'\.([A-Za-z_-][A-Za-z0-9_-]*)',
                selector,
            )

        )

    # -----------------------------------
    # IDs
    # -----------------------------------

    for selector in metadata["selectors"]:

        metadata["ids"].extend(

            re.findall(
                r'#([A-Za-z_-][A-Za-z0-9_-]*)',
                selector,
            )

        )

    # -----------------------------------
    # CSS Variable usages
    # -----------------------------------

    var_uses = re.findall(r'var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,.*?)?\)', content)
    metadata.setdefault("variable_uses", []).extend(var_uses)

    # -----------------------------------
    # Selector specificity and pseudo-selectors
    # -----------------------------------

    def _specificity(sel: str):
        # counts: ids, classes/attrs/pseudo-classes, elements/pseudo-elements
        ids = len(re.findall(r'#([A-Za-z0-9_-]+)', sel))
        classes = len(re.findall(r'\.([A-Za-z0-9_-]+)', sel))
        attrs = len(re.findall(r'\[[^\]]+\]', sel))
        pseudo_elements = len(re.findall(r'::([A-Za-z0-9_-]+)', sel))
        pseudo_classes = len(re.findall(r':(?!:)([A-Za-z0-9_-]+)', sel))
        # element/tag names (rough): tokens that look like tag names
        elements = len(re.findall(r'(^|\s|\(|>|\+|~)([a-zA-Z][a-zA-Z0-9_-]*)', sel))
        # aggregate
        return (ids, classes + attrs + pseudo_classes, elements + pseudo_elements)

    for selector in metadata["selectors"]:
        spec = _specificity(selector)
        metadata.setdefault("selector_specificity", []).append({"selector": selector, "specificity": spec})

        # pseudo selectors
        for pe in re.findall(r'::([A-Za-z0-9_-]+)', selector):
            metadata.setdefault("pseudo_selectors", []).append({"selector": selector, "pseudo": pe, "type": "element"})
        for pc in re.findall(r':(?!:)([A-Za-z0-9_-]+)', selector):
            metadata.setdefault("pseudo_selectors", []).append({"selector": selector, "pseudo": pc, "type": "class"})

    # -----------------------------------
    # Theme detection heuristics
    # -----------------------------------

    if re.search(r'prefers-color-scheme', content, flags=re.IGNORECASE):
        metadata.setdefault("themes", []).append({"type": "prefers-color-scheme"})
    # class-based dark themes
    for sel in metadata["selectors"]:
        if re.search(r'(^|\.|\s)\.dark\b', sel) or re.search(r'theme-dark', sel):
            metadata.setdefault("themes", []).append({"type": "class", "selector": sel})
        if re.search(r'\[data-theme=["\']dark["\']\]', sel):
            metadata.setdefault("themes", []).append({"type": "data-attr", "selector": sel})

    # -----------------------------------
    # Remove duplicates
    # -----------------------------------

    return clean_metadata(metadata)