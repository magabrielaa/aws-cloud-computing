# Scaling the Web Server with a Load Balancer

The single GAS web app server is fine for development and testing but notfor production. Assuming we expect heavy demand for the GAS service, we require a mechanism to automate scaling out and scaling in, when the system load subsides. For this, I use:

- The EC2 Auto Scaling service which allows us to define standard configurations and use them to launch multiple instances as needed, based on user-definable rules.
- The Elastic Load Balancer (ELB) service allows HTTP(S) requests to be distributed among multiple instances in our Auto Scaling group.

Using the AWS console, I created a load balancer and an auto scaling group using user data which can be found in `user_data_web_server.txt`. I then
attach the load balancer to the auto scaling group I created.

Finally, I use a simple load testing tool called **Locust**. The tool simulates a number of concurrent users accessing the GAS. Each user submits a
number of requests to the GAS with a specified frequency, thus creating an arbitrarily high load - a swarm of locusts descending on the Elastic Load Balancer. I use **CloudWatch** in AWS to analyze the results, which are contained in `scaling.analysis.pdf`


## About the GAS application
An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)). Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files