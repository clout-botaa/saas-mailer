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

if __name__ == "__main__":
    app.run()