import boto3
from botocore.exceptions import ClientError
import json
import os
import subprocess
import sys

# Set region
REGION = "us-east-1"

def main_function(queue_name):
    '''
    Gets queue object from SQS and continuously calls process_queue
    function to poll it and process each message.
    '''
    # Referred to "3. Get an existing queue by name"
    # https://aws.plainenglish.io/sqs-with-aws-sdk-for-python-boto3-on-ec2-85d343ba0a49
    sqs = boto3.resource('sqs', region_name = REGION)
    while True:
        try:
            queue = sqs.get_queue_by_name(QueueName=queue_name)
        except ClientError as e:
            error_message = e.response['Error']['Message']
            # If queue doesn't exist, exit main function
            if error_message == "The specified queue does not exist for this wsdl version.":
                print("Queue does not exist, exiting the system")
                sys.exit()
            else:
                print("Failure to retrieve the queue. ", e.response['Error']['Message'])
        process_queue(queue)


def process_queue(queue_object):
    '''
    Uses long polling to read messages from SQS queue, extracts job parameters
    and launches the annotator. Persists job status to the database, and, if 
    successful, deletes the processed message from the queue.
    '''
    # (1) Attempt to read a message from the queue with long polling
    # https://github.com/boto/boto3/issues/324
    print("Asking SQS for up to 10 messages.")
    try:
        messages = queue_object.receive_messages(WaitTimeSeconds=15) #Set long polling interval to 15 seconds
    except ClientError as e:
        print("Failure to retrieve messages from queue. ", e.response['Error']['Message'])
        return

    if len(messages) > 0:
        for message in messages:
            msg_body = json.loads(json.loads(message.body)["Message"])
            # If message read, extract job parameters from the message body
            job_id = msg_body["job_id"]
            input_file_name = msg_body["input_file_name"]
            s3_inputs_bucket = msg_body["s3_inputs_bucket"]
            s3_key_input_file = msg_body["s3_key_input_file"]
  
            # (2) Create a parent directory to store directories that will contain job_id's
            if not os.path.exists(f"/home/ubuntu/anntools/data/job_ids"):
                os.mkdir(f"/home/ubuntu/anntools/data/job_ids")

            # (3) If it does not exist, create a directory to store job_id locally and run the subprocess
            # https://www.geeksforgeeks.org/create-a-directory-in-python/#
            if not os.path.exists(f"/home/ubuntu/anntools/data/job_ids/{job_id}"):
                os.mkdir(f"/home/ubuntu/anntools/data/job_ids/{job_id}")
            # Get the input file S3 object and copy it to a local file
            input_file_path = f"/home/ubuntu/anntools/data/job_ids/{job_id}/{input_file_name}"
            try: 
                # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-example-download-file.html
                s3 = boto3.client('s3', region_name= REGION)
                s3.download_file(s3_inputs_bucket, s3_key_input_file, input_file_path)
            except ClientError as e:
                error_code = e.response['ResponseMetadata']['HTTPStatusCode']
                # If input file does not exist(ie. resource not found), then update job status to 'FAILED' in the
                # database and delete message from queue
                if error_code == 404: 
                    client = boto3.resource('dynamodb', region_name= REGION)
                    try:
                        # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.KeyConditions.html
                        table = client.Table("mariagabrielaa_annotations")
                        response = table.update_item(Key={"job_id": job_id},
                                                    UpdateExpression="SET job_status= :job_st",
                                                    ExpressionAttributeValues={':job_st': 'FAILED'})
                        try: # If job status updated to "FAILED" is successful, delete message from queue
                            message.delete()
                            print("Input file does not exist, message deleted from queue")
                            return
                        except ClientError as e:
                            print("Failure to delete message from the queue", e.response['Error']['Message'])
                            return
                    except ClientError as e:
                        print("Unable to update job status to 'FAILED' in the database.", e.response['Error']['Message'])
                        return
                else:
                    print("Failure to download input file from S3.", )
                    return

            # (4) Launch annotation job as a background process
            # Referred to 0:40' - 1:44', https://www.youtube.com/watch?v=VlfLqG_qjx0
            cmd = f'python a9_run.py /home/ubuntu/anntools/data/job_ids/{job_id}/{input_file_name} {job_id} {input_file_name}'
            ann_process = subprocess.Popen(cmd, shell=True)   
            # Error Handling when annotator job fails to launch: if the return code is different 
            # from 0 or None, there was an error
            # Referred to 1:28'- 1:48, https://www.youtube.com/watch?v=VlfLqG_qjx0
            if ann_process.returncode is not None and ann_process.returncode !=0:
                print("Annotator job failed to launch")
                return

            # (5) Update the “job_status” key in the annotations table to “RUNNING”
            # https://stackoverflow.com/questions/34447304/example-of-update-item-in-dynamodb-boto3
            # https://iamvickyav.medium.com/aws-dynamodb-with-python-boto3-part-4-update-attribute-delete-item-from-dynamodb-97caf4770ba
            client = boto3.resource('dynamodb', region_name= REGION)
            try:
                # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.KeyConditions.html
                table = client.Table("mariagabrielaa_annotations")
                response = table.update_item(Key={"job_id": job_id},
                                            ConditionExpression= "job_status = :current_status",
                                            UpdateExpression="SET job_status= :job_st",
                                            ExpressionAttributeValues={':job_st': 'RUNNING', ':current_status': 'PENDING'})
            except ClientError as e:
                print("Failure to update the database.", e.response['Error']['Message'])
                return

            # (6) Delete message from queue, if job was successfully submitted
            try:
                message.delete()
            except ClientError as e:
                print("Failure to delete message from the queue", e.response['Error']['Message'])
                return

# Call main function
main_function("mariagabrielaa_job_requests")