
# app.py
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import json, os, re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

users = {}
rooms = {}  # username -> room name
online_users = {}  # username -> sid

# Utility functions for user account storage
def load_users():
    if os.path.exists("user_accounts.json"):
        with open("user_accounts.json", "r") as f:
            return json.load(f)
    return {}

def save_users(data):
    with open("user_accounts.json", "w") as f:
        json.dump(data, f, indent=4)

def save_message(room, sender, msg):
    filename = f"chat_history_{room}.txt"
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"{sender}: {msg}\n")

def load_messages(room):
    filename = f"chat_history_{room}.txt"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()[-20:]
    return []


def save_private_message(sender, recipient, msg):
    os.makedirs(f"messages/{recipient}", exist_ok=True)
    with open(f"messages/{recipient}/{sender}.txt", "a", encoding="utf-8") as f:
        f.write(f"{sender}: {msg}\n")

def notify_unread_private_messages(username):
    user_folder = f"messages/{username}"
    if os.path.exists(user_folder):
        for sender_file in os.listdir(user_folder):
            with open(os.path.join(user_folder, sender_file), "r", encoding="utf-8") as f:
                messages = f.readlines()
                if messages:
                    emit("private_notification", {
                        "from": sender_file.replace(".txt", ""),
                        "count": len(messages)
                    }, room=online_users[username])

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        users_db = load_users()
        if username in users_db and users_db[username]['password'] == password:
            session['username'] = username
            session['display_name'] = users_db[username]['display_name']
            return redirect(url_for('chat'))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        display_name = request.form['display_name']

        users_db = load_users()

        if username in users_db:
            return render_template("register.html", error="\u26a0\ufe0f This username is already registered. Please choose another.")
        if not any(c.isupper() for c in username):
            return render_template("register.html", error="Username must include at least one uppercase letter.")
        if not any(c.isdigit() for c in username):
            return render_template("register.html", error="Username must include at least one digit.")
        if not any(c in "@#$%&*!" for c in username):
            return render_template("register.html", error="Username must include at least one special character (@#$%&*!).")
        if len(password) < 5:
            return render_template("register.html", error="Password must be at least 5 characters long.")

        users_db[username] = {"password": password, "display_name": display_name}
        save_users(users_db)
        return redirect(url_for('login'))

    return render_template("register.html")

@app.route("/chat")
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template("chat.html", display_name=session['display_name'])

@app.route("/clear_history", methods=["POST"])
def clear_history():
    username = session.get("username")
    if not username:
        return {"success": False, "error": "Not logged in"}

    room = rooms.get(username, "public")
    filename = f"chat_history_{room}.txt"
    if os.path.exists(filename):
        open(filename, "w").close()
    return {"success": True}

@socketio.on("join_chat")
def handle_join(data):
    username = session.get("username")
    room = "public"
    users[request.sid] = username
    rooms[username] = room
    online_users[username] = request.sid
    join_room(room)
    notify_unread_private_messages(username)
    emit("system_message", {"msg": f"\ud83d\ude80 {data['display_name']} joined the chat"}, room=room)

@socketio.on("get_history")
def handle_history():
    username = session.get("username")
    room = rooms.get(username, "public")
    history = load_messages(room)
    messages = [line.strip() for line in history]
    emit("history", {"messages": messages}, room=request.sid)

@socketio.on("send_message")
def handle_message(data):
    username = session.get("username")
    room = rooms.get(username, "public")
    msg = data['msg']
    sender = data['sender']
    print(f"[SEND] {sender}: {msg} in room {room}") 
    save_message(room, sender, msg)
    emit("receive_message", {"sender": sender, "msg": msg}, room=room)

@socketio.on("private_message")
def handle_private_message(data):
    recipient = data['recipient']
    sender = data['sender']
    message = data['message']
    recipient_sid = online_users.get(recipient)

    if recipient_sid:
        emit('receive_private_message', {'sender': sender, 'message': message}, room=recipient_sid)
        emit('private_message_alert', {'from': sender}, room=recipient_sid)
    if rooms.get(recipient) == "public":
        emit('private_message_switch_prompt', {'from': sender}, room=recipient_sid)

    else:
        print(f"[STORE] Recipient offline, storing message from {sender} to {recipient}")

    save_private_message(sender, recipient, message)

@socketio.on("disconnect")
def handle_disconnect():
    username = users.pop(request.sid, None)
    if username:
        room = rooms.pop(username, "public")
        online_users.pop(username, None)
        leave_room(room)
        emit("system_message", {"msg": f"\u274c {username} left the chat"}, room=room)

@socketio.on("switch_private")
def handle_switch_private(data):
    username = session.get("username")
    partner_display_name = data['partner']
    partner_username = None
    partner_sid = None

    users_db = load_users()

    # Map display name -> actual username
    for uname, info in users_db.items():
        if info["display_name"].lower() == partner_display_name.lower():
            partner_username = uname
            break

    if not partner_username:
        emit("system_message", {"msg": f"❌ User '{partner_display_name}' not found."}, room=request.sid)
        return

    # Now get that user's socket ID
    for sid, name in users.items():
        if name == partner_username:
            partner_sid = sid
            break

    if not partner_sid:
        emit("system_message", {"msg": f"❌ User '{partner_display_name}' is not online."}, room=request.sid)
        return

    emit("private_invite", {"from": username}, room=partner_sid)

    participants = sorted([username, partner_username])
    private_room = f"private_{participants[0]}_{participants[1]}"

    leave_room(rooms.get(username, 'public'))
    join_room(private_room)
    rooms[username] = private_room

    emit("system_message", {"msg": f"🔐 You are now in private chat with {partner_display_name}."}, room=request.sid)



@socketio.on("switch_public")
def handle_switch_public():
    username = session.get("username")
    current_room = rooms.get(username)

    leave_room(current_room)

    #  Avoid join_room crash if SID is not tracked
    if username not in users.values():
        print(f"[WARN] SID for {username} not found; skipping room join.")
        return

    join_room("public")
    rooms[username] = "public"
    emit("system_message", {"msg": "\ud83d\udd01 Switched to public chat."}, room=request.sid)



UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files["file"]
    if file:
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        return {"success": True, "url": f"/uploads/{file.filename}"}
    return {"success": False}

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@socketio.on("accept_private")
def handle_accept_private(data):
    username = session.get("username")
    from_user = data["from"]

    participants = sorted([username, from_user])
    private_room = f"private_{participants[0]}_{participants[1]}"

    leave_room(rooms.get(username, 'public'))
    join_room(private_room)
    rooms[username] = private_room

    emit("system_message", {"msg": f"\ud83d\udd12 Private chat started with {from_user}"}, room=request.sid)

@socketio.on("decline_private")
def handle_decline_private(data):
    pass  # Do nothing at all

if __name__ == '__main__':
    socketio.run(app, debug=True)