"""
A Bit MessY but it is the easiest way to do it
Meta Graph API requires alot of verification from what i read in the documentation.
I found this in JS version.
"""

import logging
import os
import json
import re
from threading import Thread
import time
from langchain_ollama import ChatOllama
import hashlib
from langchain.memory import ConversationBufferWindowMemory
import hmac
import requests
import logging
import tempfile
from pathlib import Path
from functools import wraps
from pyngrok import ngrok
from typing import Dict, Any
from langchain.tools import tool
from flask import Flask, request, jsonify, current_app
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_ollama import ChatOllama
from try3 import upload_and_search
from tools.agents import AGENTS, get_all_agents
from tools.meeting import book_meeting, book_meeting_with_agent, cancel_meeting, check_availability, list_bookings
from tools.email import send_email
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# ----------------- AGENT SETUP START -----------------


IMGBB_API_KEY = os.environ.get['IMGBB_API_KEY']
SEARCHAPI_KEY = os.environ.get['SEARCHAPI_KEY']
app = Flask(__name__)
ngrok.set_auth_token(os.environ.get['NGROK_AUTH'])

# Configure meta graph auth easy with these u can find then in ur Meta Developer Account
app.config['VERIFY_TOKEN'] = os.environ.get['VERIFY_TOKEN']
app.config['APP_SECRET'] = os.environ.get['APP_SECRET']
app.config['ACCESS_TOKEN'] = os.environ.get['ACCESS_TOKEN']
app.config['PHONE_NUMBER_ID'] = os.environ.get['PHONE_NUMBER_ID']
llm = ChatOllama(model='MrScarySpaceCat/gemma3-tools:4b', temperature=0.6, base_url= os.environ.get['BASE_URL'])

