from flask import Flask, jsonify, request
import uuid
import subprocess
import os.path
from os import path
import shutil

app = Flask(__name__)

# Keep order of sorted dictionaries passed to jsonify
#https://stackoverflow.com/questions/54446080/how-to-keep-order-of-sorted-dictionary-passed-to-jsonify-function
app.config['JSON_SORT_KEYS'] = False

@app.route('/', methods=['GET'])
def home():
    return "Hello, welcome to the Annotator API!"


@app.route('/annotations', methods=['POST'])
def annotations():
    '''
    This endpoint allows users to submit an annotation job.
    '''
    # Referred to "if you receive POST data in a request you must read it before 
    # returning a response"
    # https://stackoverflow.com/questions/14053670/no-response-with-post-request-and-content-type-application-json-in-flask
    if request.method == 'POST':
        request.form
    # https://stackoverflow.com/questions/10434599/get-the-data-received-in-a-flask-request
    # Referred to decode() function to convert bytes to JSON
    # https://stackoverflow.com/questions/52897200/getting-flask-request-data
    postbody = request.data.decode('UTF-8')
    # Error Handling when no input file provided in POST request
    # Referred to Client Error Responses
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Status#client_error_responses
    if postbody == "":
        response_code = 400
        body = {
        "code": response_code,
        "status": "error",
        "message": "Bad Request. No input_file provided"
        }
        return jsonify(body), response_code
    # (1) Extract name of input file from body of the request
    # https://stackoverflow.com/questions/52897200/getting-flask-request-data
    input_file = request.json['input_file']
    input_name = input_file[:-4] # Get rid of .vcf extension
    # Error Handling when input file not found in AnnTools directory
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Status#client_error_responses
    if not path.exists(f'/home/ubuntu/anntools/data/{input_file}'):
        response_code = 404
        body = {
        "code": response_code,
        "status": "error",
        "message": "Input file not found"
        }
        return jsonify(body), response_code
    # Success case when input file is provided and found in directory
    else:
        # (2) Generate unique ID for the annotation job
        # https://stackoverflow.com/questions/534839/how-to-create-a-guid-uuid-in-python
        job_id = str(uuid.uuid4())
        # Create a parent directory to store directories that will contain job_id's
        if not os.path.exists(f"/home/ubuntu/anntools/data/job_ids"):
            os.mkdir(f"/home/ubuntu/anntools/data/job_ids")
        # Create a directory to store the completed job_id, associated with the input_file
        # https://www.geeksforgeeks.org/create-a-directory-in-python/#
        os.mkdir(f"/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}")
        # Copy input_file to job_id directory
        # https://builtin.com/data-science/copy-a-file-with-python
        shutil.copy2(f"/home/ubuntu/anntools/data/{input_file}", f"/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/")
        # (3) Spawn a subprocess to run the annotator using the provided input file    
        # Referred to 0:40' - 1:44', https://www.youtube.com/watch?v=VlfLqG_qjx0
        cmd = f'python run.py /home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/{input_file}'
        annotator = subprocess.Popen(cmd, shell=True)   
        # Error Handling when annotator job fails to launch: if the return code is different from 0 or None, it means
        # there was an error
        # Referred to 1:28'- 1:48, https://www.youtube.com/watch?v=VlfLqG_qjx0
        if annotator.returncode is not None and annotator.returncode !=0:
            response_code = 500
            body = {
            "code": response_code,
            "status": "error",
            "message": "Annotator job failed to launch"
            }
            return jsonify(body), response_code
        # Check if input_file.annot.vcf exists, which indicates the annotation job is completed. 
        # If so, create a directory called "complete"
        if path.exists(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/{input_name}.annot.vcf'):
            os.mkdir(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/complete')
        # Otherwise the job is still running so create directory called "running"
        else:
            os.mkdir(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/running')
        #(4) Return job id to the user as a JSON formatted response
        response_code = 201
        body = {
            "code": response_code,
            "data":{
                "input_file": input_file,
                "job_id": job_id,
            }
        }
        # Use jsonify to return output/body as JSON object
        # https://stackoverflow.com/questions/13081532/return-json-response-from-flask-view
        return jsonify(body), response_code


@app.route('/annotations/<job_id>', methods=['GET'])
def get_job_status(job_id):
    '''
    This endpoint allows users to get the status of an annotation job status and, 
    for completed jobs, the contents of the log file.
    '''
    # (1) Check if parent directory to store job_id's exists, if not, it means no jobs
    # have been created - ie. job not found
    if not os.path.exists(f"/home/ubuntu/anntools/data/job_ids") or len(job_id) != 36:
        # Error Handling: job not found when GETting job status
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Status#client_error_responses
        response_code = 404
        body = {
        "code": response_code,
        "status": "error",
        "message": "Annotation job not found"
        }
        return jsonify(body), response_code
    # (2) Get a list of all subdirectories in job_ids directory and find directory that 
    # matches job_id
    # https://stackoverflow.com/questions/973473/getting-a-list-of-all-subdirectories-in-the-current-directory
    dir_lst = [i[0] for i in os.walk("/home/ubuntu/anntools/data/job_ids/")]
    # https://www.pythonforbeginners.com/basics/remove-substring-from-string-in-python
    for d in dir_lst[1:]:
        substring = "/home/ubuntu/anntools/data/job_ids/"
        split_lst = d.split(substring)
        string = "".join(split_lst)[37:]
        dir_job_id = "".join(split_lst)[:36]
        if dir_job_id == job_id: # Only retrieve input_file for dir that matches job_id
            if "/running" in string:
                input_name = string[:-8]
            elif "/complete" in string:
                input_name = string[:-9]
    # (3) Check if "complete" directory exists for specified job_id, which means the job was 
    # already complete by the time the directory was created
    if path.exists(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/complete'):
        f = open(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/{input_name}.vcf.count.log', mode='r')
        content = f.read()
        response_code = 200
        body = {
            "code": response_code,
            "data":{
                "job_id": job_id,
                "job_status": "completed",
                "log": content
                }
            }
        f.close()
        return jsonify(body), response_code
    # (4) Check if "running" directory exists for specified job_id, which means job was running at 
    # the time the directory was created
    elif path.exists(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/running'):
        # (4.1) Check if input_file.vcf.count.log and input_file.annot.vcf exist, which indicates that 
        # even though the job was running when directory was created, now it's completed
        if (path.exists(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/{input_name}.vcf.count.log') and 
        path.exists(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/{input_name}.annot.vcf')):
            f = open(f'/home/ubuntu/anntools/data/job_ids/{job_id}_{input_name}/{input_name}.vcf.count.log', mode='r')
            content = f.read()
            response_code = 200
            body = {
                "code": response_code,
                "data":{
                "job_id": job_id,
                "job_status": "completed",
                "log": content,
                }
            }
            f.close()
            return jsonify(body), response_code
        # (4.2) If one of those files does not exist, the job is still running
        else:
            response_code = 200
            body = {
                "code": response_code,
                "data":{
                    "job_id": job_id,
                    "job_status": "running",
                    }
            }
            return jsonify(body), response_code 


@app.route('/annotations', methods=['GET'])
def get_job_list():
    '''
    This endpoint allows the user to get a list of annotation jobs, and optionally the 
    status/log for a job using the link provided.
    '''
    # (1) Retrieve set of job_ids stored in subdirectories
    # https://stackoverflow.com/questions/973473/getting-a-list-of-all-subdirectories-in-the-current-directory
    dir_lst = [i[0] for i in os.walk("/home/ubuntu/anntools/data/job_ids/")]
    job_set = set()
    # https://www.pythonforbeginners.com/basics/remove-substring-from-string-in-python
    for d in dir_lst[1:]:
        substring = "/home/ubuntu/anntools/data/job_ids/"
        split_lst = d.split(substring)
        job_id = "".join(split_lst)[:36]
        job_set.add(job_id)
    job_lst = list(job_set) # Convert set to list
    # (2) Error Handling for job not found when GETting job status
    if job_lst == []:
        # Did not use a 204 No Content Response because GET request is successful 
        # https://blog.ploeh.dk/2013/04/30/rest-lesson-learned-avoid-204-responses/
        response_code = 200
        lst = []
        body = {
            "code": response_code,
            "data":{
                "jobs": lst
                }
            }
        return jsonify(body), response_code
    # (3) Success case where job_lst contains jobs
    else:
        lst = []
        for job in job_lst:
            lst.append({"job_id": job, 
            "job_details": f"http://mariagabrielaa-a4.ucmpcs.org:5000/annotations/{job}"})
        response_code = 200
        body = {
                "code": response_code,
                "data":{
                    "jobs": lst
                }
            }
        return jsonify(body), response_code


# Run the app server
app.run(host='0.0.0.0', debug=True)