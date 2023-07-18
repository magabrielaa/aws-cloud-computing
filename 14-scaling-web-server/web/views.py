# views.py
#
# Copyright (C) 2011-2022 Vas Vasiliadis
# University of Chicago
#
# Application logic for the GAS
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import uuid
import time
import json
from datetime import datetime, timezone, timedelta

import boto3
from botocore.client import Config
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from flask import (abort, flash, redirect, render_template, 
  request, session, url_for)

from app import app, db
from decorators import authenticated, is_premium

from auth import get_profile
import stripe
from stripe.error import InvalidRequestError

"""Start annotation request
Create the required AWS S3 policy document and render a form for
uploading an annotation input file using the policy document

Note: You are welcome to use this code instead of your own
but you can replace the code below with your own if you prefer.
"""
@app.route('/annotate', methods=['GET'])
@authenticated
def annotate():

  # (1) Generate a presigned URL for the S3 object
  # https://stackoverflow.com/questions/33577503/how-to-configure-authorization-mechanism-inline-with-boto3
  s3 = boto3.client('s3',
                    region_name=app.config['AWS_REGION_NAME'],
                    config=Config(signature_version='s3v4'))
  # Referred to Sample Policy and Form
  # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
  # https://www.scaleway.com/en/docs/storage/object/api-cli/post-object/
  bucket_name = app.config['AWS_S3_INPUTS_BUCKET']
  user_id = session['primary_identity']

  # (2) Generate unique ID to be used as S3 key (name)
  object_id = str(uuid.uuid4())
  key_name= app.config['AWS_S3_KEY_PREFIX'] + user_id + '/' + \
    object_id + '~' + '${filename}'

  # (3) Create the redirect URL
  redirect_url = request.url + "/job"

  # (4) Define policy conditions
  encryption = app.config['AWS_S3_ENCRYPTION']
  acl = app.config['AWS_S3_ACL']
  fields = {
    "success_action_redirect": redirect_url,
    "x-amz-server-side-encryption": encryption,
    "acl": acl
  }
  conditions = [
    ["starts-with", "$success_action_redirect", redirect_url],
    {"x-amz-server-side-encryption": encryption},
    {"acl": acl}
  ]

  # (5) Generate signed POST request
  # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
  try:
    presigned_post = s3.generate_presigned_post(
      Bucket=bucket_name, 
      Key=key_name,
      Fields=fields,
      Conditions=conditions,
      ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION'])
  except ClientError as e:
    app.logger.error(f'Unable to generate presigned URL for upload: {e}')
    return abort(500)

  # (6) Render the upload form template which will parse/submit the presigned POST
  return render_template('annotate.html', s3_post=presigned_post, role=session['role'])


"""Fires off an annotation job
Accepts the S3 redirect GET request, parses it to extract 
required info, saves a job item to the database, and then
publishes a notification for the annotator service.

Note: Update/replace the code below with your own from previous
homework assignments
"""
@app.route('/annotate/job', methods=['GET'])
@authenticated
def create_annotation_job_request():

  # (1) Parse redirect URL query parameters for S3 object info
  bucket_name = request.args.get('bucket')
  s3_key = request.args.get('key')

  # (2) Extract the job ID and input file name from the S3 key
  job_id = s3_key.split("/")[2][:36]
  input_file_name = s3_key.split("/")[2][37:] # Includes .vcf extension
 
  # (3) Create a job item and persist it to the annotations database
  job_item = {"job_id": job_id, 
            "user_id": session['primary_identity'], 
            "input_file_name": input_file_name,
            "s3_inputs_bucket": bucket_name,
            "s3_key_input_file": s3_key,
            "submit_time": int(time.time()),
            "job_status": "PENDING"}  
  # Referred to third answer:
  # https://stackoverflow.com/questions/33535613/how-to-put-an-item-in-aws-dynamodb-using-aws-lambda-with-python
  client = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
  table = client.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
  try:
    table.put_item(Item = job_item)
  except ClientError as e:
    app.logger.error(f'Failure to add job item to database: {e}')
    return abort(500)

  # (4) Publish a notification message to SNS topic
  # Referred to "Publish to a topic", https://docs.aws.amazon.com/code-library/latest/ug/python_3_sns_code_examples.html
  # https://stackoverflow.com/questions/40667452/boto3-publish-message-sns

  # Get user's role
  user_id = session['primary_identity']
  try:
    profile = get_profile(identity_id=user_id)
  except Exception as e:
    app.logger.error(f'Unable to get user profile: {e}')
    return abort(500)
  
  job_item["user_role"] = profile.role
  
  try:
    sns = boto3.client("sns", region_name=app.config['AWS_REGION_NAME'])
    response = sns.publish(TopicArn=app.config['AWS_SNS_JOB_REQUEST_TOPIC'],
                          Message = json.dumps({"default":json.dumps(job_item)}),
                          MessageStructure='json')
  except ClientError as e:
    app.logger.error(f'Failure to pubish message to SNS topic: {e}')
    return abort(500)

  return render_template('annotate_confirm.html', job_id=job_id)


"""List all annotations for the user
"""
@app.route('/annotations', methods=['GET'])
@authenticated
def annotations_list():

  user_id = session['primary_identity']

  # (1) Query table to get list of annotations to display
  dynamodb = boto3.resource("dynamodb", region_name=app.config['AWS_REGION_NAME'])
  try:
    ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
    response = ann_table.query(IndexName= 'user_id_index',
                              KeyConditionExpression= Key('user_id').eq(user_id))
  except ClientError as e:
    app.logger.error(f'Unable to query list of annotations: {e}')
    return abort(500)

  # List of annotations
  items = response['Items']

  # (2) Convert submit time entries from epoch time to instance time zone (CST)
  # https://stackoverflow.com/questions/32325209/python-how-to-convert-unixtimestamp-and-timezone-into-datetime-object
  if items: # Only do for loop if items is not an empty list
    for i in items:
      epoch_time = i["submit_time"]
      cst = timezone(-timedelta(hours=6))
      converted_time = datetime.fromtimestamp(epoch_time, cst).strftime('%Y-%m-%d %H:%M:%S')
      i["submit_time"] = converted_time

  return render_template('annotations.html', annotations=items)


"""Display details of a specific annotation job
"""
@app.route('/annotations/<id>', methods=['GET'])
@authenticated
def annotation_details(id):

  REGION = app.config['AWS_REGION_NAME']

  # (1) Get details for a given job
  dynamodb = boto3.resource("dynamodb", region_name=REGION)
  try:
    ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
    response = ann_table.get_item(Key={'job_id': id})
  except ClientError as e:
    app.logger.error(f'Unable to get job details: {e}')
    return abort(500)

  # (2) Retrieve variables
  user_id = session['primary_identity']
  input_bucket = app.config['AWS_S3_INPUTS_BUCKET']
  job_item = response['Item']
  if job_item:
    input_key = job_item["s3_key_input_file"]
  else:
    app.logger.error(f'Failed to retrieve job item: {e}')
    return abort(404)

  # (3) Return 403 error if job id does not belong to authenticated user
  if job_item["user_id"] != user_id:
    return abort(403)
  
  # (4) Convert time entries from epoch time to instance time zone (CST)
  # https://stackoverflow.com/questions/32325209/python-how-to-convert-unixtimestamp-and-timezone-into-datetime-object
  cst = timezone(-timedelta(hours=6))
  submit_epoch = job_item["submit_time"]
  converted_submit = datetime.fromtimestamp(submit_epoch, cst).strftime('%Y-%m-%d %H:%M:%S')
  job_item["submit_time"] = converted_submit
  
  # (5) Change completed time format only if job status is "COMPLETED"
  if "complete_time" in job_item: 
    complete_epoch = job_item["complete_time"]
    converted_complete = datetime.fromtimestamp(complete_epoch, cst).strftime('%Y-%m-%d %H:%M:%S')
    job_item["complete_time"] = converted_complete 

  # (6) Generate pre-signed download URL for input file
  # https://allwin-raju-12.medium.com/boto3-and-python-upload-download-generate-pre-signed-urls-and-delete-files-from-the-bucket-87b959f7bbaf
  # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
  try:
    s3_client = boto3.client('s3', region_name=REGION)  
    input_url = s3_client.generate_presigned_url(ClientMethod='get_object',
                                          ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION'],
                                          Params={'Bucket': input_bucket,
                                                  'Key': input_key,
                                                  'ResponseContentDisposition': 'attachment'})
  except ClientError as e:
    app.logger.error(f'Unable to generate presigned download URL for the input file: {e}')
    return abort(500)

  # (7) Get user role and create upgrade variable to pass to annotation.html template
  try:
    profile = get_profile(identity_id=user_id)
  except Exception as e:
    app.logger.error(f'Unable to get user profile {e}')
    return abort(500)

  user_role = profile.role

  # If state machine ARN is not in DB and user is free, then prompt to upgrade
  if user_role == "free_user" and "execution_arn" not in job_item:
    show_upgrade = True
  else:
    show_upgrade = False


  # (8) Check if file is being thawed by finding if "retrieval_request_id" attribute is in Dynamo table
  if "retrieval_request_id" in job_item:
    is_thawing = True
  else:
    is_thawing = False
  
  # (9) Generate pre-signed download URL for results file (once job is "COMPLETED")
  if job_item["job_status"] == "COMPLETED":
    results_bucket = app.config['AWS_S3_RESULTS_BUCKET']
    results_key = job_item["s3_key_result_file"]
    try:
      s3_client = boto3.client('s3', region_name=app.config['AWS_REGION_NAME'])  
      results_url = s3_client.generate_presigned_url(ClientMethod='get_object',
                                                    ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION'],
                                                    Params={'Bucket': results_bucket,
                                                            'Key': results_key,
                                                            'ResponseContentDisposition': 'attachment'})
      return render_template('annotation.html', job=job_item, input_url=input_url, results_url=results_url, upgrade=show_upgrade, is_thawing=is_thawing)
    except ClientError as e:
      app.logger.error(f'Unable to generate presigned download URL for results file: {e}')
      return abort(500)
  # If job status is not complete, render html without results file url
  else:
    return render_template('annotation.html', job=job_item, input_url=input_url, is_thawing=is_thawing)


"""Display the log file contents for an annotation job
"""
@app.route('/annotations/<id>/log', methods=['GET'])
@authenticated
def annotation_log(id):

  # (1) Query table to get S3 key name
  dynamodb = boto3.resource("dynamodb", region_name=app.config['AWS_REGION_NAME'])
  try:
    ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
    response = ann_table.get_item(Key={'job_id': id})
  except ClientError as e:
    app.logger.error(f'Unable to get job details: {e}')
    return abort(500)

  # (2) Retrieve variables if job item exists
  job_item = response['Item']
  if job_item:
    key = job_item["s3_key_log_file"]
  else:
    app.logger.error(f'Unable to retrieve values: {e}')
    return abort(404)

  # (3) Save relevant variables
  bucket = app.config['AWS_S3_RESULTS_BUCKET']
  user_id = session['primary_identity']

  # (4) Return 403 error if job id does not belong to authenticated user
  if job_item["user_id"] != user_id:
    return abort(403)

  # (5) Read S3 log file 
  # https://stackoverflow.com/questions/31976273/open-s3-object-as-a-string-with-boto3
  s3 = boto3.resource('s3', region_name=app.config['AWS_REGION_NAME'])
  try:
    obj = s3.Object(bucket, key)
    log_text = obj.get()['Body'].read().decode('utf-8')
  except ClientError as e:
      app.logger.error(f'Unable to read log file from S3 bucket: {e}')
      return abort(500)

  return render_template('view_log.html', S3_object=log_text)
  

"""Subscription management handler
"""
import stripe
from auth import update_profile

@app.route('/subscribe', methods=['GET', 'POST'])
@authenticated
def subscribe():
  if (request.method == 'GET'):
    # Display form to get subscriber credit card info
    return render_template('subscribe.html')
    
  elif (request.method == 'POST'):
    # (1)Process the subscription request
    # https://stackoverflow.com/questions/49987235/how-to-access-stripe-token-from-form-post-submission-in-python
    stripe_token = request.form['stripe_token']

    # (2) Create a customer on Stripe
    # https://www.altcademy.com/codedb/examples/create-a-stripe-customer-from-an-email-address-in-python
    # Referred to "Create a customer", https://stripe.com/docs/api/customers/create?lang=python

    # Retrieve user variable from the session
    user_id = session['primary_identity']

    try:
      profile = get_profile(identity_id=user_id)
    except Exception as e:
      app.logger.error(f'Unable to get user profile. {e}')
      return abort(500)

    name = profile.name
    email = profile.email
    stripe.api_key = app.config["STRIPE_SECRET_KEY"]

    try:
      customer = stripe.Customer.create(name=name,
                                        email=email,
                                        card=stripe_token)
      customer_id = customer["id"]
    except InvalidRequestError as e:
      app.logger.error(f'Failed to create customer on Stripe: {e}')
      return abort(500)

    # (3) Subscribe customer to pricing plan
    # Referred to "Create a subscription", https://stripe.com/docs/api/subscriptions/create?lang=python
    price_id = app.config["STRIPE_PRICE_ID"]
    try:
      subscription = stripe.Subscription.create(customer=customer_id,
                                                items=[{"price": price_id}])
    except InvalidRequestError as e:
      app.logger.error(f'Failed to subscribe customer to pricing plan: {e}')
      return abort(500)

    # (4) Update user role in accounts database
    user_id = session['primary_identity']
    try:
      update_profile(identity_id=user_id, role="premium_user")
    except Exception as e:
      app.logger.error(f'Failed to update user profile. {e}')
      return abort(500)

    # (5) Update role in the session
    session["role"] = "premium_user"

    # (6) Request restoration of the user's data from Glacier:
    # Post message to SNS premium topic
    # https://docs.aws.amazon.com/code-library/latest/ug/python_3_sns_code_examples.html
    try:
      sns = boto3.client("sns", region_name=app.config['AWS_REGION_NAME'])
      response = sns.publish(TopicArn=app.config['AWS_SNS_PREMIUM_TOPIC'],
                            Message = json.dumps({"default":json.dumps({"user_id": user_id})}),
                            MessageStructure='json')
    except ClientError as e:
      app.logger.error(f'Failure to pubish message to SNS topic: {e}')
      return abort(500)

    # Display confirmation page
    return render_template('subscribe_confirm.html', stripe_id=customer_id)


"""Set premium_user role
"""
@app.route('/make-me-premium', methods=['GET'])
@authenticated
def make_me_premium():
  # Hacky way to set the user's role to a premium user; simplifies testing
  update_profile(
    identity_id=session['primary_identity'],
    role="premium_user"
  )
  return redirect(url_for('profile'))


"""Reset subscription
"""
@app.route('/unsubscribe', methods=['GET'])
@authenticated
def unsubscribe():
  # Hacky way to reset the user's role to a free user; simplifies testing
  update_profile(
    identity_id=session['primary_identity'],
    role="free_user"
  )
  return redirect(url_for('profile'))


"""DO NOT CHANGE CODE BELOW THIS LINE
*******************************************************************************
"""

"""Home page
"""
@app.route('/', methods=['GET'])
def home():
  return render_template('home.html')

"""Login page; send user to Globus Auth
"""
@app.route('/login', methods=['GET'])
def login():
  app.logger.info(f"Login attempted from IP {request.remote_addr}")
  # If user requested a specific page, save it session for redirect after auth
  if (request.args.get('next')):
    session['next'] = request.args.get('next')
  return redirect(url_for('authcallback'))

"""404 error handler
"""
@app.errorhandler(404)
def page_not_found(e):
  return render_template('error.html', 
    title='Page not found', alert_level='warning',
    message="The page you tried to reach does not exist. \
      Please check the URL and try again."
    ), 404

"""403 error handler
"""
@app.errorhandler(403)
def forbidden(e):
  return render_template('error.html',
    title='Not authorized', alert_level='danger',
    message="You are not authorized to access this page. \
      If you think you deserve to be granted access, please contact the \
      supreme leader of the mutating genome revolutionary party."
    ), 403

"""405 error handler
"""
@app.errorhandler(405)
def not_allowed(e):
  return render_template('error.html',
    title='Not allowed', alert_level='warning',
    message="You attempted an operation that's not allowed; \
      get your act together, hacker!"
    ), 405

"""500 error handler
"""
@app.errorhandler(500)
def internal_error(error):
  return render_template('error.html',
    title='Server error', alert_level='danger',
    message="The server encountered an error and could \
      not process your request."
    ), 500

### EOF