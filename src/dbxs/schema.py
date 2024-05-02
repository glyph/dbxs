# -*- test-case-name: dbxs.test.test_schema -*-
"""
Schema-building utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import local
from typing import Callable, TypeVar


__all__ = [
    "SchemaBuilder",
]

T = TypeVar("T")


_tableSchema = """\
CREATE TABLE IF NOT EXISTS {tableName} (
    {columns}
);
"""


@dataclass
class _WorkingTable:
    back: _WorkingTable | None
    columns: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


class _TableStack(local):
    current: _WorkingTable | None = None

    def push(self) -> _WorkingTable:
        current = self.current = _WorkingTable(self.current)
        return current

    def get(self) -> _WorkingTable:
        if self.current is None:
            raise RuntimeError("not currently defining a table")
        return self.current

    def pop(self) -> _WorkingTable:
        self.current = (result := self.get()).back
        return result


@dataclass
class SchemaBuilder:
    """
    A L{SchemaBuilder} can associate fragments of a schema in-line with
    classes.
    """

    schema: str = ""
    _stack: _TableStack = field(default_factory=_TableStack)

    def table(self, tableName: str) -> Callable[[T], T]:
        """
        Decorate a class with this method to create a new table.
        """
        work = self._stack.push()

        def buildSchema(c: T) -> T:
            assert self._stack.pop() is work, "stack should match"
            sep = ",\n    "
            sep.join(work.columns)
            partialSchema = _tableSchema.format(
                tableName=tableName,
                columns=sep.join(work.columns + work.constraints),
            )
            self.schema += partialSchema
            return c

        return buildSchema

    def column(self, columnText: str) -> None:
        """
        Create a new column within a class decorated by L{SchemaBuilder.table}.
        """
        self._stack.get().columns.append(columnText)

    def constraint(self, constraintText: str) -> None:
        """
        Create a new standalone constraint within a class decorated by
        L{SchemaBuilder.table}.
        """
        self._stack.get().constraints.append(constraintText)
