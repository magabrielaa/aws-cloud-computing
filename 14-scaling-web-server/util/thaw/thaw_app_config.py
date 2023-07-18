# thaw_app_config.py
#
# Copyright (C) 2011-2021 Vas Vasiliadis
# University of Chicago
#
# Set app configuration options for thaw utility
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):

  CSRF_ENABLED = True

  AWS_REGION_NAME = "us-east-1"

  # AWS DynamoDB table
  AWS_DYNAMODB_ANNOTATIONS_TABLE = "mariagabrielaa_annotations"
  AWS_DYNAMODB_INDEX = "user_id_index"

  # AWS SQS queues
  AWS_SQS_WAIT_TIME = 20
  AWS_SQS_MAX_MESSAGES = 10
  AWS_SQS_QUEUE_NAME = "mariagabrielaa_a17_premium"
  AWS_SQS_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/127134666975/mariagabrielaa_a17_premium"

  # AWS SNS topics
  AWS_SNS_RESTORE_TOPIC = "arn:aws:sns:us-east-1:127134666975:mariagabrielaa_a17_restore"

  # AWS Glacier
  AWS_GLACIER_VAULT_NAME = "ucmpcs"
  

### EOF