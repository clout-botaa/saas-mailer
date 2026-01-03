from flask import Flask, jsonify
from supabase import create_client
import smtplib
from email.mime.text import MIMEText
import os
import datetime

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/api/cron-processor')
def cron_job():
    """
    Runs every 10 minutes or 1 hour via Vercel Cron.
    1. Gets all users.
    2. Checks their remaining limit for today.
    3. Fetches 'pending' emails from their queue.
    4. Sends as many as possible.
    """
    users = supabase.table('users').select("*").execute().data
    
    report_logs = []

    for user in users:
        # 1. Check Limit
        limit = user['daily_limit']
        used = user['used_today']
        
        # Reset if new day
        last_reset = datetime.datetime.fromisoformat(user['last_reset'])
        if (datetime.datetime.now() - last_reset).days >= 1:
            used = 0
            supabase.table('users').update({'used_today': 0, 'last_reset': datetime.datetime.now().isoformat()}).eq('id', user['id']).execute()
            # Send "Start of Day" Report Email to User here
        
        remaining = limit - used
        if remaining <= 0:
            continue # Skip user, limit reached
            
        # 2. Fetch Pending Queue
        # Only fetch what we can send today (e.g., remaining limit)
        queue = supabase.table('email_queue').select("*").eq('user_id', user['id']).eq('status', 'pending').limit(remaining).execute().data
        
        if not queue:
            continue

        # 3. Connect to Gmail
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(user['gmail_user'], user['gmail_pass'])
            
            sent_count = 0
            for job in queue:
                # Personalize
                data = job['recipient_data']
                subj = job['template_subject'].replace("{{NAME}}", data['name'])
                body = job['template_body'].replace("{{NAME}}", data['name']) # Add other replacements
                
                # Send
                msg = MIMEText(body, 'html')
                msg['Subject'] = subj
                msg['From'] = user['gmail_user']
                msg['To'] = job['recipient_email']
                
                server.send_message(msg)
                
                # Update DB
                supabase.table('email_queue').update({'status': 'sent', 'scheduled_for': datetime.datetime.now().isoformat()}).eq('id', job['id']).execute()
                sent_count += 1
            
            server.quit()
            
            # 4. Update User Usage
            new_usage = used + sent_count
            supabase.table('users').update({'used_today': new_usage}).eq('id', user['id']).execute()
            
            # 5. Check if we stopped early (Report Logic)
            if new_usage >= limit:
                # Send "Limit Reached" Report to User
                pass
                
        except Exception as e:
            print(f"Error for user {user['email']}: {e}")

    return jsonify({"status": "cron_finished"})