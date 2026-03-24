from flask import Blueprint, jsonify

api = Blueprint('api', __name__)

@api.route('/status')
def status():
    return jsonify({
        "status": "online",
        "platform": "Afrigen",
        "tagline": "African Creates, AI Generates"
    })
