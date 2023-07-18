# User Notifications

It is key to have a way to notify a user when the job is complete. I do this by publishing a notification to an SNS topic (with a subscribed SQS queue, as I did before for job requests) and running a separate Python script that sends emails to users. This way, the annotator can continue to process jobs while notifications for completed jobs are sent out-of-band. See `~/gas/util/notify` to view these changes.

See an example of how a received email notification looks like:

![Notification example]()


## About the GAS application

An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)) for use in the capstone project. Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files