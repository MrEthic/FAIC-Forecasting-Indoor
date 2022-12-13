# Brew AI IAQ Project

**The goal the project:**
1. Explore infractrucure decision for
    - Ingesting sensor data
    - Store Data in a database
    - Export data as csv
    - Build ML models
    - Train models
    - Deploy model
    - Make real-time prediction on incoming data point
2. Learn how different AWS services works and how they can interact with each others
3. Explore Databricks

# Index
1. [Infrastructure](#infrastructure)
    1. [Solution overview](#solution-overview)
    2. [AWS Schema](#infrastrucure)
2. [Database](#database)
    1. [Data Model](#data-model)
    2. [SQL Queries](#sql-queries)
3. [API](#api)
    1. [Schema](#api-schema)
    2. [GET /sensorsdata](#get-sensorsdata)
    3. [PUT /sensorsdata](#put-sensorsdata)
    4. [GET /sensorsdata/sensors](#get-sensorsdatasensors)
    5. [GET /predictions](#get-predictions)
    6. [Usage](#usage)
4. [Brew AI Data Fetcher](#brew-ai-data-fetcher)
    1. [Schema](#fetcher-schema)
    2. [BrewAI API](#brewai-api)
5. [ETLs](#etls)
    1. [Daily export](#daily-export)
    2. [Last N-days export](#last-n-days-export)

# Repo Organisation
```
aws/ --> aws IAAS code
databricks/ --> all databricks notebooks
    /models --> model notebooks
        /training --> training of models
        /selection --> model selection (UCB1)
    /etls --> databricks jobs
examples/ --> Some code example
static/ --> images for README
```

# Infrastructure
The infrastrucure is build using Terrafor's cdktf. It is built on top of the [FAIC AWS Template](https://github.com/MrEthic/FAIC-Project-AWS-Template).

## Solution overview
```mermaid
    flowchart TD
        bw(BrewAI)
        api{{API}}
        db[(Database)]
        s3[(Datalake)]
        viz[[Visualisation]]
        serving([Model Serving])
        repo([Model Repo])
        wexport[Weekly Export]
        train[Models Training]
        select[Models Selection]
        pred[Forecast]

        bw-->api
        api<-->db
        api-->viz
        api-->wexport-->s3-->train-->repo
        s3-->select
        repo--model-->select-->serving
        db<-->pred<-->serving
```

## Infrastrucure
![AWS Solution](static/img/solution.jpg "AWS Solution")

# Database
We decided to use AWS Timestream service for our solution. According to AWS, Timestream is particularly usefull when working with sensor data.

| Pros  | Cons |
| ------------- | ------------- |
| Managed service (auto scale) | AWS Depedent |
| SQL Based | No flexibility with datamodel |
| Timeseries optimized |  |
| Built-in functions |  |
| Cost efficient |  |
| Control on how much data to keep |  |
| Memory/Magnetic store |  |

## Data model
Our database has two tables:
- sensorsdata: stores sensor's measures about air quality
- predictions: stores predictions on air quality

Both tables have the same data model as Timestream doesn't allow much flexibility:

| Attribute Name  | Description |
| ------------- | ------------- |
| time | The timestamp (utc) of the measure |
| deviceId | The device id (sensor id) of the measure |
| measure_name | Name of the measure |
| measure_value | Value of the measure |

In the sensorsdata table, measure_name is one of: iaq, temperature, humidity, voc, pressure or co2.

In the predictions table, measure_name is: `{measure_name}~{timedelta}`. For example `iaq~5` is the predicted iaq 5 minutes ago. Therefor, when inserted in the table, the predictions rows have timestamp in the future.

## SQL Queries
As Timestream is SQL based, data can be queried with SQL. Check the [example notebook](databricks/examples/timestream_sql.ipynb) for example using boto3.

Example of query:
```SQL
SELECT 
  time,
  deviceId,
  measure_value::double AS temperature
FROM "database"."table"
WHERE
  measure_name='temperature'
  AND time between ago(1h) and now()
ORDER BY time DESC
```

To convert the key, value data model into a tabular format, use the MAX function with if statements:
```SQL
SELECT 
  time,
  MAX(if(deviceId = 'B84C4503F361D64A', measure_value::double)) AS "B84C4503F361D64A",
  MAX(if(deviceId = '99DD33EFB7990A71', measure_value::double)) AS "99DD33EFB7990A71",
  MAX(if(deviceId = '7BB92D02D696C5C5', measure_value::double)) AS "7BB92D02D696C5C5"
FROM "database"."table"
WHERE
  measure_name = 'iaq'
  AND time between ago(1h) and now()
GROUP BY time
ORDER BY time ASC
```

Timestream supports advance SQL synthax:
```SQL
WITH measures AS (
  SELECT
    time,
    AVG(measure_value::double) as iaq
  FROM $__database."sensors"
  WHERE deviceId='${device}'
  AND measure_name='iaq'
  AND time between date_add('hour', -6, now()) and date_add('minute', 15, now())
  GROUP BY time
), predictions as (
  SELECT 
    time,
    MAX(if(measure_name = 'iaq~5', measure_value::double)) AS iaq5,
    MAX(if(measure_name = 'iaq~10', measure_value::double)) AS iaq10,
    MAX(if(measure_name = 'iaq~15', measure_value::double)) AS iaq15
  FROM $__database."predictions"
  WHERE deviceId='${device}'
  AND time between date_add('hour', -6, now()) and date_add('minute', 15, now())
  GROUP BY time
)
SELECT
  measures.time,
  AVG(measures.iaq) as IAQ,
  AVG(predictions.iaq5) as "IAQ 5MIN",
  AVG(predictions.iaq10) as "IAQ 10MIN",
  AVG(predictions.iaq15) as "IAQ 15MIN"
FROM measures LEFT JOIN predictions on measures.time = predictions.time
GROUP BY measures.time
ORDER BY measures.time ASC
```

# API
In order to make data available to other projects, we built an API. It is also used as an abstraction layer on top of the database. People should be able to build notebooks using our data without any knowledge on how our database works.

The API is developped with API Gateway and Lambda integrations on methods. All methods are protected by API Keys (AWS).

## API Schema
```mermaid
    flowchart TD
        l[Lambdas Functions]
        r([API Resource *path*])
```
```mermaid
    flowchart TD
        db[(Database)]
        api{{API Gateway}}
        rdata([/sensorsdata])
        rpred([/predictions])
        rsensors([/sensors])
        dataget[brewai-sensor-iaq-get-data-dev]
        dataput[brewai-sensor-iaq-put-data-dev]
        sensorsget[brewai-sensor-iaq-get-sensor-dev]
        predget[brewai-sensor-iaq-get-pred-dev]

        api-- resource -->rdata-- resource -->rsensors
        api-- resource -->rpred

        rdata-- GET -->dataget<-->db
        rdata-- PUT -->dataput<-->db
        rsensors-- GET -->sensorsget<-->db
        rpred-- GET -->predget<-->db
```

## GET /sensorsdata
Get data beetween two timestamp for a specific device.

> [Lambda handler](aws/src/code/timestream_get.py)

| Parameter      | Description |
| ----------- | ----------- |
| from | Timestamp in the utc unix(s) format of the starting datetime of query |
| to | Timestamp in the utc unix(s) format of the ending datetime of query |
| device | The device id to get data from |
| (Optional) measure | Optional measure to query |

**Example**:

Query temperature of device 0 from 1/1/2022 to 30/1/2022: `GET /sensorsdata?from=1640995200&to=1643500800&device=0&measure=temperature`

**Response**
JSON
```python
{
    'Records': [
        [Objects],
        ...
    ],
    'Metadata': {
        'SourceName': String,
        'SourceType': String,
        'SourceFormat': String('Timeserie'|'Tabular'|'Text'),
        'ColumnName': [
            Strings,
            ...
        ],
        'ColumnType': [
            Strings('timestamp'|'float'|'str')
        ]
    },
    'ExecutionInfo': {
        "LastQueryId": String,
        "NextTokenConsumed": Integer,
        "NextToken": String,
    }
}
```

| Field      | Description |
| ----------- | ----------- |
| Records | List of records as list |
| Metadata | Metadata anout API |
| SourceName | Name of the source (ex: BrewAI) |
| SourceType | Type of the source (ex: SensorData) |
| SourceFormat | Format of the source, either Timeserie, Tabular or Text |
| ColumnName | List of column names (same size as records size) |
| ColumnType | List of column types (same size as records size) |
| LastQueryId | Query ID for debuging |
| NextTokenConsumed | Number of paginated queries made |
| (Optional) NextToken | Potential next token for pagination |

## PUT /sensorsdata
Insert data in database.

> [Lambda handler](aws/src/code/timestream_put.py)

**JSON Payload**
```python
{
    'devid': String(Device ID),
    'ts': String(Time of the measure),
    'readings': List[7](List of 7 readings)
}
```

## GET /sensorsdata/sensors
Get the list of unique sensors (device) ids.

> [Lambda handler](aws/src/code/sensors_get.py)

**Response**
JSON
```python
{
    'Records': [
        [String(DeviceId)],
        ...
    ],
    'Metadata': {
        'SourceName': String,
        'SourceType': String,
        'SourceFormat': String('Timeserie'|'Tabular'|'Text'),
        'ColumnName': [
            'deviceId'
        ],
        'ColumnType': [
            'str'
        ]
    },
    'ExecutionInfo': {
        "LastQueryId": String,
        "NextTokenConsumed": Integer,
        "NextToken": String,
    }
}
```

## GET /predictions
Get predictions beetween two timestamp for a specific device.

> [Lambda handler](aws/src/code/timestream_get_pred.py)

| Parameter      | Description |
| ----------- | ----------- |
| from | Timestamp in the utc unix(s) format of the starting datetime of query |
| to | Timestamp in the utc unix(s) format of the ending datetime of query |
| device | The device id to get data from |
| (Optional) measure | Optional measure to query |

**Example**:

Query predictions of iaq5 of device 0 from 1/1/2022 to 30/1/2022: `GET /sensorsdata?from=1640995200&to=1643500800&device=0&measure=iaq~5`

**Response**
JSON
```python
{
    'Records': [
        [Objects],
        ...
    ],
    'Metadata': {
        'SourceName': String,
        'SourceType': String,
        'SourceFormat': String('Timeserie'|'Tabular'|'Text'),
        'ColumnName': [
            Strings,
            ...
        ],
        'ColumnType': [
            Strings('timestamp'|'float'|'str')
        ]
    },
    'ExecutionInfo': {
        "LastQueryId": String,
        "NextTokenConsumed": Integer,
        "NextToken": String,
    }
}
```

| Field      | Description |
| ----------- | ----------- |
| Records | List of records as list |
| Metadata | Metadata anout API |
| SourceName | Name of the source (ex: BrewAI) |
| SourceType | Type of the source (ex: SensorData) |
| SourceFormat | Format of the source, either Timeserie, Tabular or Text |
| ColumnName | List of column names (same size as records size) |
| ColumnType | List of column types (same size as records size) |
| LastQueryId | Query ID for debuging |
| NextTokenConsumed | Number of paginated queries made |
| (Optional) NextToken | Potential next token for pagination |

## Usage
You can find examples on how to use the API in python in the [API Function](databricks/utils/api_functions.ipynb).

A API Key is needed, it has to be passed as a request header `{"x-api-key": API_KEY}`.

# Brew AI Data Fetcher
As we do not have sensors yet, we use an API provided by BrewAI to fetch their sensor data. This is done using a Lambda function scheduled to run every minutes by a Cloudwatch event.

Data is stored in both the database and the bronze datalake. In the datalake, json object are stored following the key: `brewai/sensors/yyyy-mm-dd/{id}.json`.

## Fetcher Schema
```mermaid
    flowchart LR
        event([Event Bridge])
        l[brewai-sensor-iaq-scheduled-fetch-from-brewai-dev]
        db[(Timestream)]
        s3[(Bronze Datalake)]

        event-- every minutes -->l
        l-->db
        l-->s3
```
> [Lambda code](aws/src/code/brewai_fetch.py)

## BrewAI API
Endpoint used to fetch the latest readings of all devices: `https://model.brewai.com/api/sensor_readings?latest=true`. We need to pass a token in the header: `{"Authorization": "Bearer {BREWAI_API_KEY}"}`.

# ETLs
Some ETLs exists to convert raw json data fetched from the API to csv files more suitable for python notebook. Those ETLs are made with spark.

## Daily export
Transform the json readings of the day into a csv file in the silver datalake.
```mermaid
    flowchart LR
        a[Extract json files from bronze datalake]-->b[Converte datetime & extract readings]-->c[Save as csv in silver datalake]
```
CSV is stored under `brewai/sensors/yyyy-mm-dd/raw.csv`.

## Last N-days export
Transform the json readings of the last N days into a csv file in the silver datalake.
```mermaid
    flowchart LR
        a[Extract json files from bronze datalake]-->b[Converte datetime & extract readings]-->c[Save as csv in silver datalake]
```
CSV is stored under `brewai/sensors/export/yyyymmdd.yyyymmdd/raw.csv` and `brewai/sensors/latest/N-days`.

# Models
Four models have been trained to predict the next 15 minutes of IAQ values. The training codes are on databricks in `/databricks/models/training`.

The models are trained every weeks (monday at 00:00 UTC+11) on the data of the last week. The databricks Job `sensors-weekly-export-and-training` is triggered every week, it runs the [sensors-weekly-export](databricks/etls/sensors-weekly-export.ipynb) etl and the training notebooks.

```mermaid
    flowchart TD
        export(sensors-weekly-export)
        xg(train-xgboost)
        lstm(train-lstm)
        mlp(train-mlp)

        export-->xg
        export-->lstm
        export-->mlp
```

All models have the same signature: `(-1, 60) --> (-1, 15)`. They accept a 2D array of list of 60 iaq values and output arrays or 15 minutes predictions. The model have to handle any normalization/preprocessing themself.

Trained models artifact are saved as MLFlow experiement. They can then be load and register later.

## Simple LSTM
## MLP
## XGBoost
## MA
## [AUTOKERAS]

# Model Selection
