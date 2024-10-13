import requests
from flask import json
import json
import http.client

# Lambda API's
warmup_api_url = "https://mjeem8gh5j.execute-api.us-east-1.amazonaws.com/default/scale_services" # Lambda function in aws which scales as per user POST request
scaled_ready_api_url = "https://fnmqom1xe9.execute-api.us-east-1.amazonaws.com/default/scaled_ready" # Lambda function in aws that checks and returns scaled_ready status
get_warmup_cost_api_url = "https://70a80doa3g.execute-api.us-east-1.amazonaws.com/default/get_warmup_cost" # Lambda function in aws that checks and returns warmup billable time and cost
get_endpoints_api_url = "https://evsgvrzii9.execute-api.us-east-1.amazonaws.com/default/get_endpoints"
terminate_api_url = "https://hbgff298dk.execute-api.us-east-1.amazonaws.com/default/terminate"
scaled_terminated_api_url = "https://1k0vnbv050.execute-api.us-east-1.amazonaws.com/default/scaled_terminated"
analyse_api_url = "https://wyjbie4tl3.execute-api.us-east-1.amazonaws.com/default/analyse"
simulation_api_url = "https://qfep3jkhk3.execute-api.us-east-1.amazonaws.com/default/simulation" # Runs the simulation of the analysis



# Threading. In order to return immediate response to warmup call
def send_request(scale, service_type):
    print("Sending request to Lambda with scale:", scale, "and service_type:", service_type)
    try:
        c = http.client.HTTPSConnection("mjeem8gh5j.execute-api.us-east-1.amazonaws.com")
        headers = {'Content-type': 'application/json'}
        payload = json.dumps({'r': scale, 's': service_type}).encode('utf-8')
        c.request("POST", "/default/scale_services", body=payload, headers=headers)
        
        response = c.getresponse()
        response_data = response.read().decode('utf-8')
        print("Response from Lambda:", response_data)
    except Exception as e:
        print("Failed to send request to Lambda:", str(e))


# For parallel analysis execution. 
## Reference: Lab3   
def getresult(id, mean, std, d):
    try:
        host = "qfep3jkhk3.execute-api.us-east-1.amazonaws.com"
        c = http.client.HTTPSConnection(host)
        # json= '{ "mean": '+str(mean)+', "std": '+str(std)+', "shots": '+str(d)+'}'
        request_json = json.dumps({ "mean": mean, "std": std, "shots": d })
        c.request("POST", "/default/simulation", request_json)
 
        response = c.getresponse()
        # data = response.read().decode('utf-8')
        data = json.loads(response.read().decode('utf-8')) # Decoding and loading into a dict
        # print(data)
        print( data, " from Thread", id )
        return data
    except IOError:
        print( 'Failed to open ', host ) # Is the Lambda address correct?
    # print(data+" from "+str(id)) # May expose threads as completing in a different order
    return "unusual behaviour of "+str(id)


# For analyse to get the list of newly created ec2 instances
def get_ec2_dns_list():
    response = requests.get(scaled_ready_api_url)
    data = response.json()['body']
    return data.get('ec2_dns_list', [])


def analyse_on_ec2(instance_dns, mean, std, shots):
    url = f'http://{instance_dns}:5000/run_analysis'
    data = {'mean': mean, 'std': std, 'shots': shots}
    response = requests.post(url, json=data)
    return response.json()


def send_terminate_request():
    print("Sending terminate request to Lambda")
    try:
        c = http.client.HTTPSConnection("hbgff298dk.execute-api.us-east-1.amazonaws.com")
        headers = {'Content-type': 'application/json'}
        c.request("GET", "/default/terminate", headers=headers)
        
        response = c.getresponse()
        response_data = response.read().decode('utf-8')
        print("Response from Lambda:", response_data)
    except Exception as e:
        print("Failed to send terminate request to Lambda:", str(e))


