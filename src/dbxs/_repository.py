# -*- test-case-name: dbxs.test.test_access.AccessTestCase.test_repository -*-
"""
A repository combines a collection of accessors.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from inspect import signature
from typing import AsyncContextManager, AsyncIterator, Callable, TypeVar

from ._access import accessor
from .async_dbapi import AsyncConnectable, transaction


T = TypeVar("T")


def repository(
    repositoryType: type[T],
) -> Callable[[AsyncConnectable], AsyncContextManager[T]]:
    """
    A L{repository} combines management of a transaction with management of a
    "repository", which is a collection of L{accessor}s and a contextmanager
    that manages a transaction.  This is easier to show with an example than a
    description::

        class Users(Protocol):
            @query(sql="...", load=one(User))
            def getUserByID(self, id: UserID) -> User: ...

        class Posts(Protocol):
            @query(sql="...", load=many(Post))
            def getPostsFromUser(self, id: UserID) -> AsyncIterator[Posts]: ...

        @dataclass
        class BlogDB:
            users: Users
            posts: Posts

        blogRepository = repository(BlogDB)

        # ...
        async def userAndPosts(pool: AsyncConnectable, id: UserID) -> str:
            async with blogRepository(pool) as blog:
                user = await blog.users.getUserByID(id)
                posts = await blog.posts.getPostsFromUser(posts)
                # transaction commits here
    """

    sig = signature(repositoryType)
    accessors = {}
    for name, parameter in sig.parameters.items():  # pragma: no branch
        annotation = parameter.annotation
        # It would be nicer to do this with signature(..., eval_str=True), but
        # that's not available until we require python>=3.10
        if isinstance(annotation, str):  # pragma: no branch
            annotation = eval(
                annotation, sys.modules[repositoryType.__module__].__dict__
            )
        accessors[name] = accessor(annotation)

    @asynccontextmanager
    async def transactify(acxn: AsyncConnectable) -> AsyncIterator[T]:
        kw = {}
        async with transaction(acxn) as aconn:
            for name in accessors:  # pragma: no branch
                kw[name] = accessors[name](aconn)
            yield repositoryType(**kw)

    return transactify
