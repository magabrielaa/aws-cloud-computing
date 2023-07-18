# run.py
#
# Copyright (C) 2011-2019 Vas Vasiliadis
# University of Chicago
#
# Wrapper script for running AnnTools
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import sys
import time
import driver
import boto3
from botocore.exceptions import ClientError
import os

"""A rudimentary timer for coarse-grained profiling
"""
class Timer(object):
    def __init__(self, verbose=True):
        self.verbose = verbose
    
    def __enter__(self):
        self.start = time.time()
        return self
    
    def __exit__(self, *args):
        self.end = time.time()
        self.secs = self.end - self.start
        if self.verbose:
            print(f"Approximate runtime: {self.secs:.2f} seconds")

if __name__ == '__main__':
    # Call the AnnTools pipeline
    if len(sys.argv) > 1:
        with Timer():
            driver.run(sys.argv[1], 'vcf')
        # Retrieve input_file and job_id from command line arguments (run by the subprocess)
        job_id = sys.argv[2]
        input_file = sys.argv[3]
        input_file_name = input_file.split(".")[0] # Remove .vcf extension

        # (1) Upload the results and log files to S3 results bucket
        # Referred to put_object(**kwargs)
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.put_object
        if os.path.exists(f'/home/ubuntu/anntools/data/job_ids/{job_id}'):
            all_files = os.listdir(f'/home/ubuntu/anntools/data/job_ids/{job_id}')
            for file in all_files:
                if file.endswith("annot.vcf") or file.endswith("count.log"):
                    try:
                        client = boto3.client('s3')
                        client.put_object(
                                        ACL='private',
                                        Body= f'/home/ubuntu/anntools/data/job_ids/{job_id}/{file}',
                                        Bucket='gas-results',
                                        Key=f'mariagabrielaa/userX/{job_id}/{file}')
                        # Remove results and log files from directory
                        os.remove(f'/home/ubuntu/anntools/data/job_ids/{job_id}/{file}')
                    except ClientError as e:
                        print("Failure to upload annotation files to S3. ", e.response['Error']['Message'])
                else:
                    os.remove(f"/home/ubuntu/anntools/data/job_ids/{job_id}/{file}") # Remove input file

        # (2) Update job item in DynamoDB table
        client = boto3.resource('dynamodb', region_name= 'us-east-1')
        try:
            # https://stackoverflow.com/questions/51048477/how-to-update-several-attributes-of-an-item-in-dynamodb-using-boto3
            table = client.Table("mariagabrielaa_annotations") 
            table.update_item(
                            Key={"job_id": job_id},
                            ConditionExpression= "job_status = :current_status",
                            UpdateExpression="SET s3_results_bucket= :results_bucket, s3_key_result_file= :results_file, \
                                            s3_key_log_file= :log_file, complete_time= :compl_time, job_status= :job_st",
                            ExpressionAttributeValues={
                                                    ':current_status': 'RUNNING',
                                                    ':results_bucket': 'gas-results', 
                                                    ':results_file': f'mariagabrielaa/userX/{job_id}~{input_file_name}.annot.vcf',
                                                    ':log_file': f'mariagabrielaa/userX/{job_id}~{input_file_name}.vcf.count.log',
                                                    ':compl_time': int(time.time()),
                                                    ':job_st': 'COMPLETED'
                                                    },
                            ReturnValues="UPDATED_NEW")
        except ClientError as e:
            print("Failure to update the database to COMPLETED.", e.response['Error']['Message'])

        # (3) Remove empty directory
        # https://wellsr.com/python/python-delete-all-files-in-folder/
        os.rmdir(f"/home/ubuntu/anntools/data/job_ids/{job_id}")

else:
        print("A valid .vcf file must be provided as input to this program.")
### EOF