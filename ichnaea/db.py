from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy import exc, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import Pool
from sqlalchemy.sql.expression import Insert


_Model = declarative_base()


@compiles(Insert)
def on_duplicate(insert, compiler, **kw):
    s = compiler.visit_insert(insert, **kw)
    if 'on_duplicate' in insert.kwargs:
        return s + " ON DUPLICATE KEY UPDATE " + insert.kwargs['on_duplicate']
    return s


# the request db_sessions and db_tween_factory are inspired by pyramid_tm
# to provide lazy session creation, session closure and automatic
# rollback in case of errors

def db_master_session(request):
    session = getattr(request, '_db_master_session', None)
    if session is None:
        db = request.registry.db_master
        request._db_master_session = session = db.session()
    return session


def db_slave_session(request):
    session = getattr(request, '_db_slave_session', None)
    if session is None:
        db = request.registry.db_slave
        request._db_slave_session = session = db.session()
    return session


@contextmanager
def db_worker_session(database):
    try:
        session = database.session()
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def db_tween_factory(handler, registry):

    def db_tween(request):
        response = handler(request)
        master_session = getattr(request, '_db_master_session', None)
        if master_session is not None:
            # only deal with requests with a session
            if response.status.startswith(('4', '5')):  # pragma: no cover
                # never commit on error
                master_session.rollback()
            master_session.close()
        slave_session = getattr(request, '_db_slave_session', None)

        # The db_master and db_slave will only be the same in the case
        # where we are running on a single node (dev) or under test
        if request.registry.db_master != request.registry.db_slave:
            if slave_session is not None:
                # always rollback/close the `read-only` slave sessions
                try:
                    slave_session.rollback()
                finally:
                    slave_session.close()
        return response

    return db_tween


class Database(object):

    def __init__(self, uri, echo=False, isolation_level='REPEATABLE READ'):
        options = {
            'pool_recycle': 3600,
            'pool_size': 10,
            'pool_timeout': 10,
            'echo': echo,
            # READ COMMITTED
            'isolation_level': isolation_level,
        }
        options['connect_args'] = {'charset': 'utf8'}
        options['execution_options'] = {'autocommit': False}
        self.engine = create_engine(uri, **options)
        event.listen(self.engine, "checkout", check_connection)

        self.session_factory = sessionmaker(
            bind=self.engine, autocommit=False, autoflush=False)

    def session(self):
        return self.session_factory()


@event.listens_for(Pool, "checkout")
def check_connection(dbapi_con, con_record, con_proxy):
    '''
    Listener for Pool checkout events that pings every connection before using.
    Implements pessimistic disconnect handling strategy. See also:
    http://docs.sqlalchemy.org/en/rel_0_9/core/pooling.html#disconnect-handling-pessimistic
    '''

    try:
        # dbapi_con.ping() ends up calling mysql_ping()
        # http://dev.mysql.com/doc/refman/5.0/en/mysql-ping.html
        dbapi_con.ping()
    except exc.OperationalError as ex:
        if ex.args[0] in (2003,     # Connection refused
                          2006,     # MySQL server has gone away
                          2013,     # Lost connection to MySQL server
                                    # during query
                          2055):    # Lost connection to MySQL server at '%s',
                                    # system error: %d
            # caught by pool, which will retry with a new connection
            raise exc.DisconnectionError()
        else:
            raise
