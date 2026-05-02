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
from grader import grade_submission  # import ฟังก์ชันตรวจโค้ด

app = Flask(__name__)
app.secret_key = "demo_secret_key_2024"

##  — Helper Functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

### get_current_user()
def get_current_user():
    if "user_id" not in session:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone() # ใช้สำหรับดึงข้อมูลเพียงแถวเดียว 1 row
    conn.close()
    return user

# ─── Routes
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("problems"))

# หน้า login
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = hash_password(request.form["password"])
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("problems"))
    return render_template("login.html")

# หน้าสมัคร
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = hash_password(request.form["password"])
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?,?)",
                (username, password)
            )
            conn.commit()
            flash("สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ")
            return redirect(url_for("login"))
        except:
            flash("ชื่อผู้ใช้นี้มีอยู่แล้ว")
        finally:
            conn.close()
    return render_template("login.html", register=True)

# ออกจากระบบ logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# หน้าโจทย์ problem
@app.route("/problems")
def problems():
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    problem_list = conn.execute("SELECT * FROM problems").fetchall()
    conn.close()
    return render_template("problems.html",
                           problems=problem_list,
                           username=session["username"])

# Route 6 — /problem/\<id\>
@app.route("/problem/<int:problem_id>")
def problem(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    prob = conn.execute("SELECT * FROM problems WHERE id=?", (problem_id,)).fetchone() 
    conn.close()
    if not prob:
        return "ไม่พบโจทย์", 404
    return render_template("problem.html",
                           problem=prob,
                           username=session["username"])

# submit route
@app.route("/submit/<int:problem_id>", methods=["POST"])
def submit(problem_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    code = request.form["code"]
    user_id = session["user_id"]

    conn = get_db()
    prob = conn.execute("SELECT * FROM problems WHERE id=?", (problem_id,)).fetchone()

    result = grade_submission(code, problem_id, user_id, conn)  # ← แก้ตรงนี้

    conn.close()

    return render_template("problem.html",
                           problem=prob,
                           result=result,
                           submitted_code=code,
                           username=session["username"])

# dashboard
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    user_id = session["user_id"]

    total = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE user_id = ?", (user_id,)
    ).fetchone()[0]

    passed = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE user_id = ? AND status = 'passed'", (user_id,)
    ).fetchone()[0]

    errors = conn.execute(
        """SELECT error_type, COUNT(*) as count
           FROM error_logs WHERE user_id=?
           GROUP BY error_type ORDER BY count DESC""",
        (user_id,)
    ).fetchall()

    # ดึง submissions ทุกครั้งตามลำดับเวลา
    # เพื่อคำนวณ PDI สะสม ณ แต่ละจุดเวลา
    all_submissions = conn.execute(
        """SELECT status, submitted_at
           FROM submissions
           WHERE user_id=?
           ORDER BY submitted_at ASC""",
        (user_id,)
    ).fetchall()

    # คำนวณ PDI สะสม ณ แต่ละ submission
    # pdi_timeline เป็น list of dict สำหรับส่งไปให้ Chart.js
    pdi_timeline   = []
    running_total  = 0
    running_passed = 0

    for sub in all_submissions:
        running_total  += 1
        if sub["status"] == "passed":
            running_passed += 1

        # PDI = passed / total ณ จุดนั้น คูณ 100 ให้เป็น %
        pdi_value = round(running_passed / running_total * 100, 1)

        pdi_timeline.append({
            "time":  sub["submitted_at"],   # label แกน X
            "pdi":   pdi_value,             # ค่าแกน Y
            "label": f"ครั้งที่ {running_total}"
        })
    
    # ดึง Error Log ล่าสุด 10 รายการ สำหรับแสดงใน Error History
    # เชื่อม error_logs กับ problems เพื่อรู้ชื่อโจทย์
    recent_errors = conn.execute(
        """SELECT el.id,
                  el.error_type,
                  el.error_message,
                  el.error_line,
                  el.logged_at,
                  p.title as problem_title,
                  p.id    as problem_id
           FROM error_logs el
           JOIN problems p ON el.problem_id = p.id
           WHERE el.user_id = ?
           ORDER BY el.logged_at DESC
           LIMIT 10""",
        (user_id,)
    ).fetchall()
    # JOIN เป็นการเชื่อม 2 ตารางเข้าด้วยกัน
    # ON el.problem_id = p.id คือเงื่อนไขการเชื่อม

    conn.close()
    return render_template("dashboard.html",username=session["username"],
                           total=total,
                           passed=passed,
                           failed=total - passed,
                           errors=errors,
                           pdi_timeline = pdi_timeline,    # ← ส่งไปให้ HTML
                           recent_errors= recent_errors
                           )

# error detail route
@app.route("/error/<int:error_id>")
def error_detail(error_id):
    """
    หน้าแสดงรายละเอียด Error แต่ละครั้ง
    ผู้เรียนกดดูจาก Dashboard แล้วเห็นรายละเอียดเต็มๆ
    รวมถึงโค้ดที่ส่งครั้งนั้น และคำอธิบาย Error Type
    """
    if "user_id" not in session: # เช็คว่า login อยู่รึป่าว
        return redirect(url_for("login"))

    conn    = get_db()
    user_id = session["user_id"]

    # ดึง error log พร้อมข้อมูลโจทย์และโค้ดที่ส่ง
    # ใช้ JOIN 3 ตาราง: error_logs + problems + submissions
    error = conn.execute(
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
           WHERE el.id = ? AND el.user_id = ?""",
        (error_id, user_id)
    ).fetchone()
    conn.close()

    if not error:
        return "ไม่พบข้อมูล", 404
    
    # คำอธิบาย Error แต่ละประเภทเป็นภาษาไทย
    # เก็บเป็น dict ใน Python แล้วส่งไปให้ HTML
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
    # ดึงคำอธิบายของ error_type นี้
    # ถ้าไม่อยู่ใน dict ใช้ข้อมูล default
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

# ─── Init ──
if __name__ == "__main__":
    init_db()
    seed_problems()
    app.run(debug=True)