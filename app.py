import os
from flask import Flask, render_template, request, jsonify, g
import sqlite3
import hashlib
import hmac
import json
from urllib.parse import parse_qsl
from database import EmailDatabase, ADMIN_ID

app = Flask(__name__)
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
DB_PATH = 'emails.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def verify_telegram_data(init_data):
    try:
        # print(f"DEBUG: Verifying init_data: {init_data}")
        parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
        if 'hash' not in parsed_data:
            print("DEBUG: No hash present")
            return False, None
        
        received_hash = parsed_data['hash']
        parsed_data.pop('hash')
        
        # Sort and join
        data_check_string = '\n'.join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )
        
        # HMAC-SHA256
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == received_hash:
            user_data = json.loads(parsed_data.get('user', '{}'))
            
            # Check if user is blocked
            db_helper = EmailDatabase(DB_PATH)
            if db_helper.is_user_blocked(user_data['id']):
                # Special handling for Admin? No, Admin shouldn't block himself.
                if user_data['id'] != ADMIN_ID:
                    return False, None # Treat blocked as invalid/unauthorized
            
            return True, user_data
        
        print(f"DEBUG: Hash mismatch. Calc: {calculated_hash} != Recv: {received_hash}")
        return False, None
    except Exception as e:
        print(f"Auth Error: {e}")
        return False, None

@app.route('/')
def index():
    return render_template('index.html')

import re

@app.route('/api/auth', methods=['POST'])
def auth():
    init_data = request.json.get('initData')
    if not init_data:
        return jsonify({"error": "No data"}), 400
        
    valid, user = verify_telegram_data(init_data)
    if valid:
        # Upsert user to ensure they exist in DB (especially for Admin)
        db_helper = EmailDatabase(DB_PATH)
        # Ensure admin alias exists (recovery)
        if user['id'] == ADMIN_ID:
            db_helper.ensure_admin_alias(ADMIN_ID)
            
        db_helper.upsert_user(
            user['id'], 
            user.get('username'), 
            user.get('first_name'), 
            user.get('last_name')
        )
        return jsonify({"status": "ok", "user": user})
    return jsonify({"error": "Invalid data"}), 403

@app.route('/api/create_alias', methods=['POST'])
def create_alias():
    init_data = request.json.get('initData')
    alias = request.json.get('alias')
    
    if not alias:
        return jsonify({"error": "Alias required"}), 400

    # Validate alias format (Local part: letters, numbers, dot, underscore, dash. Cyrillic allowed)
    # We split by @ to check local part.
    try:
        local_part, domain = alias.split('@')
    except ValueError:
        return jsonify({"error": "Invalid email format"}), 400
        
    # Regex for local part: Allow a-z, A-Z, 0-9, . _ - and Cyrillic (\u0400-\u04FF)
    if not re.match(r'^[a-zA-Z0-9._\-\u0400-\u04FF]+$', local_part):
        return jsonify({"error": "Invalid characters in alias"}), 400
        
    valid, user = verify_telegram_data(init_data)
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401
        
    user_id = user['id']
    
    # Use EmailDatabase for safe writing
    db_helper = EmailDatabase(DB_PATH)
    if db_helper.add_alias(user_id, alias):
        return jsonify({"status": "ok"})
    else:
        return jsonify({"error": "Failed to create alias"}), 500

