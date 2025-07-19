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
    node_id: str
    PM1: float
    PM2_5: float
    PM4: float
    PM10: float
    CO2: float
    temperature: float
    humidity: float

async def verify_node_token(
    node_id: str, 
    node_token: Optional[str] = Header(None, alias="X-Node-Token"),
    db: Session = Depends(get_db)
):
    """ตรวจสอบว่า node_token ถูกต้องสำหรับ node_id ที่ระบุ"""
    if not node_token:
        raise HTTPException(
            status_code=401,
            detail={"status": 0, "message": "Node token is required", "data": {}}
        )

    try:
        node = db.query(Nodes).filter(Nodes.node_id == node_id).first()
        if not node:
            raise HTTPException(
                status_code=404,
                detail={"status": 0, "message": "Node not found", "data": {}}
            )

        stored_token = node.node_token if node.node_token else None
        provided_token = node_token if node_token else None
        
        if not stored_token or stored_token != provided_token:
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
    node_id: str,
    user_id: int,
    db: Session = Depends(get_db)
):
    """ตรวจสอบว่าผู้ใช้มีสิทธิ์เข้าถึงข้อมูลของ node นี้"""
    node = db.query(Nodes).filter(
        Nodes.node_id == node_id,
        Nodes.user_id == user_id
    ).first()
    
    if not node:
        raise HTTPException(
            status_code=403,
            detail={"status": 0, "message": "Access denied to this node", "data": {}}
        )
    
    return node

async def process_aggregated_query(query: str, period: str, node_id: str):
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
                "node_id": node_id,
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

