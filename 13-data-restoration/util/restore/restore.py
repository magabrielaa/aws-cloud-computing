import json
import boto3
from botocore.exceptions import ClientError
import json

# Define constants
REGION = "us-east-1"
QUEUE_NAME = "mariagabrielaa_a16_restore"
WAIT_TIME = 15
MAX_MESSAGES = 10
GLACIER_VAULT = "ucmpcs"
DYNAMO_TABLE = "mariagabrielaa_annotations"
ACL = "private"
S3_BUCKET = "gas-results"

def lambda_handler(event, context):
    print("event:", event)
    
    # (1) Set up queue object
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#SQS.ServiceResource.get_queue_by_name
    sqs = boto3.resource('sqs', region_name=REGION)
    try:
        queue = sqs.get_queue_by_name(QueueName=QUEUE_NAME)
        print("1. Retrieved restore queue object")
    except ClientError as e:
        print("1. Failed to retrieve restore queue", e.response['Error']['Message'])
        return {'statusCode': 500, 'body': json.dumps("error: Failed to retrieve restore queue")}
    
    # (2) Attempt to read messages from restore queue
    try:
        messages = queue.receive_messages(WaitTimeSeconds=WAIT_TIME,
                                        MaxNumberOfMessages=MAX_MESSAGES)
        print("2. Retrieved messages from restore queue")
    except ClientError as e:
        print("2. Failed to retrieve messages from restore queue.", e.response['Error']['Message'])
        return {'statusCode': 500, 'body': json.dumps("error: Failed to retrieve messages from restore queue.")}
    
    # (3) Process restore message
    if len(messages) > 0:
        for message in messages:
            msg_body = json.loads(json.loads(message.body)["Message"])
            
            # Save variables
            job_id = msg_body["JobDescription"]
            retrieval_request_id = msg_body["JobId"]
            archive_id = msg_body["ArchiveId"]
            print("3. Job ID being processed: ", job_id)
            
            # (4) Get file output 
            # https://github.com/awsdocs/aws-doc-sdk-examples/blob/main/python/example_code/glacier/glacier_basics.py
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Job.get_output
            glacier = boto3.resource('glacier', region_name=REGION)
            try:
                job = glacier.Job('-', GLACIER_VAULT, retrieval_request_id)
                response = job.get_output()
                results_bytes = response['body'].read()
                print("4. Retrieved results file output successfully")
            except ClientError as e:
                print("4. Failed to get results file output", job.id)
                return {'statusCode': 500, 'body': json.dumps("error: Failed to get results file output")}

            # (5) Query the database to get results file key
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            try:
                ann_table = dynamodb.Table(DYNAMO_TABLE)
                response = ann_table.get_item(Key={'job_id': job_id})
                print("5. Queried the database to get the results file key")
            except ClientError as e:
                print("5. Failed to query the database", e.response['Error']['Message'])
                return {'statusCode': 500, 'body': json.dumps("error: Failed to query the database")}

            if "Item" in response:
                job_item = response['Item']
                key_results_file = job_item["s3_key_result_file"]
            
            # (6) Restore results file to S3
            try:
                client = boto3.client('s3', region_name=REGION)
                response = client.put_object(ACL=ACL,
                                            Body=results_bytes,
                                            Bucket=S3_BUCKET,
                                            Key=key_results_file)
                print("6. Successfully uploaded results file to S3")
            except ClientError as e:
                print("6. Failed to restore results file to S3 bucket", e.response['Error']['Message'])
                return {'statusCode': 500, 'body': json.dumps("error: Failed to restore results file to S3 bucket")}
            
            # (7) Delete archive from Glacier
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.delete_archive
            try:
                client = boto3.client('glacier', region_name=REGION)
                response = client.delete_archive(vaultName=GLACIER_VAULT,
                                                archiveId=archive_id)
                print("7. Deleted archived file from Glacier")
            except ClientError as e:
                print("7. Unable to delete archive from Glacier", e.response['Error']['Message'])
                return {'statusCode': 500, 'body': json.dumps("error: Unable to delete archive from Glacier")}
                
            # (8)) Remove archive ID and retrieval_request_id from Dynamo DB
            # https://stackoverflow.com/questions/37721245/boto3-updating-multiple-values
            resource = boto3.resource('dynamodb', region_name=REGION)
            try:
                table = resource.Table(DYNAMO_TABLE)
                response = table.update_item(Key={"job_id": job_id},
                                            UpdateExpression="REMOVE results_file_archive_id, retrieval_request_id")
                print("8. Removed archive_id and retrieval_request_id from Dynamo")
            except ClientError as e:
                print("8. Unable to remove archive_id and retrieval_request_id from Dynamo. ", e.response['Error']['Message'])
                return {'statusCode': 500, 'body': json.dumps("error: Removed archive_id and retrieval_request_id from Dynamo")}
            
            # (9) Delete message from restore queue
            try:
                message.delete()
                print("9. Message deleted from restore queue")
            except ClientError as e:
                print("9. Failed to delete message from restore queue. ", e.response['Error']['Message'])
                return {'statusCode': 500, 'body': json.dumps("error: Failed to delete message from restore queue")}
                
    return {'statusCode': 200, 'body': json.dumps("Restoration process successful")}