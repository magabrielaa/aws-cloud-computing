# Enhancing the User Interface

In this repository, I add three pages to improve the UX so users can check the status of their jobs and retrieve job results and log files:

1. I add a route handler that displays a list of all the jobs submitted by a user. See the template `annotations.html`. The code ensures that it only returns jobs for the current authenticated user. The page looks like this:

![Annotations list]()

2. I also add a route handler that displays the details of a requested job, the HTML file is `annotation.html`. For security reasons, I check that the requested job ID belongs to the user that is currently authenticated. If it does not, I return a 403 status and display a message using the 403 error route handler in `views.py`. 

![Annotation details]()

3. I provide links for users to download the results file and view the log file for a job. When the user clicks a filename hyperlink in the job detail listing:

- If the user clicks on the results file name link, it downloads the file from S3 to the user’s laptop (I use a pre-signed download URL for this purpose)
- If the user clicks on the log file link, it displays the log file in the browser (I read the S3 object into a string and return that in a simple template in `view_log.html` using a <pre> tag so that it is readable)