# Subscription Upgrade - Stripe Integration

The GAS application uses a subscription model whereby Premium users can pay $999.99 per week to run as many analyses as they want and store as much data as they want. Although this is not a realistic and sustainable business model, it's a price example to integrate Stripe into the application for credit card subscriptions.

See `subscribe.html` where I modify the template to get the user’s credit card information. 

## APPROACH

### /subscribe endpoint in `views.py`
I did not add code to handle files not yet archived because I already handle this situation by checking if a user is free or premium before sending a request to archive the results file to Glacier. This code is in lines **100-105** in `archive_app.py`. 

### `annotate.html`
I implemented code in `annotate.html` that does the following:

- Check the user role. If free role:
    - Get the file size the user is attempting to upload. 
    - If bigger than 150 KB (ie. >= 153600 Bytes) --> alert user through a pop up and prompt to upgrade to premium.
    - Disable submit button so that free user cannot submit oversized file for annotation

- If no file is uploaded --> alert user to upload a file and disable submit button. This prevents users from inadvertently submitting a job request without an input file.


## About the GAS application
An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)). Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files