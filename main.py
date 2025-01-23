import os
import json
import io
import pickle
import pandas as pd
import numpy as np

import boto3
from flask import Flask, jsonify, request, send_file
import weaviate
from weaviate.auth import AuthApiKey
from dotenv import load_dotenv
from flask_cors import CORS
from werkzeug.utils import secure_filename  # Import for secure filename handling
import hashlib

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
cors = CORS(app)

access_key = os.getenv("ACCESS_KEY")

weaviate_url = os.getenv("WEAVIATE_URL")
api_key = os.getenv("WEAVIATE_API_KEY")
auth_config = AuthApiKey(api_key=api_key)

client = weaviate.Client(
    url=weaviate_url,
    auth_client_secret=auth_config,
    additional_headers={
        "X-Openai-Api-Key": os.getenv("OPENAI_KEY")
    }
)

# Home route
@app.route('/')
def home():
    """The home route"""
    return "Welcome to the Flask web server!"

# Example API route
@app.route('/api/data', methods=['GET'])
def get_data():
    """A test route."""
    data = {
        "message": "Hello, Flask!",
        "status": "success"
    }
    return jsonify(data)

# /question/get with input
@app.route('/question/get', methods=['GET'])
def get_question_route():
    """Gets questions from the weaviate database and returns to the user."""
    # Validate authorization
    if 'Authorization' not in request.headers:
        return jsonify({"error": "Authorization header missing"}), 401
    if request.headers['Authorization'] != access_key:
        return jsonify({"error": "Invalid access key"}), 403
    
    search_query = request.args.get('query', '')
    limit = int(request.args.get('limit', 2))
    difficulty = int(request.args.get('difficulty', 0))
    className = request.args.get('class', '')
    if className == '':
        return jsonify({
            "message": "A valid class name must be passed."
        }), 400

    query = (
        client.query
        .get(
            className, ["question", "answer", "incorrect_answers", "max_marks", "difficulty"]
        )
        .with_additional(['distance', 'id'])
        .with_near_text({
            "concepts": [search_query]
        })
        .with_limit(limit)
    )

    if difficulty != 0:
        query = query.with_where({
            "path": ["difficulty"],
            "operator": "Equal",
            "valueInt": difficulty
        })

    result = query.do()

    print(result)
    return jsonify({
        "message": "success"
    }), 200


@app.route('/training_checksum', methods=['GET'])
def get_checksum():
    if 'Authorization' not in request.headers or request.headers['Authorization'] != access_key:
        print(request.headers)
        return jsonify({"error": "Access key required"}), 403
    
    with open('hash.txt') as hash_file: checksum = hash_file.read()


    return checksum, 200


