from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import logging
from fastapi.background import BackgroundTasks
from datetime import datetime, timedelta
import pytz

from api.models import *
from api.database import *
from api.email_service import send_welcome_email, send_daily_aqi_email
from api.aqi_routes import *


# Setup logger
logger = logging.getLogger(__name__)

notification_router = APIRouter(prefix="/notification", tags=["Notification"])

class NotificationRequest(BaseModel):
    email: EmailStr
    location: str

class CustomHTTPException(HTTPException):
    def __init__(self, status_code: int, message: str):
        super().__init__(
            status_code=status_code,
            detail={
                "status": 0,
                "message": message,
                "data": {}
            }
        )

def handle_error(e: Exception):
    """ฟังก์ชันจัดการ error"""
    if isinstance(e, HTTPException):
        raise e
    logger.error(f"Unexpected error: {str(e)}")
    raise HTTPException(
        status_code=500,
        detail={
            "status": 0,
            "message": f"เกิดข้อผิดพลาด: {str(e)}",
            "data": {}
        }
    )

def validate_location(location: str, db: Session):
    """ตรวจสอบว่า location มี node อยู่หรือไม่"""
    node_exists = db.query(Nodes).filter(Nodes.location == location).first()
    return node_exists is not None

def get_avg_data_for_location_at_7am(location: str, db: Session):
    """ดึงข้อมูลทุกฟิลด์ของ location ตอน 7 โมงเช้า (จาก AirQualitySummary)"""
    nodes = db.query(Nodes).filter(Nodes.location == location).all()
    node_names = [n.node_name for n in nodes]
    if not node_names:
        return None

    tz = pytz.timezone("Asia/Bangkok")
    now = datetime.now(tz)
    seven_am = now.replace(hour=7, minute=0, second=0, microsecond=0)
    seven_am_utc = seven_am.astimezone(pytz.utc)
    seven_am_str = seven_am_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    from api.aqi_routes import query_api, INFLUXDB_ORG, INFLUXDB_BUCKET
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: {seven_am_str}, stop: {seven_am_str})
          |> filter(fn: (r) => r["_measurement"] == "AirQualitySummary")
          |> filter(fn: (r) => r["_field"] == "AQI" or r["_field"] == "PM1" or r["_field"] == "PM2.5" or r["_field"] == "PM4" or r["_field"] == "PM10" or r["_field"] == "Temperature" or r["_field"] == "Humidity")
          |> filter(fn: (r) => { ' or '.join([f'r["node_name"] == "{name}"' for name in node_names]) })
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    
    result = query_api.query(org=INFLUXDB_ORG, query=query)
    
    data = {}
    
    for table in result:
        for record in table.records:
            values = record.values
            for field in ["AQI", "PM1", "PM2.5", "PM4", "PM10", "Temperature", "Humidity"]:
                if field in values and values[field] is not None:
                    if field not in data:
                        data[field] = []
                    if isinstance(values[field], (int, float)):
                        if field in ["Temperature", "Humidity"] or values[field] >= 0:
                            data[field].append(float(values[field]))
    
    result_data = {}
    for field, values in data.items():
        if values:
            result_data[field] = round(sum(values) / len(values), 2)
        else:
            result_data[field] = None
    
    if not any(v is not None for v in result_data.values()):
        return None
        
    return result_data

def send_daily_aqi_email_to_subscribers(db: Session):
    """ส่งอีเมลแจ้งเตือนข้อมูลคุณภาพอากาศเฉลี่ย 7 โมงเช้าให้ผู้สมัครรับแจ้งเตือนทุก location"""
    locations = db.query(Notification.location).filter(Notification.is_active == True).distinct().all()
    for loc in locations:
        location = loc[0]
        avg_data = get_avg_data_for_location_at_7am(location, db)
        if avg_data is None:
            continue
        subscribers = db.query(Notification).filter(Notification.location == location, Notification.is_active == True).all()
        for sub in subscribers:
            send_daily_aqi_email(sub.email, location, avg_data)
            
@notification_router.get("/locations", summary="Get available locations for notifications")
async def get_available_locations(
    db: Session = Depends(get_db)
):
    """ดึงรายการ location ที่มี node อยู่สำหรับให้เลือกรับการแจ้งเตือน"""
    try:
        locations = db.query(Nodes.location).distinct().all()
        
        result_locations = []
        for loc in locations:
            location_name = loc[0]
            
            total_nodes = db.query(Nodes).filter(Nodes.location == location_name).count()
            
            online_nodes = db.query(Nodes).filter(
                Nodes.location == location_name,
                Nodes.status == STATUS_ONLINE
            ).count()
            
            result_locations.append({
                "location": location_name,
                "display_name": f"{location_name} ({online_nodes}/{total_nodes} nodes online)",
                "total_nodes": total_nodes,
                "online_nodes": online_nodes,
                "available": online_nodes > 0
            })
        
        if not result_locations:
            return {
                "status": 0,
                "message": "ยังไม่มี location ที่พร้อมให้บริการ",
                "data": []
            }
        
        result_locations.sort(key=lambda x: x["location"])
        
        return {
            "status": 1,
            "message": "ดึงรายการ location สำเร็จ",
            "data": result_locations,
            "metadata": {
                "total_locations": len(result_locations),
                "available_locations": len([l for l in result_locations if l["available"]])
            }
        }
    except Exception as e:
        raise handle_error(e)

