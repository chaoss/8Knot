"""
Connection Common file - accessing environment variables
"""

import os
import time

from psycopg2.extensions import make_dsn

# credentials to access application cache from environment
env_dbname = os.getenv("CACHE_DB_NAME", "augur_cache")
# TODO: define best default for openshift and docker compose
# env_host = os.getenv("CACHE_HOST", "eightknot-postgres-cache")
env_host = os.getenv("CACHE_HOST", "postgres-cache")
env_user = os.getenv("CACHE_USER", "postgres")
env_password = os.getenv("POSTGRES_PASSWORD", "password")
env_port = os.getenv("CACHE_PORT", "5432")
env_schema = os.getenv("CACHE_SCHEMA", "data,augur_data")


# purely initial startup string
# psycopg2 connection string for cache pg instance, initialization only
init_cx_string = make_dsn(
    dbname="postgres",
    user=env_user,
    password=env_password,
    host=env_host,
    port=env_port,
)

# psycopg2 connection string for cache pg instance
cache_cx_string = make_dsn(
    dbname=env_dbname,
    user=env_user,
    password=env_password,
    host=env_host,
    port=env_port,
)
