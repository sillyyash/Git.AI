from dataclasses import dataclass
from typing import List

from core.repository import Repository

from core.parsers.python_parser import parse_python
from core.parsers.javascript_parser import parse_javascript
from core.parsers.html_parser import parse_html
from core.parsers.css_parser import parse_css
from core.parsers.parser_utils import empty_metadata


@dataclass
class IndexedFile:
    path: str
    language: str
    size: int
    lines: int

    imports: List[str]
    functions: List[str]
    classes: List[str]
    exports: List[str]

    # CSS
    selectors: List[str]
    ids: List[str]
    css_classes: List[str]
    variables: List[str]
    animations: List[str]
    media_queries: List[str]

    # HTML
    elements: List[dict]

    # Relationships
    calls: List[dict]
    dom_references: List[dict]
    class_ops: List[dict]


@dataclass
class RepositoryIndex:
    files: List[IndexedFile]


PARSERS = {
    "Python": parse_python,
    "Javascript": parse_javascript,
    "Typescript": parse_javascript,
    "React Jsx": parse_javascript,
    "React Tsx": parse_javascript,
    "Html": parse_html,
    "Css": parse_css,
    "Scss": parse_css,
}


def build_index(repository: Repository) -> RepositoryIndex:

    indexed_files = []

    for file in repository.files:

        language = file.language.strip().title()

        parser = PARSERS.get(language)

        metadata = parser(file.content) if parser else empty_metadata()

        indexed_files.append(

            IndexedFile(

                path=file.path,

                language=language,

                size=len(file.content.encode()),

                lines=len(file.content.splitlines()),

                imports=metadata["imports"],

                functions=metadata["functions"],

                classes=metadata["classes"],

                exports=metadata["exports"],

                selectors=metadata["selectors"],

                ids=metadata["ids"],

                css_classes=metadata["css_classes"],

                variables=metadata["variables"],

                animations=metadata["animations"],

                media_queries=metadata["media_queries"],

                elements=metadata["elements"],

                calls=metadata["calls"],

                dom_references=metadata["dom_references"],

                class_ops=metadata["class_ops"],

            )

        )

    return RepositoryIndex(indexed_files)