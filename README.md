# Flood Site Base Map - Python / Flask

เว็บไซต์แผนที่ Site Base สำหรับข้อมูลจาก `Location Site(3).xlsx`

## 1. ติดตั้ง

Windows:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 2. วางไฟล์ Excel

วาง:

```text
Location Site(3).xlsx
```

ไว้ในโฟลเดอร์เดียวกับ `app.py`

## 3. รัน

```bash
python app.py
```

จากนั้นเปิด:

```text
http://127.0.0.1:5000
```

## ความสามารถ

- แสดง Site Base จาก Excel
- รองรับข้อมูลจำนวนมากด้วย MarkerCluster
- ค้นหา Site Code
- ค้นหาชื่อสถานที่
- ค้นหาตำบล / อำเภอ / จังหวัด
- ค้นหาแล้วบินไปยังตำแหน่ง Site
- คลิกหมุดเพื่อดูรายละเอียด
- แสดง Latitude / Longitude
- เปิดตำแหน่งใน Google Maps
- ปุ่มตำแหน่งปัจจุบัน
- Responsive สำหรับโทรศัพท์
- ใช้ Flask เป็น Backend
