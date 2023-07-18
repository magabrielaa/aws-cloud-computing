from flask import Flask, jsonify, render_template, request
import requests
import uuid
import boto3
from botocore.exceptions import ClientError
from botocore.client import Config
import time
import json


app = Flask(__name__)
# Keep order of sorted dictionaries passed to jsonify
app.config['JSON_SORT_KEYS'] = False


@app.route('/annotate', methods=['GET'])
def annotate():
    '''
    This endpoint is for the user to upload an input file to the render form,
    which is then uploaded to the S3 gas-inputs bucket using a signed POST request.
    '''
    # (1) Generate a presigned URL for the S3 object
    # https://stackoverflow.com/questions/33577503/how-to-configure-authorization-mechanism-inline-with-boto3
    s3_client = boto3.client('s3', region_name='us-east-1', config= Config(signature_version='s3v4')) 
    object_id = str(uuid.uuid4()) # Generate unique object id
    # Referred to Sample Policy and Form
    # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
    # https://www.scaleway.com/en/docs/storage/object/api-cli/post-object/
    bucket_name="gas-inputs"
    user = "userX"
    object_name=f'mariagabrielaa/{user}/{object_id}~' + '${filename}'
    redirect_url = request.url + "/job"
    fields = {'acl': 'private',
            "success_action_redirect": redirect_url}
    conditions = [{"acl": "private"},
                {"success_action_redirect": redirect_url}]
    expiration = 60 # Expire after 1 minute

    # (2) Generate signed POST request
    # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
    try:
        response = s3_client.generate_presigned_post(Bucket=bucket_name,
                                                    Key=object_name,
                                                    Fields=fields,
                                                    Conditions=conditions,
                                                    ExpiresIn=expiration)
    except ClientError as e:
        response_code = 500
        body = {"code": response_code,
                "status": "error",
                "message": "Failure to generate signed POST request. " + f'{e}'}
        return jsonify(body), response_code

    # (3) Render the upload form template
    return render_template('annotate.html', policy=response, bucket_name=bucket_name)


@app.route("/annotate/job", methods=['GET'])
def annotate_job():
    '''
    Retrieves job information from S3 redirect URL and persists job to DynamoDB 
    annotations table. Then, publishes notification message to SNS topic for job requests.

    '''
    # (1) Get bucket name, key, and job ID from redirect URL
    # https://stackoverflow.com/questions/15974730/how-do-i-get-the-different-parts-of-a-flask-requests-url
    bucket_name = request.args["bucket"]
    key = request.args["key"] 
    # Split key to retrieve job_id and input_file
    object_name = key.split("mariagabrielaa/")[1] # Remove CNet ID
    job_id = object_name.split("/")[1][:36] # Get rid of "~input_file"
    input_file_name= object_name.split("~", 1)[1] # Includes .vcf extension
    # (2) Create a job item and persist it to the annotations database
    job_item = { "job_id": job_id, 
           "user_id": "userX", 
           "input_file_name": input_file_name,
           "s3_inputs_bucket": "gas-inputs",
           "s3_key_input_file": key,
           "submit_time": int(time.time()),
           "job_status": "PENDING"}    
    # Referred to third answer:
    # https://stackoverflow.com/questions/33535613/how-to-put-an-item-in-aws-dynamodb-using-aws-lambda-with-python
    client = boto3.resource('dynamodb', region_name= 'us-east-1')
    table = client.Table("mariagabrielaa_annotations")
    try:
        table.put_item(Item = job_item)
    except ClientError as e:
        response_code = 500
        body = {"code": response_code,
                "status": "error",
                "message": "Failure to add job item to database. " + f'{e}'}
        return jsonify(body), response_code
   
    # (3) Publish a notification message to SNS topic
    # Referred to "Publish to a topic", https://docs.aws.amazon.com/code-library/latest/ug/python_3_sns_code_examples.html
    # https://stackoverflow.com/questions/40667452/boto3-publish-message-sns
    # https://stackoverflow.com/questions/35071549/json-encoding-error-publishing-sns-message-with-boto-3
    try:
        sns = boto3.client("sns", region_name="us-east-1")
        response = sns.publish(TopicArn='arn:aws:sns:us-east-1:127134666975:mariagabrielaa_job_requests',
                                Message = json.dumps({"default":json.dumps(job_item)}),
                                MessageStructure='json')
    except ClientError as e:
        body = {"code": 500,
                "status": "error",
                "message": "Failure to pubish message to SNS topic. " + f'{e}'}
        return jsonify(body), 500
    
  
    # (4) Return response to the user with job id and file name
    body = {"job_id": job_id, 
           "input_file": input_file_name}
    return jsonify({"code":201, "data": body}), 201


# Run the app server
app.run(host='0.0.0.0', debug=True)