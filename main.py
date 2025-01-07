from flask import Flask, jsonify, request
import weaviate
from weaviate.auth import AuthApiKey
from dotenv import load_dotenv
import os
import json
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
    return "Welcome to the Flask web server!"

# Example API route
@app.route('/api/data', methods=['GET'])
def get_data():
    data = {
        "message": "Hello, Flask!",
        "status": "success"
    }
    return jsonify(data)

# /question/get with input
@app.route('/question/get', methods=['GET'])
def getQuestionRoute():
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
""" @app.route('/question/store', methods=['POST'])
def storeQuestionRoute():
    # Parse JSON payload from the request
    data = request.get_json()

    # Validate required fields
    required_fields = ["question", "answer", "incorrect_answers", "topic", "marks", "class"]
    missing_fields = [field for field in required_fields if field not in data or not data[field]]

    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    # Extract data
    question = data["question"].strip()
    answer = data["answer"].strip()
    incorrect_answers = data["incorrect_answers"]
    topic = data["topic"].strip()
    marks = data["marks"]
    className = data["class"].strip()

    # Ensure incorrect_answers is a list
    if not isinstance(incorrect_answers, list):
        return jsonify({"error": "incorrect_answers must be a list"}), 400

    # Debugging output
    print({
        "question": question,
        "answer": answer,
        "incorrect_answers": incorrect_answers,
        "topic": topic,
        "marks": marks,
        "class": className
    })

    uuid = client.data_object.create(
        class_name=className,
        data_object={
            "question": question,
            "answer": answer,
            "incorrect_answers": incorrect_answers,
            "topic": topic,
            "marks": marks,
        },
    )

    # Simulate storing data (add actual database/Weaviate code here)
    return jsonify({"message": "Question stored successfully", uuid: uuid}), 201 """

if __name__ == '__main__' and client.is_ready():
    print("Weaviate Connected. Running FLASK")
    app.run(host='0.0.0.0', port=5003, debug=True)