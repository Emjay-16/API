from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Response, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, String
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid
from passlib.context import CryptContext
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
import os
import logging

# from models import *
# from database import *
# from constants import *
# from email_service import send_verification_email, send_reset_email

from api.models import *
from api.database import *
from api.constants import *
from api.email_service import send_verification_email, send_reset_email

# Setup logger
logger = logging.getLogger(__name__)

user_router = APIRouter(tags=["User"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

class ForgotPasswordRequest(BaseModel):
    email: str
    
class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    
class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: str
    phone: str
    password: str

class LoginRequest(BaseModel):
    username_or_email: str
    password: str

class UpdateUserRequest(BaseModel):
    user_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[int] = None

class DeleteUserRequest(BaseModel):
    user_id: int

class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

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

def not_found_error(message: str = "ไม่พบข้อมูลที่ต้องการ"):
    return CustomHTTPException(status_code=404, message=message)

def unauthorized_error(message: str = "ไม่มีสิทธิ์เข้าถึง"):
    return CustomHTTPException(status_code=403, message=message)

def create_jwt_token(data: dict, expires_delta: timedelta = timedelta(minutes=15)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "sub": str(data["user_id"])})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise CustomHTTPException(401, "กรุณาเข้าสู่ระบบ")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        user = db.query(Users).filter(Users.user_id == int(user_id)).first()
        if not user:
            raise CustomHTTPException(401, "ไม่พบผู้ใช้")

        return user

    except JWTError:
        raise CustomHTTPException(401, "Token หมดอายุหรือไม่ถูกต้อง")

def check_admin_permission(user: Users):
    """ตรวจสอบสิทธิ์ Admin"""
    if user.role != ROLE_ADMIN:
        raise unauthorized_error("จำเป็นต้องมีสิทธิ์ Admin")

@user_router.post("/register")
async def register(request: RegisterRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        existing_user = db.query(Users).filter(
            or_(Users.username == request.username, Users.email == request.email)
        ).first()

        if existing_user:
            if existing_user.username == request.username:
                raise CustomHTTPException(status_code=400, message="ชื่อผู้ใช้นี้ถูกใช้แล้ว")
            else:
                raise CustomHTTPException(status_code=400, message="อีเมลนี้ถูกใช้แล้ว")

        hashed_password = pwd_context.hash(request.password)
        verification_token = str(uuid.uuid4())
        token_expiry = datetime.utcnow() + timedelta(minutes=30)

        new_user = Users(
            first_name=request.first_name,
            last_name=request.last_name,
            username=request.username,
            email=request.email,
            phone=request.phone,
            password=hashed_password,
            is_verified=False,
            role=ROLE_NODE_OWNER
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        new_token = Token(
            user_id=new_user.user_id,
            verification_token=verification_token,
            token_expiry=token_expiry
        )

        db.add(new_token)
        db.commit()

        background_tasks.add_task(send_verification_email, request.email, verification_token)

        return {
            "status": 1,
            "message": "สมัครสมาชิกสำเร็จ กรุณาตรวจสอบอีเมลเพื่อยืนยันบัญชี",
            "data": {
                "user_id": new_user.user_id,
                "username": new_user.username,
                "email": new_user.email,
                "role": new_user.role
            }
        }

    except CustomHTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.post("/login")
async def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(Users).filter(
        (Users.username == request.username_or_email) |
        (Users.email == request.username_or_email)
    ).first()

    if not user or not pwd_context.verify(request.password, user.password):
        raise CustomHTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    if not user.is_verified:
        raise CustomHTTPException(403, "กรุณายืนยันอีเมลก่อนเข้าสู่ระบบ")

    token_data = {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role
    }

    access_token = create_jwt_token(token_data, timedelta(days=7))
    refresh_token = create_jwt_token(token_data, timedelta(days=14)) 

    response = JSONResponse({
        "status": 1,
        "message": "เข้าสู่ระบบสำเร็จ",
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role
        },
        "authorization": access_token
    })

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60 
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=14 * 24 * 60 * 60 
    )

    return response
    
@user_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", httponly=True, secure=True, samesite="lax")
    response.delete_cookie("refresh_token", httponly=True, secure=True, samesite="lax")
    return JSONResponse(
        {"status": 1, "message": "ออกจากระบบสำเร็จ"},
        headers=response.headers
    )

@user_router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise CustomHTTPException(401, "ไม่ได้รับ refresh token")

    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            raise CustomHTTPException(401, "Token ไม่ถูกต้อง")

        user = db.query(Users).filter(Users.user_id == int(user_id)).first()
        if not user:
            raise CustomHTTPException(401, "ไม่พบผู้ใช้")

        token_data = {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role
        }
        new_access_token = create_jwt_token(token_data, timedelta(days=7))

        response = JSONResponse({"status": 1, "message": "refresh สำเร็จ"})
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60 
        )
        return response

    except JWTError:
        raise CustomHTTPException(401, "Refresh token หมดอายุหรือไม่ถูกต้อง")

