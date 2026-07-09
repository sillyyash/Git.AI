from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

_VENDOR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "vendor"))
if os.path.isdir(_VENDOR_PATH) and _VENDOR_PATH not in sys.path:
    sys.path.insert(0, _VENDOR_PATH)


class RelationshipMetadata:
    KIND = "kind"
    DIRECT = "direct"
    OBJECT = "object"
    OBJECT_NAME = "object_name"
    METHOD_NAME = "method_name"
    IS_OBJECT_CALL = "is_object_call"
    IS_IMPORTED = "is_imported"
    IMPORTED_FROM = "imported_from"
    IMPORTED_NAME = "imported_name"
    LOCAL_NAME = "local_name"
    ORIGINAL_CALLEE = "original_callee"
    RESOLVED_FROM_ALIAS = "resolved_from_alias"

    # DOM metadata keys
    DOM_SELECTOR = "selector"
    DOM_SELECTOR_TYPE = "selector_type"
    DOM_API = "api"

    # Event metadata keys
    EVENT_NAME = "event"
    EVENT_HANDLER = "handler"
    EVENT_TARGET = "target"


@dataclass(frozen=True)
class ImportAlias:
    local_name: str
    imported_name: str
    imported_from: str


@dataclass(frozen=True)
class StaticAlias:
    local_name: str
    target: str
