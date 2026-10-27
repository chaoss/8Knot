"""
Testing utilities for 8Knot application.

This module provides utilities to instrument the application for better
error detection during CI/CD testing.
"""

import os
import sys
import logging
import traceback
from functools import wraps


# Configure logging for testing
def setup_testing_logging():
    """Configure logging to be more descriptive during testing."""
    if os.getenv("DEBUG_8KNOT", "False") == "True":
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stdout), logging.StreamHandler(sys.stderr)],
        )

        # Set specific loggers
        logging.getLogger("dash").setLevel(logging.DEBUG)
        logging.getLogger("werkzeug").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def fail_fast_on_error(func):
    """
    Decorator that causes the application to exit immediately on errors
    during testing.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if os.getenv("DEBUG_8KNOT", "False") == "True":
                logging.error(f"CRITICAL ERROR in {func.__name__}: {str(e)}")
                logging.error(f"Traceback: {traceback.format_exc()}")

                # In testing mode, exit immediately on critical errors
                if os.getenv("CI", "False") == "True":
                    logging.error("Exiting due to critical error in CI environment")
                    sys.exit(1)
            raise

    return wrapper


def check_required_services():
    """
    Check that all required services are available.
    This function can be called during application startup to ensure
    all dependencies are properly configured.
    """
    checks = []

    # Check environment variables
    required_env_vars = [
        "AUGUR_DATABASE",
        "AUGUR_HOST",
        "AUGUR_PASSWORD",
        "AUGUR_USERNAME",
        "REDIS_PASSWORD",
        "POSTGRES_PASSWORD",
    ]

    for var in required_env_vars:
        if not os.getenv(var):
            checks.append(f"Missing required environment variable: {var}")

    # Check database connectivity (if CollectOSS manager is available)
    try:
        from db_manager.collectoss_manager import CollectOSSManager

        augur = CollectOSSManager()
        engine = augur.get_engine()
        with engine.connect() as conn:
            # opening the connection tests if database is reachable
            pass
        checks.append("Database connection: OK")
    except Exception as e:
        checks.append(f"Database connection failed: {str(e)}")

    # Check Postgres cache connectivity
    try:
        import psycopg2 as pg
        from cache_manager.cx_common import cache_cx_string

        with pg.connect(cache_cx_string) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        checks.append("Postgres cache connection: OK")
    except Exception as e:
        checks.append(f"Postgres cache connection failed: {str(e)}")

    return checks


def log_service_status():
    """Log the status of all required services."""
    logging.info("=== Service Status Check ===")
    checks = check_required_services()
    for check in checks:
        if "failed" in check.lower() or "missing" in check.lower():
            logging.error(check)
        else:
            logging.info(check)
    logging.info("=== End Service Status ===")


def validate_visualization_data(data, visualization_name):
    """
    Validate that visualization data is properly formatted.
    """
    if data is None:
        logging.warning(f"No data available for visualization: {visualization_name}")
        return False

    if hasattr(data, "empty") and data.empty:
        logging.warning(f"Empty dataset for visualization: {visualization_name}")
        return False

    if hasattr(data, "__len__") and len(data) == 0:
        logging.warning(f"Empty data for visualization: {visualization_name}")
        return False

    logging.debug(f"Data validation passed for visualization: {visualization_name}")
    return True


# Initialize testing utilities if in debug mode
if os.getenv("DEBUG_8KNOT", "False") == "True":
    setup_testing_logging()
    logging.info("Testing utilities initialized")
