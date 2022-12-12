import logging
import boto3
import traceback
import urllib3
import json
import os
from datetime import datetime, timedelta


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
session = boto3.Session(region_name=REGION)
timestream_write = session.client("timestream-write")
timestream_query = session.client("timestream-query")

DATABASE_NAME = os.environ["DATABASE_NAME"]
PREDICTIONS_TABLE_NAME = os.environ["PREDICTIONS_TABLE"]
SENSOR_TABLE_NAME = os.environ["SENSOR_TABLE"]
MODEL_ENDPOINT = os.environ["MODEL_ENDPOINT"]
DATABRICKS_KEY = os.getenv("DATABRICKS_KEY")
LOOKAHEAD = 15
ATTRIBUTES = ["deviceId", "timestamp"]
H = {
    "Authorization": f"Bearer {DATABRICKS_KEY}",
    "Content-Type": "application/json",
}


def retreive_last_60(device_id: str, ts: int) -> list:
    """Retreive the last 60 minutes of iaq data for a given device at a given point in time.

    We retreive data by executing a timestream query. As we might have missing data for the given device,
    we build a linear interpolation from the point that exists.

    As Timestream is eventualy consistent, sometimes the query is missing the current minute value.
    The query will always returned 60 or 59 values.

    Args:
        device_id (str): The device id
        ts (int): Timestamp in seconds

    Returns:
        list: The list of iaq values returned by the timestream query
    """
    QUERY = f"""
    WITH binned_timeseries AS (
        SELECT 
            time as bin,
            deviceId,
            measure_value::double AS iaq
        FROM "{DATABASE_NAME}"."{SENSOR_TABLE_NAME}"
        WHERE 
            time between date_add('minute', -59, from_unixtime({ts})) and from_unixtime({ts+1})
            AND measure_name='iaq'
            AND deviceId='{device_id}'
        ORDER BY time
    ), interpolated_timeseries AS (
        SELECT deviceId,
            INTERPOLATE_LINEAR(
                CREATE_TIME_SERIES(bin, iaq),
                SEQUENCE(min(bin), max(bin), 60s)) AS interpolated_iaq
        FROM binned_timeseries
        GROUP BY deviceId
    )
    SELECT time, value
    FROM interpolated_timeseries
    CROSS JOIN UNNEST(interpolated_iaq)
    ORDER BY time ASC
    """
    response = timestream_query.query(QueryString=QUERY)
    rows = [row["Data"] for row in response["Rows"]]
    hist = [[next(iter(el.values())) for el in row] for row in rows]
    hist_values = [float(x[-1]) for x in hist]
    return hist_values


def get_predictions(hist_values: list) -> list:
    """Generate prediction using databricks inference endpoint.

    If we don't have 60 points of data, we duplicate last point (should only happen due to consistency issues)

    Args:
        hist_values (list): Last 60 values of iaq

    Returns:
        list: 15 minutes of predicted data
    """
    if len(hist_values) != 60:
        LOGGER.warning(f"MISSING {60 - len(hist_values)} IAQ VALUES.")
        hist_values += [hist_values[-1]] * (60 - len(hist_values))

    model_input = {"instances": [hist_values]}
    http = urllib3.PoolManager()
    predictions = http.request(
        "POST",
        url=MODEL_ENDPOINT,
        headers=H,
        body=json.dumps(model_input),
    )
    LOGGER.info(f"Inference endpoint returned {predictions.data}")
    predictions = json.loads(predictions.data)["predictions"][0]
    return predictions


def handler(event, context):
    """Make a predicton using databricks inference endpoints.

    Args:
        event (dict): Event must be paersable as a disctionary of format deviceId => String, timestamp => Integer
        context: Lambda context (not used)
    """

    try:
        LOGGER.info(f"NEW INVOCATION WITH EVENT={event}.")

        # Verifying that event contains all necessary keys
        if not all(key in event.keys() for key in ATTRIBUTES):
            LOGGER.warning(f"REQUEST IS MISSING PARAMETERS.")
            return {
                "statusCode": 400,
                "body": '{"status":"Missing parameters."}',
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
            }

        device_id = event["deviceId"]
        ts = int(event["timestamp"])
        # datetime for the first prediction (1 minute after the current timestamp)
        dt1 = datetime.fromtimestamp(ts).replace(second=0) + timedelta(minutes=1)

        hist_values = retreive_last_60(device_id, ts)
        predictions = get_predictions(hist_values)

        # Build the list of timestamp for insertion in database
        dts = [datetime.timestamp(dt1 + timedelta(minutes=i)) for i in range(LOOKAHEAD)]

        dimensions = [{"Name": "deviceId", "Value": device_id}]

        common_attributes = {
            "Dimensions": dimensions,
            "MeasureValueType": "DOUBLE",
            "TimeUnit": "SECONDS",
        }

        records = [
            {
                "MeasureName": f"iaq~{i+1}",
                "MeasureValue": str(predictions[i]),
                "Time": str(int(dts[i])),
            }
            for i in range(LOOKAHEAD)
        ]

        result = timestream_write.write_records(
            DatabaseName=DATABASE_NAME,
            TableName=PREDICTIONS_TABLE_NAME,
            Records=records,
            CommonAttributes=common_attributes,
        )
        LOGGER.info(f"PREDICTIONS INSERTED")
        return {
            "statusCode": 201,
            "body": "Prediction generated and saved.",
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
        }
    except timestream_write.exceptions.RejectedRecordsException as err:
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
