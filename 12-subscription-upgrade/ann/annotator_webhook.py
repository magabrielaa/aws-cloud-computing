# annotator_webhook.py
#
# NOTE: This file lives on the AnnTools instance
# Modified to run as a web server that can be called by SNS to process jobs
# Run using: python annotator_webhook.py
#
# Copyright (C) 2011-2022 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import requests
from flask import Flask, jsonify, request
import json
import os, errno
import subprocess
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)
environment = 'ann_config.Config'
app.config.from_object(environment)


'''
A13 - Replace polling with webhook in annotator

Receives request from SNS; queries job queue and processes message.
Reads request messages from SQS and runs AnnTools as a subprocess.
Updates the annotations database with the status of the request.
'''
@app.route('/process-job-request', methods=['GET', 'POST'])
def annotate():

  PATH = app.config['ANNOTATOR_JOBS_DIR']
  REGION = app.config['AWS_REGION_NAME']

  if (request.method == 'GET'):
    return jsonify({ "code": 405, "error": "Expecting SNS POST request."}), 405

  # (1) Check message type
  req = json.loads(request.data)
  msg_type = req["Type"]

  # (2) Confirm SNS topic subscription confirmation
  # https://gist.github.com/iMilnb/bf27da3f38272a76c801
  if msg_type == 'SubscriptionConfirmation' and 'SubscribeURL' in req:
    response = requests.get(req['SubscribeURL'])

  # (3) If the SNS message type is a notification, poll the queue
  elif msg_type == 'Notification':
    message = req["Message"]
    msg_body = json.loads(message)
    
    # Referred to "3. Get an existing queue by name"
    # https://aws.plainenglish.io/sqs-with-aws-sdk-for-python-boto3-on-ec2-85d343ba0a49
    sqs = boto3.resource('sqs', region_name=REGION)
    try:
      queue = sqs.get_queue_by_name(QueueName=app.config["AWS_SQS_QUEUE_NAME"])
    except ClientError as e:
      return jsonify({ "code": 500, "error": f'Failed to retrieve the queue. {e}'}), 500

    # Set up wait time and max message variables
    wait_time = app.config["AWS_SQS_WAIT_TIME"]
    max_messages = app.config["AWS_SQS_MAX_MESSAGES"]
    print("Asking SQS for up to 10 messages.")

    # Attempt to poll the queue
    try:
        messages = queue.receive_messages(WaitTimeSeconds=wait_time,
                                          MaxNumberOfMessages= max_messages)
    except ClientError as e:
        return jsonify({ "code": 500, "error": f'Failure to retrieve messages from queue. {e}'}), 500

    if len(messages) > 0:
      for message in messages:
        msg_body = json.loads(json.loads(message.body)["Message"])

        # Check if message contains all required elements
        lst = ["job_id", "user_id", "input_file_name", "s3_inputs_bucket", "s3_key_input_file", "user_role"]
        # If any parameter is missing, message cannot be processed and is deleted
        if not all(val in msg_body for val in lst):
          try:
            message.delete()
            print("SNS message does not contain required fields, message deleted")
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failed to delete message from queue. {e}'}), 500

        else:
          # Extract job parameters from the message body
          job_id = msg_body["job_id"]
          user_id = msg_body["user_id"]
          input_file_name = msg_body["input_file_name"]
          s3_inputs_bucket = msg_body["s3_inputs_bucket"]
          s3_key_input_file = msg_body["s3_key_input_file"]
          user_role = msg_body["user_role"]

          # (4) Create a parent directory to store directories that will contain job_id's
          if not os.path.exists(PATH):
            try:
              os.mkdir(PATH)
            except OSError as e:
              return jsonify({ "code": 500, "error": f'Failed to create parent directory. {e}'}), 500

          # (5) If it does not exist, create a directory to store job_id locally and run the subprocess
          # https://www.geeksforgeeks.org/create-a-directory-in-python/#
          if not os.path.exists(PATH + job_id):
            try:
              os.mkdir(PATH + job_id)
            except OSError as e:
              return jsonify({ "code": 500, "error": f'Failed to create job id directory.  {e}'}), 500

          # (6) Get the input file S3 object and copy it to a local file
          input_file_path = PATH + f"{job_id}/{input_file_name}"
          try: 
            # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-example-download-file.html
            s3 = boto3.client('s3', region_name=REGION)
            s3.download_file(s3_inputs_bucket, s3_key_input_file, input_file_path)
          except ClientError as e:
            error_code = e.response['ResponseMetadata']['HTTPStatusCode']
            # If input file does not exist(ie. resource not found), then update job status to 'FAILED' in the
            # database and delete message from queue
            if error_code == 404: 
              client = boto3.resource('dynamodb', region_name=REGION)
              try:
                # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.KeyConditions.html
                table = client.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
                response = table.update_item(Key={"job_id": job_id},
                                            UpdateExpression="SET job_status= :job_st",
                                            ExpressionAttributeValues={':job_st': 'FAILED'})
              except ClientError as e:
                return jsonify({ "code": 500, "error": f'Unable to update job status to "FAILED" in the database. {e}'}), 500

              # If job status update to "FAILED" is successful, delete message from queue
              try: 
                message.delete()
              except ClientError as e:
                return jsonify({ "code": 500, "error": f'Failed to delete message from queue. {e}'}), 500

            else:
              return jsonify({ "code": 500, "error": f'Failure to download input file from S3. {e}'}), 500

          # (7) Launch annotation job as a background process
          # Referred to 0:40' - 1:44', https://www.youtube.com/watch?v=VlfLqG_qjx0
          cmd = f'python run.py {PATH}{job_id}/{input_file_name} {job_id} {input_file_name} {user_id} {user_role}'
          try: 
            ann_process = subprocess.Popen(cmd, shell=True)   
          except Exception as e:
            return jsonify({ "code": 500, "error": f'Annotator job failed to launch. {e}'}), 500

          # (8) Update the “job_status” key in the annotations table to “RUNNING”
          # https://stackoverflow.com/questions/34447304/example-of-update-item-in-dynamodb-boto3
          # https://iamvickyav.medium.com/aws-dynamodb-with-python-boto3-part-4-update-attribute-delete-item-from-dynamodb-97caf4770ba
          resource = boto3.resource('dynamodb', region_name=REGION)
          try:
            # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.KeyConditions.html
            table = resource.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
            response = table.update_item(Key={"job_id": job_id},
                                        ConditionExpression= "job_status = :current_status",
                                        UpdateExpression="SET job_status= :job_st",
                                        ExpressionAttributeValues={':job_st': 'RUNNING', ':current_status': 'PENDING'})
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failure to update the database.{e}'}), 500

          # (9) Delete message from queue, if job was successfully submitted
          # Referred to delete_message: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#SQS.Client.delete_message
          wait_time = app.config["AWS_SQS_WAIT_TIME"]
          max_messages = app.config["AWS_SQS_MAX_MESSAGES"]
          try:
            message.delete()
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failure to delete message from the queue.{e}'}), 500

  return jsonify({"code": 200, "message": "Annotation job request processed."}), 200


app.run('0.0.0.0', debug=True)

### EOF