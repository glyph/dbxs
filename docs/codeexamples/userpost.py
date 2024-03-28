from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, AsyncIterable, Protocol

from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IReactorCore
from twisted.python.failure import Failure

from dbxs import many, one, query, repository, statement
from dbxs.adapters.dbapi_twisted import adaptSynchronousDriver
from dbxs.async_dbapi import transaction


schema = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TIMESTAMP NOT NULL,
    content TEXT NOT NULL,
    author INTEGER NOT NULL,
    FOREIGN KEY(author)
        REFERENCES user(id)
        ON DELETE CASCADE
);
"""


def newConnection() -> sqlite3.dbapi2.Connection:
    result = sqlite3.connect("user-posts.sqlite")
    return result


asyncDriver = adaptSynchronousDriver(
    (lambda: newConnection()), sqlite3.paramstyle
)


# user attributes
@dataclass
class User:
    postDB: PostDB
    id: int
    name: str
    # end user attributes

    async def post(self, text: str) -> None:
        return await self.postDB.makePostByUser(datetime.now(), text, self.id)

    def posts(self) -> AsyncIterable[Post]:
        return self.postDB.postsForUser(self.id)


@dataclass
class Post:
    postDB: PostDB
    created: datetime
    content: str
    id: int
    what: object


class PostDB(Protocol):
    @query(
        sql="""
        insert into user(name)
        values({name})
        returning id, name
        """,
        load=one(User),
    )
    async def createUser(self, name: str) -> User:
        ...

    @query(
        sql="""
        select created, content, author, id
        from post
        where author = {userID}
        """,
        load=many(Post),
    )
    def postsForUser(self, userID: int) -> AsyncIterable[Post]:
        ...

    @statement(
        sql="""
        insert into post( created,   content,   author)
        values          ({created}, {content}, {author})
        """
    )
    async def makePostByUser(
        self, created: datetime, content: str, author: int
    ) -> None:
        ...


@dataclass
class BlogRepo:
    posts: PostDB


blog = repository(BlogRepo)


async def main() -> None:
    async with transaction(asyncDriver) as c:
        cur = await c.cursor()
        for expr in schema.split(";"):
            await cur.execute(expr)

    async with blog(asyncDriver) as db:
        b = await db.posts.createUser("bob")
        await b.post("a post")
        await b.post("another post")
        post: Post
        async for post in b.posts():
            print(post.created, repr(post.content))


if __name__ == "__main__":
    reactor: IReactorCore
    if not TYPE_CHECKING:
        from twisted.internet import reactor

    def reportAndStop(f: Failure | None) -> None:
        reactor.stop()
        if f is not None:
            print(f)
        else:
            return f
        print("STOP")

    reactor.callWhenRunning(
        lambda: (Deferred.fromCoroutine(main()).addBoth(reportAndStop))
    )
    reactor.run()