@aqi_router.post("/", summary="Submit Air Quality Data")
async def submit_air_quality_data(
    data: AirQualityData,
    node_token: str = Header(..., alias="X-Node-Token"),
    db: Session = Depends(get_db)
):
    """Submit air quality data to InfluxDB with node authentication"""
    try:
        logger.info(f"Received data for node: {data.node_id}")

        if not data.node_id:
            raise HTTPException(
                status_code=400,
                detail={"status": 0, "message": "Missing node ID", "data": {}}
            )

        node = await verify_node_token(data.node_id, node_token, db)
        if not node:
            logger.error(f"Node verification failed: {data.node_id}")
            raise HTTPException(
                status_code=401,
                detail={"status": 0, "message": "Invalid node token", "data": {}}
            )

        try:
            point = (
                Point("air_quality")
                .tag("node_id", data.node_id)
                .field("PM1", float(data.PM1))
                .field("PM2_5", float(data.PM2_5))
                .field("PM4", float(data.PM4))
                .field("PM10", float(data.PM10))
                .field("CO2", float(data.CO2))
                .field("temperature", float(data.temperature))
                .field("humidity", float(data.humidity))
            )
            write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            
            logger.info(f"Data recorded successfully for node: {data.node_id}")
            return {
                "status": 1,
                "message": "Air quality data recorded successfully",
                "data": {
                    "node_id": data.node_id,
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
    node_id: str, 
    hours: int = 1,
    user_id: int = None,
    db: Session = Depends(get_db)
):
    """ดึงข้อมูลตามช่วงเวลาที่กำหนด (ต้องเป็นเจ้าของ node)"""
    try:
        if user_id:
            await verify_node_access(node_id, user_id, db)
        
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
                |> filter(fn: (r) => r["node_id"] == "{node_id}")
                |> aggregateWindow(every: {hours}h, fn: mean, createEmpty: false)
                |> yield(name: "mean")
        """
        return await process_aggregated_query(query, f"{hours}h", node_id)
    except Exception as e:
        raise handle_query_error(e)

@aqi_router.get("/latest/{node_id}", summary="Get Latest Air Quality Reading")
async def get_latest_air_quality(
    node_id: str,
    user_id: int = None,
    db: Session = Depends(get_db)
):
    """ดึงข้อมูลล่าสุด"""
    try:
        if user_id:
            await verify_node_access(node_id, user_id, db)
            
        query = f"""
            from(bucket: "{INFLUXDB_BUCKET}")
                |> range(start: -1h)
                |> filter(fn: (r) => r["_measurement"] == "air_quality")
                |> filter(fn: (r) => r["_field"] == "CO2" or 
                                   r["_field"] == "PM1" or 
                                   r["_field"] == "PM10" or 
                                   r["_field"] == "PM2_5" or 
                                   r["_field"] == "PM4" or 
                                   r["_field"] == "humidity" or 
                                   r["_field"] == "temperature")
                |> filter(fn: (r) => r["node_id"] == "{node_id}")
                |> last()
        """
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        data = []
        
        for table in result:
            for record in table.records:
                data.append({
                    "field": record.get_field(),
                    "value": round(record.get_value(), 2),
                    "timestamp": record.get_time().astimezone(pytz.timezone("Asia/Bangkok")).isoformat()
                })
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail={"status": 0, "message": "ไม่พบข้อมูลล่าสุด", "data": {}}
            )
        
        return {
            "status": 1,
            "message": "ดึงข้อมูลล่าสุดสำเร็จ",
            "data": data,
            "metadata": {
                "node_id": node_id,
                "timezone": "Asia/Bangkok"
            }
        }
    except Exception as e:
        raise handle_query_error(e)

@aqi_router.get("/aqi/1hour/{node_id}", summary="Get 1 Hour AQI PM2.5")
async def get_aqi_1hour(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)

    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -2h)
            |> filter(fn: (r) => r["_measurement"] == "AQI")
            |> filter(fn: (r) => r["_field"] == "PM2_5_AQI_1h")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "aqi_1h", node_id)

@aqi_router.get("/aqi/24hours/{node_id}", summary="Get 24 Hours AQI PM2.5")
async def get_aqi_24hours(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)

    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -2d)
            |> filter(fn: (r) => r["_measurement"] == "AQI")
            |> filter(fn: (r) => r["_field"] == "PM2_5_AQI_1d")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "aqi_24h", node_id)

@aqi_router.get("/aqi/7days/{node_id}", summary="Get 7 Days AQI PM2.5")
async def get_aqi_7days(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)

    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -8d)
            |> filter(fn: (r) => r["_measurement"] == "AQI")
            |> filter(fn: (r) => r["_field"] == "PM2_5_AQI_7d")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "aqi_7d", node_id)


@aqi_router.get("/aqi/30days/{node_id}", summary="Get 30 Days AQI PM2.5")
async def get_aqi_30days(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)

    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -31d)
            |> filter(fn: (r) => r["_measurement"] == "AQI")
            |> filter(fn: (r) => r["_field"] == "PM2_5_AQI_30d")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "aqi_30d", node_id)


@aqi_router.get("/aggregated/{node_id}", summary="Get Aggregated Data")
async def get_aggregated_data(
    node_id: str,
    timeframe: str = "hourly",
    user_id: int = None,
    db: Session = Depends(get_db)
):
    """ดึงข้อมูลแบบรวมตามกรอบเวลา"""
    try:
        if user_id:
            await verify_node_access(node_id, user_id, db)
        
        timeframe_config = {
            "hourly": ("-24h", "1h"),
            "daily": ("-30d", "1d"),
            "weekly": ("-12w", "7d"),
            "monthly": ("-12mo", "30d")
        }
        
        if timeframe not in timeframe_config:
            raise HTTPException(
                status_code=400,
                detail={"status": 0, "message": "Invalid timeframe. Use: hourly, daily, weekly, monthly", "data": {}}
            )
        
        time_range, window = timeframe_config[timeframe]
        
        query = f"""
            from(bucket: "{INFLUXDB_BUCKET}")
                |> range(start: {time_range})
                |> filter(fn: (r) => r["_measurement"] == "air_quality")
                |> filter(fn: (r) => r["node_id"] == "{node_id}")
                |> filter(fn: (r) => r["_field"] == "CO2" or 
                                   r["_field"] == "PM1" or 
                                   r["_field"] == "PM10" or 
                                   r["_field"] == "PM2_5" or 
                                   r["_field"] == "PM4" or 
                                   r["_field"] == "humidity" or 
                                   r["_field"] == "temperature")
                |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
                |> yield(name: "mean")
        """
        
        return await process_aggregated_query(query, timeframe, node_id)
        
    except Exception as e:
        raise handle_query_error(e)

@aqi_router.get("/summary/1hour/{node_id}", summary="Get 1 Hour Summary")
async def get_summary_1hour(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -2h)
            |> filter(fn: (r) => r["_measurement"] == "Summary")
            |> filter(fn: (r) => r["type"] == "summary_1h")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "summary_1h", node_id)

@aqi_router.get("/summary/1day/{node_id}", summary="Get 1 Day Summary")
async def get_summary_1day(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -2d)
            |> filter(fn: (r) => r["_measurement"] == "Summary")
            |> filter(fn: (r) => r["type"] == "summary_1d")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "summary_1d", node_id)

@aqi_router.get("/summary/7days/{node_id}", summary="Get 7 Days Summary")
async def get_summary_7days(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -8d)
            |> filter(fn: (r) => r["_measurement"] == "Summary")
            |> filter(fn: (r) => r["type"] == "summary_7d")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "summary_7d", node_id)

@aqi_router.get("/summary/30days/{node_id}", summary="Get 30 Days Summary")
async def get_summary_30days(node_id: str, user_id: int = None, db: Session = Depends(get_db)):
    if user_id:
        await verify_node_access(node_id, user_id, db)
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
            |> range(start: -31d)
            |> filter(fn: (r) => r["_measurement"] == "Summary")
            |> filter(fn: (r) => r["type"] == "summary_30d")
            |> filter(fn: (r) => r["node_id"] == "{node_id}")
    '''
    return await process_aggregated_query(query, "summary_30d", node_id)