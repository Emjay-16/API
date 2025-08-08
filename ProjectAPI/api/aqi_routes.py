from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from sqlalchemy.orm import Session
import pytz
import os
from dotenv import load_dotenv
from typing import Optional
import logging
from datetime import datetime

# from models import *
# from database import *

from api.models import *
from api.database import *

load_dotenv()

INFLUXDB_URL = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET")


write_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = write_client.write_api(write_options=SYNCHRONOUS)
query_api = write_client.query_api()

logger = logging.getLogger(__name__)

aqi_router = APIRouter(prefix="/aqi", tags=["AQI - Air Quality Index"])

class AirQualityData(BaseModel):
    PM1: float
    PM2_5: float
    PM4: float
    PM10: float
    CO2: float
    temperature: float
    humidity: float

async def verify_node_token(
    node_name: Optional[str] = None,
    node_token: Optional[str] = Header(None, alias="X-Node-Token"),
    db: Session = Depends(get_db)
):
    """ตรวจสอบ node token (โดยจะค้นหาจาก node_name หรือจาก token อย่างเดียวก็ได้)"""
    if not node_token:
        raise HTTPException(
            status_code=401,
            detail={"status": 0, "message": "Node token is required", "data": {}}
        )

    try:
        if node_name:
            node = db.query(Nodes).filter(Nodes.node_name == node_name).first()
        else:
            node = db.query(Nodes).filter(Nodes.node_token == node_token).first()
        if not node:
            raise HTTPException(
                status_code=404,
                detail={"status": 0, "message": "Node not found or invalid token", "data": {}}
            )

        if node_name and node.node_token != node_token:
            raise HTTPException(
                status_code=403,
                detail={"status": 0, "message": "Invalid node token", "data": {}}
            )
        
        return node

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"status": 0, "message": f"Token verification error: {str(e)}", "data": {}}
        )

async def verify_node_access(
    node_name: str,
    user_id: int,
    db: Session = Depends(get_db)
):
    """ตรวจสอบว่าผู้ใช้มีสิทธิ์เข้าถึงข้อมูลของ node นี้"""
    node = db.query(Nodes).filter(
        Nodes.node_name == node_name,
        Nodes.user_id == user_id
    ).first()
    
    if not node:
        raise HTTPException(
            status_code=403,
            detail={"status": 0, "message": "Access denied to this node", "data": {}}
        )
    
    return node

async def process_aggregated_query(query: str, period: str, node_name: str):
    """ฟังก์ชันสำหรับประมวลผลข้อมูล query"""
    try:
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        data = []
        
        for table in result:
            for record in table.records:
                data_point = {
                    "field": record.values.get("_field", ""),
                    "value": round(float(record.values.get("_value", 0)), 2),
                    "timestamp": record.values.get("_time", "").astimezone(pytz.timezone("Asia/Bangkok")).isoformat()
                }
                data.append(data_point)
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": 0,
                    "message": f"ไม่พบข้อมูลสำหรับช่วงเวลา {period}",
                    "data": {}
                }
            )

        return {
            "status": 1,
            "message": f"ดึงข้อมูล {period} สำเร็จ",
            "data": data,
            "metadata": {
                "node_name": node_name,
                "period": period,
                "count": len(data),
                "timezone": "Asia/Bangkok"
            }
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "status": 0,
                "message": f"เกิดข้อผิดพลาดในการดึงข้อมูล: {str(e)}",
                "data": {}
            }
        )

def handle_query_error(e: Exception):
    """ฟังก์ชันจัดการ error"""
    if isinstance(e, HTTPException):
        raise e
    raise HTTPException(
        status_code=500,
        detail={
            "status": 0,
            "message": f"เกิดข้อผิดพลาด: {str(e)}",
            "data": {}
        }
    )

