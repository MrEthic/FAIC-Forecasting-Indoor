import logging
import traceback
import boto3
from boto3.dynamodb.conditions import Key
import json
import os
from decimal import Decimal


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
dynamodb = boto3.resource("dynamodb", region_name=REGION)

TABLE_NAME = os.environ["DYNAMO_TABLE"]
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


def query_between(ts1, ts2):
    """Get Items between ts1 and ts2"""
    dynamodb_response = table.query(
        KeyConditionExpression=Key("DeviceID").eq("7BB92D02D696C5C5")
        & Key("Timestamp").between(ts1, ts2),
    )
    return dynamodb_response


def handler(event, context):

    try:
        LOGGER.info(f"Received event: {event}")
        body = json.loads(event["body"])

        if set(body.keys()) == {"from", "to"}:
            ts1 = body["from"]
            ts2 = body["to"]

            items = query_between(int(ts1), int(ts2))["Items"]

        LOGGER.info(f"Succesfully retrived points bettween {ts1} and {ts2}")
        return {
            "statusCode": 200,
            "body": json.dumps(items, cls=DecimalEncoder),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
    except ValueError as e:
        LOGGER.warning(f"Bad request retreiving points")
        return {
            "statusCode": 400,
            "body": '{"status": "Invalid paramter value (ValueError)"}',
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
    except Exception as e:
        LOGGER.info(f"Error retreiving points: {e}")
        traceback.format_exc()
        return {
            "statusCode": 500,
            "body": '{"status": "Server error"}',
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
