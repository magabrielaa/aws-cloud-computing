# archive_app.py
#
# Archive free user data
#
# Copyright (C) 2011-2021 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import json
import os
import json
import requests
import time
from flask import Flask,jsonify, request
from datetime import datetime, timezone, timedelta
import boto3
from botocore.exceptions import ClientError
import sys

# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

app = Flask(__name__)
environment = 'archive_app_config.Config'
app.config.from_object(environment)

@app.route('/', methods=['GET'])
def home():
  return (f"This is the Archive utility: POST requests to /archive.")

@app.route('/archive', methods=['POST'])
def archive_free_user_data():

  REGION = app.config["AWS_REGION_NAME"]

  # (1) Check message type
  req = json.loads(request.data)
  msg_type = req["Type"]

  # (2) Confirm SNS archive topic subscription confirmation
  # https://gist.github.com/iMilnb/bf27da3f38272a76c801
  if msg_type == 'SubscriptionConfirmation' and 'SubscribeURL' in req:
    response = requests.get(req['SubscribeURL'])

  # (3) If the SNS message type is a notification, poll the archive queue
  elif msg_type == 'Notification':
    message = req["Message"]
    msg_body = json.loads(message)

    # Get queue by name
    # https://aws.plainenglish.io/sqs-with-aws-sdk-for-python-boto3-on-ec2-85d343ba0a49
    sqs = boto3.resource('sqs', region_name=REGION)
    try:
      queue = sqs.get_queue_by_name(QueueName=app.config["AWS_SQS_QUEUE_NAME"])
    except ClientError as e:
      return jsonify({ "code": 500, "error": f'Failure to retrieve the queue. {e}'}), 500

    print("Asking SQS for up to 10 messages.")
    wait_time = app.config["AWS_SQS_WAIT_TIME"]
    max_messages = app.config["AWS_SQS_MAX_MESSAGES"]

    # Attempt to read a message from the archive queue
    try:
      messages = queue.receive_messages(WaitTimeSeconds=wait_time,
                                        MaxNumberOfMessages=max_messages)
    except ClientError as e:
      return jsonify({ "code": 500, "error": 'Failure to retrieve messages from queue. {e}'}), 500

    # (4) If there is at least one message, process it
    if len(messages) > 0:
      for message in messages:
        msg_body = json.loads(json.loads(message.body)["Message"])
        job_id = msg_body["job_id"]
        print()
        print("----------START-----------")
        print("Job ID: ", job_id)

        # (5) Query the database to retrieve execution ARN 
        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        try:
          ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
          response = ann_table.get_item(Key={'job_id': job_id})
          print("Retrieved execution ARN from dynamo db")
        except ClientError as e:
          return jsonify({ "code": 500, "error": f'Failed to retrieve execution ARN from database. {e}'}), 500

        # Save variables
        if "Item" in response:
          job_item = response['Item']
          execution_arn = job_item["execution_arn"]
          user_id = job_item["user_id"]
        
        # (6) Check the user's current role:
        user_profile = helpers.get_user_profile(id=user_id)
        user_role = user_profile[4]
        print("The current user role is: ", user_role)

        # (7) If user role is premium, skip archive process
        if user_role == "premium_user":
          print("**** Results file NOT archived")

        # (8) If user role is free, proceed to archive
        else:

          # Set up variables
          results_bucket = app.config["S3_RESULTS_BUCKET"]
          key_results_file = job_item["s3_key_result_file"]

          # (8.1) Get results file from S3 bucket
          # https://stackoverflow.com/questions/70913017/how-to-read-content-of-a-file-from-a-folder-in-s3-bucket-using-python
          try:
            client = boto3.client('s3', region_name=REGION)
            response = client.get_object(Bucket=results_bucket,
                                        Key=key_results_file)
            results_bytes = response['Body'].read()  
            print("Results file retrieved from S3 bucket")
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failed to retrieve results file from S3 bucket. {e}'}), 500

          # (8.2) Upload results file to Glacier
          # http://jhshi.me/2017/03/06/backing-up-files-using-amazon-glacier/index.html#.Y_HlOS-B1Ms
          try:
            client = boto3.client('glacier', region_name=REGION)
            response = client.upload_archive(vaultName=app.config["GLACIER_VAULT_NAME"],
                                            body=results_bytes)
            archive_id = response['archiveId']
            print("Archive request completed")
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failure to upload annotation files to S3. {e}'}), 500
          
          # (8.3) Persist archive ID to the annotations database
          resource = boto3.resource('dynamodb', region_name=REGION)
          try:
            # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.KeyConditions.html
            table = resource.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
            response = table.update_item(Key={"job_id": job_id},
                                        UpdateExpression="SET results_file_archive_id= :archive_id",
                                        ExpressionAttributeValues={':archive_id': archive_id})
            print("Archive ID persisted to the Dynamo database")
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failure to persist Archive ID to the database. {e}'}), 500
          
          # (8.4) Delete results file from S3 bucket
          # https://stackoverflow.com/questions/3140779/how-to-delete-files-from-amazon-s3-bucket
          try:
            s3 = boto3.resource('s3', region_name=REGION)
            s3.Object(results_bucket, key_results_file ).delete()  
            print("Deleted results file from S3 bucket")
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failed to delete results file from s3 bucket. {e}'}), 500
         
        # (9) Delete execution ARN from database
        # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.UpdateExpressions.html#Expressions.UpdateExpressions.REMOVE
        resource = boto3.resource('dynamodb', region_name=REGION)
        try:
          ann_table = resource.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
          response = ann_table.update_item(Key={"job_id": job_id},
                                          UpdateExpression="REMOVE execution_arn")
          print("Removed execution ARN from Dynamo database")
        except ClientError as e:
          return jsonify({ "code": 500, "error": f'Failure to remove execution ARN from the database. {e}'}), 500

        # (10) Delete message from archive queue
        try:
          message.delete()
          print("Message deleted from archive queue")
        except ClientError as e:
          return jsonify({ "code": 500, "error": f'Failed to delete message from archive queue. {e}'}), 500

        print("----------END-------------")
        print()

    return jsonify({ "code": 200, "message": "Process completed."}), 200
  

# Run using dev server (remove if running via uWSGI)
app.run('0.0.0.0', debug=True)
### EOF