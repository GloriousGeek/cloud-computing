from gae_func import *
from flask import Flask, request, jsonify
import json
import requests
import threading
import yfinance as yf
from datetime import date, timedelta, datetime
from pandas_datareader import data as pdr
from concurrent.futures import ThreadPoolExecutor
import urllib.parse


app = Flask(__name__)


# Lambda functions API URL's
## All lambda functions URLS
gae_url = "xyz.appspot.com" # Google app engine URL


# Defining global variables to be used by endpoints
global scale
global service_type
global mean
global std
global d

# Global variables to store results for analysis 
profit_loss_results = []
var95_results = []
var99_results = []
avg_var95 = 0
avg_var99 = 0
total_time = 0
total_cost = 0
audit_log = []  # List to store audit information


@app.route('/') 
# A Hello Coursework test message
def hello(): 
    return 'Hello Coursework, you are tough!' 


@app.route('/warmup', methods=['POST'])
def warmup():
    if request.method == 'POST':
        if not request.json or 'r' not in request.json or 's' not in request.json:
            return jsonify({'error': 'Missing parameters, ensure both "r" (scale) and "s" (service_type) are provided'}), 400
        
        global scale # Storing value in global scale for threaded pool to be able to fetch
        global service_type # Storing value to be fetched by other endpoints
        scale = int(request.json['r'])
        service_type = request.json['s'].lower()

        # Start the request in a new thread, allowing the API to respond immediately
        threading.Thread(target=send_request, args=(scale, service_type)).start()

        # Immediately return success message
        return jsonify({'result': 'ok'}), 200


@app.route('/scaled_ready', methods=['GET'])
def scaled_ready():
    response = requests.get(scaled_ready_api_url)
    data = response.json()['body']
    return {'warm': data['warm']}


@app.route('/get_warmup_cost', methods=['GET'])
def get_warmup_cost():
    response = requests.get(get_warmup_cost_api_url)
    data = response.json()['body']
    data_dict = json.loads(data) # Converting string to dict
    billable_time = data_dict['billable_time']
    cost = data_dict['cost']
    return {
        'billable_time': billable_time,
        'cost': cost
    }


@app.route('/get_endpoints', methods=['GET'])
def get_endpoints():
    endpoints = [
        {"/warmup": f"""curl -s -H "Content-Type: application/json" -X POST -d '{{"s":"lambda", "r":"2"}}' {gae_url}/warmup"""},
        {"/scaled_ready": f"curl {gae_url}/scaled_ready"},
        {"/get_warmup_cost": f"curl {gae_url}/get_warmup_cost"},
        {"/get_endpoints": f"curl {gae_url}/get_endpoints"},
        {"/analyse": f"""curl -s -H "Content-Type: application/json" -X POST -d '{{"h": "9", "d": "100", "t": "buy", "p": "6"}}' {gae_url}/analyse"""},
        {"/get_sig_vars9599": f"curl {gae_url}/get_sig_vars9599"},
        {"/get_avg_vars9599": f"curl {gae_url}/get_avg_vars9599"},
        {"/get_sig_profit_loss": f"curl {gae_url}/get_sig_profit_loss"},
        {"/get_tot_profit_loss": f"curl {gae_url}/get_tot_profit_loss"},
        {"/get_chart_url": f"curl {gae_url}/get_chart_url"},
        {"/get_time_cost": f"curl {gae_url}/get_time_cost"},
        {"/get_audit": f"curl {gae_url}/get_audit"},
        {"/reset": f"curl {gae_url}/reset"},
        {"/terminate": f"curl {gae_url}/terminate"},
        {"/scaled_terminated": f"curl {gae_url}/scaled_terminated"}
    ]
    
    return jsonify(endpoints)


