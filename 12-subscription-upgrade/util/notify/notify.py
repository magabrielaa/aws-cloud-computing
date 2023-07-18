# notify.py
#
# Notify users of job completion
#
# Copyright (C) 2011-2021 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import boto3
import time
import os
import sys
import json
from botocore.exceptions import ClientError
from datetime import datetime, timezone, timedelta

# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration
from configparser import ConfigParser
config = ConfigParser(os.environ)
config.read('notify_config.ini')

'''Capstone - Exercise 3(d)
Reads result messages from SQS and sends notification emails.
'''
def handle_results_queue(sqs):

  # (1) Attempt to read a message from the queue with long polling
  # https://github.com/boto/boto3/issues/324
    print("Asking SQS for up to 10 messages.")
    wait_time = int(config["sqs"]["wait_time"])
    max_messages = int(config["sqs"]["max_messages"])
    try:
      messages = sqs.receive_messages(WaitTimeSeconds=wait_time,
                                      MaxNumberOfMessages=max_messages)
    except ClientError as e:
      print("Failure to retrieve messages from queue. ", e.response['Error']['Message'])
      return

    # Process message
    if len(messages) > 0:
        for message in messages:
            msg_body = json.loads(json.loads(message.body)["Message"])
            
            # Check if message contains all required elements
            lst = ["job_id", "user_id", "complete_time"]
            if not all(val in msg_body for val in lst):
              # Delete message
              try:
                message.delete()
              except ClientError as e:
                print("SNS message does not contain required fields, message deleted")
                return

            else:
              # Convert complete time entries from epoch time to instance time zone (CST)
              # https://stackoverflow.com/questions/32325209/python-how-to-convert-unixtimestamp-and-timezone-into-datetime-object
              complete_epoch = msg_body["complete_time"]
              cst = timezone(-timedelta(hours=6))
              complete_time = datetime.fromtimestamp(complete_epoch, cst).strftime('%Y-%m-%d %H:%M:%S')

              job_id = msg_body["job_id"]
              user_id = msg_body["user_id"]
              sender = config["ses"]["sender"]
              job_url = config["jobs"]["url"]+ job_id
              subject = f"Results available for job {job_id}"
              body = f"Your annotation job completed at {complete_time}. Click here to view "\
                    f"job details and results: {job_url}"
                    
              # Get recipient email address
              try:
                user_profile = helpers.get_user_profile(id=user_id)
              except Exception as e:
                print("Unable to get user profile", e)
                return
              recipient = user_profile[2]

              # Send notification email about completed job
              try:
                helpers.send_email_ses(recipients=recipient, sender=sender, subject=subject, body=body)
              except Exception as e:
                print("Failed to send email", e)
                return

              # Delete message
              try:
                message.delete()
              except ClientError as e:
                print("Failure to delete message from the queue", e.response['Error']['Message'])
                return


if __name__ == '__main__':
  
  # Get handles to resources; and create resources if they don't exist

  # Referred to "3. Get an existing queue by name"
  # https://aws.plainenglish.io/sqs-with-aws-sdk-for-python-boto3-on-ec2-85d343ba0a49
  sqs = boto3.resource('sqs', region_name=config["aws"]["region_name"])
  queue_name = config["sqs"]["queue_name"]
  while True:
    try:
      queue = sqs.get_queue_by_name(QueueName=queue_name)
    except ClientError as e:
      print("Failure to retrieve the queue. ", e.response['Error']['Message'])
    handle_results_queue(queue)


### EOF