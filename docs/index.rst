.. DBXS documentation master file, created by
   sphinx-quickstart on Tue Aug  8 00:06:45 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root toctree directive.

DataBase Acc(X)esS
================================

DBXS is a **query organizer**.

It provides a simple structure for collecting a group of queries into a set of
methods which can be executed against a database, and to describe a way to
process the results of those queries into a data structure.

The Problem
===========

In a programming language, there are several interfaces by which one might
access a database.  Ordered from low-level to high-level, they are:

1. a *database driver*, which presents an interface that accepts strings of SQL
   and parameters, and allows you to access a database.

2. an *SQL expression model*, like `SQLAlchemy Core
   <https://docs.sqlalchemy.org/en/20/core/>`_, which presents an abstract
   syntax tree, but maintains the semantics of SQL

3. an *Object Relational Mapper*, like `SQLAlchemy ORM
   <https://docs.sqlalchemy.org/en/20/orm/index.html>`_.

While ORMs and expression models can be powerful tools, they require every
developer using them to translate any database operations from the SQL that
they already know to a new, slightly different language.

However, using a database driver directly can be error-prone.  One of the
biggest problems with databases today remains `SQL injection
<https://owasp.org/Top10/A03_2021-Injection/>`_.  And when you are passing
strings directly do a database driver, even if you know that you need to be
careful to pass all your inputs as parameters, there is no structural mechanism
in your code to prevent you from forgetting that for a moment and accidentally
formatting a string.

Plus, it can be difficult to see all the ways that your database is being
queried if they're spread out throughout your code.  This can make it hard to
see, for example, what indexes might be useful to create, without combing
through database logs.


DBXS's solution
===============

To access a database with DBXS, you write a Python protocol that describes all
of the queries that your database can perform.  Let's begin with the database
interface for a very simple blog, where users can sign up, make posts, and then
read their posts.

.. literalinclude:: codeexamples/no_db_yet_userpost.py

We have a ``User`` record class, a ``Post`` record class, and a ``PostDB``
protocol that allows us to create users, list posts for users, and make posts.

First, let's fill out that ``User`` class.  We'll make it a ``dataclass``.
Record classes will need some way to refer back to their database, so it will
have a ``PostDB`` as its first attribute, then an integer ``id`` and a string
``name``.

.. literalinclude:: codeexamples/userpost.py
   :start-after: # user attributes
   :end-before: # end user attributes


.. toctree::
   :maxdepth: 2
   :caption: Table of Contents:

   howto

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
