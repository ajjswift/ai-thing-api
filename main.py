import os
import json
import io

import boto3
from flask import Flask, jsonify, request, send_file
import weaviate
from weaviate.auth import AuthApiKey
from dotenv import load_dotenv
from flask_cors import CORS
from werkzeug.utils import secure_filename  # Import for secure filename handling


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
    # Get the search query from the request
    search_query = request.args.get('search', '').strip()
    limit = request.args.get('limit', '').strip()


    if 'Authorization' not in request.headers or request.headers['Authorization'] != access_key:
        return jsonify({"error": "Access key required"}), 403

    if not limit:
        limit = 2
    else:
        limit = int(limit)

    if not search_query:
        return jsonify({"error": "Search query is required"}), 400

    # Perform Weaviate query
    try:
        response = (
            client.query
            .get("Mathematics", ["question", "answer", "incorrect_answers", "marks"])
            .with_near_text({"concepts": [search_query]})
            .with_limit(limit)
            .with_additional(["distance", "id"])
            .do()
        )
        results = response.get('data', {}).get('Get', {}).get('Mathematics', [])
        if not results:
            return jsonify({"message": "No results found"}), 404

        return jsonify(results)
    except Exception as e:# pylint: disable=broad-exception-caught
        return jsonify({"error": str(e)}), 500 
    
@app.route('/training_data', methods=['POST', 'GET'])
def post_training_data():
    if 'Authorization' not in request.headers or request.headers['Authorization'] != access_key:
        print(request.headers)
        return jsonify({"error": "Access key required"}), 403
    
    if request.method == 'POST':
        """Uploads a .burlywood file to Digital Ocean S3 bucket"""
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
            
        file = request.files['file']
        print(file.filename)
        if not file.filename.endswith('.burlywood'):
            return jsonify({"error": "Invalid file type. Must be .burlywood"}), 400

        try:
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
                "filename": file_name
            }), 200

        except Exception as e:
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