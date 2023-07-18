# Application Decoupling

The code in this directory implements the following steps in the GAS application flow:

1. The user requests an annotation by uploading a VCF file via the form built in `03-object-storage-S3`.
2. Now, after the input file is uploaded to S3, the response is redirected to the annotator EC2 instance (and the flow continues there instead of the web server)
3. The annotator then downloads the input file from the gas-inputs S3 bucket, spawns the annotation job and returns the job_id and file name to the user
4. Once the annotation is complete, the results file and the log file are moved to the S3 gas-results bucket

The updated application looks like this:

![GAS application](https://github.com/magabrielaa/aws-cloud-computing/blob/main/04-application-decoupling/application.jpg)

### Note:

- Since my approach to separating the execution of unique files is to create a subdirectory for each job, after I upload the annotated and log files to S3, I don't delete only the .vcf.count.log and .annot.vcf files but instead, I delete the whole subdirectory created for that job (which contains those two files and the input file downloaded from S3. This can be seen in my `a7_run.py` file on lines **57, 64** and **66**).
