import hashlib
import json
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.data_aws_iam_policy_document import (
    DataAwsIamPolicyDocument,
)
from cdktf_cdktf_provider_aws.data_aws_caller_identity import DataAwsCallerIdentity
from cdktf_cdktf_provider_aws.iam_policy import IamPolicy
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction
from cdktf_cdktf_provider_aws.lambda_permission import LambdaPermission
from cdktf_cdktf_provider_aws.lambda_event_source_mapping import (
    LambdaEventSourceMapping,
)
from cdktf_cdktf_provider_aws.cloudwatch_log_group import CloudwatchLogGroup
from cdktf_cdktf_provider_aws.dynamodb_table import DynamodbTable
from cdktf_cdktf_provider_aws.apigatewayv2_api import Apigatewayv2Api
from cdktf_cdktf_provider_aws.apigatewayv2_route import Apigatewayv2Route
from cdktf_cdktf_provider_aws.apigatewayv2_integration import Apigatewayv2Integration
from cdktf_cdktf_provider_aws.apigatewayv2_stage import Apigatewayv2Stage
from cdktf_cdktf_provider_aws.apigatewayv2_deployment import Apigatewayv2Deployment


class DynamoWebsocket(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        stream_arn: str,
        stream_policy_arn: str,
        tags: dict,
    ):
        """Resources for websocket API associated to a dynamo table

        Resources:
        ----------
            DynamodbTable: The table for managing open connections
            IamPolicy: Policy for managing connections
            Apigatewayv2Api: The Websocket API
            IamRole: Role for lambdas
            LambdaFunction: Manager and Messager for the API
            LambdaPermission: Allow execution from api
            CloudwatchLogGroup: Logs for lambdas
            Apigatewayv2Integration: API Integration
            Apigatewayv2Route: connect and disconnect routes
            Apigatewayv2Deployment: API deployement
            Apigatewayv2Stage: API version
            LambdaEventSourceMapping: Connect lambdas to stream
        """
        super().__init__(scope, id)

        suffix = f'-{tags["project"]}-{tags["env"]}'

        account = DataAwsCallerIdentity(self, "current")

        conn_table = DynamodbTable(
            self,
            "table",
            name=f"ProjectWebsocket{suffix}",
            billing_mode="PROVISIONED",
            read_capacity=1,
            write_capacity=1,
            hash_key="connectionId",
            attribute=[dict(name="connectionId", type="S")],
            tags=tags,
        )

        conn_policy = IamPolicy(
            self,
            "conn-policy",
            name=f"{conn_table.name}-CRUD",
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
                            "Resource": [conn_table.arn],
                            "Effect": "Allow",
                        }
                    ],
                }
            ),
            tags=tags,
        )

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

        websocket = Apigatewayv2Api(
            self,
            "api",
            protocol_type="WEBSOCKET",
            name=f"WebsocketStreamAPI{suffix}",
            route_selection_expression="$request.body.action",
            tags=tags,
        )

        manage_con_policy = IamPolicy(
            self,
            "manage_con_policy",
            name=f"{websocket.name}-MANAGECONNECTIONS",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Action": ["execute-api:ManageConnections"],
                            "Resource": [
                                websocket.arn,
                                f"arn:aws:execute-api:ap-southeast-2:{account.account_id}:{websocket.id}/v1/POST/*/*",
                            ],
                            "Effect": "Allow",
                        }
                    ],
                }
            ),
            tags=tags,
        )

        manage_role = IamRole(
            self,
            "manage-role",
            name=f"Lambda-ManageWebsocketConn{suffix}",
            assume_role_policy=assume.json,
            managed_policy_arns=[
                manage_con_policy.arn,
                "arn:aws:iam::092201464628:policy/LambdaLogging",
                conn_policy.arn,
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            ],
            tags=tags,
        )

        h = hashlib.sha1()
        with open(
            "/root/unsw/FAIC-Project-AWS-Template/src/code/archived/manage_conn.zip",
            "rb",
        ) as file:
            chunk = 0
            while chunk != b"":
                chunk = file.read(1024)
                h.update(chunk)

        manage_func = LambdaFunction(
            self,
            "manage-func",
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/manage_conn.zip",
            function_name=f"ManageWebsocketConnection{suffix}",
            source_code_hash=h.hexdigest(),
            role=manage_role.arn,
            handler="manage_conn.handler",
            runtime="python3.9",
            memory_size=128,
            timeout=5,
            environment={
                "variables": {
                    "REGION": "ap-southeast-2",
                    "CONNECTION_TABLE_NAME": conn_table.name,
                }
            },
            tags=tags,
        )

        LambdaPermission(
            self,
            "perm",
            statement_id="AllowExecutionFromAPIGateway",
            action="lambda:InvokeFunction",
            function_name=manage_func.function_name,
            principal="apigateway.amazonaws.com",
            source_arn=f"arn:aws:execute-api:ap-southeast-2:{account.account_id}:{websocket.id}/v1/*",
        )

        CloudwatchLogGroup(
            self,
            "manage_logs",
            name=f"/aws/lambda/{manage_func.function_name}",
            retention_in_days=30,
            tags=tags,
        )

        conn_integration = Apigatewayv2Integration(
            self,
            "conn-inte",
            api_id=websocket.id,
            integration_type="AWS_PROXY",
            integration_method="POST",
            integration_uri=manage_func.invoke_arn,
        )

        disconn_integration = Apigatewayv2Integration(
            self,
            "disconn-inte",
            api_id=websocket.id,
            integration_type="AWS_PROXY",
            integration_method="POST",
            integration_uri=manage_func.invoke_arn,
        )

        connect_route = Apigatewayv2Route(
            self,
            "route-connect",
            api_id=websocket.id,
            target=f"integrations/{conn_integration.id}",
            route_key="$connect",
        )

        disconnect_route = Apigatewayv2Route(
            self,
            "route-disconnect",
            api_id=websocket.id,
            target=f"integrations/{disconn_integration.id}",
            route_key="$disconnect",
        )

        dep = Apigatewayv2Deployment(
            self,
            "dep",
            api_id=websocket.id,
            lifecycle={"create_before_destroy": True},
            depends_on=[connect_route, disconnect_route],
        )

        stage = Apigatewayv2Stage(
            self,
            "stage",
            api_id=websocket.id,
            name="v1",
            deployment_id=dep.id,
            tags=tags,
        )

        msg_role = IamRole(
            self,
            "msg-role",
            name=f"Lambda-ONTableStream{suffix}",
            assume_role_policy=assume.json,
            managed_policy_arns=[
                conn_policy.arn,
                manage_con_policy.arn,
                stream_policy_arn,
                "arn:aws:iam::092201464628:policy/LambdaLogging",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            ],
            tags=tags,
        )

        h2 = hashlib.sha1()
        with open(
            "/root/unsw/FAIC-Project-AWS-Template/src/code/archived/msg_conn.zip",
            "rb",
        ) as file:
            chunk = 0
            while chunk != b"":
                chunk = file.read(1024)
                h2.update(chunk)

        msg_func = LambdaFunction(
            self,
            "msg-func",
            filename="/root/unsw/FAIC-Project-AWS-Template/src/code/archived/msg_conn.zip",
            function_name=f"MessageWebsocketConnection{suffix}",
            source_code_hash=h2.hexdigest(),
            role=msg_role.arn,
            handler="msg_conn.handler",
            runtime="python3.9",
            memory_size=128,
            timeout=20,
            environment={
                "variables": {
                    "REGION": "ap-southeast-2",
                    "CONNECTION_TABLE_NAME": conn_table.name,
                }
            },
            tags=tags,
        )

        LambdaEventSourceMapping(
            self,
            "mapping",
            event_source_arn=stream_arn,
            function_name=msg_func.function_name,
            starting_position="LATEST",
        )

        CloudwatchLogGroup(
            self,
            "msg_logs",
            name=f"/aws/lambda/{msg_func.function_name}",
            retention_in_days=30,
            tags=tags,
        )

        TerraformOutput(self, "websocker_url", value=stage.invoke_url)
