import json
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.data_aws_iam_policy_document import (
    DataAwsIamPolicyDocument,
)
from cdktf_cdktf_provider_aws.iam_policy import IamPolicy
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.dynamodb_table import DynamodbTable

from src.streaming import DynamoWebsocket


class DynamoDB(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        isstream: bool,
        tags: dict,
    ):
        """Resources for DynamoDB Project table

        Resources:
        ----------
            DynamodbTable: The table (keys, capacities etc.)
            IamPolicy: Crud permissions on table
            if isstream: Stream policy and Websocket API
        """
        super().__init__(scope, id)

        table = DynamodbTable(
            self,
            "table",
            name=f'ProjectTable-{tags["project"]}-{tags["env"]}',
            billing_mode="PROVISIONED",
            read_capacity=20,
            write_capacity=20,
            hash_key="DeviceID",
            range_key="Timestamp",
            stream_enabled=isstream,
            stream_view_type="NEW_IMAGE" if isstream else None,
            attribute=[
                dict(name="DeviceID", type="S"),
                dict(name="Timestamp", type="N"),
            ],
            tags=tags,
        )

        table_crud = IamPolicy(
            self,
            "table-crud",
            name=f"{table.name}-CRUD",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Action": [
                                "dynamodb:BatchGetItem",
                                "dynamodb:BatchWriteItem",
                                "dynamodb:ConditionCheckItem",
                                "dynamodb:PutItem",
                                "dynamodb:DescribeTable",
                                "dynamodb:DeleteItem",
                                "dynamodb:GetItem",
                                "dynamodb:Scan",
                                "dynamodb:Query",
                                "dynamodb:UpdateItem",
                            ],
                            "Resource": [table.arn],
                            "Effect": "Allow",
                        }
                    ],
                }
            ),
            tags=tags,
        )

        if isstream:

            read_stream = IamPolicy(
                self,
                "read-stream",
                name=f"{table.name}-STREAM",
                policy=json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Action": [
                                    "dynamodb:DescribeStream",
                                    "dynamodb:GetRecords",
                                    "dynamodb:GetShardIterator",
                                    "dynamodb:ListStreams",
                                ],
                                "Resource": [table.stream_arn],
                                "Effect": "Allow",
                            }
                        ],
                    }
                ),
                tags=tags,
            )

            DynamoWebsocket(
                self,
                "websocket-stream",
                table.stream_arn,
                read_stream.arn,
                tags=tags,
            )

        self.table_name = table.name
        self.crud_arn = table_crud.arn
