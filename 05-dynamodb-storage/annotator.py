from flask import Flask, jsonify, request
import uuid
import subprocess
import os.path
from os import path
import boto3
from botocore.exceptions import ClientError
import time

app = Flask(__name__)
# Keep order of sorted dictionaries passed to jsonify
app.config['JSON_SORT_KEYS'] = False


@app.route('/annotations', methods=['POST'])
def request_annotation():
    '''
    Accepts POST request, extracts parameters from the body, and runs the 
    annotator. Updates job_status in the annotations table to "RUNNING", conditional 
    on the current status being "PENDING".
    '''
    # (1) Extract job parameters from request body
    req = request.json
    job_id = req["job_id"]
    user_id = req['user_id']
    input_file_name = req["input_file_name"]
    s3_inputs_bucket = req["s3_inputs_bucket"]
    s3_key_input_file = req["s3_key_input_file"]
    submit_time = req["submit_time"]
    job_status = req["job_status"]

    # Create a parent directory to store directories that will contain job_id's
    if not os.path.exists(f"/home/ubuntu/anntools/data/job_ids"):
        os.mkdir(f"/home/ubuntu/anntools/data/job_ids")
    # Create a directory to store the job_id locally and run the subprocess
    # https://www.geeksforgeeks.org/create-a-directory-in-python/#
    os.mkdir(f"/home/ubuntu/anntools/data/job_ids/{job_id}")
    
    # (2) Get the input file S3 object and copy it to a local file
    input_file_path = f"/home/ubuntu/anntools/data/job_ids/{job_id}/{input_file_name}"
    try: 
        # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-example-download-file.html
        s3 = boto3.client('s3', region_name= 'us-east-1')
        s3.download_file(s3_inputs_bucket, s3_key_input_file, input_file_path)
    except ClientError as e:
        body = {
            "code": 500,
            "status": "error",
            "message": "Failure to download input file from S3. " + f'{e}'
            }
        return jsonify(body), 500
  
    # (3) Launch annotation job as a background process  
    # Referred to 0:40' - 1:44', https://www.youtube.com/watch?v=VlfLqG_qjx0
    cmd = f'python a8_run.py /home/ubuntu/anntools/data/job_ids/{job_id}/{input_file_name} {job_id} {input_file_name}'
    ann_process = subprocess.Popen(cmd, shell=True)   
    # Error Handling when annotator job fails to launch: if the return code is different 
    # from 0 or None, there was an error
    # Referred to 1:28'- 1:48, https://www.youtube.com/watch?v=VlfLqG_qjx0
    if ann_process.returncode is not None and ann_process.returncode !=0:
        body = {
            "code": 500,
            "status": "error",
            "message": "Annotator job failed to launch"
            }
        return jsonify(body), 500

    # Update the “job_status” key in the annotations table to “RUNNING”
    # https://stackoverflow.com/questions/34447304/example-of-update-item-in-dynamodb-boto3
    # https://iamvickyav.medium.com/aws-dynamodb-with-python-boto3-part-4-update-attribute-delete-item-from-dynamodb-97caf4770ba
    client = boto3.resource('dynamodb', region_name= 'us-east-1')
    try: 
        table = client.Table("mariagabrielaa_annotations")
        response = table.update_item(
            Key={"job_id": job_id},
            # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LegacyConditionalParameters.KeyConditions.html
            ConditionExpression= "job_status = :current_status",
            UpdateExpression="SET job_status= :job_st",
            ExpressionAttributeValues={':job_st': 'RUNNING', ':current_status': 'PENDING'},
            )
    except ClientError as e:
        body = {
            "code": 500,
            "status": "error",
            "message": "Failure to update the database. " + f'{e}',
            }
        return jsonify(body), 500

    # (4) Return response to notify user of successful submission
    data = { "job_id": job_id, 
           "input_file": input_file_name,
           }
    return jsonify({"code":201, "data": data}), 201


# Run the app server
app.run(host='0.0.0.0', debug=True)