# Annotator API

### Endpoint 1
My approach to **persisting job_ids** is:
- Create a directory containing job_id and input_file in the name
- Create a copy of the input file and place it into this new job-specific directory
- Run the subprocess within the job-specific directory
- Check if **.vcf.count.log** and **.annot.vcf** exist, which indicates the job is _complete_
    - Create a subdirectory called `complete`
- If only **.vcf.count.log** exists, the job is still _running_
    - Create a subdirectory called `running`

This approach is **scalable** because multiple concurrent job processes are accessing different directories instead of a single shared one, so it is less likely to lead to a deadlock. However, it is possible that if there is a very high number of jobs being run, it would consume significant storage in the file system.

### Endpoint 2
Given a job_id, I confirm the status of the job with the following logic:
- If the `complete` subdirectory exists for a given id --> job was already complete at the time the directory was created --> status: complete
- If the `running` directory exists for a given id, there are two options:
    - Check if **.vcf.count.log** and **.annot.vcf** files exist, which means that even though the job was running at the time the directory was created, now it's complete --> status: complete
    - Otherwise, the process is ongoing --> status: running

### Error Handling
In Endpoint 3, in the case where the job list is empty I return a message with success code 200 because the request was indeed successful, albeit with no content.

I opted against using a 204 No Content error code because this does not display any message to the user and could lead to confusion.