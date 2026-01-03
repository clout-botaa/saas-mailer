from flask import Flask, request, jsonify
from supabase import create_client, Client
import pdfplumber
import os
import json
import re

app = Flask(__name__)

# Initialize Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- AUTH ROUTES ---
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        res = supabase.table('users').insert({
            "email": data['email'],
            "password": data['password'],
            "gmail_user": data['gmail_user'],
            "gmail_pass": data['gmail_pass']
        }).execute()
        return jsonify({"status": "success", "user": res.data[0]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        res = supabase.table('users').select("*").eq('email', data['email']).eq('password', data['password']).execute()
        if res.data:
            return jsonify({"status": "success", "user": res.data[0]})
        return jsonify({"status": "error", "message": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# --- DASHBOARD & QUEUE ---
@app.route('/api/user-stats/<user_id>', methods=['GET'])
def get_stats(user_id):
    user = supabase.table('users').select("used_today, daily_limit").eq('id', user_id).execute().data[0]
    pending = supabase.table('email_queue').select("id", count='exact').eq('user_id', user_id).eq('status', 'pending').execute().count
    sent = supabase.table('email_queue').select("id", count='exact').eq('user_id', user_id).eq('status', 'sent').execute().count
    return jsonify({**user, "pending": pending, "sent": sent})

@app.route('/api/upload-and-queue', methods=['POST'])
def upload_queue():
    user_id = request.form.get('user_id')
    file = request.files['file']
    file_path = f"/tmp/{file.filename}"
    file.save(file_path)

    contacts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table:
                    r = [str(cell).strip() if cell else "" for cell in row]
                    if len(r) >= 5 and "@" in r[2]:
                        contacts.append({
                            "user_id": user_id,
                            "recipient_email": r[2],
                            "recipient_data": {"name": r[1], "title": r[3], "company": r[4]},
                            "template_subject": request.form.get('subject'),
                            "template_body": request.form.get('body')
                        })

    # Bulk Insert in chunks of 100
    for i in range(0, len(contacts), 100):
        supabase.table('email_queue').insert(contacts[i:i+100]).execute()

    return jsonify({"status": "success", "message": f"Queued {len(contacts)} emails."})

@app.route('/api/create-hook', methods=['POST'])
def create_hook():
    try:
        data = request.json
        # Create a new webhook record
        res = supabase.table('webhooks').insert({
            "user_id": data['user_id'],
            "name": data['name'],
            "action_config": {"type": "email", "subject": "New lead", "body": "Details: {{data}}"}
        }).execute()
        
        hook_id = res.data[0]['id']
        # The URL points back to our internal hook handler
        webhook_url = f"{request.host_url}api/hooks/{hook_id}"
        return jsonify({"status": "success", "webhook_url": webhook_url})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/hooks/<hook_id>', methods=['POST'])
def run_hook_automation(hook_id):
    try:
        # 1. Get Automation Config
        res = supabase.table('webhooks').select("*, users(*)").eq('id', hook_id).execute()
        if not res.data: return jsonify({"error": "Not found"}), 404
        
        hook = res.data[0]
        user = hook['users']
        incoming_data = request.json # Data sent to the webhook

        # 2. Simple Mapping (Replaces {{key}} with values from incoming JSON)
        subject = hook['action_config'].get('subject', '')
        body = hook['action_config'].get('body', '')
        
        for key, value in incoming_data.items():
            subject = subject.replace(f"{{{{{key}}}}}", str(value))
            body = body.replace(f"{{{{{key}}}}}", str(value))

        # 3. Send Immediate Email (Edge Style)
        # We reuse the SMTP logic here for an instant notification
        # ... SMTP Code ...
        
        return jsonify({"status": "success", "message": "Automation triggered"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500