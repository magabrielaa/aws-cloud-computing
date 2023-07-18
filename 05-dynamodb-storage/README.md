# Persisting Data in a Key-Value Store

Before, the GAS was refactored into two services: a web app and an annotation service. Altough both services run on separate EC2 instances, they are still dependent on each other being available for the system to remain in a consistent state.

Here, I add a key-value store (KVS) to persist the annotation job information by using AWS DynamoDB. This allows both services to access/update a job as its status changes.

The application looks like this with the updated changes:

![GAS application](https://github.com/magabrielaa/aws-cloud-computing/blob/main/05-dynamodb-storage/application.jpg)