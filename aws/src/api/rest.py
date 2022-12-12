import hashlib
import json
from constructs import Construct
from cdktf import TerraformOutput
from cdktf_cdktf_provider_aws.iam_policy import IamPolicy
from cdktf_cdktf_provider_aws.iam_role import IamRole
from cdktf_cdktf_provider_aws.data_aws_iam_policy_document import (
    DataAwsIamPolicyDocument,
)
from cdktf_cdktf_provider_aws.api_gateway_rest_api import ApiGatewayRestApi
from cdktf_cdktf_provider_aws.api_gateway_resource import ApiGatewayResource
from cdktf_cdktf_provider_aws.api_gateway_method import ApiGatewayMethod
from cdktf_cdktf_provider_aws.api_gateway_stage import ApiGatewayStage
from cdktf_cdktf_provider_aws.api_gateway_deployment import ApiGatewayDeployment
from cdktf_cdktf_provider_aws.api_gateway_integration import ApiGatewayIntegration
from cdktf_cdktf_provider_aws.api_gateway_usage_plan import ApiGatewayUsagePlan
from cdktf_cdktf_provider_aws.api_gateway_api_key import ApiGatewayApiKey
from cdktf_cdktf_provider_aws.api_gateway_usage_plan_key import ApiGatewayUsagePlanKey
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction
from cdktf_cdktf_provider_aws.lambda_permission import LambdaPermission
from cdktf_cdktf_provider_aws.cloudwatch_log_group import CloudwatchLogGroup


class RESTApi(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        endpoint_name: str,
        tags: dict,
    ):

        super().__init__(scope, id)

        self.tags = tags
        self.integration = []

        rest_api = ApiGatewayRestApi(
            self,
            "rest-api",
            name=f'PROJECT-RestApi-{tags["project"]}-{tags["env"]}',
            api_key_source="HEADER",
            endpoint_configuration={"types": ["REGIONAL"]},
            tags=tags,
        )

        self.api_id = rest_api.id

        resource = ApiGatewayResource(
            self,
            "resource",
            path_part=endpoint_name,
            rest_api_id=rest_api.id,
            parent_id=rest_api.root_resource_id,
        )

        pred_resource = ApiGatewayResource(
            self,
            "resource-pred",
            path_part="predictions",
            rest_api_id=rest_api.id,
            parent_id=rest_api.root_resource_id,
        )

        sensor_resource = ApiGatewayResource(
            self,
            "resource-sensor",
            path_part="sensors",
            rest_api_id=rest_api.id,
            parent_id=resource.id,
        )

        self.data_resource_id = resource.id
        self.pred_resource_id = pred_resource.id
        self.sensor_resource_id = sensor_resource.id

        self.assume = DataAwsIamPolicyDocument(
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

    def add_endpoint(
        self,
        http: str,
        policies: list,
        filename: str,
        environement: dict,
        timeout: int = 5,
        resource: str = "data",
    ):

        suffix = f"{http.lower()}-{resource}"
        role = IamRole(
            self,
            f"lambda-role-{suffix}",
            name=f"Lambda-{suffix}-{self.tags['project']}-{self.tags['env']}",
            assume_role_policy=self.assume.json,
            managed_policy_arns=[
                "arn:aws:iam::092201464628:policy/LambdaLogging",
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            ]
            + policies,
            tags=self.tags,
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
            f"lambda-{suffix}",
            filename=filename,
            function_name=f"{self.tags['project']}-{suffix}-{self.tags['env']}",
            source_code_hash="1",
            # source_code_hash=h.hexdigest(),
            role=role.arn,
            handler=f"{filename.split('/')[-1].split('.')[0]}.handler",
            runtime="python3.9",
            memory_size=128,
            timeout=timeout,
            environment={"variables": environement},
            tags={"api": self.api_id, **self.tags},
        )

        CloudwatchLogGroup(
            self,
            f"logs-{suffix}",
            name=f"/aws/lambda/{function.function_name}",
            retention_in_days=30,
            tags={"api": self.api_id, **self.tags},
        )

        LambdaPermission(
            self,
            f"permission-{suffix}",
            statement_id="AllowExecutionFromAPIGateway",
            action="lambda:InvokeFunction",
            function_name=function.function_name,
            principal="apigateway.amazonaws.com",
            source_arn="arn:aws:execute-api:ap-southeast-2:092201464628:*/*/*",
        )

        if resource == "data":
            resource_id = self.data_resource_id
        elif resource == "pred":
            resource_id = self.pred_resource_id
        elif resource == "sensor":
            resource_id = self.sensor_resource_id

        ApiGatewayMethod(
            self,
            f"methode-{suffix}",
            rest_api_id=self.api_id,
            resource_id=resource_id,
            http_method=http,
            authorization="NONE",
            api_key_required=True,
        )

        integration = ApiGatewayIntegration(
            self,
            f"integration-{suffix}",
            rest_api_id=self.api_id,
            resource_id=resource_id,
            http_method=http,
            integration_http_method="POST",
            type="AWS_PROXY",
            uri=function.invoke_arn,
        )

        self.integration.append(integration)
        return function.arn

    def finalize(self):
        deployement = ApiGatewayDeployment(
            self,
            "rest-deploy",
            rest_api_id=self.api_id,
            lifecycle={"create_before_destroy": True},
            description="Deploy again",
            triggers={"redeployment": "1"},
            depends_on=self.integration,
        )

        rest_stage = ApiGatewayStage(
            self,
            "rest_stage",
            deployment_id=deployement.id,
            rest_api_id=self.api_id,
            stage_name="v1",
            tags=self.tags,
        )

        plan = ApiGatewayUsagePlan(
            self,
            "plan",
            name=f"RestApi-{self.tags['project']}-{self.tags['env']}",
            api_stages=[{"apiId": self.api_id, "stage": rest_stage.stage_name}],
            tags=self.tags,
        )

        key = ApiGatewayApiKey(
            self,
            "key",
            name=f"REST-KEY-{self.tags['project']}-{self.tags['env']}",
            tags=self.tags,
        )

        ApiGatewayUsagePlanKey(
            self, "usagekey", key_id=key.id, key_type="API_KEY", usage_plan_id=plan.id
        )

        TerraformOutput(self, "rest_api_url", value=rest_stage.invoke_url)
        TerraformOutput(self, "rest_api_key_name", value=key.name)
        TerraformOutput(self, "rest_api_key_value", value=key.value, sensitive=True)
        self.api_key_value = key.value
