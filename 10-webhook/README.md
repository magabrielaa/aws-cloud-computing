# Enhancing the Annotator

Requiring the annotator to continuously poll the job requests queue, as done up to `09-user-notifications` is not good (scalable) application design. A better way is to use a **webhook**: an HTTP endpoint that is called by the producer when an event of interest to the consumer occurs (in this case, when a new job is available). SNS allows us to send a notification to an HTTP endpoint (in addition to SQS queues and other subscribers). 

See `annotator_webhook.py` for the route handler to the webhook and `ann_config.py` which stores the configuration files instead of `ann_config.ini` as before.

## About the GAS application
An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)). Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files