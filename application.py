import json
import logging
import os

import boto3
import flask
from flask import Response, request

from flask import Flask, request, session, render_template
from twilio.twiml.messaging_response import MessagingResponse
from chatbot import ask, append_interaction_to_chat_log
from datetime import datetime

# Based on https://github.com/aws-samples/eb-py-flask-signup

# Default config vals
THEME = "default" if os.environ.get("THEME") is None else os.environ.get("THEME")
FLASK_DEBUG = (
    "false" if os.environ.get("FLASK_DEBUG") is None else os.environ.get("FLASK_DEBUG")
)

# Create the Flask app
application = flask.Flask(__name__)

# Load config values specified above
application.config.from_object("default_config")

# Load configuration vals from a file
application.config.from_envvar("APP_CONFIG", silent=True)

# Only enable Flask debugging if an env var is set to true
application.debug = application.config["FLASK_DEBUG"] in ["true", "True"]

# Region
region = application.config["AWS_REGION"]

# Init DynamoDB client
dynamodb = boto3.resource("dynamodb", region_name=region)

# Init SNS client
sns_client = boto3.client("sns", region_name=region)


@application.route("/")
def welcome():
    theme = application.config["THEME"]
    return flask.render_template(
        "index.html", theme=theme, flask_debug=application.debug
    )

@application.route('/bot', methods=['POST'])
def bot():
    incoming_msg = request.values['Body']
    chat_log = session.get('chat_log')

    answer = ask(incoming_msg, chat_log)
    session['chat_log'] = append_interaction_to_chat_log(incoming_msg, answer,
                                                         chat_log)

    r = MessagingResponse()
    r.message(answer)
    return str(r)

@application.route("/signup", methods=["POST"])
def signup():
    signup_data = dict()
    for item in request.form:
        signup_data[item] = request.form[item]

    try:
        store_in_dynamo(signup_data)
        publish_to_sns(signup_data)
    except Exception as ex:
        logging.error(f"Sign up failed with error: {str(ex)}")
        return Response("", status=409, mimetype="application/json")

    return Response(json.dumps(signup_data), status=201, mimetype="application/json")


def store_in_dynamo(signup_data):
    table = dynamodb.Table(application.config["STARTUP_SIGNUP_TABLE"])
    table.put_item(Item=signup_data)


def publish_to_sns(signup_data):
    sns_client.publish(
        TopicArn=application.config["NEW_SIGNUP_TOPIC"],
        Message="New signup: %s" % signup_data["email"],
    )


if __name__ == "__main__":
    application.run(host="0.0.0.0")
