# Uploading Data to Object Storage in S3

In this repository, I usw AWS S3 to store user input files and annotated results files. The application uses two S3 buckets:

1. `gas-inputs`
2. `gas-results`

All interactions with these buckets is done using `boto3` in Python.

### Note: annotate/files endpoint

Given that by uploading a file, we are creating a new resource, I choose to return status code **201** instead of the generic 200 success code.
