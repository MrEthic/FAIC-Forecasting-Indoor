import logging
import boto3
import traceback
import json
import os


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
session = boto3.Session(region_name=REGION)
timestream_client = session.client("timestream-query")

DATABASE_NAME = os.environ["DATABASE_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]


def handler(event, context):

    try:
        LOGGER.info(f"Received event: {event}")
        QUERY = f'SELECT distinct deviceId from "{DATABASE_NAME}"."{TABLE_NAME}"'
        LOGGER.info(f"Executing SQL: {QUERY}")
        response = timestream_client.query(QueryString=QUERY)

        columns_name = [col["Name"] for col in response["ColumnInfo"]]
        columns_type = [col["Type"]["ScalarType"] for col in response["ColumnInfo"]]

        type_map = {
            "VARCHAR": "string",
            "DOUBLE": "float",
        }

        rows = [row["Data"] for row in response["Rows"]]
        rows_list = [[next(iter(el.values())) for el in row] for row in rows]

        return {
            "statusCode": 201,
            "body": json.dumps(
                {
                    "Records": rows_list,
                    "Metadata": {
                        "SourceName": "BrewAI",
                        "SourceType": "SensorsData",
                        "SourceFormat": "Timeserie",
                        "ColumnName": columns_name,
                        "ColumnType": [type_map.get(t) for t in columns_type],
                    },
                    "ExecutionInfo": {
                        "LastQueryId": response["QueryId"],
                    },
                }
            ),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
    except timestream_client.exceptions.ValidationException as err:
        LOGGER.error(f"ValidationException: {err} on {QUERY}")
        return {
            "statusCode": 400,
            "body": '{"status":"Double check time filter syntax."}',
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
    except Exception as e:
        LOGGER.error(f"Error inserting item: {e}")
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": '{"status":"Server error"}',
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