agent_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Mary, a friendly car expert and a master negotiator at SELL MY CAR QUICK. 

     TOOL USAGE RULES:
     1. If a tool requires missing information:
        - Use tools when ever they are needed
        - Politely ask ONE question at a time to get the needed detail
        - Never list multiple questions at once
        - Maintain natural conversation flow
     
     2. For image handling:
        - If customers send images, silently analyze for make/model patterns
        - Casually reference: "That [Make] [Model] looks great! Could I get..."
        - Never mention image analysis
     
     3. For sales progression:
        - When users want to proceed, collect:
          • Preferred date/time 
          • Contact details (email/phone)
          • Any special requirements
        - Then notify physical agents via email using this tools
     
     Always include natural follow-up questions about:
       • Mileage • Service history • Special features
       • Reason for selling • Any accidents 

     
     Company info (only share when asked):
     📍 61A Rooiberg St, The willows 340-Jr, Silver lakes Golf Estate, Pretoria  
     📞 012 760 3900  
     💌 info@sellmycarquick.co.za"""),
    MessagesPlaceholder("chat_history"),
    ("user", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])



def start_ngrok():
    time.sleep(2)
    try:
        public_url = ngrok.connect(5000).public_url
        print(f"\nNgrok Public URL: {public_url}\n")
    except Exception as e:
        print(f"Ngrok failed to start: {str(e)}")
# Utility Functions
def validate_signature(payload, signature):
    expected_signature = hmac.new(
        bytes(current_app.config["APP_SECRET"], "latin-1"),
        msg=payload.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

def signature_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        signature = request.headers.get("X-Hub-Signature-256", "")[7:]
        if not validate_signature(request.data.decode("utf-8"), signature):
            logging.info("Signature verification failed!")
            return jsonify({"status": "error", "message": "Invalid signature"}), 403
        return f(*args, **kwargs)
    return decorated_function

def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")

def get_text_message_input(recipient, text):
    return json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    })


def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    url = f"https://graph.facebook.com/v22.0/{current_app.config['PHONE_NUMBER_ID']}/messages"
    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.Timeout:
        logging.error("Timeout occurred while sending message (prolly netwo)")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except requests.RequestException as e:
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        log_http_response(response)
        return response
def download_whatsapp_media(media_id):
    """Download media send to u on whasapp"""
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}"
    }
    
    try:

        meta_url = f"https://graph.facebook.com/v22.0/{media_id}"
        meta_response = requests.get(meta_url, headers=headers)
        meta_response.raise_for_status()
        media_info = meta_response.json()
        
        app.logger.debug("Media Metadata: %s", json.dumps(media_info, indent=2))
        
        if 'url' not in media_info:
            raise ValueError("Missing media URL in WhatsApp API response")

        media_url = media_info['url']
        download_response = requests.get(media_url, headers=headers)
        download_response.raise_for_status()
        
        # Determine file extension from MIME type
        mime_type = media_info.get('mime_type', 'image/jpeg')
        extension = {
            'image/jpeg': '.jpg',
            'image/png': '.png'
        }.get(mime_type, '.jpg')  # default to jpg or jpeg, but it doesn't matter REALLY
        
        # Save to local file for FOR FURTHER HANDLING
        file = f"debug_{media_id}{extension}"
        with open(file, 'wb') as f:
            f.write(download_response.content)
        
        app.logger.info("Saved downloaded media to: %s", file)
        
        return {
            'content': download_response.content,
            'mime_type': mime_type,
            'sha256': media_info.get('sha256', ''),
            'file_size': media_info.get('file_size', len(download_response.content)),
            'local_path': file
        }
        
    except requests.exceptions.RequestException as e:
        app.logger.error("Media download fail: %s", str(e))
        raise ValueError(f"Failed to download media: {str(e)}")

############################################
@tool
def list_agents() -> str:
    """List all available car evaluation agents"""
    return "\n".join(
        f"{agent.name}\n"
        f"Contact: {agent.email} | WhatsApp: {agent.whatsapp}\n"
        for agent in AGENTS
    )
#########################
################ AGENT TOOLS FOR USE  ###########

tools = [send_email, book_meeting, list_agents,  book_meeting_with_agent, cancel_meeting, check_availability, list_bookings]

memory = ConversationBufferWindowMemory(memory_key="chat_history", k=10, return_messages=True)
agent = create_tool_calling_agent(llm, tools, agent_prompt)  ## tools
# Create agent

agent_executor = AgentExecutor(agent=agent, tools=tools, memory=memory, verbose=True, return_intermediate_steps=False)
##########################
#######################
def process_whatsapp_message(body):
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        wa_id = entry["contacts"][0]["wa_id"]
        message = entry["messages"][0]
        
        # Handle imgs messages
        if message["type"] == "image":
            media_id = message["image"]["id"]
            caption = message["image"].get("caption", "")
            
            # Get context from your vision system
            media_info = download_whatsapp_media(media_id)
            car_context = upload_and_search(media_info['local_path'])  # Returns "Kia Rio 2018"
            
            response = agent_executor.invoke({
                "input": f"User shared {'a car image' + (' with caption: '+caption if caption else '')}. Context: {car_context}"
            })
            
            send_message(get_text_message_input(wa_id, response["output"]))
            return
        
        # Existing text message handling
        elif message["type"] == "text":
            message_body = message.get("text", {}).get("body", "")
            response = agent_executor.invoke({"input": message_body})
            response_text = response["output"]
            #response_text = 'you said' + message_body
            data = get_text_message_input(wa_id, response_text)
            send_message(data)
                
            return
        
        else:
            logging.error("Unsupported message type: %s", message["type"])
            
    except Exception as e:
        logging.error("Error processing message: %s", str(e))
        data = get_text_message_input(wa_id, "Error processing your request. Please try again.")
        send_message(data)

def is_valid_whatsapp_message(body):
    return (
        body.get("object") and
        body.get("entry") and
        body["entry"][0].get("changes") and
        body["entry"][0]["changes"][0].get("value") and
        body["entry"][0]["changes"][0]["value"].get("messages") and
        body["entry"][0]["changes"][0]["value"]["messages"][0]
    )

# Webhook Verification
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode and token:
        if mode == "subscribe" and token == current_app.config["VERIFY_TOKEN"]:
            logging.info("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            logging.info("VERIFICATION_FAILED")
            return jsonify({"status": "error", "message": "Verification failed"}), 403
    else:
        logging.info("MISSING_PARAMETER")
        return jsonify({"status": "error", "message": "Missing parameters"}), 400

# Handle Incoming Messag
@app.route("/webhook", methods=["POST"])
@signature_required
def handle_message():
    body = request.get_json()
    app.logger.debug('Received JSON: %s', body)
    if 'statuses' in body.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}):
        app.logger.info("Received a WhatsApp status update.")
        return jsonify({"status": "ok"}), 200
    try:
        if is_valid_whatsapp_message(body):
            process_whatsapp_message(body)
            return jsonify({"status": "ok"}), 200
        else:
            app.logger.error("Invalid WhatsApp message format")
            return jsonify({"status": "error", "message": "Not a WhatsApp API event"}), 404
    except Exception as e:
        app.logger.error("Error processing request: %s", e)
        return jsonify({"status": "error", "message": "Server error"}), 500

if __name__ == "__main__":
    Thread(target=start_ngrok).start()
    app.run(debug=True, port=5000, use_reloader=False)
