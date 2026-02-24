import sqlite3
import threading

import os
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
ADMIN_EMAIL = os.environ.get('EMAIL_USER', 'your_email@yandex.ru')

ALLOWED_DOMAINS = [
    'dreampartners.online',
    'nefor-casino.online'
]

CRITICAL_LOCAL_PARTS = [
    'admin', 'support', 'help', 'info', 'security', 
    'abuse', 'postmaster', 'hostmaster', 'webmaster', 
    'contact', 'sales', 'billing', 'root', 'noreply', 
    'system', 'bot', 'mailer-daemon'
]

class EmailDatabase:
    def __init__(self, db_path="emails.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_db()

    def init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emails (
                    uid INTEGER PRIMARY KEY,
                    owner_id INTEGER,
                    to_addr TEXT,
                    from_addr TEXT,
                    subject TEXT,
                    text_body TEXT,
                    html_body BLOB,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS aliases (
                    address TEXT PRIMARY KEY,
                    user_id INTEGER,
                    active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS blocked_users (
                    user_id INTEGER PRIMARY KEY,
                    reason TEXT,
                    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Index for faster lookup by address
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_to_addr ON emails (to_addr)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_owner ON emails (owner_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alias_user ON aliases (user_id)')
            conn.commit()
            conn.close()
            
        # Strictly enforce admin alias on every init
        self.ensure_admin_alias(ADMIN_ID, ADMIN_EMAIL)

    def upsert_user(self, user_id, username, first_name, last_name):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, username, first_name, last_name))
                conn.commit()
            except Exception as e:
                print(f"DB Error upserting user: {e}")
            finally:
                conn.close()

    def add_alias(self, user_id, email, active=True):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO aliases (address, user_id, active)
                    VALUES (?, ?, ?)
                ''', (email.lower().strip(), user_id, active))
                conn.commit()
                return True
            except Exception as e:
                print(f"DB Error adding alias: {e}")
                return False
            finally:
                conn.close()

    def delete_alias(self, user_id, email):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('DELETE FROM aliases WHERE address = ? AND user_id = ?', (email.lower().strip(), user_id))
                rows = cursor.rowcount
                conn.commit()
                return rows > 0
            except Exception as e:
                print(f"DB Error deleting alias: {e}")
                return False
            finally:
                conn.close()

    def get_user_aliases(self, user_id):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM aliases WHERE user_id = ?', (user_id,))
            rows = cursor.fetchall()
            conn.close()
            
            result = []
            for row in rows:
                result.append({
                    "addr": row['address'],
                    "active": bool(row['active'])
                })
            return result

    def get_owner(self, email):
        if not email: return None
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM aliases WHERE address = ?', (email.lower().strip(),))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None

    def is_alias_active(self, user_id, email):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT active FROM aliases WHERE address = ? AND user_id = ?', (email.lower().strip(), user_id))
            row = cursor.fetchone()
            conn.close()
            if row:
                return bool(row[0])
            # If alias not found but we are checking activity, default to True? 
            # Or False? Usually if we check for email routing, we check owner first.
            # If we check for UI, it should exist.
            return True

    def toggle_alias_active(self, user_id, email):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # First get current state
                cursor.execute('SELECT active FROM aliases WHERE address = ? AND user_id = ?', (email.lower().strip(), user_id))
                row = cursor.fetchone()
                if row:
                    new_state = not bool(row[0])
                    cursor.execute('UPDATE aliases SET active = ? WHERE address = ?', (new_state, email.lower().strip()))
                    conn.commit()
                    return new_state
                return None
            finally:
                conn.close()

    def add_email(self, uid, owner_id, to_addr, from_addr, subject, text_body, html_body):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO emails (uid, owner_id, to_addr, from_addr, subject, text_body, html_body)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (uid, owner_id, to_addr, from_addr, subject, text_body, html_body))
                conn.commit()
                return True
            except Exception as e:
                print(f"DB Error adding email: {e}")
                return False
            finally:
                conn.close()

    def get_emails_for_alias(self, email_addr, limit=10, offset=0):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM emails 
                WHERE to_addr = ? 
                ORDER BY uid DESC 
                LIMIT ? OFFSET ?
            ''', (email_addr, limit, offset))
            rows = cursor.fetchall()
            
            # Count total
            cursor.execute('SELECT COUNT(*) FROM emails WHERE to_addr = ?', (email_addr,))
            total = cursor.fetchone()[0]
            
            conn.close()
            
            result = []
            for row in rows:
                result.append({
                    'uid': row['uid'],
                    'from': row['from_addr'],
                    'subject': row['subject'],
                    'text': row['text_body'],
                    'html': row['html_body']
                })
            return result, total

    def get_email_by_uid(self, uid):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM emails WHERE uid = ?', (uid,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'uid': row['uid'],
                    'from': row['from_addr'],
                    'subject': row['subject'],
                    'text': row['text_body'],
                    'html': row['html_body'],
                    'to_email': row['to_addr']
                }
            return None

    def delete_email(self, uid):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('DELETE FROM emails WHERE uid = ?', (uid,))
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                print(f"DB Error deleting email: {e}")
                return False
            finally:
                conn.close()

    def is_user_blocked(self, user_id):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()
            return bool(row)

    def block_user(self, user_id, reason=""):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO blocked_users (user_id, reason) VALUES (?, ?)', (user_id, reason))
            conn.commit()
            conn.close()
            return True

    def unblock_user(self, user_id):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            return True

    def get_all_users_stats(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all users from users table
            cursor.execute('SELECT * FROM users')
            users = cursor.fetchall()
            
            stats = []
            for user in users:
                uid = user['user_id']
                
                # Get aliases count
                cursor.execute('SELECT COUNT(*) FROM aliases WHERE user_id = ?', (uid,))
                alias_count = cursor.fetchone()[0]
                
                # Get total emails
                cursor.execute('''
                    SELECT COUNT(*) FROM emails 
                    WHERE to_addr IN (SELECT address FROM aliases WHERE user_id = ?)
                ''', (uid,))
                email_count = cursor.fetchone()[0]
                
                # Check blocked
                cursor.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (uid,))
                is_blocked = bool(cursor.fetchone())
                
                stats.append({
                    'user_id': uid,
                    'username': user['username'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name'],
                    'alias_count': alias_count,
                    'email_count': email_count,
                    'is_blocked': is_blocked
                })
            
            conn.close()
            return stats

    def ensure_admin_alias(self, admin_id, admin_alias="peter.gold123@yandex.ru"):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 1. Ensure main admin alias
            cursor.execute('SELECT 1 FROM aliases WHERE address = ?', (admin_alias,))
            if not cursor.fetchone():
                cursor.execute('INSERT INTO aliases (user_id, address, active) VALUES (?, ?, 1)', (admin_id, admin_alias))
                conn.commit()
                print(f"Restored admin alias: {admin_alias}")
            else:
                cursor.execute('UPDATE aliases SET user_id = ? WHERE address = ?', (admin_id, admin_alias))
                conn.commit()
            
            # 2. Ensure critical aliases for all domains
            for domain in ALLOWED_DOMAINS:
                for local in CRITICAL_LOCAL_PARTS:
                    critical_email = f"{local}@{domain}"
                    cursor.execute('SELECT user_id FROM aliases WHERE address = ?', (critical_email,))
                    row = cursor.fetchone()
                    
                    if not row:
                        # Create if not exists
                        cursor.execute('INSERT INTO aliases (user_id, address, active) VALUES (?, ?, 1)', (admin_id, critical_email))
                        print(f"Created critical alias: {critical_email}")
                    elif row[0] != admin_id:
                        # Takeover if owned by someone else
                        cursor.execute('UPDATE aliases SET user_id = ? WHERE address = ?', (admin_id, critical_email))
                        print(f"Reclaimed critical alias: {critical_email} from {row[0]}")
            
            conn.commit()
            
            # Cleanup old incorrect alias if exists
            incorrect_alias = "admin@dreampartners.online"
            # We just secured admin@... so we don't want to delete it if it's in CRITICAL_LOCAL_PARTS (which it is)
            # But let's check if there's any specific cleanup needed. 
            # The previous code deleted it. But now we want 'admin' to be valid and owned by admin.
            # So I will remove the deletion logic for admin@dreampartners.online
                
            conn.close()

    def get_user_details_admin(self, user_id):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get user info
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user_info = cursor.fetchone()

            # Aliases
            cursor.execute('SELECT * FROM aliases WHERE user_id = ?', (user_id,))
            aliases = []
            for row in cursor.fetchall():
                aliases.append({
                    'addr': row['address'],
                    'active': bool(row['active']),
                    'created_at': row['created_at']
                })
                
            # Blocked status
            cursor.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
            is_blocked = bool(cursor.fetchone())
            
            conn.close()
            return {
                'user_id': user_id,
                'username': user_info['username'] if user_info else None,
                'first_name': user_info['first_name'] if user_info else None,
                'last_name': user_info['last_name'] if user_info else None,
                'aliases': aliases,
                'is_blocked': is_blocked
            }

    def get_user_emails_admin(self, user_id, limit=50, offset=0):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM emails 
                WHERE to_addr IN (SELECT address FROM aliases WHERE user_id = ?)
                ORDER BY uid DESC 
                LIMIT ? OFFSET ?
            ''', (user_id, limit, offset))
            
            emails = []
            for row in cursor.fetchall():
                emails.append({
                    'uid': row['uid'],
                    'to': row['to_addr'],
                    'from': row['from_addr'],
                    'subject': row['subject'],
                    'date': row['received_at']
                })
                
            cursor.execute('''
                SELECT COUNT(*) FROM emails 
                WHERE to_addr IN (SELECT address FROM aliases WHERE user_id = ?)
            ''', (user_id,))
            total = cursor.fetchone()[0]
            
            conn.close()
            return emails, total


    def delete_email(self, uid):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('DELETE FROM emails WHERE uid = ?', (uid,))
                rows = cursor.rowcount
                conn.commit()
                return rows > 0
            except Exception as e:
                print(f"DB Error deleting email: {e}")
                return False
            finally:
                conn.close()

    def delete_user_data(self, user_id):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # Delete emails
                cursor.execute('''
                    DELETE FROM emails 
                    WHERE to_addr IN (SELECT address FROM aliases WHERE user_id = ?)
                ''', (user_id,))
                
                # Delete aliases
                cursor.execute('DELETE FROM aliases WHERE user_id = ?', (user_id,))
                
                # Delete from blocked
                cursor.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
                
                # Delete from users
                cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
                
                conn.commit()
                return True
            except Exception as e:
                print(f"Error deleting user: {e}")
                return False
            finally:
                conn.close()

    def get_last_uid(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT MAX(uid) FROM emails')
            result = cursor.fetchone()[0]
            conn.close()
            return result if result else 0

    def delete_email(self, uid):
        # Optional: if we want to allow deleting from local DB
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM emails WHERE uid = ?', (uid,))
            conn.commit()
            conn.close()