@notification_router.post("/subscribe", summary="Subscribe to email notifications")
async def subscribe_notification(
    request: NotificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """สมัครรับการแจ้งเตือนทางอีเมล"""
    try:
        if not request.location or request.location.strip() == "":
            raise CustomHTTPException(
                status_code=400,
                message="กรุณาเลือกพื้นที่สำหรับรับการแจ้งเตือน"
            )
        
        if not validate_location(request.location, db):
            available_locations = db.query(Nodes.location).distinct().all()
            location_list = [loc[0] for loc in available_locations]
            
            raise CustomHTTPException(
                status_code=400,
                message=f"ไม่พบ node ใน location: {request.location}. พื้นที่ที่มี: {', '.join(location_list)}"
            )
        
        existing_notification = db.query(Notification).filter(
            Notification.email == request.email
        ).first()

        is_new_subscription = False

        if existing_notification:
            if existing_notification.is_active:
                if existing_notification.location != request.location:
                    existing_notification.location = request.location
                    existing_notification.updated_at = datetime.utcnow()
                    db.commit()
                    db.refresh(existing_notification)
                    
                    return {
                        "status": 1,
                        "message": f"อัปเดท location เป็น {request.location} แล้ว",
                        "data": {
                            "email_id": existing_notification.email_id,
                            "email": existing_notification.email,
                            "is_active": existing_notification.is_active,
                            "location": existing_notification.location,
                            "updated_at": existing_notification.updated_at.isoformat() if existing_notification.updated_at else None
                        }
                    }
                else:
                    return {
                        "status": 1,
                        "message": "อีเมลนี้ได้สมัครรับการแจ้งเตือนแล้ว",
                        "data": {
                            "email_id": existing_notification.email_id,
                            "email": existing_notification.email,
                            "is_active": existing_notification.is_active,
                            "location": existing_notification.location,
                            "created_at": existing_notification.created_at.isoformat() if existing_notification.created_at else None
                        }
                    }
            else:
                existing_notification.is_active = True
                existing_notification.location = request.location
                existing_notification.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(existing_notification)
                is_new_subscription = True
                
                response_data = {
                    "status": 1,
                    "message": "เปิดใช้งานการแจ้งเตือนทางอีเมลแล้ว",
                    "data": {
                        "email_id": existing_notification.email_id,
                        "email": existing_notification.email,
                        "is_active": existing_notification.is_active,
                        "location": existing_notification.location,
                        "updated_at": existing_notification.updated_at.isoformat() if existing_notification.updated_at else None
                    }
                }
        else:
            new_notification = Notification(
                email=request.email,
                location=request.location,
                is_active=True
            )

            db.add(new_notification)
            db.commit()
            db.refresh(new_notification)
            is_new_subscription = True

            response_data = {
                "status": 1,
                "message": "สมัครรับการแจ้งเตือนทางอีเมลสำเร็จ",
                "data": {
                    "email_id": new_notification.email_id,
                    "email": new_notification.email,
                    "is_active": new_notification.is_active,
                    "location": new_notification.location,
                    "created_at": new_notification.created_at.isoformat() if new_notification.created_at else None
                }
            }

        if is_new_subscription:
            background_tasks.add_task(send_welcome_email, request.email, request.location)
            response_data["message"] += " - จะได้รับอีเมลยืนยันภายใน 5 นาที"

        return response_data

    except Exception as e:
        db.rollback()
        raise handle_error(e)

@notification_router.get("/subscribers/{location}", summary="Get subscribers by location")
async def get_subscribers_by_location(
    location: str,
    db: Session = Depends(get_db)
):
    """ดึงรายการผู้สมัครรับการแจ้งเตือนตาม location (สำหรับ admin)"""
    try:
        subscribers = db.query(Notification).filter(
            Notification.location == location,
            Notification.is_active == True
        ).all()
        
        subscriber_list = [{
            "email_id": sub.email_id,
            "email": sub.email,
            "location": sub.location,
            "created_at": sub.created_at.isoformat() if sub.created_at else None
        } for sub in subscribers]
        
        return {
            "status": 1,
            "message": f"ดึงรายการผู้สมัครใน {location} สำเร็จ",
            "data": subscriber_list,
            "metadata": {
                "location": location,
                "total_subscribers": len(subscriber_list)
            }
        }
    except Exception as e:
        raise handle_error(e)

