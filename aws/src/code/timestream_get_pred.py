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
PARAMETERS = ["from", "to", "device"]


def build_query_one_measure(from_ts: int, to_ts: int, device: str, measure: str):
    QUERY = f"""
    SELECT 
        time,
        measure_value::double AS {measure}
    FROM "{DATABASE_NAME}"."{TABLE_NAME}"
        WHERE
        time between from_unixtime({from_ts}) and from_unixtime({to_ts})
        AND measure_name='{measure}'
        AND deviceId='{device}'
    ORDER BY time DESC
    """
    QUERY = " ".join([s.strip() for s in QUERY.split("\n")])
    return QUERY


def build_query(from_ts: int, to_ts: int, device: str):
    measures = [f"iaq~{i}" for i in range(1, 16)]
    QUERY = f"""
    SELECT 
        time,
        {
            ",".join(["MAX(if(measure_name = '{mn}',".format(mn=m) + ' measure_value::double)) AS "{mn}"'.format(mn=m) for m in measures])
        }
    FROM "{DATABASE_NAME}"."{TABLE_NAME}"
        WHERE
        time between from_unixtime({from_ts}) and from_unixtime({to_ts})
        AND deviceId='{device}'
    GROUP BY time
    ORDER BY time DESC
    """
    QUERY = " ".join([s.strip() for s in QUERY.split("\n")])
    return QUERY


def handler(event, context):

    try:
        LOGGER.info(f"Received event: {event}")
        # payload = json.loads(event["body"])
        query_string_parameters = event["queryStringParameters"]
        if not all(key in query_string_parameters.keys() for key in PARAMETERS):
            LOGGER.info(f"Missing parameters in requests.")
            return {
                "statusCode": 400,
                "body": '{"status":"Missing parameters."}',
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
            }

        from_ts = query_string_parameters["from"]
        to_ts = query_string_parameters["to"]
        device = query_string_parameters["device"]

        try:
            from_ts = int(from_ts)
            to_ts = int(to_ts)
        except:
            LOGGER.warning(f"Can't cast timestamp to int.")
            return {
                "statusCode": 400,
                "body": '{"status":"Invalid parameter types."}',
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
            }

        if query_string_parameters.get("measure") is not None:
            QUERY = build_query_one_measure(
                from_ts, to_ts, device, query_string_parameters.get("measure")
            )
        else:
            QUERY = build_query(from_ts, to_ts, device)

        kwargs = {}
        if query_string_parameters.get("nextToken") is not None:
            LOGGER.info("Found initial NextToken in query...")
            kwargs = {"NextToken": query_string_parameters.get("nextToken")}

        LOGGER.info(f"Executing SQL: {QUERY}")
        response = timestream_client.query(QueryString=QUERY, **kwargs)

        columns_name = [col["Name"] for col in response["ColumnInfo"]]
        columns_type = [col["Type"]["ScalarType"] for col in response["ColumnInfo"]]

        type_map = {
            "TIMESTAMP": "timestamp",
            "DOUBLE": "float",
        }

        rows = [row["Data"] for row in response["Rows"]]
        n_iter = 0
        while "NextToken" in response and n_iter < 5:
            response = timestream_client.query(
                QueryString=QUERY, NextToken=response["NextToken"]
            )
            rows += [row["Data"] for row in response["Rows"]]
            n_iter += 1
            LOGGER.info(f"NextToken {n_iter} Consumed")

        rows_list = [[next(iter(el.values())) for el in row] for row in rows]

        LOGGER.info(f"Success {QUERY}")

        return {
            "statusCode": 201,
            "body": json.dumps(
                {
                    "Records": rows_list,
                    "Metadata": {
                        "SourceName": "BrewAI",
                        "SourceType": "IAQPredictions",
                        "SourceFormat": "Timeserie",
                        "ColumnName": columns_name,
                        "ColumnType": [type_map.get(t) for t in columns_type],
                    },
                    "ExecutionInfo": {
                        "LastQueryId": response["QueryId"],
                        "NextTokenConsumed": n_iter,
                        "NextToken": response.get("NextToken", None),
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
