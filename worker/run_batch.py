import os
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client

# Load environment variables (From GitHub Secrets)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def run_batch():
    print("--- STARTING BATCH PROCESSOR ---")
    
    # 1. Get all users
    users = supabase.table('users').select("*").execute().data
    
    for user in users:
        print(f"Checking user: {user['email']}")
        
        # 2. Reset Limit if 24 hours passed
        # (Simplified logic: If it's a new calendar day in UTC, reset)
        # For robustness, we check the last_reset timestamp in DB
        # ... (You can add precise time logic here)
        
        # 3. Check Remaining Limit
        limit = user['daily_limit']
        used = user['used_today']
        remaining = limit - used
        
        if remaining <= 0:
            print(f"  -> Limit reached ({used}/{limit}). Skipping.")
            continue
            
        print(f"  -> Limit remaining: {remaining}")
        
        # 4. Fetch Pending Queue for this User
        # Only fetch what we can send right now
        queue = supabase.table('email_queue').select("*")\
            .eq('user_id', user['id'])\
            .eq('status', 'pending')\
            .limit(remaining)\
            .execute().data
            
        if not queue:
            print("  -> No pending emails.")
            continue
            
        print(f"  -> Found {len(queue)} emails to send.")
        
        # 5. Connect to Gmail
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(user['gmail_user'], user['gmail_pass'])
            
            sent_count = 0
            for job in queue:
                try:
                    # Parse Data
                    data = job['recipient_data']
                    
                    # Replacements
                    subj = job['template_subject']
                    body = job['template_body']
                    for k, v in data.items():
                        if v:
                            subj = subj.replace(f"{{{{{k.upper()}}}}}", v).replace(f"{{{{{k}}}}}", v)
                            body = body.replace(f"{{{{{k.upper()}}}}}", v).replace(f"{{{{{k}}}}}", v)
                    
                    # Construct Email
                    msg = MIMEMultipart()
                    msg['From'] = user['gmail_user']
                    msg['To'] = job['recipient_email']
                    msg['Subject'] = subj
                    msg.attach(MIMEText(body, 'html'))
                    
                    # Send
                    server.send_message(msg)
                    print(f"     [Sent] {job['recipient_email']}")
                    
                    # Update DB: Mark as Sent
                    supabase.table('email_queue').update({'status': 'sent'}).eq('id', job['id']).execute()
                    sent_count += 1
                    
                    # Polite Delay (avoid Gmail spam filters)
                    time.sleep(2) 
                    
                except Exception as e:
                    print(f"     [Failed] {job['recipient_email']}: {e}")
                    supabase.table('email_queue').update({'status': 'failed', 'error_log': str(e)}).eq('id', job['id']).execute()
            
            server.quit()
            
            # 6. Update User Usage
            new_total = used + sent_count
            supabase.table('users').update({'used_today': new_total}).eq('id', user['id']).execute()
            print(f"  -> Batch complete. New usage: {new_total}/{limit}")

        except Exception as e:
            print(f"  -> Critical SMTP Error: {e}")

if __name__ == "__main__":
        # --- CLEANUP LOGIC ---
# Delete all 'sent' records for this user except the most recent 4
    sent_records = supabase.table('email_queue')\
    .select("id")\
    .eq('user_id', user['id'])\
    .eq('status', 'sent')\
    .order('created_at', desc=True)\
    .execute().data

if len(sent_records) > 4:
    ids_to_delete = [r['id'] for r in sent_records[4:]]
    supabase.table('email_queue').delete().in_('id', ids_to_delete).execute()
    run_batch()