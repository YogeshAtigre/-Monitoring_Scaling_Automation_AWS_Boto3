import base64
import boto3

# Initialize boto3 clients
ec2 = boto3.client('ec2',region_name='ap-south-1')
elb = boto3.client('elbv2',region_name='ap-south-1')
autoscaling = boto3.client('autoscaling',region_name='ap-south-1')
sns = boto3.client('sns',region_name='ap-south-1')
s3 = boto3.client('s3',region_name='ap-south-1')

def create_s3_bucket(bucket_name):
    """Create an S3 bucket and enable versioning."""
    s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': 'ap-south-1'})
    s3.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={'Status': 'Enabled'})
    print(f"S3 bucket {bucket_name} created and versioning enabled.")

def launch_ec2_instance(key_name, security_group_id, bucket_name):
    """Launch an EC2 instance with a web server and deploy files."""
    user_data = f"""#!/bin/bash
    yum update -y
    yum install -y httpd
    systemctl start httpd
    systemctl enable httpd
    aws s3 cp s3://{bucket_name}/index.html /var/www/html/
    """
    response = ec2.run_instances(
        ImageId='ami-00b7c98b4ec9462b0',
        InstanceType='t2.micro',
        KeyName=key_name,
        SecurityGroupIds=[security_group_id],
        MinCount=1,
        MaxCount=1,
        UserData=user_data
    )
    instance_id = response['Instances'][0]['InstanceId']
    print(f"EC2 Instance launched: {instance_id}")
    # Wait for the instance to be in the 'running' state
    waiter = ec2.get_waiter('instance_running')
    print("Waiting for the instance to reach 'running' state...")
    waiter.wait(InstanceIds=[instance_id])
    print(f"Instance {instance_id} is now running.")
    return instance_id

def create_alb(subnet_ids, security_group_id):
    """Create an Application Load Balancer."""
    response = elb.create_load_balancer(
        Name='my-alb',
        Subnets=subnet_ids,
        SecurityGroups=[security_group_id],
        Scheme='internet-facing',
        Type='application',
        IpAddressType='ipv4'
    )
    alb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
    print(f"ALB created: {alb_arn}")
    return alb_arn

def create_target_group(vpc_id):
    """Create a target group for the ALB."""
    response = elb.create_target_group(
        Name='my-target-group',
        Protocol='HTTP',
        Port=80,
        VpcId=vpc_id,
        HealthCheckProtocol='HTTP',
        HealthCheckPath='/',
        TargetType='instance'
    )
    target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
    print(f"Target group created: {target_group_arn}")
    return target_group_arn

def register_instance_to_target_group(target_group_arn, instance_id):
    """Register EC2 instance to the target group."""
    elb.register_targets(TargetGroupArn=target_group_arn, Targets=[{'Id': instance_id}])
    print(f"Instance {instance_id} registered to target group.")

def create_auto_scaling_group(launch_template_id, target_group_arn, subnet_ids):
    """Create an Auto Scaling Group."""
    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName='my-asg',
        LaunchTemplate={'LaunchTemplateId': launch_template_id},
        MinSize=1,
        MaxSize=3,
        DesiredCapacity=1,
        VPCZoneIdentifier=','.join(subnet_ids),
        TargetGroupARNs=[target_group_arn]
    )
    print("Auto Scaling Group created.")

def create_sns_topics():
    """Create SNS topics for alerts and return their ARNs."""
    topics = {
        'health_issues': sns.create_topic(Name='health_issues')['TopicArn'],
        'scaling_events': sns.create_topic(Name='scaling_events')['TopicArn'],
        'high_traffic': sns.create_topic(Name='high_traffic')['TopicArn']
    }
    print(f"SNS topics created: {topics}")
    return topics

def integrate_sns_with_lambda(topic_arns):
    """Integrate SNS topics with Lambda for notifications."""
    for topic_name, topic_arn in topic_arns.items():
        # Example: Subscribe a Lambda function or email to each topic
        sns.subscribe(
            TopicArn=topic_arn,
            Protocol='email',  # Can be 'email', 'sms', or 'lambda'
            Endpoint='example@example.com'  # Replace with actual email/SMS/Lambda endpoint
        )
        print(f"Integrated SNS topic {topic_name} with notifications.")

