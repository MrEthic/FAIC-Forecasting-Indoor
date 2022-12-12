import logging
import boto3
import traceback
import json
import os
from datetime import datetime, timedelta


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
session = boto3.Session(region_name=REGION)
timestream_client = session.client("timestream-write")
lambda_client = session.client("lambda")

DATABASE_NAME = os.environ["DATABASE_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]
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

        if date < datetime.now() - timedelta(days=1):
            return {
                "statusCode": 200,
                "body": '{"status":"Date out of database range"}',
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
            }

        ts = str(int(datetime.timestamp(date.replace(second=0))))

        dimensions = [{"Name": "deviceId", "Value": payload["devid"]}]

        common_attributes = {
            "Dimensions": dimensions,
            "MeasureValueType": "DOUBLE",
            "Time": ts,
            "TimeUnit": "SECONDS",
        }

        _, t, h, p, iaq, co2, voc = [str(v) for v in payload["readings"]]

        records = [
            {"MeasureName": "temperature", "MeasureValue": t},
            {"MeasureName": "humidity", "MeasureValue": h},
            {"MeasureName": "pressure", "MeasureValue": p},
            {"MeasureName": "iaq", "MeasureValue": iaq},
            {"MeasureName": "co2", "MeasureValue": co2},
            {"MeasureName": "voc", "MeasureValue": voc},
        ]

        result = timestream_client.write_records(
            DatabaseName=DATABASE_NAME,
            TableName=TABLE_NAME,
            Records=records,
            CommonAttributes=common_attributes,
        )
        LOGGER.info(f"Item inserted")

        lambda_client.invoke(
            FunctionName="brewai-sensor-iaq-invokable-make-prediction-dev",
            InvocationType="Event",
            LogType="None",
            Payload=json.dumps({"timestamp": ts, "deviceId": payload["devid"]}),
        )

        return {
            "statusCode": 201,
            "body": "successfully created item!",
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
    except timestream_client.exceptions.RejectedRecordsException as err:
        LOGGER.error(f"RejectedRecords: {err}")
        for rr in err.response["RejectedRecords"]:
            LOGGER.error(
                "Rejected Index " + str(rr["RecordIndex"]) + ": " + rr["Reason"]
            )
            if "ExistingVersion" in rr:
                LOGGER.error(
                    "Rejected record existing version: ", rr["ExistingVersion"]
                )
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
