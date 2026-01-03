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