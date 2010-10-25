from __future__ import with_statement

from fabric.api import run, put, sudo, env, cd, local, prompt, settings
from fabric.contrib import files
from louis import conf


def create_postgres_user(username, password):
    """
    Creates a plain postgres user: nosuperuser, nocreaterole, createdb.
    """
    psql_string = "CREATE ROLE %s PASSWORD '%s' NOSUPERUSER CREATEDB NOCREATEROLE INHERIT LOGIN;" % (username, password)
    sudo('echo "%s" | psql' % psql_string, user='postgres')


def delete_postgres_user(username):
    """
    Deletes a postgres user.
    """
    sudo('dropuser %s' % username, user='postgres')


def create_postgres_db(owner, dbname):
    """
    Creates a postgres database given its owner (a postgres user) and the name
    of the database.
    """
    sudo('createdb -E UTF8 -T template0 -O %s %s' % (owner, dbname), user='postgres')

def drop_postgres_db(dbname):
    """
    Drops a postgres database.
    """
    sudo('dropdb %s' % dbname, user='postgres')