@user_router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    try:
        user = db.query(Users).filter(Users.email == request.email).first()

        if not user:
            raise CustomHTTPException(status_code=400, message="ไม่พบอีเมลนี้ในระบบ")

        token = str(uuid.uuid4())
        token_expiry = datetime.utcnow() + timedelta(minutes=15)

        db.query(Token).filter(Token.user_id == user.user_id).delete()
        
        new_token = Token(
            user_id=user.user_id,
            verification_token=token,
            token_expiry=token_expiry
        )

        db.add(new_token)
        db.commit()

        background_tasks.add_task(send_reset_email, user.email, token)

        return {
            "status": 1,
            "message": "ส่งลิงก์รีเซ็ตรหัสผ่านไปยังอีเมลของท่านแล้ว",
            "data": {}
        }
    except CustomHTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        token_data = db.query(Token).filter(
            Token.verification_token == data.token,
            Token.token_expiry > datetime.utcnow()
        ).first()

        if not token_data:
            raise CustomHTTPException(status_code=400, message="ลิงก์หมดอายุหรือไม่ถูกต้อง")

        user = db.query(Users).filter(Users.user_id == token_data.user_id).first()

        if not user:
            raise CustomHTTPException(status_code=400, message="ไม่พบข้อมูลผู้ใช้")

        hashed_password = pwd_context.hash(data.new_password)
        user.password = hashed_password

        db.delete(token_data)
        db.commit()

        return {
            "status": 1,
            "message": "รีเซ็ตรหัสผ่านสำเร็จ",
            "data": {}
        }
    except CustomHTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.post("/verify-email")
async def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        token_data = db.query(Token).filter(
            Token.verification_token == token,
            Token.token_expiry > datetime.utcnow()
        ).first()

        if not token_data:
            raise CustomHTTPException(status_code=400, message="ลิงก์หมดอายุหรือไม่ถูกต้อง")

        user = db.query(Users).filter(Users.user_id == token_data.user_id).first()

        if not user:
            raise CustomHTTPException(status_code=400, message="ไม่พบข้อมูลผู้ใช้")

        user.is_verified = True
        
        db.delete(token_data)
        db.commit()

        return {
            "status": 1,
            "message": "ยืนยันอีเมลสำเร็จ",
            "data": {}
        }
    except CustomHTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.get("/users")