@app.route('/api/dashboard', methods=['POST'])
def dashboard():
    init_data = request.json.get('initData')
    valid, user = verify_telegram_data(init_data)
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = user['id']
    db = get_db()
    
    # Aliases
    cursor = db.execute('SELECT * FROM aliases WHERE user_id = ?', (user_id,))
    aliases = []
    alias_addresses = []
    for row in cursor.fetchall():
        aliases.append({
            "addr": row['address'],
            "active": bool(row['active']),
            "created_at": row['created_at']
        })
        alias_addresses.append(row['address'])
        
    return jsonify({
        "status": "ok",
        "aliases": aliases,
        "user_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    })

@app.route('/api/emails', methods=['POST'])
def get_emails():
    init_data = request.json.get('initData')
    alias_filter = request.json.get('alias')
    search_query = request.json.get('query')
    page = request.json.get('page', 0)
    limit = 20
    offset = page * limit
    
    valid, user = verify_telegram_data(init_data)
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = user['id']
    db = get_db()
    
    # Get user's aliases to ensure security (can only see emails for own aliases)
    cursor = db.execute('SELECT address FROM aliases WHERE user_id = ?', (user_id,))
    user_aliases = [row['address'] for row in cursor.fetchall()]
    
    if not user_aliases:
        return jsonify({"status": "ok", "emails": []})
        
    # Determine which aliases to query
    target_aliases = []
    if alias_filter:
        if alias_filter in user_aliases:
            target_aliases = [alias_filter]
        else:
            return jsonify({"error": "Access denied to this alias"}), 403
    else:
        target_aliases = user_aliases
        
    placeholders = ','.join('?' for _ in target_aliases)
    params = list(target_aliases)
    
    query_sql = f'''
        SELECT uid, to_addr, from_addr, subject, received_at, 
               CASE WHEN html_body IS NOT NULL THEN 1 ELSE 0 END as has_html
        FROM emails 
        WHERE to_addr IN ({placeholders})
    '''
    
    if search_query:
        query_sql += ''' AND (
            subject LIKE ? OR 
            from_addr LIKE ? OR 
            text_body LIKE ?
        )'''
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term, search_term])
        
    # Get total count first
    count_sql = f'SELECT COUNT(*) as count FROM emails WHERE to_addr IN ({placeholders})'
    count_params = list(target_aliases)
    
    if search_query:
        count_sql += ''' AND (
            subject LIKE ? OR 
            from_addr LIKE ? OR 
            text_body LIKE ?
        )'''
        count_params.extend([search_term, search_term, search_term])
        
    count_cursor = db.execute(count_sql, count_params)
    total_count = count_cursor.fetchone()['count']
        
    query_sql += f' ORDER BY uid DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor = db.execute(query_sql, params)
    
    emails = []
    for row in cursor.fetchall():
        emails.append({
            "uid": row['uid'],
            "to": row['to_addr'],
            "from": row['from_addr'],
            "subject": row['subject'],
            "date": row['received_at'],
            "has_html": bool(row['has_html'])
        })
        
    return jsonify({"status": "ok", "emails": emails, "total": total_count})

@app.route('/api/email_body', methods=['POST'])
def email_body():
    init_data = request.json.get('initData')
    uid = request.json.get('uid')
    
    valid, user = verify_telegram_data(init_data)
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401
        
    db = get_db()
    # Check ownership
    # 1. Get email to_addr
    cursor = db.execute('SELECT * FROM emails WHERE uid = ?', (uid,))
    row = cursor.fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
        
    # 2. Check if user owns this alias
    owner_cursor = db.execute('SELECT user_id FROM aliases WHERE address = ?', (row['to_addr'],))
    owner_row = owner_cursor.fetchone()
    
    # Allow if owner matches OR if user is admin
    if (not owner_row or owner_row['user_id'] != user['id']) and not is_admin(user['id']):
        return jsonify({"error": "Access denied"}), 403

    return jsonify({
        "status": "ok",
        "uid": row['uid'],
        "subject": row['subject'],
        "from": row['from_addr'],
        "to": row['to_addr'],
        "text_body": row['text_body'],
        "html_body": row['html_body'].decode('utf-8', errors='ignore') if row['html_body'] else None,
        "date": row['received_at']
    })

@app.route('/api/toggle_alias', methods=['POST'])
def toggle_alias():
    init_data = request.json.get('initData')
    alias = request.json.get('alias')
    
    valid, user = verify_telegram_data(init_data)
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401
        
    user_id = user['id']
    db_helper = EmailDatabase(DB_PATH)
    
    # Verify ownership happens inside toggle_alias_active via user_id check
    new_state = db_helper.toggle_alias_active(user_id, alias)
    
    if new_state is not None:
        return jsonify({"status": "ok", "active": new_state})
    else:
        return jsonify({"error": "Failed or access denied"}), 400

