"""Search regression tests using a disposable database on a PostgreSQL test server.

Install application dependencies, then run:
    PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=... python scripts/ci/search_test.py

The role needs CREATEDB. Only the generated database is modified. The real DDL,
search SQL, CollectOSS manager, and callbacks run; Redis/session state is mocked.
"""

import importlib
import json
import logging
import os
import runpy
import sys
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import dash
import psycopg2 as pg
from celery import Celery
from psycopg2 import sql
from sqlalchemy.exc import SQLAlchemyError


APP_ROOT = Path(__file__).resolve().parents[2] / "8Knot"


class SearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = f"search_test_{uuid.uuid4().hex}"
        with closing(pg.connect(dbname="postgres")) as conn:
            params = conn.get_dsn_parameters()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.database)))
        cls.addClassCleanup(cls.drop_database)

        environment = patch.dict(
            os.environ,
            {
                "AUGUR_USERNAME": params["user"],
                "AUGUR_PASSWORD": os.getenv("PGPASSWORD", ""),
                "AUGUR_HOST": params["host"],
                "AUGUR_PORT": params["port"],
                "AUGUR_DATABASE": cls.database,
                "AUGUR_SCHEMA": "augur_data",
                "AUGUR_LOGIN_ENABLED": "False",
                "CACHE_DB_NAME": cls.database,
                "CACHE_HOST": params["host"],
                "CACHE_PORT": params["port"],
                "CACHE_USER": params["user"],
                "POSTGRES_PASSWORD": os.getenv("PGPASSWORD", ""),
                "DEBUG_8KNOT": "False",
            },
        )
        environment.start()
        cls.addClassCleanup(environment.stop)
        sys.path[:0] = [str(APP_ROOT), str(APP_ROOT / "cache_manager")]
        cls.cf = importlib.import_module("cache_manager.cache_facade")
        importlib.import_module("db_init")._create_application_tables()
        cls.CollectOSSManager = importlib.import_module("db_manager.augur_manager").AugurManager
        cls.engine = cls.CollectOSSManager().get_engine()
        cls.addClassCleanup(cls.engine.dispose)

        cls.query("CREATE SCHEMA augur_data")
        cls.query("CREATE TABLE augur_data.repo_groups (repo_group_id int PRIMARY KEY, rg_name text)")
        cls.query("CREATE TABLE augur_data.repo (repo_id int, repo_git text, repo_name text, repo_group_id int)")

        # Import the actual callbacks without booting the application or a Celery worker.
        stub_app = ModuleType("app")
        stub_app.augur = None
        stub_app.celery_app = Celery("search_test", broker="memory://")
        with patch.dict(sys.modules, {"app": stub_app}):
            cls.callbacks = importlib.import_module("pages.index.index_callbacks")
        from pages.index.search_utils import create_search_input_section

        cls.dash_app = dash.Dash(__name__, suppress_callback_exceptions=True)
        cls.dash_app.layout = create_search_input_section({"value": "chaoss", "label": "org: CHAOSS"})

    @classmethod
    def drop_database(cls):
        with closing(pg.connect(dbname="postgres")) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(cls.database)))

    @classmethod
    def query(cls, statement, params=None):
        with closing(pg.connect(dbname=cls.database)) as conn:
            with conn, conn.cursor() as cur:
                cur.execute(statement, params)
                return cur.fetchall() if cur.description else None

    def setUp(self):
        self.query("TRUNCATE search_options, augur_data.repo, augur_data.repo_groups")
        self.query("INSERT INTO augur_data.repo_groups VALUES (1, 'CHAOSS'), (2, 'kubernetes')")
        self.query(
            """INSERT INTO augur_data.repo VALUES
            (1, 'https://github.com/chaoss/collectoss', 'collectoss', 1),
            (2, 'https://github.com/chaoss/collectoss-utils', 'collectoss-utils', 1),
            (3, 'https://github.com/kubernetes/kubernetes', 'kubernetes', 2)"""
        )
        self.collectoss = self.CollectOSSManager()
        self.collectoss.engine = self.engine
        self.collectoss.multiselect_startup()
        self.options = self.collectoss.get_multiselect_options()
        self.cf.sync_search_options(self.options)
        self.current_options = [{"value": "chaoss", "label": "org: CHAOSS"}]
        for name, value in (("collectoss", self.collectoss), ("current_user", SimpleNamespace(is_authenticated=False))):
            replacement = patch.object(self.callbacks, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def search(self, text, selections=None, current_options=None):
        return self.callbacks.dynamic_multiselect_options(
            text,
            ["chaoss"] if selections is None else selections,
            self.current_options if current_options is None else current_options,
        )

    def values(self, text, item_type=None):
        return [option["value"] for option in self.cf.search_options_query(text, item_type)]

    def add_new_org(self):
        self.query("INSERT INTO augur_data.repo_groups VALUES (3, 'BrandNewTeam')")
        self.query("INSERT INTO augur_data.repo VALUES (4, 'https://github.com/brandnewteam/project', 'project', 3)")
        newer_process = self.CollectOSSManager()
        newer_process.engine = self.engine
        newer_process.multiselect_startup()
        self.cf.sync_search_options(newer_process.get_multiselect_options())

    def test_newly_published_org_resolves_on_older_web_process(self):
        self.add_new_org()
        self.assertFalse(self.collectoss.is_org("brandnewteam"))
        self.assertIn("brandnewteam", self.values("brandnewteam", "org"))
        self.assertEqual(
            self.callbacks.multiselect_values_to_repo_ids(1, ["brandnewteam"]), ("", [4], ["brandnewteam"])
        )
        is_open, elements = self.callbacks.show_repolist_alert(1, False, [4])
        self.assertTrue(is_open)
        self.assertEqual(elements[1].children[0].children, "github.com/brandnewteam/project")

    def test_other_process_loads_repo_labels_in_one_batch(self):
        other_process = self.CollectOSSManager()
        other_process.engine = self.engine
        other_process.multiselect_startup()
        self.add_new_org()
        with patch.object(self.engine, "connect", wraps=self.engine.connect) as connect:
            self.assertEqual(
                other_process.repo_ids_to_git([4, 1, 4, 999]),
                [
                    "https://github.com/brandnewteam/project",
                    "https://github.com/chaoss/collectoss",
                    "https://github.com/brandnewteam/project",
                    "Repository 999",
                ],
            )
            self.assertEqual(connect.call_count, 1)
        with patch.object(self.engine, "connect") as connect:
            self.assertEqual(other_process.repo_id_to_git(4), "https://github.com/brandnewteam/project")
            connect.assert_not_called()

    def test_unavailable_repo_labels_keep_usable_ids(self):
        with (
            patch.object(self.engine, "connect", side_effect=SQLAlchemyError("offline")),
            self.assertLogs(level="ERROR"),
        ):
            self.assertEqual(self.collectoss.repo_ids_to_git([999]), ["Repository 999"])

    def test_changed_org_membership_uses_current_source(self):
        self.query("DELETE FROM augur_data.repo WHERE repo_id = 2")
        self.assertEqual(self.callbacks.multiselect_values_to_repo_ids(1, ["chaoss"]), ("", [1], ["chaoss"]))

    def test_missing_selection_keeps_previous_repo_choices(self):
        message, choices, applied = self.callbacks.multiselect_values_to_repo_ids(1, ["removed-org", "1"])
        self.assertTrue(message)
        self.assertIs(choices, dash.no_update)
        self.assertIs(applied, dash.no_update)

    def test_source_error_does_not_dispatch_partial_selection(self):
        with (
            patch.object(self.engine, "connect", side_effect=SQLAlchemyError("source unavailable")),
            self.assertLogs(level="ERROR"),
        ):
            message, choices, applied = self.callbacks.multiselect_values_to_repo_ids(1, ["chaoss", "3"])
        self.assertTrue(message)
        self.assertIs(choices, dash.no_update)
        self.assertIs(applied, dash.no_update)

    def test_repo_only_selection_does_not_query_collectoss(self):
        with patch.object(self.engine, "connect") as connect:
            self.assertEqual(self.callbacks.multiselect_values_to_repo_ids(1, ["1"]), ("", [1], ["1"]))
            connect.assert_not_called()

    def test_private_group_and_public_org_selection(self):
        self.callbacks.current_user = SimpleNamespace(is_authenticated=True, get_id=lambda: "alice")
        users_cache = Mock()
        users_cache.get.return_value = json.dumps({"tooling": [3]})
        with patch.object(self.callbacks.redis, "StrictRedis", return_value=users_cache):
            message, choices, applied = self.callbacks.multiselect_values_to_repo_ids(1, ["chaoss", "tooling"])
        self.assertEqual(message, "")
        self.assertEqual(set(choices), {1, 2, 3})
        self.assertEqual(applied, ["chaoss", "tooling"])

    def test_public_selection_skips_private_membership_lookup(self):
        self.callbacks.current_user = SimpleNamespace(is_authenticated=True, get_id=lambda: "alice")
        with patch.object(self.callbacks.redis, "StrictRedis") as users_cache:
            result = self.callbacks.multiselect_values_to_repo_ids(1, ["chaoss"])
        self.assertEqual(set(result[1]), {1, 2})
        users_cache.assert_not_called()

    def test_private_group_timeout_keeps_previous_choices(self):
        self.callbacks.current_user = SimpleNamespace(is_authenticated=True, get_id=lambda: "alice")
        users_cache = Mock()
        users_cache.get.side_effect = self.callbacks.redis.exceptions.TimeoutError("offline")
        with (
            patch.object(self.callbacks.redis, "StrictRedis", return_value=users_cache),
            self.assertLogs(level="ERROR"),
        ):
            message, choices, applied = self.callbacks.multiselect_values_to_repo_ids(1, ["tooling"])
        self.assertTrue(message)
        self.assertIs(choices, dash.no_update)
        self.assertIs(applied, dash.no_update)

    def test_org_names_are_bound_sql_parameters(self):
        self.assertEqual(self.collectoss.resolve_org_repos(["'; DROP TABLE repo; --", "chaoss"]), {"chaoss": [1, 2]})
        self.assertEqual(self.query("SELECT count(*) FROM augur_data.repo"), [(3,)])

    def test_failed_startup_sync_is_fatal_even_with_old_rows(self):
        importlib.import_module("pages.landing")
        landing = ModuleType("pages.landing.landing_callbacks")
        with (
            patch("db_manager.augur_manager.AugurManager", return_value=self.collectoss),
            patch.object(self.cf, "sync_search_options", side_effect=pg.OperationalError("sync unavailable")),
            patch.dict(sys.modules, {"pages.landing.landing_callbacks": landing}),
            patch("dash.Dash", side_effect=AssertionError("Application started after failed synchronization")),
            self.assertLogs(level="ERROR"),
        ):
            with self.assertRaises(pg.OperationalError):
                runpy.run_path(str(APP_ROOT / "app.py"), run_name="search_startup_test")
        self.assertEqual(self.query("SELECT count(*) FROM search_options"), [(5,)])

    def test_repo_prefix_preserves_selected_private_group_label(self):
        self.callbacks.current_user = SimpleNamespace(is_authenticated=True, get_id=lambda: "alice")
        selected = [{"value": "tooling", "label": "org: alice: Tooling"}]
        result = self.search("repo:collectoss", ["tooling"], selected)[0]
        self.assertIn(selected[0], result)

    def test_dash_request_preserves_selected_labels(self):
        selected = [{"value": "tooling", "label": "org: alice: Tooling"}]
        response = self.dash_app.server.test_client().post(
            "/_dash-update-component",
            json={
                "output": "..projects.data...projects.nothingFoundMessage..",
                "outputs": [
                    {"id": "projects", "property": "data"},
                    {"id": "projects", "property": "nothingFoundMessage"},
                ],
                "changedPropIds": ["projects.searchValue"],
                "inputs": [{"id": "projects", "property": "searchValue", "value": "repo:collectoss"}],
                "state": [
                    {"id": "projects", "property": "value", "value": ["tooling"]},
                    {"id": "projects", "property": "data", "value": selected},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        props = response.get_json()["response"]["projects"]
        self.assertIn(selected[0], props["data"])
        self.assertEqual(props["nothingFoundMessage"], "No matching repos/orgs.")

    def test_search_failure_preserves_labels_and_reports_unavailability(self):
        selected = [{"value": "tooling", "label": "org: alice: Tooling"}]
        with (
            patch.object(self.cf, "search_options_query", side_effect=pg.OperationalError("offline")),
            self.assertLogs(level="ERROR"),
        ):
            result, message = self.search("collectoss", ["tooling"], selected)
        self.assertEqual(result, selected)
        self.assertIn("unavailable", message.lower())

    def test_failed_confirmation_feedback_is_in_search_controls(self):
        client = self.dash_app.server.test_client()
        layout = client.get("/_dash-layout").get_json()
        feedback = next(child for child in layout["props"]["children"] if child["props"].get("id") == "selection-error")
        self.assertEqual(feedback["props"]["role"], "alert")
        self.assertNotEqual(feedback["props"].get("style", {}).get("display"), "none")
        response = client.post(
            "/_dash-update-component",
            json={
                "output": "..selection-error.children...repo-choices.data...applied-projects.data..",
                "outputs": [
                    {"id": "selection-error", "property": "children"},
                    {"id": "repo-choices", "property": "data"},
                    {"id": "applied-projects", "property": "data"},
                ],
                "changedPropIds": ["search-button.n_clicks"],
                "inputs": [{"id": "search-button", "property": "n_clicks", "value": 1}],
                "state": [{"id": "projects", "property": "value", "value": ["removed-org"]}],
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        updates = response.get_json()["response"]
        self.assertIn("selection-error", updates)
        self.assertNotIn("repo-choices", updates)
        self.assertNotIn("applied-projects", updates)

    def test_pills_follow_successful_confirmation_not_click_or_stale_response(self):
        self.assertEqual(self.callbacks.update_pill_color_on_search([], ["chaoss"]), "searchbar-dropdown")
        self.assertEqual(
            self.callbacks.update_pill_color_on_search(["chaoss"], ["chaoss"]), "searchbar-dropdown searching"
        )
        self.assertEqual(self.callbacks.update_pill_color_on_search(["chaoss"], ["kubernetes"]), "searchbar-dropdown")

    def test_selection_labels_do_not_scan_full_catalog(self):
        with patch.object(self.collectoss, "get_multiselect_options", side_effect=AssertionError("full catalog scan")):
            result = self.search("kubernetes")[0]
        self.assertIn(self.current_options[0], result)

    def test_empty_index_is_rebuilt_but_no_match_is_not(self):
        self.query("TRUNCATE search_options")
        self.assertIn("1", [option["value"] for option in self.search("collectoss")[0]])
        with patch.object(self.cf, "sync_search_options") as sync:
            result, message = self.search("zzzzzzzzzzzzzzzzzzz", [])
        self.assertEqual(result, [])
        self.assertEqual(message, "No matching repos/orgs.")
        sync.assert_not_called()

    def test_exact_url_prefix_typo_and_separator_matching(self):
        for text in ("chaoss/collectoss", "HTTPS://GitHub.com/chaoss/collectoss", "chaoss / collectoss"):
            with self.subTest(text=text):
                self.assertEqual(self.values(text)[0], "1")
        self.assertIn("2", self.values("collectoss ut"))
        self.assertIn("1", self.values("co"))
        self.assertIn("3", self.values("kubrnetes"))

    def test_type_filters_and_exact_repo_name_ranking(self):
        self.cf.sync_search_options(self.options + [{"value": "9", "label": "https://github.com/collectoss/longname"}])
        self.assertEqual(self.values("chaoss", "org"), ["chaoss"])
        values = self.values("collectoss", "repo")
        self.assertLess(values.index("1"), values.index("9"))
        self.assertTrue(all(value.isnumeric() for value in values))

    def test_result_cap_and_parameter_safety(self):
        self.cf.sync_search_options(
            [{"value": str(i), "label": f"https://github.com/test/repo{i}"} for i in range(120)]
        )
        self.assertEqual(len(self.values("test")), 100)
        for query in ("%", "_", "\\", "---", "x'; DROP TABLE search_options; --", "café"):
            self.values(query)
        self.assertEqual(self.query("SELECT count(*) FROM search_options"), [(120,)])

    def test_sync_is_idempotent_and_deletes_stale_rows(self):
        before = self.query("SELECT value, xmin::text, ctid::text FROM search_options ORDER BY value")
        self.cf.sync_search_options(self.options)
        self.assertEqual(self.query("SELECT value, xmin::text, ctid::text FROM search_options ORDER BY value"), before)
        self.cf.sync_search_options([{"value": "1", "label": "first"}, {"value": "1", "label": "last"}])
        self.assertEqual(self.query("SELECT value, label FROM search_options"), [("1", "last")])


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    unittest.main()