async def get_users(
    page: int = 1, 
    per_page: int = 10, 
    search: str = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        check_admin_permission(current_user)

        offset = (page - 1) * per_page
        
        query = db.query(Users)
        
        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Users.user_id.cast(String).ilike(search_term),
                    Users.username.ilike(search_term),
                    Users.email.ilike(search_term),
                    Users.first_name.ilike(search_term),
                    Users.last_name.ilike(search_term),
                    Users.phone.ilike(search_term)
                )
            )
        

        total_users = query.count()
        total_pages = (total_users + per_page - 1) // per_page
        

        users = query.offset(offset).limit(per_page).all()

        serialized_users = [{
            "user_id": str(user.user_id),
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "is_verified": user.is_verified,
            "role": user.role,
            "role_text": user.role_text,
            "created_at": user.created_at.isoformat() if hasattr(user, 'created_at') and user.created_at else None
        } for user in users]

        return {
            "status": 1,
            "message": "ดึงข้อมูลผู้ใช้สำเร็จ",
            "data": serialized_users,
            "total": total_users,
            "totalPages": total_pages,
            "currentPage": page,
            "perPage": per_page
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.delete("/delete_users")
async def delete_user(
    user_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        logger.info(f"Delete request received for user_id: {user_id}")
        logger.info(f"Current user: {current_user.user_id}, role: {current_user.role}")
        
        if current_user.role != ROLE_ADMIN:
            logger.warning(f"Unauthorized delete attempt by user {current_user.user_id}")
            raise unauthorized_error("ไม่มีสิทธิ์ลบผู้ใช้")
        
        target_user = db.query(Users).filter(Users.user_id == user_id).first()
        if not target_user:
            logger.warning(f"User {user_id} not found")
            raise not_found_error("ไม่พบผู้ใช้ที่ต้องการลบ")
        
        if current_user.user_id == user_id:
            logger.warning(f"User {current_user.user_id} tried to delete themselves")
            raise CustomHTTPException(status_code=400, message="ไม่สามารถลบตนเองได้")
        
        logger.info(f"Found target user: {target_user.username}")
        
        try:
            deleted_tokens = db.query(Token).filter(Token.user_id == user_id).delete(synchronize_session=False)
            logger.info(f"Deleted {deleted_tokens} tokens for user {user_id}")
            
            updated_nodes = db.query(Nodes).filter(Nodes.user_id == user_id).update(
                {"user_id": None}, 
                synchronize_session=False
            )
            logger.info(f"Updated {updated_nodes} nodes for user {user_id}")
            
            username = target_user.username
            db.delete(target_user)
            
            db.commit()
            
            logger.info(f"Successfully deleted user {user_id}")
            
            return {
                "status": 1,
                "message": f"ลบผู้ใช้ {username} สำเร็จ",
                "data": {
                    "deleted_user_id": user_id,
                    "deleted_username": username,
                    "deleted_tokens": deleted_tokens,
                    "updated_nodes": updated_nodes,
                    "deleted_at": datetime.now().astimezone().isoformat()
                }
            }
            
        except Exception as db_error:
            logger.error(f"Database error while deleting user {user_id}: {str(db_error)}")
            db.rollback()
            raise CustomHTTPException(
                status_code=500, 
                message=f"เกิดข้อผิดพลาดในการลบข้อมูล: {str(db_error)}"
            )
            
    except CustomHTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting user {user_id}: {str(e)}")
        db.rollback()
        raise CustomHTTPException(
            status_code=500, 
            message=f"เกิดข้อผิดพลาดในระบบ: {str(e)}"
        )

@user_router.post("/resend-verification")
async def resend_verification_email(
    email: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(Users).filter(Users.email == email).first()
        if not user:
            raise not_found_error("ไม่พบอีเมลนี้ในระบบ")

        if user.is_verified:
            raise CustomHTTPException(status_code=400, message="บัญชีนี้ได้รับการยืนยันแล้ว")

        db.query(Token).filter(Token.user_id == user.user_id).delete()

        verification_token = str(uuid.uuid4())
        token_expiry = datetime.utcnow() + timedelta(minutes=30)

        new_token = Token(
            user_id=user.user_id,
            verification_token=verification_token,
            token_expiry=token_expiry
        )

        db.add(new_token)
        db.commit()

        background_tasks.add_task(send_verification_email, user.email, verification_token)

        return {
            "status": 1,
            "message": "ส่งอีเมลยืนยันไปยังอีเมลของท่านแล้ว",
            "data": {}
        }
    except CustomHTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.patch("/update-user")
async def update_user(
    body: UpdateUserRequest,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if current_user.role == ROLE_ADMIN and body.user_id is not None:
            if body.user_id != current_user.user_id:
                target_user = db.query(Users).filter(Users.user_id == body.user_id).first()
                if not target_user:
                    raise not_found_error("ไม่พบข้อมูลผู้ใช้")
            else:
                target_user = current_user
        else:
            if body.user_id is not None and current_user.role != ROLE_ADMIN:
                raise unauthorized_error("ไม่มีสิทธิ์แก้ไขข้อมูลของผู้อื่น")
            if body.user_id is not None and body.user_id != current_user.user_id:
                raise unauthorized_error("ไม่มีสิทธิ์แก้ไขข้อมูลของผู้อื่น")
            target_user = current_user
        
        updated_fields = []
        
        if body.first_name is not None:
            target_user.first_name = body.first_name
            updated_fields.append("ชื่อ")
        
        if body.last_name is not None:
            target_user.last_name = body.last_name
            updated_fields.append("นามสกุล")
        
        if body.phone is not None:
            target_user.phone = body.phone
            updated_fields.append("เบอร์โทรศัพท์")

        if body.role is not None:
            if current_user.role != ROLE_ADMIN:
                raise unauthorized_error("ไม่มีสิทธิ์เปลี่ยนแปลง role")
            
            if body.role not in [ROLE_NODE_OWNER, ROLE_ADMIN]:
                raise CustomHTTPException(
                    status_code=400,
                    message=f"Role ไม่ถูกต้อง ต้องเป็น {ROLE_NODE_OWNER} (Node Owner) หรือ {ROLE_ADMIN} (Admin)"
                )
            
            old_role_text = target_user.role_text
            target_user.role = body.role
            new_role_text = target_user.role_text
            updated_fields.append(f"role จาก {old_role_text} เป็น {new_role_text}")

        if not updated_fields:
            return {
                "status": 0,
                "message": "ไม่มีข้อมูลที่ต้องอัปเดท",
                "data": {
                    "user_id": str(target_user.user_id),
                    "username": target_user.username,
                    "email": target_user.email,
                    "first_name": target_user.first_name,
                    "last_name": target_user.last_name,
                    "phone": target_user.phone,
                    "is_verified": target_user.is_verified,
                    "role": target_user.role,
                    "role_text": target_user.role_text
                }
            }

        db.commit()
        db.refresh(target_user)

        return {
            "status": 1,
            "message": f"อัปเดทข้อมูลสำเร็จ: {', '.join(updated_fields)}",
            "data": {
                "user_id": str(target_user.user_id),
                "username": target_user.username,
                "email": target_user.email,
                "first_name": target_user.first_name,
                "last_name": target_user.last_name,
                "phone": target_user.phone,
                "is_verified": target_user.is_verified,
                "role": target_user.role,
                "role_text": target_user.role_text
            }
        }
        
    except CustomHTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.get("/profile")
async def get_profile(
    current_user: Users = Depends(get_current_user)
):
    try:
        return {
            "status": 1,
            "message": "ดึงข้อมูลโปรไฟล์สำเร็จ",
            "data": {
                "user_id": str(current_user.user_id),
                "username": current_user.username,
                "email": current_user.email,
                "first_name": current_user.first_name,
                "last_name": current_user.last_name,
                "phone": current_user.phone,
                "is_verified": current_user.is_verified,
                "role": current_user.role,
                "role_text": current_user.role_text,
                "created_at": current_user.created_at.isoformat() if hasattr(current_user, 'created_at') and current_user.created_at else None
            }
        }
    except Exception as e:
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.patch("/update-profile")
async def update_profile(
    body: UpdateProfileRequest,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        updated_fields = []
        
        if body.first_name is not None:
            if body.first_name.strip() == "":
                raise CustomHTTPException(status_code=400, message="ชื่อไม่สามารถเป็นค่าว่างได้")
            current_user.first_name = body.first_name.strip()
            updated_fields.append("ชื่อ")
        
        if body.last_name is not None:
            if body.last_name.strip() == "":
                raise CustomHTTPException(status_code=400, message="นามสกุลไม่สามารถเป็นค่าว่างได้")
            current_user.last_name = body.last_name.strip()
            updated_fields.append("นามสกุล")
        
        if body.phone is not None:
            if body.phone.strip() != "" and not body.phone.strip().replace("-", "").replace(" ", "").isdigit():
                raise CustomHTTPException(status_code=400, message="เบอร์โทรศัพท์ไม่ถูกต้อง")
            current_user.phone = body.phone.strip()
            updated_fields.append("เบอร์โทรศัพท์")

        if not updated_fields:
            return {
                "status": 0,
                "message": "ไม่มีข้อมูลที่ต้องอัปเดท",
                "data": {
                    "user_id": str(current_user.user_id),
                    "username": current_user.username,
                    "email": current_user.email,
                    "first_name": current_user.first_name,
                    "last_name": current_user.last_name,
                    "phone": current_user.phone,
                    "is_verified": current_user.is_verified,
                    "role": current_user.role,
                    "role_text": current_user.role_text
                }
            }

        db.commit()
        db.refresh(current_user)

        return {
            "status": 1,
            "message": f"อัปเดทข้อมูลสำเร็จ: {', '.join(updated_fields)}",
            "data": {
                "user_id": str(current_user.user_id),
                "username": current_user.username,
                "email": current_user.email,
                "first_name": current_user.first_name,
                "last_name": current_user.last_name,
                "phone": current_user.phone,
                "is_verified": current_user.is_verified,
                "role": current_user.role,
                "role_text": current_user.role_text
            }
        }
        
    except CustomHTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")

@user_router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if not pwd_context.verify(body.current_password, current_user.password):
            raise CustomHTTPException(status_code=400, message="รหัสผ่านปัจจุบันไม่ถูกต้อง")
        
        if len(body.new_password) < 6:
            raise CustomHTTPException(status_code=400, message="รหัสผ่านใหม่ต้องมีอย่างน้อย 6 ตัวอักษร")
        
        if body.current_password == body.new_password:
            raise CustomHTTPException(status_code=400, message="รหัสผ่านใหม่ต้องแตกต่างจากรหัสผ่านปัจจุบัน")
        
        hashed_password = pwd_context.hash(body.new_password)
        current_user.password = hashed_password
        
        db.commit()
        
        return {
            "status": 1,
            "message": "เปลี่ยนรหัสผ่านสำเร็จ",
            "data": {}
        }
        
    except CustomHTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise CustomHTTPException(status_code=500, message=f"เกิดข้อผิดพลาด: {str(e)}")