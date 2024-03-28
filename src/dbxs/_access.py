# -*- test-case-name: dbxs.test.test_access -*-
from __future__ import annotations

from dataclasses import dataclass, field
from inspect import (
    BoundArguments,
    currentframe,
    getsourcefile,
    getsourcelines,
    isawaitable,
    signature,
)
from types import FrameType, TracebackType
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    Iterable,
    List,
    NoReturn,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

from ._typing_compat import ParamSpec, Protocol
from .async_dbapi import AsyncConnection, AsyncCursor


T = TypeVar("T")
P = ParamSpec("P")
A = TypeVar("A", bound=Union[AsyncIterable[object], Awaitable[object]])


class ParamMismatch(Exception):
    """
    The parameters required by the query are different than the parameters
    specified by the function.
    """


class IncorrectResultCount(Exception):
    """
    An assumption about the number of rows from a given query was violated;
    there were either too many or too few.
    """


class NotEnoughResults(IncorrectResultCount):
    """
    There were not enough results for the query to satify L{one}.
    """


class TooManyResults(IncorrectResultCount):
    """
    There were more results for a query than expected; more than one for
    L{one}, or any at all for L{zero}.
    """


class ExtraneousMethods(Exception):
    """
    An access pattern defined extraneous methods.
    """


class WrongRowShape(TypeError):
    """
    The row was the wrong shape for the given callable.
    """


@dataclass
class _ExceptionFixer:
    loader: Callable[..., object]
    definitionLine: int
    decorationLine: int
    decorationFrame: FrameType
    definitionFrame: FrameType

    def reraise(self, row: object, e: Exception) -> NoReturn:
        withDecorationAdded = TracebackType(
            None, self.decorationFrame, 0, self.decorationLine
        )
        withDefinitionAdded = TracebackType(
            withDecorationAdded, self.definitionFrame, 0, self.definitionLine
        )
        raise WrongRowShape(
            f"loader {self.loader.__module__}.{self.loader.__name__}"
            f" could not handle {row}"
        ).with_traceback(withDefinitionAdded) from e

    @classmethod
    def create(cls, loader: Callable[..., T]) -> _ExceptionFixer:
        subFrame = currentframe()
        assert subFrame is not None
        frameworkFrame = subFrame.f_back  # the caller; 'one' or 'many'
        assert frameworkFrame is not None
        realDecorationFrame = frameworkFrame.f_back
        assert realDecorationFrame is not None
        wholeSource, definitionLine = getsourcelines(loader)

        # coverage is tricked by the __code__ modifications below, so we have
        # to explicitly ignore the gap

        def decoratedHere() -> FrameType | None:
            return currentframe()  # pragma: no cover

        def definedHere() -> FrameType | None:
            return currentframe()  # pragma: no cover

        decoratedHere.__code__ = decoratedHere.__code__.replace(
            co_name="<<decorated here>>",
            co_filename=realDecorationFrame.f_code.co_filename,
            co_firstlineno=realDecorationFrame.f_lineno,
        )

        definedSourceFile = getsourcefile(loader)
        definedHere.__code__ = definedHere.__code__.replace(
            co_name="<<defined here>>",
            co_filename=definedSourceFile or "unknown definition",
            co_firstlineno=definitionLine,
        )

        fakeDecorationFrame = decoratedHere()
        definitionFrame = definedHere()
        assert realDecorationFrame is not None
        assert definitionFrame is not None
        assert fakeDecorationFrame is not None

        return cls(
            loader=loader,
            definitionFrame=definitionFrame,
            definitionLine=definitionLine,
            decorationFrame=fakeDecorationFrame,
            decorationLine=realDecorationFrame.f_lineno,
        )


_NR = TypeVar("_NR")


def _makeTranslator(
    fixer: _ExceptionFixer,
    load: Callable[..., T],
    noResults: Callable[[], _NR],
) -> Callable[[object, AsyncCursor], Coroutine[object, object, T | _NR]]:
    async def translator(db: object, cursor: AsyncCursor) -> T | _NR:
        rows = await cursor.fetchall()
        if len(rows) < 1:
            return noResults()
        if len(rows) > 1:
            raise TooManyResults()
        [row] = rows
        try:
            return load(db, *row)
        except TypeError as e:
            fixer.reraise(row, e)

    return translator


