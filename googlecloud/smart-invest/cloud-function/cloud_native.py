import datetime
import os

from google.cloud import bigquery
from google.cloud import logging
from google.cloud import secretmanager

LOG_SEVERITY_DEFAULT = 'DEFAULT'
LOG_SEVERITY_INFO = 'INFO'
LOG_SEVERITY_WARNING = 'WARNING'
LOG_SEVERITY_DEBUG = 'DEBUG'
LOG_SEVERITY_NOTICE = 'NOTICE'
LOG_SEVERITY_ERROR = 'ERROR'
app_name = 'smart-invest'


def log(text, severity=LOG_SEVERITY_DEFAULT, log_name=app_name):
    logging_client = logging.Client(project=os.environ['PROJECT_ID'])
    logger = logging_client.logger(log_name)

    return logger.log_text(text, severity=severity)


def get_secret_value(env_var_secret_name):
    sm_client = secretmanager.SecretManagerServiceClient()
    secret_path_latest = sm_client.secret_path(os.environ.get('SECRET_MANAGER_PROJECT_ID'),
                                               os.environ.get(env_var_secret_name)) + "/versions/latest"
    secret_latest_version = sm_client.access_secret_version(request={"name": secret_path_latest})
    log('read secret value for secret name {}'.format(os.environ.get(env_var_secret_name)), LOG_SEVERITY_NOTICE)
    secret_value = secret_latest_version.payload.data.decode("UTF-8")
    return secret_value


def insert_to_bq(bq_table: str, trades: dict, account: int = -1):
    recommended_timestamp = str(datetime.datetime.now())
    rows_to_insert = []
    for ticker, order in trades.items():
        if isinstance(order, Exception):
            continue
        rows_to_insert.append(
            {
                "account": account,
                "ticker": ticker,
                "cash": order.cash,
                "price": order.price,
                "shares": order.shares,
                "updated": recommended_timestamp
            }
        )
    client = bigquery.Client()
    try:
        errors = client.insert_rows_json(bq_table, rows_to_insert)
        if errors:
            log("Encountered errors while inserting rows to BigQuery table "
                "{}: {}".format(bq_table, errors),
                severity=LOG_SEVERITY_ERROR)
            return errors
    except Exception as ex:
        log("Encountered errors while inserting rows to BigQuery table "
            "{}: type {} => {}".format(bq_table, type(ex), ex),
            severity=LOG_SEVERITY_ERROR)
        return ex
