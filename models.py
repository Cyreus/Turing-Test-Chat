from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class HumanMessages(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50))
    message = db.Column(db.Text)
    is_structured = db.Column(db.Boolean)
    contains_personal_comments = db.Column(db.Boolean)
    message_length = db.Column(db.Integer)


class AIMessages(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50))
    message = db.Column(db.Text)
    is_structured = db.Column(db.Boolean)
    contains_personal_comments = db.Column(db.Boolean)
    message_length = db.Column(db.Integer)
