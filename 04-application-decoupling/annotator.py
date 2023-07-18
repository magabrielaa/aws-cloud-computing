from flask import Flask, jsonify, request
import uuid
import subprocess
import os.path
from os import path
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)
# Keep order of sorted dictionaries passed to jsonify
app.config['JSON_SORT_KEYS'] = False


@app.route('/annotations', methods=['GET'])
def annotations():
    '''
    This endpoint is reached by redirection when a user uploads a file through a form. The 
    endpoint downloads the file from S3, launches the subprocess through a uniquely identifiable
    file system, and returns the job id and file name to the user.
    '''
    # (1) Extract bucket name and object key from S3 redirect URL
    # https://stackoverflow.com/questions/15974730/how-do-i-get-the-different-parts-of-a-flask-requests-url
    bucket_name = request.args["bucket"]
    obj_name = request.args["key"] 
    # Split object name to retrieve input_file name and job_id
    user_job_id = obj_name.split("mariagabrielaa/")[1]
    job_id = user_job_id.split("/")[1][:36] # Get rid of "~input_file"
    input_file = obj_name.split("~", 1)[1] # Includes .vcf extension
    # Create a parent directory to store directories that will contain job_id's
    if not os.path.exists(f"/home/ubuntu/anntools/data/job_ids"):
        os.mkdir(f"/home/ubuntu/anntools/data/job_ids")
    # Create a directory to store the job_id
    # https://www.geeksforgeeks.org/create-a-directory-in-python/#
    os.mkdir(f"/home/ubuntu/anntools/data/job_ids/{job_id}")

    # (2) Download the input file from S3 and save it to the AnnTools instance
    # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-example-download-file.html
    input_path = f"/home/ubuntu/anntools/data/job_ids/{job_id}/{input_file}"
    # Error handling when downloading file from S3
    try: 
        s3 = boto3.client('s3', region_name= 'us-east-1')
        s3.download_file(bucket_name, obj_name, input_path)
    except ClientError as e:
        response_code = 500
        body = {
            "code": response_code,
            "status": "error",
            "message": e['Error']['Message']
            }
        return jsonify(body), response_code

    # (3) Spawn a subprocess to run the annotator using the provided input file    
    # Referred to 0:40' - 1:44', https://www.youtube.com/watch?v=VlfLqG_qjx0
    cmd = f'python a7_run.py /home/ubuntu/anntools/data/job_ids/{job_id}/{input_file}'
    annotator = subprocess.Popen(cmd, shell=True)   
    # Error Handling when annotator job fails to launch: if the return code is different 
    # from 0 or None, it means there was an error
    # Referred to 1:28'- 1:48, https://www.youtube.com/watch?v=VlfLqG_qjx0
    if annotator.returncode is not None and annotator.returncode !=0:
        response_code = 500
        body = {
            "code": response_code,
            "status": "error",
            "message": "Annotator job failed to launch"
            }
        return jsonify(body), response_code
    #(4) Return job id to the user as a JSON formatted response
    response_code = 201
    body = {
        "code": response_code,
        "data":{
            "input_file": input_file,
            "job_id": job_id,
            }
        }
    return jsonify(body), response_code


# Run the app server
app.run(host='0.0.0.0', debug=True)