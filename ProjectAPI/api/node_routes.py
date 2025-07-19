from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import secrets
import pytz
import os
from contextlib import contextmanager

from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError

from api.models import *
from api.database import *
from api.user_routes import *

logger = logging.getLogger(__name__)

node_router = APIRouter(prefix="/node", tags=["Node Management"])

THAILAND_TZ = pytz.timezone('Asia/Bangkok')

class NodeRequest(BaseModel):
    node_name: str 
    location: str
    description: Optional[str] = None

class UpdateNodeRequest(BaseModel):
    node_id: str
    node_name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    status: Optional[int] = None

class NodeIdRequest(BaseModel):
    """Request body model for endpoints that need user_id"""
    user_id: int

class NodeDeleteBody(BaseModel):
    """Request body สำหรับลบ node"""
    node_id: str
    reason: Optional[str] = None

class NodeStatusResponse(BaseModel):
    """Response model for node status"""
    node_id: str
    node_name: str
    last_seen: Optional[str]
    status: int
    status_text: str
    last_data_time: Optional[str] = None

class InfluxDBConfig:
    """InfluxDB configuration"""
    def __init__(self):
        self.url = os.getenv("INFLUXDB_URL")
        self.token = os.getenv("INFLUXDB_TOKEN")
        self.org = os.getenv("INFLUXDB_ORG")
        self.bucket = os.getenv("INFLUXDB_BUCKET")
        
        if not all([self.url, self.token, self.org, self.bucket]):
            raise ValueError("Missing required InfluxDB environment variables")

def create_node_token(node_id: str) -> str:
    """สร้าง random token สำหรับ Node"""
    try:
        token = secrets.token_urlsafe(32)  #ความยาว 32 
        return token
    except Exception as e:
        logger.error(f"Token generation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"status": 0, "message": "ไม่สามารถสร้าง token ได้", "data": {}}
        )

def format_timestamp(dt: datetime) -> str:
    """แปลง datetime เป็น ISO format string ที่มีรูปแบบเดียวกัน"""
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        thailand_time = THAILAND_TZ.localize(dt)
    else:
        thailand_time = dt.astimezone(THAILAND_TZ)
    
    return thailand_time.isoformat(timespec="seconds")

def get_thailand_now() -> datetime:
    """ดึงเวลาไทยปัจจุบันแบบ naive datetime (ไม่มี timezone info)"""
    return datetime.now(THAILAND_TZ).replace(tzinfo=None)

def handle_error(e: Exception) -> HTTPException:
    """ฟังก์ชันจัดการ error ทั่วไป"""
    if isinstance(e, HTTPException):
        return e
    
    logger.error(f"Unexpected error: {str(e)}", exc_info=True)
    return HTTPException(
        status_code=500,
        detail={
            "status": 0,
            "message": f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {str(e)}",
            "data": {}
        }
    )

@contextmanager
def get_influx_client():
    """Context manager for InfluxDB client"""
    config = InfluxDBConfig()
    client = None
    try:
        client = InfluxDBClient(
            url=config.url,
            token=config.token,
            org=config.org
        )
        yield client, config
    except InfluxDBError as e:
        logger.error(f"InfluxDB connection error: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail={"status": 0, "message": "ไม่สามารถเชื่อมต่อกับฐานข้อมูล InfluxDB ได้", "data": {}}
        )
    except Exception as e:
        logger.error(f"Unexpected InfluxDB error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"status": 0, "message": "เกิดข้อผิดพลาดในการเชื่อมต่อฐานข้อมูล", "data": {}}
        )
    finally:
        if client:
            client.close()

