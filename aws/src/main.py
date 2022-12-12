#!/usr/bin/env python
import json
import os
from dotenv import load_dotenv
from constructs import Construct
from cdktf import App, TerraformStack, S3Backend
from cdktf_cdktf_provider_aws.provider import AwsProvider
from cdktf_cdktf_provider_aws.iam_policy import IamPolicy
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.data_aws_iam_policy_document import (
    DataAwsIamPolicyDocument,
)
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction
from cdktf_cdktf_provider_aws.lambda_permission import LambdaPermission
from cdktf_cdktf_provider_aws.cloudwatch_log_group import CloudwatchLogGroup

from src.dynamo import DynamoDB
from src.api import RESTApi
from src.timestream import Timestream
from src.lambdas import ScheduledLambdas, InvokableLambdas

load_dotenv()


class MyStack(TerraformStack):
    def __init__(self, scope: Construct, ns: str, env: str, project_owner: str):
        super().__init__(scope, ns)

        tags = {"env": env, "project": ns, "project_owner": project_owner}

        AwsProvider(self, "AWS", region="ap-southeast-2", profile="unsw")

        # Backend for storing state
        S3Backend(
            self,
            bucket="terraform-backend-faic-infra",
            key=f"{ns}/terraform-{env}.tfstate",
            region="ap-southeast-2",
        )

        # dynamo = DynamoDB(self, "dynamo", isstream=False, tags=tags)

        ts = Timestream(self, "ts", tags=tags)
        sensor_data_table, sensor_data_table_crud = ts.add_table(table_name="sensors")
        predictions_data_table, predictions_data_table_crud = ts.add_table(
            table_name="predictions"
        )

        api = RESTApi(
            self,
            "api",
            endpoint_name="sensordata",
            tags=tags,
        )

        policy = IamPolicy(
            self,
            "make-pred",
            name=f"Lambda-{tags['project']}-{tags['env']}-Invoke",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Action": [
                                "lambda:InvokeFunction",
                            ],
                            "Resource": ["*"],
                            "Effect": "Allow",
                        },
                    ],
                }
            ),
            tags=tags,
        )

        put_arn = api.add_endpoint(
            http="PUT",
            policies=[sensor_data_table_crud, policy.arn],
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/timestream_put.zip",
            environement={"DATABASE_NAME": ts.db_name, "TABLE_NAME": sensor_data_table},
            resource="data",
        )

        api.add_endpoint(
            http="GET",
            policies=[sensor_data_table_crud],
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/timestream_get.zip",
            environement={"DATABASE_NAME": ts.db_name, "TABLE_NAME": sensor_data_table},
            timeout=20,
            resource="data",
        )

        api.add_endpoint(
            http="GET",
            policies=[sensor_data_table_crud],
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/sensors_get.zip",
            environement={"DATABASE_NAME": ts.db_name, "TABLE_NAME": sensor_data_table},
            timeout=20,
            resource="sensor",
        )

        api.add_endpoint(
            http="GET",
            policies=[predictions_data_table_crud],
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/timestream_get_pred.zip",
            environement={
                "DATABASE_NAME": ts.db_name,
                "TABLE_NAME": predictions_data_table,
            },
            timeout=20,
            resource="pred",
        )

        api.finalize()

        ScheduledLambdas(
            self,
            "fetcher",
            name="fetch-from-brewai",
            schedule_expression="rate(1 minute)",
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/brewai_fetch.zip",
            policies=[],
            memory_size=512,
            timeout=20,
            environement={
                "BREWAI_API_KEY": os.getenv("BREWAI_API_KEY"),
                "PROJECT_API_KEY": api.api_key_value,
            },
            tags=tags,
        )

        InvokableLambdas(
            self,
            "make-prediction",
            name="make-prediction",
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/make_prediction.zip",
            policies=[sensor_data_table_crud, predictions_data_table_crud],
            invoke_principal="lambda.amazonaws.com",
            invoke_from_arn=put_arn,
            memory_size=512,
            timeout=20,
            environement={
                "DATABASE_NAME": ts.db_name,
                "SENSOR_TABLE": sensor_data_table,
                "PREDICTIONS_TABLE": predictions_data_table,
                "MODEL_ENDPOINT": "https://dbc-4e63b9e5-9d6d.cloud.databricks.com/model/iaq_forecast_ucb/Staging/invocations",
                "DATABRICKS_KEY": os.getenv("DATABRICKS_KEY"),
                "REGION": "ap-southeast-2",
            },
            tags=tags,
        )


app = App()
MyStack(app, "brewai-sensor-iaq", "dev", "Alan")

app.synth()