def update_auto_scaling_group():
    """Update the Auto Scaling Group to modify scaling policies."""
    print("Updating Auto Scaling Group...")
    autoscaling.update_auto_scaling_group(
        AutoScalingGroupName='my-asg',
        DesiredCapacity=2,  # Example: Increase desired capacity
        MinSize=2,
        MaxSize=4
            )
    print("Auto Scaling Group updated with new capacity settings.")

def teardown_infrastructure(bucket_name, launch_template_id, target_group_arn, alb_arn):
    """Tear down the entire infrastructure."""
    print("Tearing down infrastructure...")

    # Delete Auto Scaling Group
    print("Deleting Auto Scaling Group...")
    autoscaling.delete_auto_scaling_group(AutoScalingGroupName='my-asg', ForceDelete=True)

    # Delete Launch Template
    print("Deleting Launch Template...")
    ec2.delete_launch_template(LaunchTemplateId=launch_template_id)

    # Delete Target Group
    print("Deleting Target Group...")
    elb.delete_target_group(TargetGroupArn=target_group_arn)

    # Delete Load Balancer
    print("Deleting Load Balancer...")
    elb.delete_load_balancer(LoadBalancerArn=alb_arn)

    # Delete S3 Bucket and its contents
    print("Deleting S3 bucket...")
    objects = s3.list_objects_v2(Bucket=bucket_name)
    if 'Contents' in objects:
        for obj in objects['Contents']:
            s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
    s3.delete_bucket(Bucket=bucket_name)
    print("Infrastructure teardown completed.")

def setup_infrastructure():
    """Complete setup of the entire infrastructure."""
    bucket_name = "yogeshwebappbucket"
    key_name = "Deploy"
    security_group_id = "sg-0ac9c70d5d447c692"  # Replace with your security group ID
    subnet_ids = ['subnet-0780ec884d3fa729c', 'subnet-0fad7d42ee710009a']  # Replace with your subnets
    vpc_id = "vpc-04cf53aa05edeadc2"  # Replace with your VPC ID
    
    # Step 1: S3 bucket creation
    create_s3_bucket(bucket_name)

    # Step 2: EC2 Instance deployment
    instance_id = launch_ec2_instance(key_name, security_group_id, bucket_name)

    # Step 3: ALB setup
    alb_arn = create_alb(subnet_ids, security_group_id)
    target_group_arn = create_target_group(vpc_id)
    register_instance_to_target_group(target_group_arn, instance_id)

    user_data_script = f"""#!/bin/bash
    yum update -y
    yum install -y httpd
    systemctl start httpd
    systemctl enable httpd
    echo "<h1>Welcome to Yogesh's WebApp</h1>" > /var/www/html/index.html
    """
    # Encode user data in Base64
    user_data_encoded = base64.b64encode(user_data_script.encode('utf-8')).decode('utf-8')
    # Step 4: Auto Scaling Group setup
    # Create launch template
    response = ec2.create_launch_template(
        LaunchTemplateName='my-launch-template',
        LaunchTemplateData={
            'InstanceType': 't2.micro',
            'ImageId': 'ami-053b12d3152c0cc71',
            'UserData': user_data_encoded
        }
    )
    launch_template_id = response['LaunchTemplate']['LaunchTemplateId']
    create_auto_scaling_group(launch_template_id, target_group_arn, subnet_ids)

    # Step 5: SNS Setup
    topic_arns = create_sns_topics()
    integrate_sns_with_lambda(topic_arns)

    print("Infrastructure setup completed successfully!")
    return bucket_name, launch_template_id, target_group_arn, alb_arn

if __name__ == "__main__":
    while True:
        print("\nChoose an action:")
        print("1. Setup Infrastructure")
        print("2. Update Infrastructure")
        print("3. Teardown Infrastructure")
        print("4. Exit")

        choice = input("Enter your choice: ")

        if choice == '1':
            bucket_name, launch_template_id, target_group_arn, alb_arn = setup_infrastructure()
        elif choice == '2':
            update_auto_scaling_group()
        elif choice == '3':
            if bucket_name and launch_template_id and target_group_arn and alb_arn:
                teardown_infrastructure(bucket_name, launch_template_id, target_group_arn, alb_arn)
            else:
                print("Infrastructure not set up yet.")
        elif choice == '4':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")