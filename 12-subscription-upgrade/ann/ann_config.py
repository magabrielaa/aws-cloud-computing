# ann_config.py
#
# Copyright (C) 2011-2022 Vas Vasiliadis
# University of Chicago
#
# Set GAS annotator configuration options
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

class Config(object):

  CSRF_ENABLED = True

  ANNOTATOR_BASE_DIR = "/home/ubuntu/gas/ann/"
  ANNOTATOR_JOBS_DIR = "/home/ubuntu/gas/ann/jobs/"

  AWS_REGION_NAME = "us-east-1"

  # AWS S3 upload parameters
  AWS_S3_INPUTS_BUCKET = "gas-inputs"
  AWS_S3_RESULTS_BUCKET = "gas-results"

  # AWS SNS topics
  AWS_SNS_RESULTS_ARN = "arn:aws:sns:us-east-1:127134666975:mariagabrielaa_a15_job_results"

  # AWS SQS queues
  AWS_SQS_WAIT_TIME = 20
  AWS_SQS_MAX_MESSAGES = 10
  AWS_SQS_QUEUE_NAME = "mariagabrielaa_a15_job_requests"
  AWS_SQS_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/127134666975/mariagabrielaa_a15_job_requests"

  # AWS DynamoDB
  AWS_DYNAMODB_ANNOTATIONS_TABLE = "mariagabrielaa_annotations"

### EOF