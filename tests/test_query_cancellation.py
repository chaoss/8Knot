"""Live PostgreSQL regression checks; run with QUERY_TEST_DSN set to a test database."""

import importlib
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from uuid import uuid4

import psycopg2 as pg
from psycopg2 import sql
import sqlalchemy as salc

APP_PATH = str(Path(__file__).resolve().parents[1] / "8Knot")


class QueryCancellationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.getenv("QUERY_TEST_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("Set QUERY_TEST_DSN to run database-backed tests")
        credentials = pg.extensions.parse_dsn(cls.dsn)
        cls.environment = patch.dict(
            os.environ,
            {
                "AUGUR_HOST": credentials["host"],
                "AUGUR_PORT": credentials.get("port", "5432"),
                "AUGUR_DATABASE": credentials["dbname"],
                "AUGUR_USERNAME": credentials["user"],
                "AUGUR_PASSWORD": credentials["password"],
                "COLLECTOSS_STATEMENT_TIMEOUT_MS": "1000",
                "COLLECTOSS_ENGINE_STATEMENT_TIMEOUT_MS": "1500",
                "COLLECTOSS_IDLE_TX_TIMEOUT_MS": "2000",
            },
        )
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        cls.cf = importlib.import_module("cache_manager.cache_facade")
        cls.manager_class = importlib.import_module("db_manager.collectoss_manager").CollectOSSManager
        cls.celery_app = importlib.import_module("_celery").celery_app
        cls.observer = pg.connect(cls.dsn)
        cls.observer.autocommit = True
        cls.addClassCleanup(cls.observer.close)

    def execute(self, query, parameters=None):
        with self.observer.cursor() as cursor:
            cursor.execute(query, parameters)
            if cursor.description:
                return cursor.fetchall()

    def setUp(self):
        self.schema = f"query_test_{uuid4().hex}"
        self.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"AUGUR_SCHEMA": self.schema}))
        self.worker = self.manager_class(worker_query=True)
        stack.callback(lambda: self.worker.engine.dispose() if self.worker.engine else None)
        stack.enter_context(patch.object(self.cf, "collectoss", self.worker))
        stack.enter_context(
            patch.object(self.cf, "cache_cx_string", f"{self.dsn} options='-c search_path={self.schema}'")
        )
        self.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        self.execute("CREATE TABLE query_cache (repo_id integer, value integer PRIMARY KEY)")
        self.execute("CREATE TABLE cache_bookkeeping (cache_func text, repo_id integer)")

    def test_connection_settings_and_pool_reuse(self):
        app_manager = self.manager_class()
        self.addCleanup(lambda: app_manager.engine.dispose() if app_manager.engine else None)
        for manager, timeout in ((self.worker, "1s"), (app_manager, "1500ms")):
            with manager.get_engine().connect() as connection:
                self.assertEqual(connection.exec_driver_sql("SHOW statement_timeout").scalar_one(), timeout)
                self.assertEqual(connection.exec_driver_sql("SHOW search_path").scalar_one(), self.schema)
                self.assertEqual(
                    connection.exec_driver_sql("SHOW idle_in_transaction_session_timeout").scalar_one(), "2s"
                )
                pid = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            with manager.get_engine().connect() as connection:
                self.assertEqual(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one(), pid)
        self.assertEqual(self.worker.engine.pool.checkedout(), 0)

    def test_streaming_and_bookkeeping(self):
        cursors = []

        def observe_cursor(connection, cursor, statement, parameters, context, executemany):
            cursors.append(cursor.name)

        salc.event.listen(self.worker.get_engine(), "after_cursor_execute", observe_cursor)
        with patch.object(self.cf, "execute_values", wraps=self.cf.execute_values) as insert:
            self.cf.caching_wrapper(
                "query_cache",
                "SELECT 1, x FROM generate_series(1, 5001) AS x WHERE 1 IN %s AND 1 IN %s",
                [1],
                n_repolist_uses=2,
            )
            batches = [len(call.kwargs["argslist"]) for call in insert.call_args_list]
        self.assertTrue(cursors and all(cursors), "Source query must use a named, server-side cursor")
        self.assertEqual(batches, [2000, 2000, 1001, 1])
        self.assertEqual(self.execute("SELECT count(*) FROM query_cache"), [(5001,)])
        self.assertEqual(self.execute("SELECT * FROM cache_bookkeeping"), [("query_cache", 1)])
        self.assertEqual(self.worker.engine.pool.checkedout(), 0)

    def test_mid_stream_timeout_rolls_back_without_retry(self):
        self.worker.statement_timeout_ms = "100"

        @self.celery_app.task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 5})
        def slow_query():
            self.cf.caching_wrapper(
                "query_cache",
                """SELECT 1, x FROM generate_series(1, 2001) AS x
                   CROSS JOIN LATERAL pg_sleep(CASE WHEN x = 2001 THEN 1 ELSE 0 END)
                   WHERE 1 IN %s""",
                [1],
            )

        with (
            patch.object(slow_query, "retry") as retry,
            patch.object(self.cf, "execute_values", wraps=self.cf.execute_values) as insert,
        ):
            with self.assertLogs(level="ERROR"), self.assertRaises(pg.errors.QueryCanceled):
                slow_query.run()
            retry.assert_not_called()
            self.assertEqual(len(insert.call_args_list[0].kwargs["argslist"]), 2000)
        self.assertEqual(self.execute("SELECT count(*) FROM query_cache"), [(0,)])
        self.assertEqual(self.execute("SELECT count(*) FROM cache_bookkeeping"), [(0,)])
        self.assertEqual(self.worker.engine.pool.checkedout(), 0)
        with self.worker.get_engine().connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT 1").scalar_one(), 1)

    @unittest.skipUnless(hasattr(os, "fork"), "Requires a prefork worker platform")
    def test_fork_does_not_reuse_parent_connection(self):
        with self.worker.get_engine().connect() as connection:
            parent_backend = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        reader, writer = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(reader)
            try:
                with self.worker.get_engine().connect() as connection:
                    backend = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                os.write(writer, str(backend).encode())
                self.worker.engine.dispose()
            finally:
                os._exit(0)
        os.close(writer)
        try:
            child_backend = int(os.read(reader, 32))
        finally:
            os.close(reader)
            os.waitpid(child, 0)
        self.assertNotEqual(parent_backend, child_backend)
        with self.worker.get_engine().connect() as connection:
            self.assertEqual(connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one(), parent_backend)

    def test_killed_client_query_is_reclaimed(self):
        code = """
from db_manager.collectoss_manager import CollectOSSManager
with CollectOSSManager(worker_query=True).get_engine().connect() as connection:
    print(connection.exec_driver_sql('SELECT pg_backend_pid()').scalar_one(), flush=True)
    connection.exec_driver_sql('SELECT pg_sleep(60)')
"""
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": APP_PATH,
                "COLLECTOSS_STATEMENT_TIMEOUT_MS": "30000",
            },
        )
        try:
            backend = int(process.stdout.readline())
            self.addCleanup(
                self.execute, "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = %s", (backend,)
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.execute("SELECT wait_event FROM pg_stat_activity WHERE pid = %s", (backend,)) == [("PgSleep",)]:
                    break
                time.sleep(0.05)
            else:
                self.fail("Child query never started")
            process.kill()
            process.wait(timeout=5)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if not self.execute("SELECT pid FROM pg_stat_activity WHERE pid = %s", (backend,)):
                    return
                time.sleep(0.1)
            self.fail("Killed client's query survived the 10-second disconnect-check interval")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