@aqi_router.post("/", summary="Submit Air Quality Data (Token Only)")
async def submit_air_quality_data(
    data: AirQualityData,
    node_token: str = Header(..., alias="X-Node-Token"),
    db: Session = Depends(get_db)
):
    """Submit air quality data to InfluxDB. Node name is derived from token."""
    try:
        node = await verify_node_token(node_token=node_token, db=db)
        if not node:
            logger.error(f"Node verification failed by token.")
            raise HTTPException(
                status_code=401,
                detail={"status": 0, "message": "Invalid node token", "data": {}}
            )
        node_name = node.node_name

        try:
            point = (
                Point("air_quality")
                .tag("node_name", node_name)
                .field("PM1", float(data.PM1))
                .field("PM2_5", float(data.PM2_5))
                .field("PM4", float(data.PM4))
                .field("PM10", float(data.PM10))
                .field("CO2", float(data.CO2))
                .field("temperature", float(data.temperature))
                .field("humidity", float(data.humidity))
            )
            write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            
            logger.info(f"Data recorded for node: {node_name}")
            return {
                "status": 1,
                "message": "Air quality data recorded successfully",
                "data": {
                    "node_name": node_name,
                    "timestamp": datetime.now().isoformat()
                }
            }

        except Exception as e:
            logger.error(f"InfluxDB write error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={"status": 0, "message": "Failed to write data", "data": {}}
            )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"status": 0, "message": "Internal server error", "data": {}}
        )

@aqi_router.get("/", summary="Get Air Quality Data")
async def get_air_quality_data(
    node_name: str, 
    hours: int = 1,
    user_id: int = None,
    db: Session = Depends(get_db)
):
    """ดึงข้อมูลตามช่วงเวลาที่กำหนด (ต้องเป็นเจ้าของ node)"""
    try:
        if user_id:
            await verify_node_access(node_name, user_id, db)
        
        query = f"""
            from(bucket: "{INFLUXDB_BUCKET}")
                |> range(start: -{hours}h)
                |> filter(fn: (r) => r["_measurement"] == "air_quality")
                |> filter(fn: (r) => r["_field"] == "CO2" or 
                                   r["_field"] == "PM1" or 
                                   r["_field"] == "PM10" or 
                                   r["_field"] == "PM2_5" or 
                                   r["_field"] == "PM4" or 
                                   r["_field"] == "humidity" or 
                                   r["_field"] == "temperature")
                |> filter(fn: (r) => r["node_name"] == "{node_name}")
                |> aggregateWindow(every: {hours}h, fn: mean, createEmpty: false)
                |> yield(name: "mean")
        """
        return await process_aggregated_query(query, f"{hours}h", node_name)
    except Exception as e:
        raise handle_query_error(e)

@aqi_router.get("/months/{node_name}", summary="Get months that have data")
async def get_months_with_data(
    node_name: str,
    db: Session = Depends(get_db)
):
    """
    แสดงรายชื่อเดือน (yyyy-mm) ที่มีข้อมูล air_quality ของ node_name นี้ใน InfluxDB
    """
    try:
        query = f'''
            from(bucket: "{INFLUXDB_BUCKET}")
              |> range(start: -5y)
              |> filter(fn: (r) => r["_measurement"] == "air_quality")
              |> filter(fn: (r) => r["node_name"] == "{node_name}")
              |> keep(columns: ["_time"])
              |> group()
        '''
        
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        months_set = set()
        for table in result:
            for record in table.records:
                time_value = record.values.get("_time")
                if time_value:
                    month_str = time_value.strftime("%Y-%m")
                    months_set.add(month_str)

        months = sorted(list(months_set))
        
        return {
            "status": 1,
            "message": "ดึงเดือนที่มีข้อมูลสำเร็จ",
            "data": months
        }
        
    except Exception as e:
        raise handle_query_error(e)