@node_router.post("/add", summary="เพิ่ม Node ใหม่")
async def add_node(
    req: NodeRequest,
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    """สร้าง node ใหม่สำหรับตรวจวัดคุณภาพอากาศ"""
    try:
        logger.info(f"Starting node creation: {req.node_name} for user {current_user.user_id}")

        if not req.node_name.strip() or not req.location.strip():
            raise HTTPException(
                status_code=400,
                detail={"status": 0, "message": "กรุณากรอกข้อมูลให้ครบถ้วน", "data": {}}
            )
            
        existing_name = db.query(Nodes).filter(
            Nodes.node_name == req.node_name.strip(),
            Nodes.user_id == current_user.user_id
        ).first()
        
        if existing_name:
            raise HTTPException(
                status_code=409,
                detail={"status": 0, "message": "ชื่อ Node นี้ถูกใช้งานแล้วในบัญชีของคุณ", "data": {}}
            )

        node_id = req.node_name.strip()
        existing_id = db.query(Nodes).filter(Nodes.node_id == node_id).first()
        
        if existing_id:
            raise HTTPException(
                status_code=409,
                detail={"status": 0, "message": "ชื่อ Node นี้ถูกใช้งานแล้วในระบบ กรุณาใช้ชื่ออื่น", "data": {}}
            )

        node_token = create_node_token(node_id)

        new_node = Nodes(
            node_id=node_id,
            node_name=req.node_name.strip(),
            location=req.location.strip(),
            description=req.description.strip() if req.description else None,
            node_token=node_token,
            user_id=current_user.user_id,
            status=0,
            created_at=get_thailand_now()
        )

        db.add(new_node)
        db.commit()
        db.refresh(new_node)

        logger.info(f"Node created successfully: {node_id}")
        return {
            "status": 1,
            "message": "เพิ่ม Node สำเร็จ",
            "data": {
                "node_id": new_node.node_id,
                "node_name": new_node.node_name,
                "location": new_node.location,
                "description": new_node.description,
                "status": new_node.status,
                "status_text": new_node.status_text,
                "node_token": node_token,
                "created_at": format_timestamp(new_node.created_at)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error in add_node: {str(e)}")
        raise handle_error(e)

@node_router.get("/all", summary="ดูข้อมูล Nodes ทั้งหมด")
async def get_all_nodes(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ดึงข้อมูล nodes ทั้งหมดของ user นี้"""
    try:
        nodes = db.query(Nodes).filter(Nodes.user_id == current_user.user_id).all()

        if not nodes:
            return {
                "status": 1,
                "message": "ไม่พบ Node ในระบบ",
                "data": {
                    "nodes": [],
                    "total_nodes": 0
                }
            }
        
        return {
            "status": 1,
            "message": "ดึงข้อมูล Nodes ทั้งหมดสำเร็จ",
            "data": {
                "nodes": [{
                    "node_id": node.node_id,
                    "node_name": node.node_name,
                    "location": node.location,
                    "description": node.description,
                    "status": node.status,
                    "status_text": node.status_text,
                    "created_at": format_timestamp(node.created_at),
                    "updated_at": format_timestamp(node.updated_at),
                    "user_id": node.user_id,
                    "node_token": node.node_token
                } for node in nodes],
                "total_nodes": len(nodes)
            }
        }

    except Exception as e:
        logger.error(f"Error getting all nodes: {str(e)}")
        raise handle_error(e)

@node_router.get("/my-nodes", summary="ดูข้อมูล Node ของตัวเอง")
async def get_my_nodes(
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    """User ดึงข้อมูล nodes ทั้งหมดของตัวเอง"""
    try:
        user_nodes = db.query(Nodes).filter(Nodes.user_id == current_user.user_id).all()
        
        if not user_nodes:
            return {
                "status": 1,
                "message": "ไม่พบ Node ของผู้ใช้",
                "data": {
                    "nodes": [],
                    "total_nodes": 0
                }
            }

        return {
            "status": 1,
            "message": "ดึงข้อมูล Node สำเร็จ",
            "data": {
                "nodes": [{
                    "node_id": node.node_id,
                    "node_name": node.node_name,
                    "location": node.location,
                    "description": node.description,
                    "status": node.status,
                    "status_text": node.status_text,
                    "node_token": node.node_token,
                    "created_at": format_timestamp(node.created_at),
                    "updated_at": format_timestamp(node.updated_at)
                } for node in user_nodes],
                "total_nodes": len(user_nodes)
            }
        }

    except Exception as e:
        logger.error(f"Error fetching nodes: {str(e)}")
        raise handle_error(e)

@node_router.delete("/delete", summary="ลบ Node")
async def delete_node(
    body: NodeDeleteBody,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """ลบ node ผ่าน request body"""
    try:
        node = db.query(Nodes).filter(
            Nodes.node_id == body.node_id,
            Nodes.user_id == current_user.user_id
        ).first()

        if not node:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": 0,
                    "message": "ไม่พบ Node หรือคุณไม่มีสิทธิ์ลบ",
                    "data": {}
                }
            )

        logger.info(f"Deleting node {body.node_id} by user {current_user.user_id}, reason: {body.reason}")

        db.delete(node)
        db.commit()

        return {
            "status": 1,
            "message": "ลบ Node สำเร็จ",
            "data": {
                "node_id": body.node_id,
                "deleted_at": format_timestamp(get_thailand_now()),  # ใช้ฟังก์ชันใหม่
                "reason": body.reason
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_error(e)

@node_router.put("/update", summary="อัพเดต Node")
async def update_node(
    body: UpdateNodeRequest,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """อัพเดต node ผ่าน request body"""
    try:
        node = db.query(Nodes).filter(
            Nodes.node_id == body.node_id,
            Nodes.user_id == current_user.user_id
        ).first()

        if not node:
            raise HTTPException(
                status_code=404,
                detail={
                    "status": 0,
                    "message": "ไม่พบ Node หรือคุณไม่มีสิทธิ์แก้ไข",
                    "data": {}
                }
            )

        if body.node_name and body.node_name != node.node_name:
            existing = db.query(Nodes).filter(
                Nodes.node_name == body.node_name.strip(),
                Nodes.user_id == current_user.user_id,
                Nodes.node_id != body.node_id
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "status": 0,
                        "message": "ชื่อ Node นี้ถูกใช้งานแล้ว",
                        "data": {}
                    }
                )

        update_data = body.dict(exclude_unset=True, exclude={"node_id"})
        for key, value in update_data.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(node, key, value)

        node.updated_at = get_thailand_now()
        db.commit()
        db.refresh(node)

        logger.info(f"Node {body.node_id} updated successfully by user {current_user.user_id}")

        return {
            "status": 1,
            "message": "อัพเดต Node สำเร็จ",
            "data": {
                "node_id": node.node_id,
                "node_name": node.node_name,
                "location": node.location,
                "description": node.description,
                "status": node.status,
                "status_text": node.status_text,
                "created_at": format_timestamp(node.created_at),
                "updated_at": format_timestamp(node.updated_at)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_error(e)

@node_router.post("/status/check", summary="เช็คสถานะ Node จาก InfluxDB")
async def check_node_status(
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    """เช็คว่า Node ยังออนไลน์หรือไม่ โดยดูจากข้อมูลล่าสุดใน InfluxDB"""
    try:
        nodes = db.query(Nodes).filter(Nodes.user_id == current_user.user_id).all()
        
        if not nodes:
            return {
                "status": 1,
                "message": "ไม่พบ Node ในระบบ",
                "data": []
            }

        result = []
        
        with get_influx_client() as (influx_client, config):
            query_api = influx_client.query_api()
            
            for node in nodes:
                try:
                    query = f'''
                    from(bucket: "{config.bucket}")
                        |> range(start: -1h)
                        |> filter(fn: (r) => r["_measurement"] == "air_quality")
                        |> filter(fn: (r) => r["node_id"] == "{node.node_id}")
                        |> sort(columns: ["_time"], desc: true)
                        |> limit(n: 1)
                    '''
                    
                    influx_result = query_api.query(org=config.org, query=query)
                    
                    last_time = None
                    for table in influx_result:
                        for record in table.records:
                            last_time = record.get_time()
                            break

                    is_online = False
                    if last_time:
                        now = datetime.now(pytz.UTC)
                        time_diff = now - last_time
                        is_online = time_diff < timedelta(minutes=5)
                    
                    old_status = node.status
                    new_status = 1 if is_online else 0
                    
                    if old_status != new_status:
                        node.status = new_status
                        node.updated_at = get_thailand_now()
                        logger.info(f"Node {node.node_id} status changed from {old_status} to {new_status}")
                    
                    result.append({
                        "node_id": node.node_id,
                        "node_name": node.node_name,
                        "last_seen": format_timestamp(last_time) if last_time else None,
                        "status": new_status,
                        "status_text": "Online" if new_status == 1 else "Offline",
                        "last_data_time": format_timestamp(last_time) if last_time else None
                    })
                    
                except Exception as node_error:
                    logger.error(f"Error checking status for node {node.node_id}: {str(node_error)}")
                    result.append({
                        "node_id": node.node_id,
                        "node_name": node.node_name,
                        "last_seen": None,
                        "status": node.status,
                        "status_text": "Unknown",
                        "last_data_time": None,
                        "error": "ไม่สามารถตรวจสอบสถานะได้"
                    })
        
        db.commit()
        
        online_count = sum(1 for r in result if r["status"] == 1)
        offline_count = len(result) - online_count
        
        return {
            "status": 1,
            "message": "อัปเดตสถานะ Node สำเร็จ",
            "data": {
                "nodes": result,
                "summary": {
                    "total_nodes": len(result),
                    "online_nodes": online_count,
                    "offline_nodes": offline_count
                }
            }
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error in check_node_status: {str(e)}")
        raise handle_error(e)

@node_router.get("/status/summary", summary="สรุปสถานะ Node ทั้งหมด")
async def get_node_status_summary(
    db: Session = Depends(get_db),
    current_user: Users = Depends(get_current_user)
):
    """ดึงสรุปสถานะ Node ทั้งหมดของ user"""
    try:
        nodes = db.query(Nodes).filter(Nodes.user_id == current_user.user_id).all()
        
        if not nodes:
            return {
                "status": 1,
                "message": "ไม่พบ Node ในระบบ",
                "data": {
                    "total_nodes": 0,
                    "online_nodes": 0,
                    "offline_nodes": 0,
                    "nodes": []
                }
            }
        
        online_nodes = sum(1 for node in nodes if node.status == 1)
        offline_nodes = len(nodes) - online_nodes
        
        return {
            "status": 1,
            "message": "ดึงสรุปสถานะ Node สำเร็จ",
            "data": {
                "total_nodes": len(nodes),
                "online_nodes": online_nodes,
                "offline_nodes": offline_nodes,
                "nodes": [{
                    "node_id": node.node_id,
                    "node_name": node.node_name,
                    "status": node.status,
                    "status_text": node.status_text,
                    "updated_at": format_timestamp(node.updated_at)
                } for node in nodes]
            }
        }
        
    except Exception as e:
        logger.error(f"Error in get_node_status_summary: {str(e)}")
        raise handle_error(e)