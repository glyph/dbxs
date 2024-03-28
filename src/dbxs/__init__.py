"""
DBXS (“D.B. Access”) is an SQL database access layer for Python.
"""

from ._access import (
    ExtraneousMethods,
    IncorrectResultCount,
    NotEnoughResults,
    ParamMismatch,
    TooManyResults,
    accessor,
    many,
    maybe,
    one,
    query,
    statement,
)
from ._repository import repository


__version__ = "0.1.0"


__all__ = [
    "one",
    "many",
    "maybe",
    "accessor",
    "repository",
    "statement",
    "query",
    "ParamMismatch",
    "TooManyResults",
    "NotEnoughResults",
    "IncorrectResultCount",
    "ExtraneousMethods",
]
