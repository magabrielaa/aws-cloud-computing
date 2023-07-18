# thaw_app.py
#
# Thaws upgraded (premium) user data
#
# Copyright (C) 2011-2021 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import json
import os
import requests
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

from flask import Flask, request, jsonify

app = Flask(__name__)
environment = 'thaw_app_config.Config'
app.config.from_object(environment)
app.url_map.strict_slashes = False

@app.route('/', methods=['GET'])
def home():
  return (f"This is the Thaw utility: POST requests to /thaw.")

@app.route('/thaw', methods=['POST'])
def thaw_premium_user_data():

  REGION = app.config["AWS_REGION_NAME"]

  # (1) Check message type
  req = json.loads(request.data)
  msg_type = req["Type"]

  # (2) Confirm SNS premium topic subscription confirmation
  # https://gist.github.com/iMilnb/bf27da3f38272a76c801
  if msg_type == 'SubscriptionConfirmation' and 'SubscribeURL' in req:
    response = requests.get(req['SubscribeURL'])

  # (3) If the SNS message type is a notification, poll the premium queue
  elif msg_type == 'Notification':
    message = req["Message"]
    msg_body = json.loads(message)

    # Get queue by name
    # https://aws.plainenglish.io/sqs-with-aws-sdk-for-python-boto3-on-ec2-85d343ba0a49
    sqs = boto3.resource('sqs', region_name=REGION)
    try:
      queue = sqs.get_queue_by_name(QueueName=app.config["AWS_SQS_QUEUE_NAME"])
    except ClientError as e:
      return jsonify({ "code": 500, "error": "Failure to retrieve the queue"}), 500

    print("Asking SQS for up to 10 messages.")
    wait_time = app.config["AWS_SQS_WAIT_TIME"]
    max_messages = app.config["AWS_SQS_MAX_MESSAGES"]

    # (4) Attempt to read a message from the premium queue
    try:
      messages = queue.receive_messages(WaitTimeSeconds=wait_time,
                                        MaxNumberOfMessages=max_messages)
    except ClientError as e:
      return jsonify({ "code": 500, "error": "Failure to retrieve messages from premium queue."}), 500

    # (5) If there is at least one message, process it
    if len(messages) > 0:
      for message in messages:
        msg_body = json.loads(json.loads(message.body)["Message"])
        
        # If message doesn't contain user_id, message cannot be processed and is deleted
        if "user_id" not in msg_body:
          print("Message does not contain required user_id parameter")
          try:
            message.delete()
            print("Message deleted from archive queue")
          except ClientError as e:
            return jsonify({ "code": 500, "error": f'Failed to delete message from archive queue. {e}'}), 500
        # Otherwise, process the message
        else:
          user_id = msg_body["user_id"]

          # (6) Query the database to retrieve archive ID's associated with user ID who 
          # upgraded to premium
          dynamodb = boto3.resource("dynamodb", region_name=REGION)
          try:
            ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
            response = ann_table.query(IndexName=app.config["AWS_DYNAMODB_INDEX"],
                                      KeyConditionExpression= Key('user_id').eq(user_id))
          except ClientError as e:
            print("Failed to retrieve list of archive IDs. ", e.response['Error']['Message'])
            return jsonify({ "code": 500, "error": f'Failed to retrieve list of archive IDs. {e}'}), 500

          # (7) Get list of archive ID's 
          if "Items" in response: # Only loop through if items is not an empty list
            items = response['Items']
            archive_ids = []
            for i in items:
              job_item = {}
              # If retrieval_request id is in the database, the job is already being thawed
              if "retrieval_request_id" in i:
                  job_id = i["job_id"]
                  print()
                  print("--------START-------")
                  print (f'*** THAWING ALREADY IN PROCESS for job_id: {job_id}')
                  try:
                      message.delete()
                      print("Message deleted from the premium queue")
                      print("--------END---------")
                      print()
                  except ClientError as e:
                      print("Failed to delete message from premium queue. ", e.response['Error']['Message'])
                      return jsonify({ "code": 500, "error": f'Failed to delete message from premium queue. {e}'}), 500
              else: 
                if "results_file_archive_id" in i:
                  job_item['job_id']= i["job_id"]
                  job_item['archive_id']= i["results_file_archive_id"]
                  archive_ids.append(job_item)

          # (8) Iterate over list of dictionaries that contain archive IDs and job iID to 
          # request retrieval from Glacier
          for i in archive_ids:
            job_id = i["job_id"]
            archive_id = i["archive_id"]
            print()
            print("--------START-------")
            print("Job ID: ", job_id)

            # (9) Initiate retrieval job from Glacier. 
            # Referred to "initiate_job", https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.initiate_job

            # (9.1) First try to EXPEDITED retrieval
            try:
              print("Attempting expedited retrieval from Glacier ...")
              client = boto3.client('glacier', region_name=REGION)
              response = client.initiate_job(accountId='-',
                                            jobParameters={
                                                          'Description': job_id,
                                                          'SNSTopic': app.config["AWS_SNS_RESTORE_TOPIC"],
                                                          'Tier': 'Expedited',
                                                          'ArchiveId': archive_id,
                                                          'Type': 'archive-retrieval',},
                                            vaultName=app.config["AWS_GLACIER_VAULT_NAME"])
              request_id = response["jobId"]
              print("Expedited retrieval request successful")

            except ClientError as e:
              # Before trying Standard Retrieval, catch insufficient capacity error
              if e.response['Error']['Code'] == "InsufficientCapacityException":
                print("Expedited Retrieval Failed. ", e.response['Error']['Message'])

                # (9.2) If Expedited retrieval request fails, resubmit retrieval request using 
                # STANDARD retrieval
                try:
                  print("Attempting standard retrieval from Glacier ...")
                  client = boto3.client('glacier', region_name=REGION)
                  response = client.initiate_job(accountId='-',
                                                jobParameters={
                                                            'Description': job_id,
                                                            'SNSTopic': app.config["AWS_SNS_RESTORE_TOPIC"],
                                                            'Tier': 'Standard',
                                                            'ArchiveId': archive_id,
                                                            'Type': 'archive-retrieval',},
                                                vaultName=app.config["AWS_GLACIER_VAULT_NAME"])
                  request_id = response["jobId"]
                  print("Standard retrieval request successful")
                except ClientError as e:
                  print("Standard Retrieval Failed. ", e.response['Error']['Message'])
                  return jsonify({ "code": 500, "error": f'Standard Retrieval Failed. {e}'}), 500
              else:
                print("Expedited Retrieval failed for reasons other than insufficient capacity. \
                      Standard Retrieval not attempted. ", e.response['Error']['Message'])
                return jsonify({ "code": 500, "error": f'Expedited Retrieval Failed. {e}'}), 500


            # (10) Persist retrieval request id to the annotations database
            resource = boto3.resource('dynamodb', region_name=REGION)
            try:
              # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.KeyConditions.html
              table = resource.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
              response = table.update_item(Key={"job_id": job_id},
                                          UpdateExpression="SET retrieval_request_id= :req_id",
                                          ExpressionAttributeValues={':req_id': request_id})
              print("Glacier Request ID persisted to the database")
            except ClientError as e:
              print("Failure to persist Retrieval Request ID to the database. ", e.response['Error']['Message'])
              return jsonify({ "code": 500, "error": f'Failure to persist Retrieval Request ID to the database. {e}'}), 500

          # (11) Delete message from premium queue
          try:
            message.delete()
            print("Message deleted from the premium queue")
            print("--------END---------")
            print()
          except ClientError as e:
            print("Failed to delete message from premium queue. ", e.response['Error']['Message'])
            return jsonify({ "code": 500, "error": f'Failed to delete message from archive queue. {e}'}), 500

  return jsonify({ "code": 200, "message": "Thaw process completed."}), 200

  
# Run using dev server (remove if running via uWSGI)
app.run('0.0.0.0', port=5001, debug=True)
### EOF