@app.route('/analyse', methods=["POST"])
def analyse():
    global avg_var95, avg_var99, var95_results, var99_results, total_time, total_cost

    start_time = datetime.now()  # Start timing

    global d
    # Parsing the request body for parameters
    params = request.get_json()
    t = params.get('t', 'sell').strip().lower()  
    # print(f"Trading Type: {t}")  # Debugging
    p = int(params.get('p', 7))  # profit check days
    h = int(params.get('h', 101))  # history length
    d = int(params.get('d', 100))  # number of data points (shots)
    # service_type = params.get('service_type', 'lambda').strip().lower()  # lambda or ec2

    # Reference: Coursework Document
    # Override yfinance with pandas
    yf.pdr_override()
    # Get stock data from Yahoo Finance – here, asking for about 3 years
    today = date.today()
    timePast = today - timedelta(days=1095)
    data = pdr.get_data_yahoo('AMZN', start=timePast, end=today)

    # Add two columns for Buy and Sell signals, initialized to zero
    data['Buy'] = 0
    data['Sell'] = 0

    # Clear lists at the beginning of each call to ensure a fresh start
    var95_results.clear()
    var99_results.clear()
    profit_loss_results.clear()

    # Find the signals
    for i in range(2, len(data)):
        body = 0.01  # Threshold for identifying significant body size in candlestick

        # Three Soldiers
        if (data['Close'][i] - data['Open'][i]) >= body and \
           data['Close'][i] > data['Close'][i-1] > data['Close'][i-2] and \
           (data['Close'][i-1] - data['Open'][i-1]) >= body and \
           (data['Close'][i-2] - data['Open'][i-2]) >= body:
            data.at[data.index[i], 'Buy'] = 1  # Buy signal
            # print(f"Buy Signal at {i}")

        # Three Crows
        if (data['Open'][i] - data['Close'][i]) >= body and \
           data['Close'][i] < data['Close'][i-1] < data['Close'][i-2] and \
           (data['Open'][i-1] - data['Close'][i-1]) >= body and \
           (data['Open'][i-2] - data['Close'][i-2]) >= body:
            data.at[data.index[i], 'Sell'] = 1  # Sell signal
            # print(f"Sell Signal at {i}")

        # Checking if there is enough data to calculate profit/loss after this day
        if i + p < len(data) and ((t == 'buy' and data['Buy'][i] == 1) or (t == 'sell' and data['Sell'][i] == 1)):
            price_on_signal_day = data['Close'][i]
            price_p_days_later = data['Close'][i + p]
            profit_or_loss = price_p_days_later - price_on_signal_day if t == 'buy' else price_on_signal_day - price_p_days_later
            profit_loss_results.append(profit_or_loss)

    ## DM for full analysis


@app.route('/get_sig_vars9599', methods=["GET"])
def get_sig_vars9599():
    # Access the global lists that hold all the calculated values from /analyse
    global var95_results, var99_results
    return {'var95': var95_results, 'var99': var99_results}


@app.route('/get_avg_vars9599', methods=["GET"])
def get_avg_vars9599():
    global avg_var95, avg_var99
    # Return the stored averages
    return {'var95': avg_var95, 'var99': avg_var99}


@app.route('/get_sig_profit_loss', methods=["GET"])
def get_sig_profit_loss():
    global profit_loss_results
    return {'profit_loss': profit_loss_results}


@app.route('/get_tot_profit_loss', methods=["GET"])
def get_tot_profit_loss():
    global profit_loss_results
    total_profit_loss = sum(profit_loss_results)  # Sum up all the individual profit/loss values
    return {'profit_loss': total_profit_loss}


def generate_chart():
    chart_data = {
        "type": "line",
        "data": {
            "labels": [str(i) for i in range(len(var95_results))],  
            "datasets": [
                {
                    "label": "VaR 95%",
                    "backgroundColor": "rgb(255, 99, 132)",
                    "borderColor": "rgb(255, 99, 132)",
                    "data": var95_results,
                    "fill": False,
                },
                {
                    "label": "VaR 99%",
                    "backgroundColor": "rgb(54, 162, 235)",
                    "borderColor": "rgb(54, 162, 235)",
                    "data": var99_results,
                    "fill": False,
                },
                {
                    "label": "Average VaR 95%",
                    "backgroundColor": "rgb(75, 192, 192)",
                    "borderColor": "rgb(75, 192, 192)",
                    "data": [avg_var95] * len(var95_results),  # Repeat the average value for each label
                    "fill": False,
                },
                {
                    "label": "Average VaR 99%",
                    "backgroundColor": "rgb(153, 102, 255)",
                    "borderColor": "rgb(153, 102, 255)",
                    "data": [avg_var99] * len(var99_results),  # Repeat the average value for each label
                    "fill": False,
                },
            ],
        },
        "options": {
            "title": {
                "display": True,
                "text": "VaR Values Chart",
            },
        },
    }

    chart_data_json = json.dumps(chart_data)
    encoded_chart_data = urllib.parse.quote(chart_data_json)

    base_url = "https://image-charts.com/chart.js/2.8.0"
    chart_url = f"{base_url}?bkg=white&c={encoded_chart_data}"

    return chart_url

@app.route('/get_chart_url', methods=['GET'])
def get_chart_url():
    chart_url = generate_chart()
    return jsonify({'url': chart_url})


@app.route('/get_time_cost', methods=["GET"])
def get_time_cost():
    global total_time, total_cost
    return {'time': total_time, 'cost': total_cost}


@app.route('/get_audit', methods=["GET"])
def get_audit():
    global audit_log
    return jsonify(audit_log)


@app.route('/reset', methods=['GET'])
def reset():
    # Clear all analysis results
    global profit_loss_results, var95_results, var99_results, avg_var95, avg_var99, total_time, total_cost
    profit_loss_results.clear()
    var95_results.clear()
    var99_results.clear()
    avg_var95 = 0
    avg_var99 = 0
    total_time = 0
    total_cost = 0

    return jsonify({'result': 'ok'})


@app.route('/terminate', methods=['GET'])
def terminate():
    threading.Thread(target=send_terminate_request).start()
    return jsonify({'result': 'ok'}), 200


@app.route('/scaled_terminated', methods=['GET'])
def scaled_terminated():
    response = requests.get(scaled_terminated_api_url)
    data = response.json()['body']
    return data


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
