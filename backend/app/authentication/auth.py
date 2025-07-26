from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from . import crud
from .. import schemas
from ..config import settings
from ..database import SessionLocal

# OAuth2密码授权方案， 令牌获取URL为/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# 创建访问令牌
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()  # 复制数据避免修改原数据

    # 设置过期时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=24)

    # 添加过期时间到编码数据
    to_encode.update({"exp": expire})

    # 使用JWT编码生成令牌
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


# 获取当前用户
async def get_current_user(token: str = Depends(oauth2_scheme)):
    # 定义认证异常
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 解码JWT令牌
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")  # 获取用户名
        if username is None:
            raise credentials_exception

        # 创建令牌数据
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception

    # 获取数据库会话
    db = SessionLocal()
    # 通过用户名查询用户
    user = crud.get_user_by_username(db, username=token_data.username)
    db.close()

    if user is None:
        raise credentials_exception
    return user
