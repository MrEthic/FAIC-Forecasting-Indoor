import hashlib
from constructs import Construct
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.data_aws_iam_policy_document import (
    DataAwsIamPolicyDocument,
)
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction
from cdktf_cdktf_provider_aws.lambda_permission import LambdaPermission
from cdktf_cdktf_provider_aws.cloudwatch_log_group import CloudwatchLogGroup
from cdktf_cdktf_provider_aws.cloudwatch_event_rule import CloudwatchEventRule
from cdktf_cdktf_provider_aws.cloudwatch_event_target import CloudwatchEventTarget


class ScheduledLambdas(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        schedule_expression: str,
        filename: str,
        policies: list,
        memory_size: int,
        timeout: int,
        environement: dict,
        tags: dict,
    ):
        super().__init__(scope, id)

        assume = DataAwsIamPolicyDocument(
            self,
            "assume",
            statement=[
                {
                    "actions": ["sts:AssumeRole"],
                    "principals": [
                        {
                            "type": "Service",
                            "identifiers": ["lambda.amazonaws.com"],
                        }
                    ],
                }
            ],
        )

        role = IamRole(
            self,
            f"role",
            name=f"ScheduledLambdas-{name}-{tags['project']}-{tags['env']}",
            assume_role_policy=assume.json,
            managed_policy_arns=[
                "arn:aws:iam::092201464628:policy/LambdaLogging",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            ]
            + policies,
            tags=tags,
        )

        """ h = hashlib.sha1()
        with open(put_file_path) as file:
            chunk = 0
            while chunk != b"":
                chunk = file.read(1024)
                h.update(chunk) """

        environement.update({"REGION": "ap-southeast-2"})
        function = LambdaFunction(
            self,
            f"lambda",
            filename=filename,
            function_name=f"{tags['project']}-scheduled-{name}-{tags['env']}",
            source_code_hash="1",
            # source_code_hash=h.hexdigest(),
            role=role.arn,
            handler=f"{filename.split('/')[-1].split('.')[0]}.handler",
            runtime="python3.9",
            memory_size=memory_size,
            timeout=timeout,
            environment={"variables": environement},
            tags=tags,
        )

        CloudwatchLogGroup(
            self,
            f"logs",
            name=f"/aws/lambda/{function.function_name}",
            retention_in_days=30,
            tags=tags,
        )

        schedule = CloudwatchEventRule(
            self,
            "rule",
            name=f"{name}-Schedule",
            schedule_expression=schedule_expression,
        )

        CloudwatchEventTarget(self, "target", rule=schedule.name, arn=function.arn)

        LambdaPermission(
            self,
            "permission",
            statement_id="AllowExecutionFromCloudWatch",
            action="lambda:InvokeFunction",
            function_name=function.function_name,
            principal="events.amazonaws.com",
            source_arn=schedule.arn,
        )


class InvokableLambdas(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        filename: str,
        policies: list,
        invoke_principal: str,
        invoke_from_arn: str,
        memory_size: int,
        timeout: int,
        environement: dict,
        tags: dict,
    ):
        super().__init__(scope, id)

        assume = DataAwsIamPolicyDocument(
            self,
            "assume",
            statement=[
                {
                    "actions": ["sts:AssumeRole"],
                    "principals": [
                        {
                            "type": "Service",
                            "identifiers": ["lambda.amazonaws.com"],
                        }
                    ],
                }
            ],
        )

        role = IamRole(
            self,
            f"role",
            name=f"InvokableLambda-{name}-{tags['project']}-{tags['env']}",
            assume_role_policy=assume.json,
            managed_policy_arns=[
                "arn:aws:iam::092201464628:policy/LambdaLogging",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            ]
            + policies,
            tags=tags,
        )

        """ h = hashlib.sha1()
        with open(put_file_path) as file:
            chunk = 0
            while chunk != b"":
                chunk = file.read(1024)
                h.update(chunk) """

        environement.update({"REGION": "ap-southeast-2"})
        function = LambdaFunction(
            self,
            f"lambda",
            filename=filename,
            function_name=f"{tags['project']}-invokable-{name}-{tags['env']}",
            source_code_hash="1",
            # source_code_hash=h.hexdigest(),
            role=role.arn,
            handler=f"{filename.split('/')[-1].split('.')[0]}.handler",
            runtime="python3.9",
            memory_size=memory_size,
            timeout=timeout,
            environment={"variables": environement},
            tags=tags,
        )

        CloudwatchLogGroup(
            self,
            f"logs",
            name=f"/aws/lambda/{function.function_name}",
            retention_in_days=30,
            tags=tags,
        )

        LambdaPermission(
            self,
            "permission",
            statement_id="AllowExecutionFromSomewhere",
            action="lambda:InvokeFunction",
            function_name=function.function_name,
            principal=invoke_principal,
            source_arn=invoke_from_arn,
        )
