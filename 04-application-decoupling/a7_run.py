
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
            relative_path = sys.argv[1].split("/home/ubuntu/anntools/data/job_ids/")[1]
            job_id = relative_path.split("/")[0][:36]
            input_file = relative_path.split("/")[1]
            # (1) Upload the results and log files to S3 results bucket
            # Referred to put_object(**kwargs)
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.put_object
            all_files = os.listdir(f'/home/ubuntu/anntools/data/job_ids/{job_id}')
            for file in all_files:
                if file.endswith("annot.vcf") or file.endswith("count.log"):
                    try:
                        client = boto3.client('s3', region_name= 'us-east-1')
                        client.put_object(ACL='private',
                                        Body= f'/home/ubuntu/anntools/data/job_ids/{job_id}/{file}',
                                        Bucket='gas-results',
                                        Key=f'mariagabrielaa/userX/{job_id}/{file}')
                        # Remove results and log files from directory
                        os.remove(f'/home/ubuntu/anntools/data/job_ids/{job_id}/{file}')
                    except ClientError as e:
                        print(e['Error']['Message'])

            # (2) Clean up (delete) local job files
            # https://pynative.com/python-delete-files-and-directories/
            # Remove input file from the directory
            os.remove(f"/home/ubuntu/anntools/data/job_ids/{job_id}/{input_file}")
            # Remove empty directory
            os.rmdir(f"/home/ubuntu/anntools/data/job_ids/{job_id}")
    else:
        print("A valid .vcf file must be provided as input to this program.")
### EOF