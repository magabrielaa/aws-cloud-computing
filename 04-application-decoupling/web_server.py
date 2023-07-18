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
    This endpoint is for the user to upload an input file into the S3 gas-inputs 
    bucket, after which the user will be redirected to a page that returns the 
    job id and the name of the input file.
    '''
    # (1) Generate a presigned URL for the S3 object
    object_id = str(uuid.uuid4()) # Generate unique object id
    # Referred to Sample Policy and Form
    # https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
    # https://www.scaleway.com/en/docs/storage/object/api-cli/post-object/
    bucket_name="gas-inputs"
    user = "userX"
    object_name=f'mariagabrielaa/{user}/{object_id}~' + '${filename}'
    fields = {
        'acl': 'private',
        "success_action_redirect": "http://mariagabrielaa-a7-ann.ucmpcs.org:5000/annotations",
        }
    conditions = [
        {"acl": "private"},
        {"success_action_redirect": "http://mariagabrielaa-a7-ann.ucmpcs.org:5000/annotations"}
        ]
    expiration = 60 # Expire after 1 minute

    # (2) Generate signed POST request
    # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
    try:
        s3_client = boto3.client('s3', region_name='us-east-1') 
        response = s3_client.generate_presigned_post(Bucket=bucket_name,
                                                    Key=object_name,
                                                    Fields=fields,
                                                    Conditions=conditions,
                                                    ExpiresIn=expiration)
    except ClientError as e:
        response_code = 500
        body = {
            "code": response_code,
            "status": "error",
            "message": e['Error']['Message']
            }
        return jsonify(body), response_code

    # (3) Render the upload form template
    return render_template('annotate.html', policy=response, bucket_name=bucket_name)


# Run the app server
app.run(host='0.0.0.0', debug=True)