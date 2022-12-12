import boto3
import os
import logging
import traceback
import json

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
DYNAMODB_CLIENT = boto3.client("dynamodb", region_name=REGION)

CONNECTION_TABLE_NAME = os.environ["CONNECTION_TABLE_NAME"]


def handler(event, context):
    LOGGER.info(f"Received event stream message {event}")

    try:
        active_connections = DYNAMODB_CLIENT.scan(
            TableName=CONNECTION_TABLE_NAME,
            ProjectionExpression="connectionId,connectionEndpoint",
        )
    except Exception:
        traceback.print_exc()
        return {"statusCode": 500, "body": "Failed to read active connections"}

    for record in event["Records"]:
        for connection in active_connections["Items"]:
            try:
                if record["eventName"].upper() == "REMOVE":
                    ddb_stream_capture = {
                        "isRemoved": "true",
                        "featureId": record["dynamodb"]["Keys"],
                    }
                else:
                    ddb_stream_capture = record["dynamodb"]["NewImage"]

                connection_endpoint = connection["connectionEndpoint"]["S"]
                connection_id = connection["connectionId"]["S"]

                api_gw_client = boto3.client(
                    "apigatewaymanagementapi", endpoint_url=connection_endpoint
                )

                api_gw_client.post_to_connection(
                    ConnectionId=connection_id, Data=json.dumps(ddb_stream_capture)
                )

                LOGGER.info(
                    f"Posted update of {record} to connection_id {connection_id}"
                )

            except api_gw_client.exceptions.GoneException:
                LOGGER.info(
                    f"connection_id {connection_id} is no longer active. Deleting this connection."
                )
                DYNAMODB_CLIENT.delete_item(
                    TableName=CONNECTION_TABLE_NAME,
                    Key={"connectionId": {"S": connection_id}},
                )
            except Exception:
                LOGGER.info(f"Failed to post message to connection {connection}")
                traceback.print_exc()

    return {"statusCode": 200, "body": "Data Stream update processed successfully"}
