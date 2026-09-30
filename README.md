# Flood Site Base Operations Dashboard

Dashboard สำหรับ Site Base เฉพาะ 4 จังหวัด:
- กรุงเทพมหานคร
- ปทุมธานี
- นนทบุรี
- สมุทรปราการ

## Job Monitor Excel
สามารถ Upload Excel Job Monitor ได้จากหน้า Dashboard โดยระบบจะ:
1. ตรวจหา column Title Job / Job Title / Title อัตโนมัติ
2. วิเคราะห์ Job ID จาก Title Job
3. วิเคราะห์ Site Code จาก Title Job
4. วิเคราะห์ Latitude / Longitude จาก Title Job โดยรองรับรูปแบบ `Latitude: 13.x, Longitude: 100.x` และ `13.x, 100.x`
5. ถ้า Title ไม่มีพิกัด แต่พบ Site Code ใน Site Base ระบบจะเติมพิกัดจาก Site Base และระบุ Coordinate Source = `site_base`
6. Match Site Code กับฐานข้อมูล Site Base 4 จังหวัด
7. แสดง Job เป็นหมุดสีม่วงบนแผนที่
8. แสดงตาราง Job และ Export ผลวิเคราะห์เป็น Excel

รองรับไฟล์ `.xlsx`, `.xlsm`, `.xltx`, `.xltm` และอ่าน worksheet แรกของไฟล์

## Run

```powershell
pip install -r requirements.txt
python app.py
```

เปิด `http://127.0.0.1:5000`
