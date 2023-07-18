# GAS Cloud Application

The following repository contains the step-by-step building of an enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)) that implements a distributed system on the cloud using AWS and boto3. The fina version adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:

* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files

The complete application has the following workflow:

![Final GAS application]()