import boto3
import os
import logging
import traceback

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
DYNAMODB_CLIENT = boto3.client("dynamodb", region_name=REGION)

CONNECTION_TABLE_NAME = os.environ["CONNECTION_TABLE_NAME"]


def handler(event, context):

    LOGGER.info(f"Received message: {event}")
    connection_id = event["requestContext"]["connectionId"]

    try:
        if event["requestContext"]["routeKey"] == "$connect":
            connection_endpoint = (
                "https://"
                + event["requestContext"]["domainName"]
                + "/"
                + event["requestContext"]["stage"]
            )

            DYNAMODB_CLIENT.put_item(
                TableName=CONNECTION_TABLE_NAME,
                Item={
                    "connectionId": {"S": connection_id},
                    "connectionEndpoint": {"S": connection_endpoint},
                },
            )

            LOGGER.info("Successfully added connection to connections table")
            return {"statusCode": 200, "body": "Connected"}

        elif event["requestContext"]["routeKey"] == "$disconnect":
            DYNAMODB_CLIENT.delete_item(
                TableName=CONNECTION_TABLE_NAME,
                Key={"connectionId": {"S": connection_id}},
            )

            LOGGER.info("Successfully deleted connection from connections table")
            return {"statusCode": 200, "body": "Disconnected"}

        else:
            LOGGER.info(
                f"Expected $connect or $disconnect.  Received: {event['requestContext']['routeKey']}"
            )
            return {"statusCode": 400, "body": "Failed to process message."}

    except Exception:
        traceback.print_exc()
        return {"statusCode": 500, "body": "Failed to process message"}
