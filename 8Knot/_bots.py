from db_manager.collectoss_manager import CollectOSSManager
from sqlalchemy.exc import SQLAlchemyError
import logging


def get_bots_list():
    query_string = f"""
                    SELECT
	                    cntrb_id
                    FROM
                        contributors c
                    WHERE
	                    gh_type LIKE 'Bot'
                """

    try:
        dbm = CollectOSSManager()
        engine = dbm.get_engine()
    except KeyError:
        # noack, data wasn't successfully set.
        logging.error("BOT_DATA_QUERY - INCOMPLETE ENVIRONMENT")
    except SQLAlchemyError:
        logging.error("BOT_DATA_QUERY - COULDN'T CONNECT TO DB")
        # allow retry via Celery rules.
        raise SQLAlchemyError("DBConnect failed")

    df = dbm.run_query(query_string)
    # reformat cntrb_id
    df["cntrb_id"] = df["cntrb_id"].astype(str)
    df["cntrb_id"] = df["cntrb_id"].str[:15]
    bots_list = df["cntrb_id"].tolist()
    return bots_list
