from flask import Flask, jsonify, render_template
import uuid
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)
# Keep order of sorted dictionaries passed to jsonify
app.config['JSON_SORT_KEYS'] = False


@app.route('/annotate', methods=['GET'])
def annotate():
    '''
    User can upload an input file into the S3 bucket, after which the user will
    be redirected to a page that lists all the files they have uploaded.
    '''
    # (1) Generate a presigned URL for the S3 object
    s3_client = boto3.client('s3', region_name= 'us-east-1') 
    object_id = str(uuid.uuid4()) # Generate unique object id
    # Referred to Sample Policy and Form
    # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
    # https://www.scaleway.com/en/docs/storage/object/api-cli/post-object/
    bucket_name="gas-inputs"
    object_name=f'mariagabrielaa/{object_id}~' + '${filename}'
    fields = {
        'acl': 'private',
        "success_action_redirect": "http://mariagabrielaa-a6.ucmpcs.org:5000/annotate/files",
        }
    conditions = [
        {"acl": "private"},
        {"success_action_redirect": "http://mariagabrielaa-a6.ucmpcs.org:5000/annotate/files"}
        ]
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
        print(e['Error']['Message'])
        exit()
    # (3) Render the upload form template
    return render_template('annotate.html', policy=response, bucket_name=bucket_name)

    
@app.route('/annotate/files', methods=['GET'])
def annotate_files():
    '''
    This endpoint gets a list of objects from the S3 input bucket and returns them to
    the user in a JSON object.
    '''
    # Referred to list_objects_v2(**kwargs)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.list_objects_v2
    # https://stackoverflow.com/questions/35803027/retrieving-subfolders-names-in-s3-bucket-from-boto3
    s3 = boto3.client("s3", region_name= 'us-east-1')
    try: 
        all_objects = s3.list_objects_v2(Bucket = 'gas-inputs', Prefix ='mariagabrielaa/')
    except ClientError as e:
        print(e['Error']['Message'])
        exit()
        
    obj_lst = []
    for obj in all_objects["Contents"]:
        obj_lst.append(obj["Key"])

    response_code = 201
    body = {
        "code": response_code,
        "data": {
            "files": obj_lst
        }
    }
    return jsonify(body), response_code


# Run the app server
app.run(host='0.0.0.0', debug=True)