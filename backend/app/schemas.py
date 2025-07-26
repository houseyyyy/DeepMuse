from pydantic import BaseModel, EmailStr, Field, field_validator


# 用户基础模型
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    email: EmailStr  # 使用Pydantic的EmailStr验证邮箱格式


# 用户创建模型
class UserCreate(UserBase):
    # 密码必须包含字母和数字，至少8个字符
    password: str = Field(..., min_length=8)
    confirm_password: str

    @field_validator("password")
    def password_complexity(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isalpha() for char in v):
            raise ValueError("Password must contain at least one letter")
        return v

    class Config:
        # 示例数据，用于API文档
        json_schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "johndoe@example.com",
                "password": "password123",
                "confirm_password": "password123",
            }
        }


# 用户登陆模型
class UserLogin(BaseModel):
    username_or_email: str
    password: str


# 用户输出模型，返回给客户端
class UserOut(UserBase):
    id: int

    class Config:
        # 允许ORM模式，可以从数据库模型直接转换
        from_attributes = True


# 令牌模型
class Token(BaseModel):
    access_token: str
    token_type: str


# 令牌数据模型，解码后的JWT内容
class TokenData(BaseModel):
    username: str | None = None