def one(
    load: Callable[..., T],
) -> Callable[[object, AsyncCursor], Coroutine[object, object, T]]:
    """
    Fetch a single result with a translator function.
    """
    fixer = _ExceptionFixer.create(load)

    def noResults() -> NoReturn:
        raise NotEnoughResults()

    return _makeTranslator(fixer, load, noResults)


def maybe(
    load: Callable[..., T]
) -> Callable[[object, AsyncCursor], Coroutine[object, object, Optional[T]]]:
    """
    Fetch a single result and pass it to a translator function, but return None
    if it's not found.
    """
    fixer = _ExceptionFixer.create(load)

    def noResults() -> None:
        return None

    return _makeTranslator(fixer, load, noResults)


def many(
    load: Callable[..., T]
) -> Callable[[object, AsyncCursor], AsyncIterable[T]]:
    """
    Fetch multiple results with a function to translate rows.
    """
    fixer = _ExceptionFixer.create(load)

    async def translateMany(
        db: object, cursor: AsyncCursor
    ) -> AsyncIterable[T]:
        while True:
            row = await cursor.fetchone()
            if row is None:
                return
            try:
                yield load(db, *row)
            except TypeError as e:
                fixer.reraise(row, e)

    return translateMany


async def zero(loader: object, cursor: AsyncCursor) -> None:
    """
    Zero record loader.
    """
    result = await cursor.fetchone()
    if result is not None:
        raise TooManyResults("statemnts should not return values")
    return None


METADATA_KEY = "__query_metadata__"


@dataclass
class MaybeAIterable:
    down: Any
    cursor: AsyncCursor = field(init=False)

    def __await__(self) -> Any:
        return self.down.__await__()

    async def __aiter__(self) -> Any:
        try:
            actuallyiter = await self
            async for each in actuallyiter:
                yield each
        finally:
            await self.cursor.close()


@dataclass
class QueryMetadata:
    """
    Metadata defining a certain function on a protocol as a query method.
    """

    sql: str
    load: Callable[[AccessProxy, AsyncCursor], A]
    proxyMethod: Callable[..., Awaitable[object]] = field(init=False)

    def setOn(self, protocolMethod: Any) -> None:
        """
        Attach this QueryMetadata to the given protocol method definition,
        checking its arguments and computing C{proxyMethod} in the process,
        raising L{ParamMismatch} if the expected parameters do not match.
        """
        sig = signature(protocolMethod)
        precomputedSQL: Dict[str, Tuple[str, NameMapMapping]] = {}
        for style, mapFactory in styles.items():
            mapInstance = mapFactory()
            styledSQL = self.sql.format_map(mapInstance)
            precomputedSQL[style] = (styledSQL, mapInstance)

        sampleSQL, sampleInstance = precomputedSQL["qmark"]
        selfExcluded = list(sig.parameters)[1:]
        if set(sampleInstance.names) != set(selfExcluded):
            raise ParamMismatch(
                f"when defining {protocolMethod.__name__}(...), "
                f"SQL placeholders {sampleInstance.names} != "
                f"function params {selfExcluded}"
            )

        def proxyMethod(
            proxySelf: AccessProxy, *args: object, **kw: object
        ) -> Any:
            """
            Implementation of all database-proxy methods on objects returned
            from C{accessor}.

            @note: This should really be two separate methods.  From
                annotations we should know whether to use the aiterable path or
                the awaitable path, we should not need to do the runtime check
                every time.
            """

            maybeai: MaybeAIterable

            async def body() -> Any:
                conn = proxySelf.__query_connection__
                styledSQL, styledMap = precomputedSQL[conn.paramstyle]
                cur = await conn.cursor()
                bound = sig.bind(None, *args, **kw)
                bound.apply_defaults()
                await cur.execute(styledSQL, styledMap.queryArguments(bound))
                maybeAgen: Any = self.load(proxySelf, cur)
                if isawaitable(maybeAgen):
                    # if it's awaitable, then it's not an aiterable.
                    result = await maybeAgen
                    await cur.close()
                    return result
                else:
                    # if it's aiterable, we should be iterating it, not
                    # awaiting it.  MaybeAIterable takes care of the implicit
                    # await of _this_ coroutine.
                    nonlocal maybeai
                    maybeai.cursor = cur
                    return maybeAgen

            maybeai = MaybeAIterable(body())
            return maybeai

        self.proxyMethod = proxyMethod
        setattr(protocolMethod, METADATA_KEY, self)

    @classmethod
    def loadFrom(cls, f: object) -> Optional[QueryMetadata]:
        """
        Load the query metadata for C{f} if it has any.
        """
        self: Optional[QueryMetadata] = getattr(f, METADATA_KEY, None)
        return self

    @classmethod
    def filterProtocolNamespace(
        cls, protocolNamespace: Iterable[Tuple[str, object]]
    ) -> Iterable[Tuple[str, QueryMetadata]]:
        """
        Load all QueryMetadata
        """
        extraneous = []
        for attrname, value in protocolNamespace:
            qm = QueryMetadata.loadFrom(value)
            if qm is None:
                if attrname not in PROTOCOL_IGNORED_ATTRIBUTES:
                    extraneous.append(attrname)
                continue
            yield attrname, qm
        if extraneous:
            raise ExtraneousMethods(
                f"non-query/statement methods defined: {extraneous}"
            )


