import os
import sqlite3

from flask import redirect, render_template, session
from functools import wraps


# Initialize graji.db
DB_PATH = os.path.join("db", "graji.db")
SCHEMA_PATH = os.path.join("db", "schema.sql")

os.makedirs("db", exist_ok=True)

conn = sqlite3.connect(DB_PATH)

with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    conn.executescript(f.read())


# Execute a query in database
def sqlexecute(query, *args):
    conn = sqlite3.connect(DB_PATH)
    
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(query, args)
    
    result = None
    query_clean = query.strip().upper()
    
    if query_clean.startswith("SELECT"):
        result = [dict(row) for row in cursor.fetchall()]
    else:
        conn.commit()
        if query_clean.startswith("INSERT"):
            result = cursor.lastrowid
        else:
            result =  cursor.rowcount
            
    conn.close()
    return result


# Decorate routes to require login.
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


# Verify Level
def level_required(required_level):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get("user_id")

            result = sqlexecute("SELECT nivel_acesso FROM login WHERE id_login = ?",user_id)

            if not result or int(result[0]["nivel_acesso"]) < required_level:
                return httperror("Você não tem permissão para acessar esta página.", 403)

            return f(*args, **kwargs)

        return decorated_function
    return decorator


# Return an error page
def httperror(message, errorcode):
    return render_template("error.html", error_message = message, error_code = errorcode)
