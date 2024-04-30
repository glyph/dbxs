"""
Tests for L{dbxs.schema}.
"""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from unittest import TestCase

from dbxs.schema import SchemaBuilder


class SchemaBuilderTests(TestCase):
    def test_simpleSchema(self) -> None:
        """
        Decorating a class with L{SchemaBuilder.table} and then calling
        L{SchemaBuilder.column} on it from within the class body will generate
        a C{CREATE TABLE IF NOT EXISTS} statement in the schema.
        """
        builder = SchemaBuilder()

        @builder.table("hello")
        @dataclass
        class Hello:
            foo: int
            builder.column("foo INTEGER NOT NULL")
            builder.constraint("UNIQUE (foo)")
            bar: str
            builder.column("bar TEXT NOT NULL")

        self.assertEqual(
            builder.schema,
            dedent(
                """\
                CREATE TABLE IF NOT EXISTS hello (
                    foo INTEGER NOT NULL,
                    bar TEXT NOT NULL,
                    UNIQUE (foo)
                );
                """
            ),
        )

    def test_nesting(self) -> None:
        """
        Declaring a nested table-class with SchemaBuilder.table will emit the
        inner table in the schema.
        """
        builder = SchemaBuilder()

        @builder.table("hello")
        @dataclass
        class Hello:
            foo: int
            builder.column("foo INTEGER NOT NULL")

            @builder.table("goodbye")
            @dataclass
            class Goodbye:
                farewell: str
                builder.column("farewell TEXT NOT NULL")

            bar: str
            builder.column("bar TEXT NOT NULL")

        self.assertEqual(
            builder.schema,
            dedent(
                """\
                CREATE TABLE IF NOT EXISTS goodbye (
                    farewell TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS hello (
                    foo INTEGER NOT NULL,
                    bar TEXT NOT NULL
                );
                """
            ),
        )