@aqi_router.get("/daily/{node_name}/{month}", summary="Get daily summary air quality data for a node by month")
async def get_daily_summary_24h(
    node_name: str,
    month: str,
    db: Session = Depends(get_db)
):
    """
    ดึงข้อมูลสรุป air_quality รายวัน (AirQualitySummary24h) ของ node_name ตามเดือน (month: yyyy-mm)
    """
    try:
        from datetime import datetime, timedelta
        year, mon = map(int, month.split('-'))
        start_date = datetime(year, mon, 1)
        if mon == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, mon + 1, 1) - timedelta(seconds=1)

        query = f'''
            from(bucket: "{INFLUXDB_BUCKET}")
              |> range(start: {start_date.isoformat()}Z, stop: {end_date.isoformat()}Z)
              |> filter(fn: (r) => r["_measurement"] == "AirQualitySummary24h")
              |> filter(fn: (r) => r["node_name"] == "{node_name}")
        '''
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        
        daily_data = {}
        for table in result:
            for record in table.records:
                date_str = record.get_time().strftime("%Y-%m-%d")
                field = record.values.get("_field")
                value = record.values.get("_value")
                
                if date_str not in daily_data:
                    daily_data[date_str] = {"date": date_str}
                
                if value is not None and isinstance(value, (int, float)):
                    if str(value).lower() in ['nan', 'inf', '-inf'] or value < 0:
                        daily_data[date_str][field] = 0.0
                    else:
                        daily_data[date_str][field] = round(float(value), 2)
                else:
                    daily_data[date_str][field] = 0.0
        
        data = []
        for date_str in sorted(daily_data.keys()):
            day_record = daily_data[date_str]
            data.append({
                "date": day_record.get("date"),
                "AQI": day_record.get("AQI", 0.0),
                "PM1": day_record.get("PM1", 0.0),
                "PM2_5": day_record.get("PM2_5", 0.0),
                "PM4": day_record.get("PM4", 0.0),
                "PM10": day_record.get("PM10", 0.0),
                "CO2": day_record.get("CO2", 0.0),
                "temperature": day_record.get("temperature", 0.0),
                "humidity": day_record.get("humidity", 0.0),
            })
        
        return {
            "status": 1,
            "message": "ดึงข้อมูลสรุปรายวันสำเร็จ",
            "data": data,
            "metadata": {
                "node_name": node_name,
                "month": month,
                "total_days": len(data)
            }
        }
    except Exception as e:
        raise handle_query_error(e)

@aqi_router.get("/hourly/{node_name}/{date}", summary="Get hourly air quality data for a node by date")
async def get_hourly_summary(
    node_name: str,
    date: str,
    db: Session = Depends(get_db)
):
    """
    ดึงข้อมูลสรุป air_quality รายชั่วโมง (AirQualitySummary) ของ node_name ตามวันที่ (date: yyyy-mm-dd)
    """
    try:
        from datetime import datetime, timedelta
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        start_date = date_obj
        end_date = date_obj + timedelta(days=1) - timedelta(seconds=1)

        query = f'''
            from(bucket: "{INFLUXDB_BUCKET}")
              |> range(start: {start_date.isoformat()}Z, stop: {end_date.isoformat()}Z)
              |> filter(fn: (r) => r["_measurement"] == "AirQualitySummary")
              |> filter(fn: (r) => r["node_name"] == "{node_name}")
        '''
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        
        hourly_data = {}
        for table in result:
            for record in table.records:
                time_obj = record.get_time()
                hour_str = time_obj.strftime("%H:%M")
                datetime_str = time_obj.strftime("%Y-%m-%d %H:%M:%S")
                field = record.values.get("_field")
                value = record.values.get("_value")
                
                if hour_str not in hourly_data:
                    hourly_data[hour_str] = {
                        "time": hour_str,
                        "datetime": datetime_str
                    }
                
                if value is not None and isinstance(value, (int, float)):
                    if str(value).lower() in ['nan', 'inf', '-inf'] or value < 0:
                        hourly_data[hour_str][field] = 0.0
                    else:
                        hourly_data[hour_str][field] = round(float(value), 2)
                else:
                    hourly_data[hour_str][field] = 0.0
        
        data = []
        for hour_str in sorted(hourly_data.keys()):
            hour_record = hourly_data[hour_str]
            data.append({
                "time": hour_record.get("time"),
                "datetime": hour_record.get("datetime"),
                "AQI": hour_record.get("AQI", 0.0),
                "PM1": hour_record.get("PM1", 0.0),
                "PM2_5": hour_record.get("PM2_5", 0.0),
                "PM4": hour_record.get("PM4", 0.0),
                "PM10": hour_record.get("PM10", 0.0),
                "CO2": hour_record.get("CO2", 0.0),
                "temperature": hour_record.get("temperature", 0.0),
                "humidity": hour_record.get("humidity", 0.0),
            })
        
        return {
            "status": 1,
            "message": "ดึงข้อมูลสรุปรายชั่วโมงสำเร็จ",
            "data": data,
            "metadata": {
                "node_name": node_name,
                "date": date,
                "total_hours": len(data)
            }
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"status": 0, "message": "รูปแบบวันที่ไม่ถูกต้อง ใช้ YYYY-MM-DD", "data": {}}
        )
    except Exception as e:
        raise handle_query_error(e)

