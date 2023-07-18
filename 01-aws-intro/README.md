# AWS Intro

### (1)

I included an additional print statement for the case where an instance is in an invalid state (ie. "shutting down" or "terminated")
to alert that the attribute "DisableApiTermination" cannot be modified in this scenario.

In this case, the code will not attempt to terminate the instance because it is either already terminated or in the process of terminating.

This can be found on lines **57-59** in my `intro.py` file.

### Error handling

Throughout the code, I used a ClientError try/except whenever there is a call to the AWS API to catch the case when the connection might fail.
