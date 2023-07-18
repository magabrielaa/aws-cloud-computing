# Application Decoupling Using Message Queues

Here, I add components that further the GAS application services and allow them to _scale independently_ of each other. These are the additional components:

1. A **message queue** that will act as a “buffer” between the web app and the annotator. New annotation requests will be posted to the message queue and the annotator will retrieve them independently. Requests can be successfully accepted by the GAS, even if the annotator service is not available. This is an important requirement for increasing the availability of a distributed system. I use AWS Simple Message Queue **(SQS)** service to implement the queue.

2. A **notification topic** that accepts messages (i.e. annotation requests) from the web app. When a notification is sent to the topic, a message will be created in the message queue. I use AWS Simple Notification Service (SNS) for this purpose. SNS has the convenient property that an SQS queue can subscribe to get messages from SNS topics. 

With these changes, the application now looks like this:


### Note: Error Handling

My approach to error handling was creating a secondary function called **process_queue()**, which returns to the main function everytime there is an error such as: failure to download the input file from S3, failure to launch to the annotator or failure to update the database.

I included a few edge cases in my error handling:

- Lines **26-29** in `annotator.py`: If the queue doesn't exist, then I exit with **sys.exit()** the while loop because this is a system design issue and it doesn't make sense to stay within the while loop if there is no queue to process. 
- Lines **75-87** in `annotator.py`: If the input file doesn't exist, then it will not be possible to download it from S3 or continue with the rest of the process, no matter how many times the message is processed. In this case:
    - I update the job status to **"FAILED"** in the database
    - Delete the message from the queue 
- Lines in `run.py`: I added a conditional statement to only update the table to "COMPLETED" if the previous status is "RUNNING", as a safeguard.