@aqi_router.get("/graph/{node_name}/{time_range}", summary="Get graph data by time range")
async def get_graph_data(
    node_name: str,
    time_range: str,
    data_type: str = "AQI",
    db: Session = Depends(get_db)
):
    """
    ดึงข้อมูลสำหรับแสดงกราฟตาม time range ที่กำหนด
    - time_range: "24h" (24 ชั่วโมง), "7d" (7 วัน), "30d" (30 วัน)
    - data_type: ประเภทข้อมูลที่ต้องการ (AQI, PM1, PM2_5, PM4, PM10, CO2, temperature, humidity)
    """
    try:
        valid_time_ranges = ["24h", "7d", "30d"]
        if time_range not in valid_time_ranges:
            raise HTTPException(
                status_code=400,
                detail={"status": 0, "message": f"time_range ต้องเป็น {valid_time_ranges}", "data": {}}
            )
        
        valid_data_types = ["AQI", "PM1", "PM2_5", "PM4", "PM10", "CO2", "temperature", "humidity"]
        if data_type not in valid_data_types:
            raise HTTPException(
                status_code=400,
                detail={"status": 0, "message": f"data_type ต้องเป็น {valid_data_types}", "data": {}}
            )

        if time_range == "24h":
            window = "1h"
            measurement = "AirQualitySummary"
        elif time_range == "7d":
            window = "1d"
            measurement = "AirQualitySummary24h"
        else:
            window = "1d"
            measurement = "AirQualitySummary24h"

        query = f'''
            from(bucket: "{INFLUXDB_BUCKET}")
              |> range(start: -{time_range})
              |> filter(fn: (r) => r["_measurement"] == "{measurement}")
              |> filter(fn: (r) => r["node_name"] == "{node_name}")
              |> filter(fn: (r) => r["_field"] == "{data_type}")
              |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
              |> sort(columns: ["_time"])
        '''
        
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        
        graph_data = []
        for table in result:
            for record in table.records:
                time_obj = record.get_time()
                value = record.values.get("_value")
                
                if value is not None and isinstance(value, (int, float)):
                    if str(value).lower() in ['nan', 'inf', '-inf'] or value < 0:
                        clean_value = 0.0
                    else:
                        clean_value = round(float(value), 2)
                else:
                    clean_value = 0.0
                
                if time_range == "24h":
                    time_label = time_obj.strftime("%H:%M")
                    datetime_str = time_obj.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    time_label = time_obj.strftime("%m-%d")
                    datetime_str = time_obj.strftime("%Y-%m-%d")
                
                graph_data.append({
                    "time": time_label,
                    "datetime": datetime_str,
                    "value": clean_value,
                    "timestamp": time_obj.isoformat()
                })
        
        values = [point["value"] for point in graph_data if point["value"] > 0]
        stats = {}
        if values:
            stats = {
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "avg": round(sum(values) / len(values), 2),
                "count": len(values)
            }
        else:
            stats = {"min": 0, "max": 0, "avg": 0, "count": 0}
        
        return {
            "status": 1,
            "message": f"ดึงข้อมูลกราฟ {data_type} สำหรับ {time_range} สำเร็จ",
            "data": graph_data,
            "metadata": {
                "node_name": node_name,
                "time_range": time_range,
                "data_type": data_type,
                "window": window,
                "measurement": measurement,
                "total_points": len(graph_data),
                "statistics": stats
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise handle_query_error(e)
