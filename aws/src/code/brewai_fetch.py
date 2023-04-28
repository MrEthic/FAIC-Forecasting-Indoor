import logging
import boto3
import traceback
import os
import json
import urllib3
from datetime import datetime


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

REGION = os.environ.get("REGION", "ap-southeast-2")
PROJECT_API_KEY = os.getenv("PROJECT_API_KEY")
BREWAI_API_KEY = os.getenv("BREWAI_API_KEY")
H = {"Authorization": f"Bearer {BREWAI_API_KEY}"}


def handler(event, context):

    try:
        LOGGER.info(f"FETCHING DATA...")

        http = urllib3.PoolManager()

        readings = http.request(
            "GET",
            url="https://model.brewai.com/api/sensor_readings?latest=true",
            headers=H,
        )
        readings = json.loads(readings.data)["readings"]

        trace = []

        for reading in readings:

            put = http.request(
                "PUT",
                url="https://jov3dcr05d.execute-api.ap-southeast-2.amazonaws.com/v1/sensordata",
                headers={"x-api-key": PROJECT_API_KEY},
                body=json.dumps(reading),
            )
            trace.append(put.status)
            if put.status == 500 or put.status == 503:
                LOGGER.warning(
                    f"API returned {put.data} at {datetime.now()}\n\ton {reading}"
                )

        LOGGER.info(
            f"Done ({len(trace)}), ok: {trace.count(201)}, out: {trace.count(200)}, error: {trace.count(500) + trace.count(503)}"
        )
        return {"statusCode": 200}
    except Exception as e:
        LOGGER.error(f"Error inserting item: {e}")
        traceback.print_exc()
        return {"statusCode": 500}
