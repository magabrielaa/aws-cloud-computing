import sys
import boto3
# https://www.trek10.com/blog/handling-errors-in-boto3-botocore
from botocore.exceptions import ClientError


# (1)
def instance_protect(tag_name):
    '''
    Prints the instance ID, launch time, and availability zone for each instance associated with the given
    Name tag.
    Checks for termination protection and if not enabled, sets it for each instance. Attempts to terminate
    each instance and handles error in print message.
    Input (str): tag_name / CNet ID
    '''
    ec2_client = boto3.client("ec2", region_name="us-east-1")
    ec2 = boto3.resource('ec2')
    # Referred to list of running instances by tag
    # https://stackoverflow.com/questions/48072398/get-list-of-ec2-instances-with-specific-tag-and-value-in-boto3
    try:
        instances = ec2.instances.filter(Filters=[{'Name': 'tag:Name', 'Values': [tag_name]}])
    except ClientError as e:
        # Referred to error handling with boto3
        # https://stackoverflow.com/questions/33068055/how-to-handle-errors-with-boto3
        print(e['Error']['Message'])
        return
    print()
    for instance in instances:
        print("Instance ID:", instance.id)
        print("Launch Time:", instance.launch_time,"(Availability Zone):", instance.placement['AvailabilityZone'])
        # Referred to "describe_instance_attribute(**kwargs)"
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#instance
        try:
            response = ec2_client.describe_instance_attribute(
            Attribute='disableApiTermination',
            InstanceId= instance.id
            )
        except ClientError as e:
            print(e['Error']['Message'])
            return
        state_code = instance.state['Code']
        # State codes obtained from https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceState.html
        valid_codes = [0, 16, 64, 80] 
        # Codes 32 and 48 corresponding to states "shutting down" and "terminated" are excluded because an instance 
        # cannot be modified or terminated in these 2 cases
        if response['DisableApiTermination']['Value'] is False: # Check if termination protection is enabled
            if state_code in valid_codes: # Check if instance is in a valid state
                # https://stackoverflow.com/questions/58024395/how-to-change-termination-protection-by-boto3
                try:
                    ec2.Instance(instance.id).modify_attribute(
                        DisableApiTermination={
                        'Value': True
                        }
                    )
                except ClientError as e:
                    print(e.response['Error']['Message'])
                    return
            else: # Error message when instance is in an invalid state
                print(f"Attribute modification failed: The instance '{instance.id}' is in an invalid state: " 
                "'shutting down' or 'terminated' and termination protection cannot be enabled.")
        try:
            ec2.Instance(instance.id).terminate()
        except ClientError as e:
            print("Instance termination failed:", e.response['Error']['Message'])
            

# (2)
def ebs_profile():
    '''
    Prints the total number of EBS volumes currently provisioned/ attached to EC2 instances in 
    our shared AWS account, including the storage in GB.
    '''
    # Referred to "command to list out all attached volumes"
    # https://stackoverflow.com/questions/34002826/list-ec2-volumes-in-boto
    ec2 = boto3.resource('ec2')
    try:
        # Filtered by volumes attached to instances
        volumes = ec2.volumes.filter(Filters=[{'Name': 'status', 'Values': ['in-use']}]) 
    except ClientError as e:
        print(e.response['Error']['Message'])
        return
    count = 0
    size = 0
    # https://stackoverflow.com/questions/46368997/how-can-i-get-the-aws-volumes-available-size-by-boto3
    for volume in volumes:
        count += 1
        size += volume.size
    print()
    print ("Number of EBS volumes:", count)
    print("Total provisioned storage (GB):", size)


# (3)
def security_group_rules(sec_group_name):
    '''
    Given a security group name, prints: the open inbound ports and the IP
    addresses (v4 and v6) ranges of allowed inbound traffic for each open port.
    Input (str): EC2 security group
    '''
    ec2_client = boto3.client("ec2", region_name="us-east-1")
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.describe_security_groups
    try:
        response = ec2_client.describe_security_groups(GroupNames=[sec_group_name,])
    except ClientError as e:
        print(e.response['Error']['Message'])
        return
    ip_permissions = response['SecurityGroups'][0]['IpPermissions']
    # Initalize lists to hold port numbers and IP address ranges (v4 and v6)
    ports = []
    v4_ranges = []
    v6_ranges = []
    for i, ip in enumerate(ip_permissions):
        ports.append(ip['FromPort'])
        if ip['IpRanges'] != []:
            v4_ranges.append([ip['IpRanges'][0]['CidrIp']])
        else:
            v4_ranges.append([])
        if ip["Ipv6Ranges"] != []:
            v6_ranges.append([ip['Ipv6Ranges'][0]['CidrIpv6']])
        else:
            v6_ranges.append([])
    # String output in table format
    print()
    print("Port     Inbound IP Address Range(s)")
    print("----     ---------------------------")
    for i in range(len(ports)):
        if len(str(ports[i])) == 4:
            print(ports[i], "   ", v4_ranges[i], v6_ranges[i])
        elif len(str(ports[i])) == 3:
            print(ports[i], "    ", v4_ranges[i], v6_ranges[i])
        else:
            print(ports[i], "     ", v4_ranges[i], v6_ranges[i])
    print()


# (4)
def main_function(arguments):
    '''
    Checks that the the two required arguments were provided by the client and subsequently calls the 
    following functions: instance_protect, ebs_profile, security_group_rules.
    Input (list): CNet ID and security group name
    '''
    if len(arguments) < 2:
        print ("Error: Either the CNetID or security group name were not provided. Please include both "
        "arguments and run again.")
        return
    elif len(arguments) > 2:
        print ("Error: Too many arguments included. Only two are required: CNetID and security group name." 
        "Please include only both arguments and run again")
    else:
        instance_protect(arguments[0])
        ebs_profile()
        security_group_rules(arguments[1])


# https://stackoverflow.com/questions/35054616/passing-arguments-to-functions-in-python-using-argv
arguments = sys.argv[1:] # Store console arguments in a list, excluding the name of the file
main_function(arguments)