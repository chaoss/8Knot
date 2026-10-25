import os

# Set dummy environment variables required by cache_manager.cx_common at import time
os.environ.setdefault("AUGUR_DATABASE", "test_augur")
os.environ.setdefault("AUGUR_HOST", "localhost")
os.environ.setdefault("AUGUR_PASSWORD", "test_pass")
os.environ.setdefault("AUGUR_PORT", "5432")
os.environ.setdefault("AUGUR_USERNAME", "test_user")

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import cache_manager.cache_facade as cf


def test_get_uncached_empty_repolist():
    """Verify get_uncached returns empty list immediately for empty or None repolist."""
    with patch("cache_manager.cache_facade.pg.connect") as mock_connect:
        assert cf.get_uncached("test_func", []) == []
        assert cf.get_uncached("test_func", None) == []
        mock_connect.assert_not_called()


def test_get_uncached_success():
    """Verify get_uncached queries bookkeeping and closes connection properly."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.return_value = [(101,)]

    with patch("cache_manager.cache_facade.pg.connect", return_value=mock_conn):
        uncached = cf.get_uncached("test_func", [101, 102])

    assert uncached == [102]
    mock_conn.close.assert_called_once()
    mock_cur.execute.assert_called_once()


def test_retrieve_from_cache_empty_repolist():
    """Verify retrieve_from_cache returns empty DataFrame immediately for empty or None repolist."""
    with patch("cache_manager.cache_facade.pg.connect") as mock_connect:
        df_empty = cf.retrieve_from_cache("test_table", [])
        assert isinstance(df_empty, pd.DataFrame)
        assert df_empty.empty

        df_none = cf.retrieve_from_cache("test_table", None)
        assert isinstance(df_none, pd.DataFrame)
        assert df_none.empty

        mock_connect.assert_not_called()


def test_retrieve_from_cache_success():
    """Verify retrieve_from_cache formats query with Identifier, extracts data, and closes connection."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.description = [("repo_id",), ("commit_count",)]
    mock_cur.fetchall.return_value = [(101, 42), (102, 17)]

    with patch("cache_manager.cache_facade.pg.connect", return_value=mock_conn):
        df = cf.retrieve_from_cache("test_table", [101, 102])

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["repo_id", "commit_count"]
    mock_conn.close.assert_called_once()


def test_wait_for_cache_empty_repolist():
    """Verify wait_for_cache returns immediately for empty or None repolist."""
    with patch("cache_manager.cache_facade.get_uncached") as mock_get_uncached:
        cf.wait_for_cache("test_func", [])
        cf.wait_for_cache("test_func", None)
        mock_get_uncached.assert_not_called()


def test_wait_for_cache_success():
    """Verify wait_for_cache loops until get_uncached returns empty list."""
    with patch("cache_manager.cache_facade.get_uncached", side_effect=[[101], []]):
        with patch("time.sleep") as mock_sleep:
            cf.wait_for_cache("test_func", [101], timeout=10)
            mock_sleep.assert_called_once()


def test_wait_for_cache_timeout():
    """Verify wait_for_cache raises TimeoutError when deadline is exceeded."""
    with patch("cache_manager.cache_facade.get_uncached", return_value=[101]):
        with patch("time.sleep"):
            with pytest.raises(TimeoutError, match="timed out"):
                cf.wait_for_cache("test_func", [101], timeout=0.01)


def test_caching_wrapper_empty_repolist():
    """Verify caching_wrapper returns early without executing queries when repolist is empty."""
    with (
        patch("cache_manager.cache_facade.get_uncached") as mock_get_uncached,
        patch("cache_manager.cache_facade.cache_query_results") as mock_cqr,
    ):
        cf.caching_wrapper("test_func", "SELECT 1;", [])
        cf.caching_wrapper("test_func", "SELECT 1;", None)
        mock_get_uncached.assert_not_called()
        mock_cqr.assert_not_called()
