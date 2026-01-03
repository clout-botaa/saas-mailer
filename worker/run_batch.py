import os
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client

supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

def send_report(user, subject, message):
    try:
        msg = MIMEText(message, 'html')
        msg['Subject'] = subject
        msg['From'] = user['gmail_user']
        msg['To'] = user['email']
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(user['gmail_user'], user['gmail_pass'])
        server.send_message(msg)
        server.quit()
    except Exception as e: print(f"Report failed: {e}")

def run_batch():
    users = supabase.table('users').select("*").execute().data
    for user in users:
        # Check Remaining Limit
        remaining = user['daily_limit'] - user['used_today']
        if remaining <= 0: continue

        queue = supabase.table('email_queue').select("*").eq('user_id', user['id']).eq('status', 'pending').limit(remaining).execute().data
        if not queue: continue

        # Send Batch
        sent_now = 0
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(user['gmail_user'], user['gmail_pass'])
            
            for job in queue:
                data = job['recipient_data']
                body = job['template_body']
                # Variable replacement
                for k, v in data.items():
                    body = body.replace(f"{{{{{k.upper()}}}}}", v)
                
                msg = MIMEMultipart()
                msg['Subject'] = job['template_subject'].replace("{{NAME}}", data['name'])
                msg.attach(MIMEText(body, 'html'))
                server.send_message(msg, from_addr=user['gmail_user'], to_addrs=job['recipient_email'])
                
                supabase.table('email_queue').update({'status': 'sent'}).eq('id', job['id']).execute()
                sent_now += 1
                time.sleep(2)
            server.quit()

            # Update usage and cleanup (Keep last 4)
            supabase.table('users').update({'used_today': user['used_today'] + sent_now}).eq('id', user['id']).execute()
            
            # Delete old sent records except top 4
            all_sent = supabase.table('email_queue').select("id").eq('user_id', user['id']).eq('status', 'sent').order('id', desc=True).execute().data
            if len(all_sent) > 4:
                ids = [x['id'] for x in all_sent[4:]]
                supabase.table('email_queue').delete().in_('id', ids).execute()
                
            send_report(user, "Automation Update", f"Sent {sent_now} emails. {remaining - sent_now} left for today.")

        except Exception as e:
            send_report(user, "Automation Error", str(e))

if __name__ == "__main__":
    run_batch()