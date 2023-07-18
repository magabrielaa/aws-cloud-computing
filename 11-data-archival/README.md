# Data Archival with AWS Glacier

Free users can only download their results file for up to 5 minutes after completion of their annotation job. Yes, this is ridiculously restrictive, but I use such a  short interval to test the application more easily.

After 5 minutes elapse, a free user’s results file (not the log file) will be archived to a Glacier vault. This allows us to retain user data at relatively low cost, and to restore it in the event that the user decides to upgrade to a Premium user

For the data archival, my approach consists of the following steps:

### AWS Console Set up:
- Create an SNS Archive topic called _mariagabrielaa_a14_archive_
- Create SQS Archive queue called _mariagabrielaa_a14_archive_ and  subscribe it to the SNS Archive topic
- Set up a State Machine with two steps:
    - Wait - Configured to 300 seconds (5 min)
    - Task - Publish to SNS Archive Topic
-  Subscribe **/archive** endpoint in `archive_app.py` to SNS Archive Topic

### Code:

`run.py`
- When an annotation is complete, check user status
    - If free user:
        - Start State Machine execution and include the **job_id** as an input
        - Persist **execution ARN** to the Dynamo DB table

`archive_app.py`
- Check request message type
    - If the type is "SubscriptionConfirmation" --> confirm subscription
    - If the type is "Notification" --> poll the SQS Archive Queue for the max # of 10 messages
        - Retrieve the **job_id** from the message body
        - Query the Dynamo DB table using the **job_id** to get the **execution_Arn**
        - Check the user's current role
            - If premium user:
                - Skip archival process
            - Else if free user:
                - Retrieve results file from **S3 bucket** in bytes
                - Upload results file bytes to **Glacier** 
                - Persist **archive_id** to Dynamo DB table
                - Delete results file from S3 gas-results bucke
            - Delete **execution_ARN** from Dynamo DB table
            - Delete message from SQS Archive Queue


## Rationale

I decided to use an AWS **Step Function** to wait for the 5 min so the application is **scalable**. Other approaches like constantly polling the archive queue and checking the time difference until it's been 5 min or using sleep functions, block the application and result in downtime, which detrimines the user experience.

With the step function, the wait time is processed externally, and is **decoupled** from the rest of the application, allowing it to run independently without blocking other application components while the 5 minutes elapse. 

When the 5 mins have elapsed, the Step Function immediately publishes an **SNS archive message** , which then triggers my Flask **archive webhook**. I opted for a webhook instead of constantly polling the archive queue to make the application **more scalable**. This way the webhook gets triggered only when it's necessary, ie. when an execution has ran succesfully. The assumption is that at scale, there would be enough user requests such that if a message is not processed, it gets processed the next time the webhook is triggered.

When polling the archive queue, I check for the max # of 10 messages. The reason is in case there is a failure processing a particular message, it will remain in the archive queue and it will be processed the next time the webook is triggered.

Before proceeding with the archival process, I check if the user's role is **free**. Otherwise, it skips the archival process altogether. This is done to ensure that if a free user upgrades to premium before the 5 min have elapsed, they will still be able to access their result files.

After the message processing is complete, I **delete the execution ARN** from the Dynamo DB table because it corresponds to an ephemeral state that has already transcurred. The goal is to keep _only_ the necessary information in the Dynamo DB table.



## About the GAS application
An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)). Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files