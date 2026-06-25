from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    session,
    request,
    flash
)
from database import init_db, seed_problems, get_db
import hashlib
from grader import grade_submission

app = Flask(__name__)
app.secret_key = "demo_secret_key_2024"


# ─── Helper Functions ───────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user():
    if "user_id" not in session:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


# ─── Routes ─────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("problems"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = hash_password(request.form["password"])
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username = %s AND password = %s",
            (username, password)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("problems"))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = hash_password(request.form["password"])
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                (username, password)
            )
            conn.commit()
            flash("สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ")
            return redirect(url_for("login"))
        except:
            flash("ชื่อผู้ใช้นี้มีอยู่แล้ว")
        finally:
            cursor.close()
            conn.close()
    return render_template("login.html", register=True)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/problems")
def problems():
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM problems")
    problem_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("problems.html",
                           problems=problem_list,
                           username=session["username"])


@app.route("/problem/<int:problem_id>")
def problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM problems WHERE id = %s", (problem_id,))
    prob = cursor.fetchone()
    cursor.close()
    conn.close()
    if not prob:
        return "ไม่พบโจทย์", 404
    return render_template("problem.html",
                           problem=prob,
                           username=session["username"])


@app.route("/submit/<int:problem_id>", methods=["POST"])
def submit(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    code    = request.form["code"]
    user_id = session["user_id"]

    conn   = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM problems WHERE id = %s", (problem_id,))
    prob = cursor.fetchone()
    cursor.close()

    result = grade_submission(code, problem_id, user_id, conn)
    conn.close()

    return render_template("problem.html",
                           problem=prob,
                           result=result,
                           submitted_code=code,
                           username=session["username"])


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn    = get_db()
    cursor  = conn.cursor()
    user_id = session["user_id"]

    # นับ submission ทั้งหมด
    # DictCursor คืนค่าเป็น dict จึงต้องใช้ alias "count"
    cursor.execute(
        "SELECT COUNT(*) as count FROM submissions WHERE user_id = %s",
        (user_id,)
    )
    total = cursor.fetchone()["count"]

    # นับที่ผ่าน
    cursor.execute(
        "SELECT COUNT(*) as count FROM submissions WHERE user_id = %s AND status = 'passed'",
        (user_id,)
    )
    passed = cursor.fetchone()["count"]

    # Error แต่ละประเภท
    cursor.execute(
        """SELECT error_type, COUNT(*) as count
           FROM error_logs WHERE user_id = %s
           GROUP BY error_type ORDER BY count DESC""",
        (user_id,)
    )
    errors = cursor.fetchall()

    # ดึง submissions ทั้งหมดตามเวลาสำหรับ PDI Timeline
    cursor.execute(
        """SELECT status, submitted_at
           FROM submissions
           WHERE user_id = %s
           ORDER BY submitted_at ASC""",
        (user_id,)
    )
    all_submissions = cursor.fetchall()

    # คำนวณ PDI สะสม
    pdi_timeline   = []
    running_total  = 0
    running_passed = 0

    for sub in all_submissions:
        running_total += 1
        if sub["status"] == "passed":
            running_passed += 1
        pdi_value = round(running_passed / running_total * 100, 1)
        pdi_timeline.append({
            "time":  str(sub["submitted_at"]),
            "pdi":   pdi_value,
            "label": f"ครั้งที่ {running_total}"
        })

    # Error History 10 รายการล่าสุด
    cursor.execute(
        """SELECT el.id,
                  el.error_type,
                  el.error_message,
                  el.error_line,
                  el.logged_at,
                  p.title as problem_title,
                  p.id    as problem_id
           FROM error_logs el
           JOIN problems p ON el.problem_id = p.id
           WHERE el.user_id = %s
           ORDER BY el.logged_at DESC
           LIMIT 10""",
        (user_id,)
    )
    recent_errors = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        username     = session["username"],
        total        = total,
        passed       = passed,
        failed       = total - passed,
        errors       = errors,
        pdi_timeline = pdi_timeline,
        recent_errors= recent_errors
    )


