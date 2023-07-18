# Data Restoration

When a Free user converts to a Premium user, I move all of that user’s results files from the AWS Glacier vault back to the `gas-results` S3 bucket. 

## Approach
For the data restoration, my approach consists of the following steps:

![Data Restoration Flow]()

###  /subscribe endpoint in `views.py`
When a free user updates to premium, I post a message to a new SNS Premium Topic. This message contains the **user_id**.

### `thaw_app.py`
I set up thaw as a webhook app that follows these steps:

- Check request message type from SNS Premium message
    - If the type is "SubscriptionConfirmation" --> confirm subscription
    - If the type is "Notification" --> poll the SQS **Premium Queue** for the max # of 10 messages
        - Retrieve the **user_id** from the message body
        - Query the **Dynamo DB** database to get list of archive ID's associated with the user_id in the message
            - If the attribute retrieval_request_id is in that job item, it means that a retrieve request is already in process in Glacier
                - Delete the message --> no need to re-process
            - Else, if the job item has an archive_id but no retrieval_request_id --> retrieval request is needed
                - Create a list of dictionaries called **archive_ids** where each dictionary contains job_id and archive_id for one job
        - Loop through list of dictionaries:
            - Try expedited retrieval from Glacier --> include **SNS Restore** topic as a parameter and pass **job_id** in the description
            - If expedited request fails:
                - Check if Client error is due to _insufficient capacity_, if so:
                    - Try Standard retrieval request --> include **SNS Restore** topic as a parameter and pass **job_id** in the description
                - Else print message and return
            - Persist **retrieval_request_id** to Dynamo DB
            - Delete message from queue

###  AWS Lambda function - copied in `restore.py`
My Lambda gets triggered when a new message is posted by Glacier to the **SNS Restore** topic. The function does the following:

- Poll the **SQS Restore queue** 
- Process restore messages:
    - Retrieve the job_id, archive_id, and retrieval_request_id from the SNS restore message
    - Get the file output from Glacier
    - Query **Dynamo DB** to get the **results file key** by using job_id as a partition key
    - Restore results file to **S3 gas-results bucket**
    - Delete archive from **Glacier**
    - Delete message from **SQS Restore queue**
    - Remove archive_id and retrieval_request_id from **Dynamo DB**

### /annotation/<id> endpoint in `views.py`
A user hits this endpoint when they want to see the details of an annotation job. Here I:

- Check if the job is thawing through the response obtained from the **Dynamo DB** query in lines **193-199**
    - If the **retrieval_request_id** attribute is in the database --> job is in thaw/restoration process
        - Create a variable called **is_thawing** set to _True_
    - Else if **retrieval_request_id** is NOT in the database --> the job is either no longer thawing or was never thawed to begin with (ie. because the user was already premium when the job was annotated)
        - Set **is_thawing** to _False_
    - Pass **is_thawing** to **annotation.html** in render_template so that, if _True_, it can be used to display the following message to the user _"File is being restored. Please check back later."_ 

## RATIONALE
First, I decided to create two additional SNS topics and SQS queues: **premium** and **restore**. Since data restoration is a two-step operation, I **decoupled** both steps to achieve more **scalability** by having:

1. **Premium SNS** trigger the **thaw process**
2. **Restore SNS** trigger the **restore process**

My thaw process is set up as **webhook** instead of continous long polling so that this resource is only called when there is a something to be done, contributing to the application's scalability.

I placed the try-except **Standard retrieval** request nested within the except part of the **Expedited retrieval**. First I check if the specific error was due insufficient capacity, and if so, Standard retrieval is attempted. Otherwise, the Standard Retrieval is not attempted (for example if the Glacier server is down, it doesn't make sense to try another retrieval).

I make use of the **retrieval_request_id** attribute to check whether a job is thawing. This attribute is written to **Dynamo DB** after the retrieval request succeeds (either through Expedited or Standard) and it is only deleted at the end of my **Lambda** once the restoration process is complete.

Therefore, in the **/annotation/id** endpoint in `views.py`, I check if the **retrieval_request_id** attribute exists for that job and if it does, I know that the job is still in the thaw/restoration procedure. If it does not exist, then it means either: 

1. The job is done restoring and the **retrieval_request_id** was deleted by Lambda, or
2. The job was never thawed/restored in the first place because the user was premium when the job was run (since we are not dealing with the edge case of a premium user downgrading to free, there is no need to keep track of this case)

At the end of my **serverless Lambda function**, I remove **archive_id** in addition to **retrieval_request_id** from my Dynamo DB table because they both correspond to ephemeral states that have completed by this point.

In my Lambda, I opted to have a queue in addition to the SNS restore topic so that, in case the message fails to be processed, it is not lost and can be re-processed the next time the Lambda is triggered. I did this to improve the **user_experience** because otherwise, if a message fails to be processed, after 24 hours the results file will be re-archived to Glacier and the user will not be able to download it, despite having upgraded and paid to be a premium subscriber.

For this same reason, I decided to include **returns** at every step in my Lambda function, because each step is dependent on each other and if there is a failure, the message can be reprocessed in the queue. Additionally, I changed the **Lambda timeout** from the default of 3 seconds to 30 seconds, to give it enough leeway to go through all the steps in the function. I expect the function to take 10-15 seconds on average, so I set an upper bound of 30 in case there is a delay. Setting it higher than that would have **cost implications** for a resource that will not be utilized. 


## About the GAS application
An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)). Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files