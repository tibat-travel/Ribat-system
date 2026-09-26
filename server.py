import os
import json
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("RIBAT_DB_PATH", BASE_DIR / "ribat.db"))
FRONTEND_FILE = os.environ.get("RIBAT_FRONTEND", "index.html")

app = Flask(__name__)
CORS(app, supports_credentials=False)

PERMISSIONS = [
    "dashboard", "clients_view", "clients_manage", "services_view",
    "services_manage", "invoices_view", "invoices_manage",
    "expenses_view", "expenses_manage", "reports_view",
    "settings_manage", "backup_manage"
]

ROLE_PERMS = {
    "admin": PERMISSIONS,
    "sales": ["dashboard","clients_view","clients_manage","services_view",
             "invoices_view","invoices_manage","reports_view"],
    "operations": ["dashboard","clients_view","clients_manage","services_view"],
    "team_leader": ["dashboard","clients_view","clients_manage","services_view","services_manage","invoices_view","invoices_manage","expenses_view","reports_view"],
    "marketing_captain": ["dashboard","clients_view","clients_manage","services_view","services_manage","reports_view"],
    "accountant": ["dashboard","clients_view","invoices_view","invoices_manage",
                   "expenses_view","expenses_manage","reports_view"],
    "viewer": ["dashboard","clients_view","services_view","invoices_view","reports_view"],
    "custom": []
}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def password_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    row = conn.execute("SELECT id FROM app_state WHERE id=1").fetchone()
    if not row:
        admin_id = secrets.token_hex(8)
        state = {
            "company": {"name": "مجموعة رباط الخدمية", "currency": "USD"},
            "users": [{
                "id": admin_id,
                "name": "المدير",
                "username": "admin",
                "role": "admin",
                "permissions": None,
                "passwordHash": password_hash("123456")
            }],
            "clients": [],
            "orders": [],
            "services": [
                {"id": secrets.token_hex(8), "cat": "دراسة", "country": "رواندا",
                 "name": "التسجيل الجامعي + التأشيرة الدراسية",
                 "desc": "متابعة كاملة من القبول حتى السفر", "price": 450, "currency": "USD"},
                {"id": secrets.token_hex(8), "cat": "دراسة", "country": "الهند",
                 "name": "برنامج القبول الجامعي",
                 "desc": "اختيار الجامعة والتقديم والمتابعة", "price": 400, "currency": "USD"},
                {"id": secrets.token_hex(8), "cat": "سفر", "country": "رواندا",
                 "name": "حجز تذاكر الطيران",
                 "desc": "حجز وإصدار تذاكر ذهاب وعودة", "price": 60, "currency": "USD"},
                {"id": secrets.token_hex(8), "cat": "سياحة", "country": "الهند",
                 "name": "باقة سياحية أسبوعية",
                 "desc": "إقامة + مواصلات + برنامج سياحي", "price": 650, "currency": "USD"}
            ],
            "invoices": [],
            "expenses": []
        }
        conn.execute(
            "INSERT INTO app_state(id,state_json,updated_at) VALUES(1,?,?)",
            (json.dumps(state, ensure_ascii=False), now_iso())
        )
        conn.commit()
    conn.close()

def get_state():
    conn = db()
    row = conn.execute("SELECT state_json FROM app_state WHERE id=1").fetchone()
    conn.close()
    return json.loads(row["state_json"])

def save_state(state):
    conn = db()
    conn.execute(
        "UPDATE app_state SET state_json=?, updated_at=? WHERE id=1",
        (json.dumps(state, ensure_ascii=False), now_iso())
    )
    conn.commit()
    conn.close()

