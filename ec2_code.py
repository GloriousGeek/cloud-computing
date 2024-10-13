# To run aws ec2 

# app.py
from flask import Flask, request, jsonify
import random
import boto3

app = Flask(__name__)

@app.route('/run_analysis', methods=["POST"])
def run_analysis():
    event = request.get_json()
    mean = float(event['mean'])
    std = float(event['std'])
    shots = int(event['shots'])

    # Simulate risk calculation
    simulated = [random.gauss(mean, std) for x in range(shots)]
    simulated.sort(reverse=True)
    var95 = simulated[int(len(simulated) * 0.95)]
    var99 = simulated[int(len(simulated) * 0.99)]
    results = {'var95': var95, 'var99': var99}
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

