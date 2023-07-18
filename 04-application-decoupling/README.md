# Application Decoupling

### Ex. 3

- Since my approach to separating the execution of unique files is to create a subdirectory for each job, after I upload the annotated and log files to S3, I don't delete only the .vcf.count.log and .annot.vcf files but instead, I delete the whole subdirectory created for that job (which contains those two files and the input file downloaded from S3. This can be seen in my `a7_run.py` file on lines **57, 64** and **66**).
