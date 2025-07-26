from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# 应用配置类
# 会自动从环境变量或.env文件中读取配置
class Settings(BaseSettings):
    # 数据库连接URL
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    # JWT密钥
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    # JWT算法
    ALGORITHM: str = "HS256"
    # JWT过期时间（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 文件上传目录
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "temp_uploads")
    DOUBAO_APP_ID: str = os.getenv("DOUBAO_APP_ID")
    DOUBAO_TOKEN: str = os.getenv("DOUBAO_TOKEN")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY")

    class Config:
        env_file = ".env"


# 创建配置实例
settings = Settings()
