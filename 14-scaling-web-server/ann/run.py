# run.py
#
# Copyright (C) 2011-2019 Vas Vasiliadis
# University of Chicago
#
# Wrapper script for running AnnTools
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import sys
import time
import driver
import boto3
from botocore.exceptions import ClientError
import os, errno
import json

# Get configuration
from configparser import ConfigParser
config = ConfigParser(os.environ)
config.read('ann_config.ini')

# Constant variables for reuse
REGION = config["aws"]["region_name"]
PATH = config["file_system"]["path"]

"""A rudimentary timer for coarse-grained profiling
"""
class Timer(object):
    def __init__(self, verbose=True):
        self.verbose = verbose
    
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        self.end = time.time()
        self.secs = self.end - self.start
        if self.verbose:
            print(f"Approximate runtime: {self.secs:.2f} seconds")

if __name__ == '__main__':
    # Call the AnnTools pipeline
    if len(sys.argv) > 1:
        with Timer():
            driver.run(sys.argv[1], 'vcf')
        # Retrieve input_file and job_id from command line arguments (run by the subprocess)
        job_id = sys.argv[2]
        input_file = sys.argv[3]
        user_id = sys.argv[4]
        input_file_name = input_file.split(".")[0] # Remove .vcf extension
        user_role = sys.argv[5]

        # Set up variables
        acl = config["s3"]["acl"]
        results_bucket = config["s3"]["results_bucket"]
        log_file = config["s3"]["key_prefix"] + f'{user_id}/{job_id}~{input_file_name}.vcf.count.log'
        results_file = config["s3"]["key_prefix"] + f'{user_id}/{job_id}~{input_file_name}.annot.vcf'
        completion_time = int(time.time())

        # (1) Upload the results and log files to S3 results bucket
        # Referred to put_object(**kwargs)
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.put_object
        if os.path.exists(PATH + job_id):
            all_files = os.listdir(PATH + job_id)
            for file in all_files:
                if file.endswith("annot.vcf") or file.endswith("count.log"):
                    try:
                        # https://www.radishlogic.com/aws/s3/how-to-upload-a-local-file-to-s3-bucket-using-boto3-and-python/
                        with open(PATH + job_id + "/" + file, 'rb') as data:
                            client = boto3.client('s3', region_name=REGION)
                            client.put_object(
                                        ACL=acl,
                                        Body=data,
                                        Bucket=results_bucket,
                                        Key=config["s3"]["key_prefix"] + f'{user_id}/{job_id}~{file}')
                    except ClientError as e:
                        print("Failure to upload annotation files to S3. ", e.response['Error']['Message'])
                    # Remove results and log files from directory
                    # https://stackoverflow.com/questions/10840533/most-pythonic-way-to-delete-a-file-which-may-not-exist
                    try:
                        os.remove(PATH + job_id + "/" + file)
                    except OSError as e: 
                        print(f'Failed to remove {file}. {e}')
                else:
                    try:
                        os.remove(PATH + job_id + "/" + file) # Remove input file
                    except OSError as e: 
                        print(f'Failed to remove {file}. {e}')

        # (2) Update job item in DynamoDB table
        client = boto3.resource('dynamodb', region_name=REGION)
        try:
            # https://stackoverflow.com/questions/51048477/how-to-update-several-attributes-of-an-item-in-dynamodb-using-boto3
            table = client.Table(config["dynamodb"]["table_name"])
            table.update_item(
                            Key={"job_id": job_id},
                            ConditionExpression="job_status = :current_status",
                            UpdateExpression="SET s3_results_bucket= :results_bucket, s3_key_result_file= :results_file, \
                                            s3_key_log_file= :log_file, complete_time= :compl_time, job_status= :job_st",
                            ExpressionAttributeValues={
                                                    ':current_status': 'RUNNING',
                                                    ':results_bucket': results_bucket, 
                                                    ':results_file': results_file ,
                                                    ':log_file': log_file,
                                                    ':compl_time': completion_time ,
                                                    ':job_st': 'COMPLETED'
                                                    },
                            ReturnValues="UPDATED_NEW")
        except ClientError as e:
            print("Failure to update the database to COMPLETED.", e.response['Error']['Message'])

        # (3) Remove empty directory
        # https://ubuntuforums.org/archive/index.php/t-1459923.html
        try:
            os.rmdir(PATH + job_id)
        except OSError as e:
            if e.errno == os.errno.ENOTEMPTY:
                print("Failed to empty directory")

        # (4) Publish a notification message to SNS results topic 
        # Referred to "Publish to a topic", https://docs.aws.amazon.com/code-library/latest/ug/python_3_sns_code_examples.html
        # https://stackoverflow.com/questions/40667452/boto3-publish-message-sns
        message = {
                "job_id": job_id,
                "user_id": user_id, 
                "complete_time": completion_time,
                "job_status": "COMPLETED"}
        try:
            sns = boto3.client("sns", region_name=REGION)
            response = sns.publish(
                                TopicArn=config["sns"]["results_arn"],
                                Message=json.dumps({"default":json.dumps(message)}),
                                MessageStructure='json')
        except ClientError as e:
            print("Unable to publish message to SNS topic:", e.response['Error']['Message'])

        # (5) If the user role is free, start state machine execution
        # https://stackoverflow.com/questions/45790568/invoking-aws-step-function-from-lambda-in-python
        if user_role == "free_user":
            try:
                client = boto3.client('stepfunctions', region_name=REGION)
                response = client.start_execution(
                                                stateMachineArn=config["state_machine"]["arn"],
                                                name=job_id,
                                                input=json.dumps({"job_id": job_id}))
            except ClientError as e:
                print("Failed to start state machine execution")

            # (5.1) Persist execution ARN to the database
            execution_arn = response["executionArn"]
            resource = boto3.resource('dynamodb', region_name=REGION)
            
            try:
                table = resource.Table(config["dynamodb"]["table_name"])
                response = table.update_item(
                                            Key={"job_id": job_id},
                                            UpdateExpression="SET execution_arn= :exec_arn",
                                            ExpressionAttributeValues={':exec_arn': execution_arn})
            except ClientError as e:
                print("Failure to update the database with execution ARN")
else:
        print("A valid .vcf file must be provided as input to this program.")
### EOF