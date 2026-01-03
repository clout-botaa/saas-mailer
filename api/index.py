from flask import Flask, request, jsonify
from supabase import create_client, Client
import os

app = Flask(__name__)

# ENV VARS (Add these in Vercel Settings later)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("WARNING: Supabase credentials missing")

# --- AUTH ROUTES ---

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        # Insert new user into DB
        res = supabase.table('users').insert({
            "email": data['email'],
            "password": data['password'], # In production, hash this!
            "gmail_user": data['gmail_user'],
            "gmail_pass": data['gmail_pass'],
            "daily_limit": 500,
            "used_today": 0
        }).execute()
        return jsonify({"status": "success", "user": res.data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        # Find user
        res = supabase.table('users').select("*").eq('email', data['email']).eq('password', data['password']).execute()
        
        if len(res.data) > 0:
            return jsonify({"status": "success", "user": res.data[0]})
        else:
            return jsonify({"status": "error", "message": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# ... (Include your previous Upload/Queue routes here)
import pdfplumber
import json
from datetime import datetime

# --- CAMPAIGN & QUEUE ROUTES ---

@app.route('/api/upload-and-queue', methods=['POST'])
def upload_queue():
    try:
        user_id = request.form.get('user_id')
        subject = request.form.get('subject')
        body = request.form.get('body')
        
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No PDF file provided"}), 400
            
        file = request.files['file']
        # Vercel only allows writing to /tmp
        file_path = f"/tmp/{file.filename}"
        file.save(file_path)

        # 1. Extract Data from PDF
        contacts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    for row in table:
                        r = [str(cell).strip() if cell else "" for cell in row]
                        # Validate email presence in column 3
                        if len(r) >= 5 and "@" in r[2]:
                            contacts.append({
                                "user_id": user_id,
                                "recipient_email": r[2],
                                "recipient_data": {
                                    "name": r[1],
                                    "title": r[3],
                                    "company": r[4]
                                },
                                "template_subject": subject,
                                "template_body": body,
                                "status": "pending"
                            })

        if not contacts:
            return jsonify({"status": "error", "message": "No valid contacts found in PDF"}), 400

        # 2. Bulk Insert into Supabase Queue
        # We process in chunks of 100 to avoid request size limits
        for i in range(0, len(contacts), 100):
            chunk = contacts[i:i + 100]
            supabase.table('email_queue').insert(chunk).execute()

        return jsonify({
            "status": "success", 
            "message": f"Successfully queued {len(contacts)} emails. Our background worker will start sending them shortly."
        })

    except Exception as e:
        print(f"Queue Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/user-stats/<user_id>', methods=['GET'])
def get_stats(user_id):
    try:
        # Get User Limit Info
        user = supabase.table('users').select("used_today, daily_limit").eq('id', user_id).execute().data[0]
        
        # Get Queue Info
        pending = supabase.table('email_queue').select("id", count='exact').eq('user_id', user_id).eq('status', 'pending').execute().count
        sent = supabase.table('email_queue').select("id", count='exact').eq('user_id', user_id).eq('status', 'sent').execute().count
        failed = supabase.table('email_queue').select("id", count='exact').eq('user_id', user_id).eq('status', 'failed').execute().count
        
        return jsonify({
            "used_today": user['used_today'],
            "daily_limit": user['daily_limit'],
            "pending": pending,
            "sent": sent,
            "failed": failed
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    @app.route('/api/hooks/<hook_id>', methods=['POST'])
def handle_webhook(hook_id):
    # 1. Get the Hook Configuration
    hook = supabase.table('webhooks').select("*, users(*)").eq('id', hook_id).execute().data[0]
    user = hook['users']
    config = hook['action_config']
    
    # 2. Extract incoming data (e.g., from a form or another app)
    incoming_data = request.json
    
    # 3. Perform Action
    if config['type'] == 'email':
        # Send instant email using user's Gmail creds
        # (Reuse your direct send logic here)
        return jsonify({"status": "success", "action": "email_sent"})
        
    return jsonify({"status": "hook_received"})