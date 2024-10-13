## DM for all the aws lambda functions  


# scale_services (warmup) 
import json
import boto3
import uuid
from datetime import datetime
import time
import http.client

def lambda_handler(event, context):
    service_type = event['s']
    scale = int(event['r'])
    response = {'responses': []}  # Initialize to collect responses from each invocation
    service_info = []

    warmup_start_time = datetime.utcnow()
    s3_client = boto3.client('s3', region_name='us-east-1')
    ec2_client = boto3.resource('ec2', region_name='us-east-1')

    if service_type == 'lambda':
        host = "qfep3jkhk3.execute-api.us-east-1.amazonaws.com"
        path = "/default/simulation"  # Path to the Lambda function via API Gateway

        def invoke_lambda():
            for _ in range(scale):
                try:
                    c = http.client.HTTPSConnection(host)
                    json_payload = json.dumps({"mean": "0.2", "std": "0.4", "shots": "100"})  # Dummy values
                    c.request("POST", path, body=json_payload)
                    response_http = c.getresponse()
                    data = response_http.read().decode('utf-8')
                    lambda_data = json.loads(data)
                    response['responses'].append(lambda_data)  # Append the data received from the Lambda

                    # Fetch the ARN from the Lambda context, which needs to be handled in API Gateway settings to include it in response
                    lambda_arn = context.invoked_function_arn  # Access ARN directly from the context

                    service_info.append({
                        'type': 'lambda',
                        'status': response_http.status,
                        'data': data,
                        'arn': lambda_arn  # Store the ARN directly from the context
                    })
                except Exception as e:
                    print('Failed to invoke lambda:', e)
                    response['responses'].append({'error': str(e)})

        invoke_lambda()

    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/service-resource/create_instances.html
    elif service_type == 'ec2':
        instances = ec2_client.create_instances(
            ImageId='ami-07d92623f71b05fce',
            MinCount=1,
            MaxCount=scale,
            InstanceType='t2.micro',
            KeyName='ut_keypair',
            SecurityGroups=['ssh_security'], 
            TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Project', 'Value': 'Coursework'}]}],
            UserData='''#!/bin/bash
                        cd /home/ec2-user/analysis_app
                        source /home/ec2-user/venv/bin/activate
                        nohup python3 app.py > app.log 2>&1 &
                     '''
        )
        waiter = ec2_client.meta.client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[i.id for i in instances])
        for i in instances:
            i.reload()
            service_info.append({
                'id': i.id,
                'type': 'ec2',
                'state': i.state['Name'],
                'dns': i.public_dns_name,
                'arn': i.instance_id  # Store the instance ID as ARN for consistency
            })

    warmup_end_time = datetime.utcnow()
    service_metadata = {
        'service_type': service_type,
        'service_info': service_info,
        'warmup_start_time': warmup_start_time.strftime('%Y-%m-%dT%H:%M:%S'),
        'warmup_end_time': warmup_end_time.strftime('%Y-%m-%dT%H:%M:%S')
    }
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html
    s3_client.put_object(
        Bucket='cw-service-bucket',
        Key='service_state.json',
        Body=json.dumps(service_metadata)
    )

    return {'result': 'ok'}


# Scaled_ready (returning S3 dns list for analyse to fetch)
import boto3
import json

def lambda_handler(event, context):
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    s3_client = boto3.client('s3', region_name='us-east-1')

    # Fetch the stored service data from S3
    try:
        # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_object.html
        response = s3_client.get_object(Bucket='cw-service-bucket', Key='service_state.json')
        service_metadata = json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f"Error retrieving service metadata: {str(e)}")
        return {'statusCode': 200, 'body': {'warm': False}}

    # Retrieve the list of services from the service metadata
    service_data = service_metadata['service_info']
    all_active = True
    ec2_dns_list = []

    for service in service_data:
        if service['type'] == 'lambda':
            try:
                lambda_response = lambda_client.get_function(FunctionName=service['arn'])
                if lambda_response['Configuration']['State'] != 'Active':
                    all_active = False
                    break
            except Exception as e:
                all_active = False
                break

        elif service['type'] == 'ec2':
            try:
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_instances.html
                ec2_response = ec2_client.describe_instances(InstanceIds=[service['id']])
                instance_state = ec2_response['Reservations'][0]['Instances'][0]['State']['Name']
                instance_status = ec2_client.describe_instance_status(InstanceIds=[service['id']])
                
                status_ok = False
                if instance_status['InstanceStatuses']:
                    status_check = instance_status['InstanceStatuses'][0]['InstanceStatus']['Status']
                    if status_check == 'ok':
                        status_ok = True

                if instance_state != 'running' or not status_ok:
                    all_active = False
                    break
                else:
                    ec2_dns_list.append(service['dns'])
            except Exception as e:
                all_active = False
                break

    return {
        'statusCode': 200,
        'body': {
            'warm': all_active,
            'ec2_dns_list': ec2_dns_list
        }
    }


# simulation (connects with GAE)
import json
import random
import boto3

def lambda_handler(event, context):
    mean = float(event['mean'])
    std = float(event['std'])
    shots = int(event['shots'])

    # Initialize S3
    s3 = boto3.client('s3')
    
    # Per simulation, there will be one pair of values for 95 and 99. Need to be stored in GAE and show the combined result to user
    ## Reference: Coursework Document
    simulated = [random.gauss(mean, std) for x in range(shots)]
    simulated.sort(reverse=True)
    var95 = simulated[int(len(simulated) * 0.95)]
    var99 = simulated[int(len(simulated) * 0.99)]
    results = {'var95': var95, 'var99': var99}

    # Generate a unique key for this execution so multiple services do not overwrite each other
    unique_key = f"analysis_results_{context.aws_request_id}.json"
    
    return {
        'statusCode': 200,
        'body': {'results': results, 'data_key': unique_key}
    }


