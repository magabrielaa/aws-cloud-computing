# archive_app_config.py
#
# Copyright (C) 2011-2022 Vas Vasiliadis
# University of Chicago
#
# Set app configuration options for archive utility
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

class Config(object):

  CSRF_ENABLED = True

  AWS_REGION_NAME = "us-east-1"

  # AWS SQS queues
  AWS_SQS_WAIT_TIME = 20
  AWS_SQS_MAX_MESSAGES = 10
  AWS_SQS_QUEUE_NAME = "mariagabrielaa_a14_archive"
  AWS_SQS_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/127134666975/mariagabrielaa_a14_archive"

  # AWS DynamoDB table
  AWS_DYNAMODB_ANNOTATIONS_TABLE = "mariagabrielaa_annotations"

  # AWS State Machine
  AWS_STATE_MACHINE_ARN = "arn:aws:states:us-east-1:127134666975:stateMachine:mariagabrielaa_a14"

  # AWS S3
  S3_RESULTS_BUCKET = "gas-results"

  # AWS GLACIER
  GLACIER_VAULT_NAME = "ucmpcs"

### EOF