def query(
    *,
    sql: str,
    load: Callable[[object, AsyncCursor], A],
) -> Callable[[Callable[P, A]], Callable[P, A]]:
    """
    Declare a query method.
    """
    qm = QueryMetadata(sql=sql, load=load)

    def decorator(f: Callable[P, A]) -> Callable[P, A]:
        qm.setOn(f)
        return f

    return decorator


def statement(
    *,
    sql: str,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, None]]],
    Callable[P, Coroutine[Any, Any, None]],
]:
    """
    Declare a query method.
    """
    return query(sql=sql, load=zero)


@dataclass
class DBProxy:
    """
    Database Proxy
    """

    name: str
    transaction: AsyncConnection


@dataclass
class IndexCountingParamstyleMap:
    placeholder: str
    names: List[str] = field(default_factory=list)

    def __getitem__(self, name: str) -> str:
        self.names.append(name)
        return self.placeholder

    def queryArguments(self, bound: BoundArguments) -> Sequence[object]:
        """
        Compute the arguments to the query.
        """
        return [bound.arguments[each] for each in self.names]


class _EmptyProtocol(Protocol):
    """
    Empty protocol for setting a baseline of what attributes to ignore while
    metaprogramming.
    """


PROTOCOL_IGNORED_ATTRIBUTES = set(_EmptyProtocol.__dict__.keys())


class NameMapMapping(Protocol):
    names: List[str]

    def __getitem__(self, __key: str) -> Any:
        ...

    def queryArguments(self, bound: BoundArguments) -> Sequence[object]:
        ...


styles: dict[str, Callable[[], NameMapMapping]] = {
    "qmark": lambda: IndexCountingParamstyleMap("?"),
    "pyformat": lambda: IndexCountingParamstyleMap("%s"),
}


@dataclass
class AccessProxy:
    """
    Superclass of all access proxies.
    """

    __query_connection__: AsyncConnection


def accessor(
    accessPatternProtocol: Callable[[], T]
) -> Callable[[AsyncConnection], T]:
    """
    Create a factory which binds a database transaction in the form of an
    AsyncConnection to a set of declared SQL methods.
    """
    return type(
        f"_{accessPatternProtocol.__name__}_Accessor",
        tuple([AccessProxy]),
        {
            name: metadata.proxyMethod
            for name, metadata in QueryMetadata.filterProtocolNamespace(
                accessPatternProtocol.__dict__.items()
            )
        },
    )