@app.route('/api/delete_alias', methods=['POST'])
def delete_alias():
    init_data = request.json.get('initData')
    alias = request.json.get('alias')
    
    valid, user = verify_telegram_data(init_data)
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401
        
    user_id = user['id']
    db_helper = EmailDatabase(DB_PATH)
    
    # Use delete_alias from DB which checks user_id
    success = db_helper.delete_alias(user_id, alias)
    
    if success:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"error": "Failed or access denied"}), 400

# --- Admin API ---

def is_admin(user_id):
    return user_id == ADMIN_ID

@app.route('/api/admin/users', methods=['POST'])
def admin_users():
    init_data = request.json.get('initData')
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    
    # Ensure admin alias exists (recovery)
    db_helper.ensure_admin_alias(ADMIN_ID)
    
    stats = db_helper.get_all_users_stats()
    return jsonify({"status": "ok", "users": stats})

@app.route('/api/admin/user_details', methods=['POST'])
def admin_user_details():
    init_data = request.json.get('initData')
    target_user_id = request.json.get('user_id')
    
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    details = db_helper.get_user_details_admin(target_user_id)
    return jsonify({"status": "ok", "details": details})

@app.route('/api/admin/block_user', methods=['POST'])
def admin_block_user():
    init_data = request.json.get('initData')
    target_user_id = request.json.get('user_id')
    block = request.json.get('block', True)
    
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    if block:
        db_helper.block_user(target_user_id, "Admin blocked")
    else:
        db_helper.unblock_user(target_user_id)
        
    return jsonify({"status": "ok"})

@app.route('/api/admin/delete_user', methods=['POST'])
def admin_delete_user():
    init_data = request.json.get('initData')
    target_user_id = request.json.get('user_id')
    
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    if db_helper.delete_user_data(target_user_id):
        return jsonify({"status": "ok"})
    return jsonify({"error": "Failed"}), 500

@app.route('/api/admin/user_emails', methods=['POST'])
def admin_user_emails():
    init_data = request.json.get('initData')
    target_user_id = request.json.get('user_id')
    page = request.json.get('page', 0)
    
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    emails, total = db_helper.get_user_emails_admin(target_user_id, offset=page*50)
    return jsonify({"status": "ok", "emails": emails, "total": total})

@app.route('/api/admin/delete_email', methods=['POST'])
def admin_delete_email():
    init_data = request.json.get('initData')
    uid = request.json.get('uid')
    
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    db_helper.delete_email(uid)
    return jsonify({"status": "ok"})

@app.route('/api/admin/add_alias', methods=['POST'])
def admin_add_alias():
    init_data = request.json.get('initData')
    target_user_id = request.json.get('user_id')
    alias = request.json.get('alias')
    
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    if db_helper.add_alias(target_user_id, alias):
        return jsonify({"status": "ok"})
    return jsonify({"error": "Failed"}), 500

@app.route('/api/delete_email', methods=['POST'])
def delete_email():
    init_data = request.json.get('initData')
    uid = request.json.get('uid')
    
    valid, user = verify_telegram_data(init_data)
    if not valid:
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    # Verify ownership before deleting
    email = db_helper.get_email_by_uid(uid)
    if not email:
        return jsonify({"error": "Not found"}), 404
        
    # Check if the email's 'to_addr' belongs to one of the user's aliases
    owner_id = db_helper.get_owner(email['to_email'])
    if owner_id != user['id']:
        return jsonify({"error": "Forbidden"}), 403
        
    if db_helper.delete_email(uid):
        return jsonify({"status": "ok"})
    return jsonify({"error": "Failed"}), 500

@app.route('/api/admin/toggle_alias', methods=['POST'])
def admin_toggle_alias():
    init_data = request.json.get('initData')
    target_user_id = request.json.get('user_id')
    alias = request.json.get('alias')
    
    valid, user = verify_telegram_data(init_data)
    if not valid or not is_admin(user['id']):
        return jsonify({"error": "Unauthorized"}), 403
        
    db_helper = EmailDatabase(DB_PATH)
    new_state = db_helper.toggle_alias_active(target_user_id, alias)
    if new_state is not None:
        return jsonify({"status": "ok", "active": new_state})
    return jsonify({"error": "Failed"}), 400

if __name__ == '__main__':
    # Run on port 8003
    app.run(host='127.0.0.1', port=8003)
