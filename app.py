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
from grader import grade_submission, calc_performance_metrics

app = Flask(__name__)
app.secret_key = "demo_secret_key_2024"

# ลำดับหัวข้อตามขอบเขตของโครงร่างปัญหาพิเศษ (หัวข้อ 5.1)
CATEGORY_ORDER = [
    "ตัวแปรและชนิดข้อมูล",
    "นิพจน์และตัวดำเนินการ",
    "คำสั่งเงื่อนไข",
    "คำสั่งวนซ้ำ",
    "ฟังก์ชัน",
]


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
            "SELECT * FROM users WHERE username = %s AND password_hash = %s",
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
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
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

    # เรียงเนื้อหาโจทย์แยกตามประเภท (หัวข้อการเรียน) ตามลำดับที่กำหนดในขอบเขตโครงงาน
    grouped = {}
    for idx, p in enumerate(problem_list, start=1):
        p["number"] = idx
        grouped.setdefault(p["category"], []).append(p)

    ordered_categories = [c for c in CATEGORY_ORDER if c in grouped]
    ordered_categories += [c for c in grouped if c not in CATEGORY_ORDER]
    grouped_problems = [(c, grouped[c]) for c in ordered_categories]

    return render_template("problems.html",
                           grouped_problems=grouped_problems,
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
        "SELECT COUNT(*) as count FROM submissions WHERE user_id = %s AND status = 'Passed'",
        (user_id,)
    )
    passed = cursor.fetchone()["count"]

    # Error แต่ละประเภท — error_logs ไม่เก็บ user_id ซ้ำแล้ว ต้อง JOIN ผ่าน submissions
    cursor.execute(
        """SELECT el.error_type, COUNT(*) as count
           FROM error_logs el
           JOIN submissions s ON el.submission_id = s.id
           WHERE s.user_id = %s
           GROUP BY el.error_type ORDER BY count DESC""",
        (user_id,)
    )
    errors = cursor.fetchall()

    # ตัวชี้วัดผลการส่งโปรแกรม ตามหัวข้อ 5.1.1 ของโครงร่างปัญหาพิเศษ
    # SuccessRate, ExecutionErrorRate, FirstAttemptRate — เป็นค่าร้อยละที่แสดง "แนวโน้ม"
    # การเปลี่ยนแปลงของผลการส่งโปรแกรม ไม่ใช่คะแนนวัดความสามารถ
    performance_metrics = calc_performance_metrics(cursor, user_id)

    # Error History 10 รายการล่าสุด — error_logs ไม่เก็บ user_id/problem_id ซ้ำแล้ว
    # ต้อง JOIN ผ่าน submissions เพื่อดึง user_id และ problem_id
    cursor.execute(
        """SELECT el.id,
                  el.exception_name,
                  el.error_type,
                  el.error_message,
                  el.error_line,
                  el.logged_at,
                  p.title as problem_title,
                  p.id    as problem_id
           FROM error_logs el
           JOIN submissions s ON el.submission_id = s.id
           JOIN problems    p ON s.problem_id     = p.id
           WHERE s.user_id = %s
           ORDER BY el.logged_at DESC
           LIMIT 10""",
        (user_id,)
    )
    recent_errors = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        username          = session["username"],
        total             = total,
        passed            = passed,
        failed            = total - passed,
        errors            = errors,
        recent_errors     = recent_errors,
        success_rate         = performance_metrics["success_rate"],
        execution_error_rate = performance_metrics["execution_error_rate"],
        first_attempt_rate   = performance_metrics["first_attempt_rate"]
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
                  el.exception_name,
                  el.error_type,
                  el.error_message,
                  el.error_line,
                  el.logged_at,
                  p.title       as problem_title,
                  p.id          as problem_id,
                  p.description as problem_description,
                  s.code        as submitted_code
           FROM error_logs el
           JOIN submissions s ON el.submission_id = s.id
           JOIN problems    p ON s.problem_id      = p.id
           WHERE el.id = %s AND s.user_id = %s""",
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
        "IndexError": {
            "title": "IndexError — เข้าถึงตำแหน่งที่ไม่มีอยู่",
            "desc":  "เข้าถึงสมาชิกใน List/Tuple/String เกินจำนวนที่มีอยู่จริง",
            "tips":  [
                "ตรวจสอบขนาด (length) ก่อนเข้าถึงด้วย index",
                "ระวัง index เริ่มที่ 0 ไม่ใช่ 1",
                "ใช้ for item in list แทนการวน index ถ้าไม่จำเป็นต้องใช้ index"
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
        error["exception_name"],
        {
            "title": error["exception_name"],
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