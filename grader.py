import subprocess
import tempfile
import os
import re
import ast


def ast_check(code, category=""):
    result = {
        "passed":   True,
        "errors":   [],
        "warnings": []
    }

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result["passed"] = False
        result["errors"].append(
            f"SyntaxError: บรรทัดที่ {e.lineno} — {e.msg}"
        )
        return result

    node_types = set()
    for node in ast.walk(tree):
        node_types.add(type(node).__name__)

    if category == "loop":
        has_loop = ("For" in node_types or "While" in node_types)
        if not has_loop:
            result["warnings"].append(
                "⚠️ โจทย์นี้ควรใช้ Loop (for/while) แต่ไม่พบในโค้ดของคุณ"
            )

    if category == "function":
        has_func = "FunctionDef" in node_types
        if not has_func:
            result["warnings"].append(
                "⚠️ โจทย์นี้ควรนิยาม Function (def) แต่ไม่พบในโค้ดของคุณ"
            )

    allowed_short = {"i", "j", "k", "n", "x", "y", "z"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            name = node.id
            if len(name) == 1 and name not in allowed_short:
                result["warnings"].append(
                    f"💡 ตัวแปรชื่อ '{name}' สั้นเกินไป ควรตั้งชื่อที่อ่านแล้วเข้าใจ"
                )
                break

    return result


def run_code(code, input_data="", timeout=2):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name

        result = subprocess.run(
            ["python", temp_path],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.stderr:
            return {"output": "", "error": result.stderr, "is_error": True}

        return {"output": result.stdout, "error": None, "is_error": False}

    except subprocess.TimeoutExpired:
        return {
            "output":   "",
            "error":    "TimeoutError: โค้ดใช้เวลานานเกินไป (เกิน 2 วินาที) อาจเกิดจาก infinite loop",
            "is_error": True
        }

    except Exception as e:
        return {"output": "", "error": str(e), "is_error": True}

    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def extract_error_type(error_message):
    if not error_message:
        return "UnknownError"
    pattern = r"(\w+Error|\w+Exception)"
    match = re.search(pattern, error_message)
    if match:
        return match.group(1)
    if "TimeoutError" in error_message:
        return "TimeoutError"
    return "UnknownError"


def extract_error_line(error_message):
    if not error_message:
        return None
    pattern = r"line (\d+)"
    match = re.search(pattern, error_message)
    if match:
        return int(match.group(1))
    return None


def grade_submission(code, problem_id, user_id, conn):

    # MySQL ต้องสร้าง cursor ก่อนทุกครั้ง
    # ไม่มี conn.execute() แบบ SQLite
    cursor = conn.cursor()

    # ดึงข้อมูลโจทย์ — MySQL ใช้ %s แทน ?
    cursor.execute("SELECT * FROM problems WHERE id = %s", (problem_id,))
    problem  = cursor.fetchone()
    category = problem["category"] if problem else ""

    # ดึง test cases ทั้งหมด
    cursor.execute(
        "SELECT * FROM test_cases WHERE problem_id = %s", (problem_id,)
    )
    test_cases = cursor.fetchall()

    all_passed    = True
    has_error     = False
    error_message = None
    results       = []
    ast_warnings  = []

    # AST check ก่อนรันโค้ดจริง
    ast_result   = ast_check(code, category)
    ast_warnings = ast_result["warnings"]

    if not ast_result["passed"]:
        error_message = "\n".join(ast_result["errors"])
        has_error     = True

        cursor.execute(
            """INSERT INTO submissions
               (user_id, problem_id, code, status)
               VALUES (%s, %s, %s, %s)""",
            (user_id, problem_id, code, "error")
        )
        conn.commit()

        # MySQL ใช้ cursor.lastrowid แทน last_insert_rowid()
        submission_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO error_logs
               (user_id, problem_id, submission_id,
                error_type, error_message, error_line)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, problem_id, submission_id,
             "SyntaxError", error_message, None)
        )
        conn.commit()
        cursor.close()

        return {
            "status":        "error",
            "results":       [],
            "error_message": error_message,
            "error_type":    "SyntaxError",
            "submission_id": submission_id,
            "ast_warnings":  ast_warnings
        }

    # Dynamic Testing
    for tc in test_cases:
        timeout = problem["timeout_sec"] if problem.get("timeout_sec") else 2
        run_result = run_code(code, tc["input_data"], timeout=timeout)

        if run_result["is_error"]:
            has_error     = True
            all_passed    = False
            error_message = run_result["error"]

            results.append({
                "input":    tc["input_data"],
                "expected": tc["expected"],
                "got":      "ERROR",
                "passed":   False,
                "hidden":   tc["is_hidden"]
            })
            break

        else:
            got      = run_result["output"].strip()
            expected = tc["expected"].strip()
            passed   = (got == expected)

            if not passed:
                all_passed = False

            results.append({
                "input":    tc["input_data"],
                "expected": expected,
                "got":      got,
                "passed":   passed,
                "hidden":   tc["is_hidden"]
            })

    if has_error:
        status = "error"
    elif all_passed:
        status = "passed"
    else:
        status = "failed"

    cursor.execute(
        """INSERT INTO submissions
           (user_id, problem_id, code, status)
           VALUES (%s, %s, %s, %s)""",
        (user_id, problem_id, code, status)
    )
    conn.commit()

    # MySQL ใช้ cursor.lastrowid
    submission_id = cursor.lastrowid

    if has_error and error_message:
        error_type = extract_error_type(error_message)
        error_line = extract_error_line(error_message)

        cursor.execute(
            """INSERT INTO error_logs
               (user_id, problem_id, submission_id,
                error_type, error_message, error_line)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, problem_id, submission_id,
             error_type, error_message, error_line)
        )
        conn.commit()

# คำนวณ E_recentN — ดึง 10 submissions ล่าสุดของ user นี้
    N = 10
    cursor.execute(
            """SELECT status FROM submissions
            WHERE user_id = %s
            ORDER BY submitted_at DESC
            LIMIT %s""",
            (user_id, N)
    )
    recent = cursor.fetchall()
    e_recent_n = sum(1 for r in recent if r["status"] == "error")

    cursor.close()

    return {
        "status":        status,
        "results":       results,
        "error_message": error_message,
        "error_type":    extract_error_type(error_message) if error_message else None,
        "submission_id": submission_id,
        "ast_warnings":  ast_warnings,
        "e_recent_n":    e_recent_n
    }


if __name__ == "__main__":
    print("=== ทดสอบ run_code() ===\n")

    result = run_code('print("Hello World")')
    print(f"ทดสอบ 1 — โค้ดถูก:")
    print(f"  output:   {repr(result['output'])}")
    print(f"  is_error: {result['is_error']}\n")

    result = run_code("print(x)")
    print(f"ทดสอบ 2 — NameError:")
    print(f"  error:    {result['error'][:60]}...")
    print(f"  is_error: {result['is_error']}\n")

    result = run_code("print('hello'")
    print(f"ทดสอบ 3 — SyntaxError:")
    print(f"  error_type: {extract_error_type(result['error'])}\n")

    result = run_code("while True: pass")
    print(f"ทดสอบ 4 — Timeout:")
    print(f"  error_type: {extract_error_type(result['error'])}\n")

    result = run_code("a, b = map(int, input().split())\nprint(a + b)", "3 5")
    print(f"ทดสอบ 5 — Input/Output:")
    print(f"  output: {repr(result['output'])}")
    print(f"  คาดหวัง: '8'")
    print(f"  ผ่าน: {result['output'].strip() == '8'}")