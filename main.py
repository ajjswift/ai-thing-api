import os
import json

from flask import Flask, jsonify, request
import weaviate
from weaviate.auth import AuthApiKey
from dotenv import load_dotenv
from flask_cors import CORS

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
    limit = int(request.args.get('limit', '').strip())
    
    print(request.headers)
    passed_access_key = request.headers['Authorization']

    if access_key != passed_access_key:
        return jsonify({"error": "Access key required"}), 403

    if not limit:
        limit = 2

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


if __name__ == '__main__' and client.is_ready():
    print("Weaviate Connected. Running FLASK")
    app.run(host='0.0.0.0', port=5003, debug=True)