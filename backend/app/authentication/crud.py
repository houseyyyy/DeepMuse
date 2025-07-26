from sqlalchemy.orm import Session
from .. import models, schemas
from passlib.context import CryptContext

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# 通过用户名获取用户
def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


# 通过邮箱获取用户
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


# 创建用户
def create_user(db: Session, user: schemas.UserCreate):
    # 生成密码哈希
    hashed_password = pwd_context.hash(user.password)
    # 创建用户实例
    db_user = models.User(
        username=user.username, email=user.email, password_hash=hashed_password
    )
    # 添加到数据库
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# 验证密码
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)
