# config.py 
# 弃用
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv(override=True)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DOUBAO_APP_ID = os.getenv("DOUBAO_APP_ID")
DOUBAO_TOKEN = os.getenv("DOUBAO_TOKEN")

if not (DEEPSEEK_API_KEY or DOUBAO_TOKEN or DOUBAO_APP_ID):
    raise ValueError("错误：请在 .env 文件中正确设置")
