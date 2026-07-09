from pathlib import Path
from dataclasses import dataclass
from typing import List


# ---------------------------------
# Supported Languages
# ---------------------------------

LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "React JSX",
    ".tsx": "React TSX",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".md": "Markdown",
    ".txt": "Text",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
}


# ---------------------------------
# Ignore these folders
# ---------------------------------

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".idea",
    ".vscode",
}


# ---------------------------------
# Ignore these files
# ---------------------------------

IGNORE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".exe",
    ".dll",
    ".mp4",
    ".mp3",
}


# ---------------------------------
# File Object
# ---------------------------------

@dataclass
class RepoFile:

    path: str
    language: str
    content: str


# ---------------------------------
# Repository Object
# ---------------------------------

@dataclass
class Repository:

    root: str
    files: List[RepoFile]


# ---------------------------------
# Scanner
# ---------------------------------

def scan_repository(repo_path: str) -> Repository:

    repo = Path(repo_path)

    files: List[RepoFile] = []

    for file in repo.rglob("*"):

        if not file.is_file():
            continue

        if any(part in IGNORE_DIRS for part in file.parts):
            continue

        if file.suffix.lower() in IGNORE_EXTENSIONS:
            continue

        language = LANGUAGES.get(file.suffix.lower(), "Unknown")

        try:
            content = file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

        except Exception:
            continue

        files.append(
            RepoFile(
                path=str(file.relative_to(repo)),
                language=language,
                content=content,
            )
        )

    return Repository(
        root=str(repo.resolve()),
        files=files,
    )