from bs4 import BeautifulSoup

from core.parsers.css_parser import parse_css
from core.parsers.javascript_parser import parse_javascript
from core.parsers.parser_utils import (
    empty_metadata,
    clean_metadata,
    merge_metadata,
)


def parse_html(content: str) -> dict:

    metadata = empty_metadata()

    soup = BeautifulSoup(content, "html.parser")

    # -----------------------------------
    # HTML Elements / IDs / CSS Classes
    # -----------------------------------

    for tag in soup.find_all():

        # Extract string attrs only to keep metadata simple
        attrs = {key: value for key, value in tag.attrs.items() if isinstance(value, str)}

        # Semantic attributes: data-*, role, aria-*
        data_attrs = {k: v for k, v in attrs.items() if k.startswith("data-")}
        role = attrs.get("role")
        aria_attrs = {k: v for k, v in attrs.items() if k.startswith("aria-")}

        element = {
            "tag": tag.name,
            "id": tag.get("id"),
            "classes": tag.get("class", []),
            "attrs": attrs,
        }

        if data_attrs:
            element["data_attrs"] = data_attrs
            for k in data_attrs.keys():
                metadata.setdefault("data_attributes", []).append(k)

        if role:
            element["role"] = role
            metadata.setdefault("roles", []).append(role)

        if aria_attrs:
            element["aria"] = aria_attrs
            for k in aria_attrs.keys():
                metadata.setdefault("aria_attributes", []).append(k)

        metadata["elements"].append(element)

        html_id = tag.get("id")

        if html_id:
            metadata["ids"].append(html_id)

        for cls in tag.get("class", []):
            metadata["css_classes"].append(cls)

        # Asset references
        # img, script handled elsewhere; capture common media and resource sources
        src = tag.get("src") or tag.get("data-src")
        href = tag.get("href")
        if src:
            metadata.setdefault("assets", []).append(src)
        elif href:
            # link rel=icon, manifest, etc. treat as asset
            rel = tag.get("rel") or []
            if isinstance(rel, list):
                rel_list = rel
            else:
                rel_list = [rel]
            if any(r in {"icon", "manifest", "preload"} for r in rel_list) or tag.name in {"link", "object", "iframe"}:
                metadata.setdefault("assets", []).append(href)

    # -----------------------------------
    # External JavaScript
    # -----------------------------------

    for script in soup.find_all("script"):

        src = script.get("src")

        if src:
            metadata["imports"].append(src)

    # -----------------------------------
    # External CSS
    # -----------------------------------

    for style in soup.find_all("style"):

        css = style.string

        if not css:
            css = style.get_text()

        if not css.strip():
             continue

        result = parse_css(css)

        merge_metadata(metadata, result)

    for link in soup.find_all("link"):

        rel = link.get("rel")

        if rel and "stylesheet" in rel:

            href = link.get("href")

            if href:
                metadata["imports"].append(href)

    # -----------------------------------
    # Inline JavaScript
    # -----------------------------------

    for script in soup.find_all("script"):

        if script.get("src"):
            continue

        js = script.string

        if not js:
            js = script.get_text()

        if not js.strip():
            continue

        result = parse_javascript(js)

        merge_metadata(metadata, result)

    # -----------------------------------
    # Forms: collect contained inputs, selects, textareas, buttons
    # -----------------------------------

    for form in soup.find_all("form"):
        form_id = form.get("id")
        form_name = form.get("name")
        inputs = []
        buttons = []

        for control in form.find_all(["input", "textarea", "select", "button"]):
            ctrl = {
                "tag": control.name,
                "id": control.get("id"),
                "name": control.get("name"),
                "type": control.get("type") if control.name == "input" else None,
                "classes": control.get("class", []),
                "attrs": {k: v for k, v in control.attrs.items() if isinstance(v, str)},
            }
            if control.name == "button" or (control.name == "input" and control.get("type") in {"button", "submit", "reset"}):
                buttons.append(ctrl)
            else:
                inputs.append(ctrl)

        metadata.setdefault("forms", []).append({
            "id": form_id,
            "name": form_name,
            "inputs": inputs,
            "buttons": buttons,
        })

    # -----------------------------------
    # Remove duplicates
    # -----------------------------------

    return clean_metadata(metadata)