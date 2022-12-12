# Fintech Artificial Inteligence Consortium LAB AWS Project Template

Complete documentation available on [github pages](https://mrethic.github.io/FAIC-Project-AWS-Template/)

The Fintech Artificial Inteligence Consortium LAB is an UNSW vistual lab.

This is a template for starting new project on AWS.

## Important consideration

The state of the terraform configuration is saved to an S3 bucket.

It is saved in the bucket terraform-backend-faic-infra under a folder named after your project.
the tfstate file is suffixed with the environement. If you change the backend configuration, you might destroy your infrastructure...

## How to use?

Please, learn how to use terraform and how AWS works before doing anything...

1. Configure your AWS credentials, refer to [provider documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs#authentication-and-configuration), **do not hard code your secret token**. You will need IAM permission to deploy services and access the terraform-backend-faic-infra bucket.

2. Modify the infrastructure definition.

3. run `pipenv install`

4. run `make` in the console. **Double check the terraform plan** before accepting the changes.

    3.1 Depending on your os, you might need to run `pipenv shell`

5. Check the outputs.json file to find API url and API keys.

## Commands

- `make zip_lambdas`: compress lambdas code
- `make deploy`: deploy stack
- `make output`: write outputs to outputs.json
- `make destroy`: destroy the stack (bad idea)

## Modules

### DynamoDB
DynamoDB: `src.dynamo` you will find a preconfigured DynamoDB table for your project.

DynamoWebsocket: `src.streaming` you can set `isstrem=True` when creating the DynamoDB object table. A websocket API that stream DynamoDB insertion will be created.

### Timestream
Timestream: `src.timestream` preconfigured timestream table for timestaries

### RESTApi
RESTApi: `src.api` create a rest API for your project table. The sample codes are made to work with dynamoDB, you must update them dependings on your needs.
> Usage: create the api then call api.add_endpoint to add lambda proxy endpoints. Call api.finalize to finalize the api (stage, keys, etc.)

### Lambdas
Contains a set a configurable lambdas:
- ScheduledLambdas: Lambda that runs according to a schudle exeption (every minutes, week, crontask, etc.)
- InvokableLambdas: Lambda that can be executed from another service

## Modifying the stack

Few considerations when it comes to modifying the stack.

1. All lambdas code goes to `/src/code`
2. If you don't want to use the prefefined infrastructure (Dynamo, Timeseries, RESTApi etc.), no support will be made
3. Do not add to much abstraction, keep things simple
4. One module = one functionality (exemple: datalake, docker orchestration, sagemaker env etc.), do not split resources belongings to same functionality (Datalake API go with the actual Datalake definition)


<span style="color:red">⚠️🔴**There is no ctrl-z in terraform and AWS**🔴⚠️</span>