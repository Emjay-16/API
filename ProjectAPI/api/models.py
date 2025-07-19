from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, Boolean, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

# from database import Base
from api.database import Base
from api.constants import *

class Users(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    username = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    phone = Column(Text, nullable=False)
    password = Column(Text, nullable=False)
    is_verified = Column(Boolean, default=False)
    role = Column(Integer, nullable=False, default=ROLE_NODE_OWNER)
    
    __table_args__ = (
        CheckConstraint(f'role IN ({ROLE_NODE_OWNER}, {ROLE_ADMIN})', name='check_valid_role'),
    )

    nodes = relationship("Nodes", back_populates="user")
    tokens = relationship("Token", back_populates="user")

    @property
    def role_text(self) -> str:
        return ROLE_CHOICES.get(self.role, "Unknown")

class Token(Base):
    __tablename__ = "tokens"
    token_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    verification_token = Column(Text, nullable=False)
    token_expiry = Column(DateTime, nullable=False)
    is_verified = Column(Boolean, default=False)
    user = relationship("Users", back_populates="tokens")

    def is_token_expired(self):
        return datetime.utcnow() > self.token_expiry if self.token_expiry else False

class Nodes(Base):
    __tablename__ = "nodes"
    
    node_id = Column(Text, primary_key=True, index=True)
    node_name = Column(Text, nullable=False)
    location = Column(Text)
    description = Column(Text)
    node_token = Column(Text, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False, index=True)
    status = Column(Integer, nullable=False, default=STATUS_OFFLINE)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("Users", back_populates="nodes")

    __table_args__ = (
        CheckConstraint(f'status IN ({STATUS_OFFLINE}, {STATUS_ONLINE})', name='check_valid_status'),
        )
    
    @property
    def status_text(self) -> str:
        return STATUS_CHOICES.get(self.status, "Unknown")
    
    def __repr__(self):
        return f"<Node(node_id={self.node_id}, node_name={self.node_name}, location={self.location}, status={self.status_text})>"