def auth_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    conn = db()
    row = conn.execute(
        "SELECT user_id FROM sessions WHERE token=?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    state = get_state()
    return next((u for u in state.get("users", []) if u.get("id") == row["user_id"]), None)

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "ribat-backend"})

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()
    supplied_hash = str(data.get("passwordHash", "")).strip()

    if not username or not supplied_hash:
        return jsonify({"error": "أدخل اسم المستخدم وكلمة المرور"}), 400

    state = get_state()
    user = next(
        (u for u in state.get("users", [])
         if str(u.get("username", "")).strip().lower() == username),
        None
    )
    if not user or user.get("passwordHash") != supplied_hash:
        return jsonify({"error": "اسم المستخدم أو كلمة المرور غير صحيحة"}), 401

    token = secrets.token_urlsafe(48)
    conn = db()
    conn.execute(
        "INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)",
        (token, user["id"], now_iso())
    )
    conn.commit()
    conn.close()

    safe_user = dict(user)
    safe_user.pop("passwordHash", None)
    return jsonify({"token": token, "state": state, "user": safe_user})

@app.get("/api/state")
def read_state():
    user = auth_user()
    if not user:
        return jsonify({"error": "غير مصرح"}), 401
    state = get_state()
    safe_user = dict(user)
    safe_user.pop("passwordHash", None)
    return jsonify({"state": state, "user": safe_user})

@app.put("/api/state")
def write_state():
    user = auth_user()
    if not user:
        return jsonify({"error": "غير مصرح"}), 401

    payload = request.get_json(silent=True) or {}
    state = payload.get("state")
    if not isinstance(state, dict):
        return jsonify({"error": "بيانات النظام غير صالحة"}), 400

    # حماية أساسية: لا يمكن لأي مستخدم تغيير حسابه إلى مدير أو حذف آخر مدير.
    old_state = get_state()
    old_users = old_state.get("users", [])
    new_users = state.get("users", [])
    if not isinstance(new_users, list) or not new_users:
        return jsonify({"error": "يجب أن يوجد مستخدم واحد على الأقل"}), 400

    old_admins = [u for u in old_users if u.get("role") == "admin"]
    new_admins = [u for u in new_users if u.get("role") == "admin"]

    if user.get("role") != "admin":
        old_ids = {u.get("id") for u in old_users}
        new_ids = {u.get("id") for u in new_users}
        # غير المدير لا يستطيع تعديل قائمة المستخدمين أو الصلاحيات.
        if new_ids != old_ids or new_users != old_users:
            return jsonify({"error": "إدارة المستخدمين متاحة للمدير فقط"}), 403

    if old_admins and not new_admins:
        return jsonify({"error": "يجب أن يبقى مدير واحد على الأقل"}), 400

    # فرض الصلاحيات على مستوى الخادم أيضاً: المستخدم غير المدير لا يستطيع
    # تعديل أقسام لا يملك صلاحية إدارتها حتى لو أرسل طلب API يدوياً.
    if user.get("role") != "admin":
        role = user.get("role", "custom")
        explicit = user.get("permissions")
        perms = set(explicit) if isinstance(explicit, list) else set(ROLE_PERMS.get(role, []))
        protected = {
            "clients": "clients_manage",
            "orders": "clients_manage",
            "services": "services_manage",
            "invoices": "invoices_manage",
            "expenses": "expenses_manage",
            "company": "settings_manage",
        }
        for key, perm in protected.items():
            if state.get(key) != old_state.get(key) and perm not in perms:
                return jsonify({"error": f"ليس لديك صلاحية لتعديل {key}"}), 403

        # المستخدم غير المدير لا يستطيع تغيير بيانات المستخدمين أو الصلاحيات.
        if new_users != old_users:
            return jsonify({"error": "إدارة المستخدمين متاحة للمدير فقط"}), 403

    save_state(state)
    return jsonify({"ok": True, "state": state})

@app.post("/api/logout")
def logout():
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if token:
        conn = db()
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
    return jsonify({"ok": True})

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def frontend(path):
    # Serve the frontend from the same Render service so API_BASE='' works.
    target = Path(path) if path else Path(FRONTEND_FILE)
    if target.name == "server.py" or target.name == DB_PATH.name:
        return jsonify({"error": "Not found"}), 404
    candidate = BASE_DIR / target
    if candidate.is_file():
        return send_from_directory(BASE_DIR, target.as_posix())
    index = BASE_DIR / FRONTEND_FILE
    if index.is_file():
        return send_from_directory(BASE_DIR, FRONTEND_FILE)
    return jsonify({
        "ok": True,
        "message": "Ribat backend is running. Upload the frontend HTML as index.html."
    })

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
