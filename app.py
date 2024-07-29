import random
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from dotenv import load_dotenv
import os
import csv
from collections import defaultdict
import threading
from openai import OpenAI
from configuration import dev
from models import db, HumanMessages, AIMessages
from flask_migrate import Migrate

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
socketio = SocketIO(app)

app.config['SQLALCHEMY_DATABASE_URI'] = dev.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

message_data = defaultdict(list)

csv_headers = ['user', 'message', 'is_structured', 'contains_personal_comments', 'message_length', 'response_type']

client = OpenAI(api_key="your_key")

with open('chat_analysis.csv', 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=csv_headers)
    writer.writeheader()


def analyze_message(user, message, is_human):
    def search(doc):
        if "," in doc:
            return True
        else:
            return False

    is_structured = message.endswith('.') or message.endswith('?') or search(message)
    contains_personal_comments = 'I' in message or 'my' in message or 'me' in message or 'ben' in message or 'sen' in message
    message_length = len(message)
    response_type = 'Human' if is_human else 'AI'

    analysis_result = {
        'user': user,
        'message': message,
        'is_structured': is_structured,
        'contains_personal_comments': contains_personal_comments,
        'message_length': message_length,
        'response_type': response_type
    }

    return analysis_result


def log_analysis_to_csv(analysis_result):
    with open('chat_analysis.csv', 'a', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_headers)
        writer.writerow(analysis_result)

    if analysis_result['response_type'] == 'Human':
        message = HumanMessages(
            user=analysis_result['user'],
            message=analysis_result['message'],
            is_structured=analysis_result['is_structured'],
            contains_personal_comments=analysis_result['contains_personal_comments'],
            message_length=analysis_result['message_length']
        )
    else:
        message = AIMessages(
            user=analysis_result['user'],
            message=analysis_result['message'],
            is_structured=analysis_result['is_structured'],
            contains_personal_comments=analysis_result['contains_personal_comments'],
            message_length=analysis_result['message_length']
        )

    db.session.add(message)
    db.session.commit()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/another')
def another():
    return render_template('another.html')


@app.route('/log_result', methods=['POST'])
def log_result():
    data = request.json
    user = data['user']
    text = data['text']
    result = data['result']
    correct_answers = data['correctAnswers']
    incorrect_answers = data['incorrectAnswers']

    # Calculate the ratio of correct to incorrect answers
    if incorrect_answers == 0:
        ratio = 'Infinity'  # Avoid division by zero
    else:
        ratio = correct_answers / incorrect_answers

    # Write to CSV
    with open('results.csv', 'a', newline='') as csvfile:
        fieldnames = ['user', 'text', 'result', 'correctAnswers', 'incorrectAnswers', 'ratio']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write the header if the file is new
        if csvfile.tell() == 0:
            writer.writeheader()

        writer.writerow({
            'user': user,
            'text': text,
            'result': result,
            'correctAnswers': correct_answers,
            'incorrectAnswers': incorrect_answers,
            'ratio': ratio
        })

    return jsonify(success=True)

def call_openai_api(msg):
    with app.app_context():
        time.sleep(1.5)
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "user",
                        "content": msg['text'],
                    },
                ],
            )
            gpt_response = response.choices[0].message.content

            # Emit message with AI identifier
            socketio.emit('message', {"user": "Tester", "text": gpt_response, "is_ai": True})

            analysis_result = analyze_message("AI", gpt_response, is_human=False)
            log_analysis_to_csv(analysis_result)

        except Exception as e:
            print(f"OpenAI API error: {e}")
            socketio.emit('message',
                          {"user": "Tester", "text": "Sorry, I couldn't process your request at the moment.",
                           "is_ai": True})

@app.route('/check_message', methods=['POST'])
def check_message():
    data = request.json
    user = data['user']
    text = data['text']
    guess = data['guess']
    is_ai = user == "AI"
    correct = (guess == 'yes' and is_ai) or (guess == 'no' and not is_ai)
    result = "Correct!" if correct else "Incorrect!"
    return jsonify(result=result)

@socketio.on('message')
def handle_message(msg):
    print(f"Message from {msg['user']}: {msg['text']}")
    socketio.emit('message', msg)

    if msg['user'] == 'Tester':
        analysis_result = analyze_message(msg['user'], msg['text'], is_human=True)
        log_analysis_to_csv(analysis_result)
    else:
        if random.random() < 0.80:
            api_thread = threading.Thread(target=call_openai_api, args=(msg,))
            api_thread.daemon = True
            api_thread.start()


if __name__ == '__main__':
    socketio.run(app, debug=True, use_reloader=True, log_output=True,allow_unsafe_werkzeug=True)
