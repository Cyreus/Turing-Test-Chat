import random
import time
from flask import Flask, render_template
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


def call_openai_api(msg):
    with app.app_context():
        time.sleep(10)
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

            socketio.emit('message', {"user": "Tester", "text": gpt_response})

            analysis_result = analyze_message("AI", gpt_response, is_human=False)
            log_analysis_to_csv(analysis_result)

        except Exception as e:
            print(f"OpenAI API error: {e}")
            socketio.emit('message',
                          {"user": "Tester", "text": "Sorry, I couldn't process your request at the moment."})


@socketio.on('message')
def handle_message(msg):
    print(f"Message from {msg['user']}: {msg['text']}")
    socketio.emit('message', msg)

    if msg['user'] == 'Tester':
        analysis_result = analyze_message(msg['user'], msg['text'], is_human=True)
        log_analysis_to_csv(analysis_result)
    else:
        if random.random() < 0.5:
            api_thread = threading.Thread(target=call_openai_api, args=(msg,))
            api_thread.daemon = True
            api_thread.start()


if __name__ == '__main__':
    socketio.run(app, debug=True, use_reloader=True, log_output=True)
