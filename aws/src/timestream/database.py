import json
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.data_aws_iam_policy_document import (
    DataAwsIamPolicyDocument,
)
from cdktf_cdktf_provider_aws.iam_policy import IamPolicy
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.timestreamwrite_database import (
    TimestreamwriteDatabase,
)
from cdktf_cdktf_provider_aws.timestreamwrite_table import (
    TimestreamwriteTable,
)


class Timestream(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        tags: dict,
    ):
        super().__init__(scope, id)

        self.tags = tags

        db = TimestreamwriteDatabase(
            self,
            "db",
            database_name=f'{tags["project"]}-database-{tags["env"]}',
            tags=tags,
        )

        self.db_name = db.database_name

    def add_table(
        self, table_name: str, magnetic_days: int = 30, memory_hours: int = 24
    ):
        table = TimestreamwriteTable(
            self,
            table_name,
            database_name=self.db_name,
            table_name=table_name,
            retention_properties=dict(
                magnetic_store_retention_period_in_days=magnetic_days,
                memory_store_retention_period_in_hours=memory_hours,
            ),
            tags=self.tags,
        )

        table_crud = IamPolicy(
            self,
            f"{table_name}-crud",
            name=f"{table.database_name}-{table.table_name}-CRUD",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Action": [
                                "timestream:DescribeEndpoints",
                                "timestream:DescribeTable",
                                "timestream:DescribeDatabase",
                                "timestream:ListTables",
                                "timestream:ListDatabases",
                            ],
                            "Resource": ["*"],
                            "Effect": "Allow",
                        },
                        {
                            "Action": [
                                "timestream:WriteRecords",
                                "timestream:WriteRecords",
                                "timestream:ListMeasures",
                                "timestream:Select",
                            ],
                            "Resource": [table.arn],
                            "Effect": "Allow",
                        },
                    ],
                }
            ),
            tags=self.tags,
        )

        return table.table_name, table_crud.arn
