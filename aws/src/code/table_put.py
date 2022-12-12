import logging
import boto3
import traceback
import json
import os
from datetime import datetime


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
session = boto3.Session(region_name=REGION)
dynamodb_client = session.client("dynamodb")

TABLE_NAME = os.environ["DYNAMO_TABLE"]
ATTRIBUTES = ["devid", "ts", "readings"]


def handler(event, context):

    try:
        LOGGER.info(f"Received event: {event}")
        payload = json.loads(event["body"])

        if not all(key in payload.keys() for key in ATTRIBUTES):
            LOGGER.info(f"Missing parameters in requests")
            return {
                "statusCode": 400,
                "body": '{"status":"Missing attributes for insertion"}',
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
            }

        date = datetime.strptime(payload["ts"], "%a, %d %b %Y %H:%M:%S GMT")
        ts = str(int(datetime.timestamp(date)))
        readings = [{"N": str(r)} for r in payload["readings"]]

        dynamodb_response = dynamodb_client.put_item(
            TableName=TABLE_NAME,
            Item={
                "DeviceID": {"S": payload["devid"]},
                "Timestamp": {"N": ts},
                "Readings": {"L": readings},
            },
        )
        LOGGER.info(f"Item inserted")
        return {
            "statusCode": 200,
            "body": "successfully created item!",
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