@app.route('/test_data', methods=['POST'])
def test_data():
    """Tests data using the current model and returns predictions"""
    if 'Authorization' not in request.headers or request.headers['Authorization'] != access_key:
        return jsonify({"error": "Access key required"}), 403

    try:
        # Get JSON data from request
        data = request.get_json()
        if not data or not isinstance(data, list):
            return jsonify({"error": "Invalid data format. Expected JSON array"}), 400

        # Validate the data structure
        required_fields = ['difficulty', 'marks', 'max_marks']
        if not all(isinstance(entry, dict) and all(field in entry for field in required_fields) 
                  for entry in data):
            return jsonify({"error": "Invalid data format. Each entry must contain: difficulty, marks, max_marks"}), 400

        # Load and use the latest model
        model_path = os.path.join('models', 'difficulty_predictor_model.burlywood')
        if not os.path.exists(model_path):
            return jsonify({"error": "Model not found"}), 404

        with open(model_path, 'rb') as f:
            model_state = pickle.load(f)

        # Prepare features using the same logic as in trainer.py
        df = pd.DataFrame(data)
        df['performance_ratio'] = df['marks'] / df['max_marks']
        df['rolling_performance'] = df['performance_ratio'].rolling(window=3, min_periods=1).mean().fillna(df['performance_ratio'])
        df['performance_trend'] = df['performance_ratio'].rolling(window=3, min_periods=1).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) > 1 else 0
        ).fillna(0)
        
        difficulty_performance = df.groupby('difficulty')['performance_ratio'].mean().to_dict()
        df['avg_difficulty_performance'] = df['difficulty'].map(difficulty_performance)
        
        performance_variance = df['performance_ratio'].std() if len(df) > 1 else 0
        
        features = pd.DataFrame({
            'recent_performance': df['rolling_performance'],
            'performance_trend': df['performance_trend'],
            'avg_difficulty_performance': df['avg_difficulty_performance'].fillna(df['performance_ratio'].mean()),
            'current_difficulty': df['difficulty'],
            'overall_performance': df['performance_ratio'].mean(),
            'performance_variance': performance_variance,
            'max_difficulty_attempted': df['difficulty'].max(),
            'min_performance': df['performance_ratio'].min(),
            'max_performance': df['performance_ratio'].max()
        })
        
        features = features.fillna(0)
        
        # Make prediction using the model
        features_scaled = model_state['scaler'].transform(features.iloc[[-1]])
        prediction = model_state['model'].predict(features_scaled)[0]
        prediction = round(np.clip(prediction, 1, 5), 2)

        return jsonify({
            "prediction": prediction,
            "model_timestamp": model_state.get('timestamp', 'unknown')
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/training_data', methods=['POST', 'GET'])
def post_training_data():
    if 'Authorization' not in request.headers or request.headers['Authorization'] != access_key:
        print(request.headers)
        return jsonify({"error": "Access key required"}), 403
    
    if request.method == 'POST':
        """Uploads a .burlywood file to Digital Ocean S3 bucket and stores locally"""
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
            
        file = request.files['file']
        print(file.filename)
        if not file.filename.endswith('.burlywood'):
            return jsonify({"error": "Invalid file type. Must be .burlywood"}), 400

        try:
            # Calculate checksum
            file_content = file.read()
            checksum = hashlib.sha256(file_content).hexdigest()
            
            # Write checksum to hash.txt, overwriting previous content
            with open('hash.txt', 'w') as hash_file:
                hash_file.write(checksum)
            
            # Reset file pointer to beginning for upload
            file.seek(0)
            
            # Save file locally
            local_filename = secure_filename(file.filename)
            local_path = os.path.join('models', local_filename)
            os.makedirs('models', exist_ok=True)  # Create models directory if it doesn't exist
            file.save(local_path)
            
            # Reset file pointer again for S3 upload
            file.seek(0)
            
            # Upload file to DO Spaces
            s3_client = boto3.client('s3',
                endpoint_url='https://lon1.digitaloceanspaces.com', 
                aws_access_key_id=os.getenv('DO_ACCESS_KEY'),
                aws_secret_access_key=os.getenv('DO_SECRET_KEY')
            )

            bucket_name = os.getenv('DO_BUCKET_NAME')
            file_name = secure_filename(file.filename)
            
            s3_client.upload_fileobj(
                file,
                bucket_name,
                file_name,
                ExtraArgs={'ACL': 'private'}
            )

            return jsonify({
                "message": "File uploaded successfully",
                "filename": file_name,
                "checksum": checksum,
            }), 200

        except Exception as e:
            print(e)
            return jsonify({"error": str(e)}), 500

    elif request.method == 'GET':
        try:
            s3_client = boto3.client('s3',
                endpoint_url='https://lon1.digitaloceanspaces.com',
                aws_access_key_id=os.getenv('DO_ACCESS_KEY'),
                aws_secret_access_key=os.getenv('DO_SECRET_KEY')
            )

            bucket_name = os.getenv('DO_BUCKET_NAME')
            file_name = request.args.get('filename')
            
            if not file_name:
                return jsonify({"error": "Filename parameter required"}), 400

            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=file_name
            )
            
            file_content = response['Body'].read()
            return send_file(
                io.BytesIO(file_content),
                mimetype='application/octet-stream',
                as_attachment=True,
                download_name=file_name
            )

        except Exception as e:
            return jsonify({"error": str(e)}), 500


if __name__ == '__main__' and client.is_ready():
    print("Weaviate Connected. Running FLASK")
    app.run(host='0.0.0.0', port=5003, debug=True)