# CHANGELOG

รายการใหม่อยู่บนสุด ทุกรายการใช้รูปแบบเดียวกัน

## รูปแบบ
```
### YYYY-MM-DD ชื่อสั้นของงาน
- ไฟล์ที่แก้: path (ชื่อฟังก์ชัน)
- แก้อย่างไร:
- เหตุผล:
- เกี่ยวกับโครงร่าง: หัวข้อ/ตารางที่
- วิธีตรวจ: คำสั่งหรือขั้นตอนที่รันแล้วเห็นผล
```

### 2026-10-28 ปรับ UI, ลบ PDI, แก้ค่า dashboard, Error Frequency เป็นร้อยละ
- ไฟล์ที่แก้: grader.py (grade_submission, calc_performance_metrics, classify_error_type), app.py (route /dashboard), database.py (migrate_legacy_status_and_error_type), templates/dashboard.html, templates/_icons.html, static/css/*
- แก้อย่างไร: ลบ PDI ทั้งหมด, error_logs บันทึกเฉพาะ Execution Error, เพิ่ม migration แปลง status/error_type แบบเก่า, จัด TabError เข้า IndentationError, กราฟ Error Frequency แสดงเป็นร้อยละของ error ทั้งหมด, เพิ่ม Dockerfile และ test_docker.py
- เหตุผล: ให้ตรงกับโครงร่างฉบับล่าสุด และแก้ค่า dashboard ที่ไม่ตรง
- เกี่ยวกับโครงร่าง: 5.1.1, ตารางที่ 4, ตารางที่ 5, 5.5 ข้อ 2
- วิธีตรวจ: เปิด /dashboard ของ user ที่มีข้อมูล ผลรวมร้อยละของกราฟ Error Frequency ต้องได้ 100