@app.route("/error/<int:error_id>")
def error_detail(error_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn    = get_db()
    cursor  = conn.cursor()
    user_id = session["user_id"]

    cursor.execute(
        """SELECT el.id,
                  el.error_type,
                  el.error_message,
                  el.error_line,
                  el.logged_at,
                  p.title       as problem_title,
                  p.id          as problem_id,
                  p.description as problem_description,
                  s.code        as submitted_code
           FROM error_logs el
           JOIN problems    p ON el.problem_id    = p.id
           JOIN submissions s ON el.submission_id = s.id
           WHERE el.id = %s AND el.user_id = %s""",
        (error_id, user_id)
    )
    error = cursor.fetchone()
    cursor.close()
    conn.close()

    if not error:
        return "ไม่พบข้อมูล", 404

    error_explanations = {
        "SyntaxError": {
            "title": "SyntaxError — โค้ดผิดรูปแบบ",
            "desc":  "Python ไม่เข้าใจโค้ดที่เขียน มักเกิดจากลืมวงเล็บ ลืม : หรือพิมพ์ผิด",
            "tips":  [
                "ตรวจบรรทัดที่ระบุและบรรทัดก่อนหน้า",
                "เช็คว่าวงเล็บ ( ) [ ] { } เปิด-ปิดครบ",
                "เช็คว่ามี : หลัง if, for, while, def, class"
            ]
        },
        "IndentationError": {
            "title": "IndentationError — ย่อหน้าผิด",
            "desc":  "Python ใช้การย่อหน้าแทนวงเล็บ ถ้าย่อหน้าไม่ตรงกันจะ error",
            "tips":  [
                "ใช้ space หรือ tab อย่างใดอย่างหนึ่งสม่ำเสมอ (แนะนำ 4 spaces)",
                "โค้ดในบล็อกเดียวกันต้องย่อหน้าเท่ากัน",
                "หลัง if/for/while/def ต้องย่อหน้าเพิ่ม"
            ]
        },
        "NameError": {
            "title": "NameError — ใช้ชื่อที่ไม่มีอยู่",
            "desc":  "ใช้ตัวแปรหรือฟังก์ชันที่ยังไม่ได้ประกาศ",
            "tips":  [
                "ตรวจสอบการสะกดชื่อตัวแปร Python แยกตัวใหญ่-เล็ก",
                "ต้องประกาศตัวแปรก่อนใช้งาน",
                "ถ้าใช้ฟังก์ชัน ตรวจว่า import หรือ def ไว้แล้วหรือยัง"
            ]
        },
        "TypeError": {
            "title": "TypeError — ใช้ข้อมูลผิดประเภท",
            "desc":  "พยายามทำอะไรบางอย่างกับข้อมูลที่ไม่รองรับ เช่น บวก string กับ int",
            "tips":  [
                "ใช้ int() หรือ float() แปลงข้อมูลก่อนคำนวณ",
                "input() ส่งคืน string เสมอ ต้อง int(input()) ถ้าต้องการตัวเลข",
                "ตรวจประเภทด้วย type(ตัวแปร)"
            ]
        },
        "ValueError": {
            "title": "ValueError — ค่าไม่ถูกต้อง",
            "desc":  "ข้อมูลถูกประเภทแต่ค่าไม่ถูก เช่น int('abc')",
            "tips":  [
                "ตรวจว่า input ที่รับมาเป็นตัวเลขจริงๆ",
                "ใช้ try/except ดักจับกรณี input ไม่ใช่ตัวเลข"
            ]
        },
        "TimeoutError": {
            "title": "TimeoutError — โค้ดทำงานนานเกินไป",
            "desc":  "โค้ดใช้เวลาเกิน 2 วินาที มักเกิดจาก infinite loop",
            "tips":  [
                "ตรวจ while loop ว่าเงื่อนไขจะเป็น False ได้ไหม",
                "เช็คว่ามีการอัปเดตตัวแปรใน loop หรือเปล่า",
                "ลอง trace โค้ดด้วยมือทีละขั้น"
            ]
        }
    }

    explanation = error_explanations.get(
        error["error_type"],
        {
            "title": error["error_type"],
            "desc":  "เกิดข้อผิดพลาดขณะรันโค้ด",
            "tips":  ["อ่าน error message ด้านบนเพื่อหาสาเหตุ"]
        }
    )

    return render_template(
        "error_detail.html",
        error       = error,
        explanation = explanation,
        username    = session["username"]
    )


# ─── Init ────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    seed_problems()
    app.run(debug=True)