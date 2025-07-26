from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, WebSocket, WebSocketDisconnect, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from . import models, schemas
from .authentication import auth, crud
from .database import SessionLocal, engine
from datetime import timedelta, datetime
from .ai.ai_core_parallel import main_process  # ai_core
# from .ai.ai_core import main_process
from .config import settings
from typing import Optional
import os
import shutil
import uuid
import json
import pytz

# 创建数据库表
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# 获取数据库会话依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 用户注册端点
@app.post(
    "/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED
)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 检查密码是否匹配
    if user.password != user.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match"
        )

    # 检查用户名是否已存在
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User already exists"
        )

    # 检查邮箱是否已存在
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
        )

    # 创建用户
    return crud.create_user(db, user)


# 用户登录端点
@app.post("/login", response_model=schemas.Token)
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):

    # 尝试通过用户名或邮箱获取用户
    db_user = crud.get_user_by_username(db, username=user.username_or_email)
    if not db_user:
        db_user = crud.get_user_by_email(db, email=user.username_or_email)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Username or password is incorrect"
            )

    # 验证密码
    if not crud.verify_password(user.password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Username or password is incorrect"
        )

    # 创建访问令牌
    access_token = auth.create_access_token(
        data={"sub": db_user.username},
        expires_delta=timedelta(minutes=auth.settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {"access_token": access_token, "token_type": "bearer"}


# 获取用户资料端点
@app.get("/profile", response_model=schemas.UserOut)
def read_profile(current_user: schemas.UserOut = Depends(auth.get_current_user)):
    return current_user

# 根路径
@app.get("/")
def read_root():
    return {"message": "Welcome to the backend API!"}


"""以下用于AI助手"""

class ConnectionManager:
    def __init__(self):
        # 存储活跃的WebSocket连接, {conversation_id: websocket}
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, conversation_id: int):
        # 接收客户端WebSocket连接, 并将其添加到活跃连接列表中
        await websocket.accept()
        self.active_connections[conversation_id] = websocket

    def disconnect(self, conversation_id: int):
        # 断开客户端WebSocket连接, 并将其从活跃连接列表中删除
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]

    async def send_message(self, message: str, conversation_id: int):
        # 发送消息给指定对话的WebSocket连接
        if conversation_id in self.active_connections:
            await self.active_connections[conversation_id].send_json(message)

# 创建一个管理器实例
manager = ConnectionManager()


@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...), # 上传的文件
    new_filename: str = Form(...), # 新的文件名
    current_user: schemas.UserOut = Depends(auth.get_current_user), # 当前登录用户
    db: Session = Depends(get_db),
):
    """
    处理文件上传
    
    :param file: 上传的文件
    :param current_user: 当前登录用户
    :param db: 数据库会话
    :return: 返回对话ID和保存的文件名
    """

    # 在数据库中创建新的对话记录
    new_conversation = models.Conversation(
        user_id = current_user.id,
        filename = new_filename,
        created_at = datetime.now(pytz.timezone('Asia/Shanghai')),
    )
    print(datetime.now(pytz.timezone("Asia/Shanghai")))
    db.add(new_conversation)
    db.commit()
    db.refresh(new_conversation)

    # 创建用户专属目录
    user_dir = os.path.join(settings.UPLOAD_DIR, str(current_user.username), str(new_conversation.id or uuid.uuid4()))
    os.makedirs(user_dir, exist_ok=True)

    # 生成唯一文件名
    file_ext = os.path.splitext(file.filename)[1]
    file_path = os.path.join(user_dir, f"{new_filename}{file_ext}")
    transcript_path = os.path.join(user_dir, f"{new_filename}_transcript.txt")
    notes_path = os.path.join(user_dir, f"{new_filename}_notes.md")
    quiz_path = os.path.join(user_dir, f"{new_filename}_quiz.md")

    # 保存上传的文件到本地
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    new_conversation.file_path = file_path
    new_conversation.transcript_path = transcript_path
    new_conversation.notes_path = notes_path
    new_conversation.quiz_path = quiz_path
    db.commit()
    db.refresh(new_conversation)

    return {"conversation_id": new_conversation.id, "filename": f"{new_filename}{file_ext}"}


# 文件下载端点
@app.get("/download/{file_path:path}")
def download_file(
    file_path: str, 
    current_user: schemas.UserOut = Depends(auth.get_current_user)
):
    """
    下载用户生成的文件（笔记或测验题）

    :param file_path: 文件路径（URL编码）
    :param current_user: 当前登录用户
    :return: 文件响应
    """
    try:
        # URL解码文件路径
        import urllib.parse

        decoded_path = urllib.parse.unquote(file_path)
        print(f"原始路径: {file_path}")  # 调试日志
        print(f"解码后路径: {decoded_path}")  # 调试日志
        # 安全检查：确保文件路径在用户目录内
        user_upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user.username))
        if not decoded_path.startswith(user_upload_dir):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        # 检查文件是否存在
        if not os.path.exists(decoded_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
            )

        # 获取文件名
        filename = os.path.basename(decoded_path)
        print(f"下载文件名: {filename}")

        # 返回文件
        return FileResponse(
            path=decoded_path, filename=filename, media_type="application/octet-stream"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}",
        )


@app.get("/conversations/")
def get_conversations(
    current_user: schemas.UserOut = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取用户的所有对话历史
    
    :param current_user: 当前登录用户
    :param db: 数据库会话
    :return: 所有对话的列表(id, filename, created_at, notes_path, quiz_path)
    """
    # 查询当前用户所有对话，按创建时间倒序排列
    conversations = db.query(models.Conversation).filter(
        models.Conversation.user_id == current_user.id
    ).order_by(models.Conversation.created_at.desc()).all()
    # print(
    #     conversations[0]
    #     .created_at.astimezone(pytz.timezone("Asia/Shanghai"))
    #     .isoformat()
    # )
    # 打印结果为2025-07-23T19:20:52
    return [{
        "id": conv.id,
        "filename": conv.filename,
        "created_at": conv.created_at.astimezone(pytz.timezone('Asia/Shanghai')).isoformat(),
        "notes_path": conv.notes_path,
        "quiz_path": conv.quiz_path,
    } for conv in conversations]


@app.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    current_user: schemas.UserOut = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取特定对话的详细信息
    
    :param conversation_id: 对话的ID
    :param current_user: 当前登录用户
    :param db: 数据库会话
    :return: 对话的详细信息(id, filename, transcript, notes, quiz, messages)
    """
    # 查询当前用户的指定ID的对话
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id,
        models.Conversation.user_id == current_user.id
    ).first()

    # 若对话不存在或不属于当前用户, 返回404错误
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # 读取相关文件内容
    # 读取转录文本(若文件存在)
    transcript = ""
    if os.path.exists(conversation.transcript_path):
        with open(conversation.transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()

    # 读取笔记内容(若存在)
    notes = ""
    if conversation.notes_path and os.path.exists(conversation.notes_path):
        try:
            with open(conversation.notes_path, "r", encoding="utf-8") as f:
                notes = f.read()
        except Exception as e:
            print(f"Error reading notes file: {e}")

    # 读取测试题内容(若存在)
    quiz = ""
    if conversation.quiz_path and os.path.exists(conversation.quiz_path):
        try:
            with open(conversation.quiz_path, "r", encoding="utf-8") as f:
                quiz = f.read()
        except Exception as e:
            print(f"Error reading quiz file: {e}")

    return {
        "id": conversation_id,
        "filename": conversation.filename,
        "transcript": transcript,
        "notes_path": conversation.notes_path,
        "quiz_path": conversation.quiz_path,
        "notes": notes,
        "quiz": quiz,
        "messages": json.loads(conversation.messages) if conversation.messages else []
    }

@app.post("/process")
async def process_file(
    conversation_id: int,
    generate_quiz: bool = False,
    extra_requirements: Optional[str] = None,
    current_user: schemas.UserOut = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    处理文件并生成笔记和测试题
    
    :param conversation_id: 对话的ID
    :param generate_quiz: 是否生成测试题(默认不生成)
    :param extra_requirements: 用户额外需求(可选)
    :param current_user: 当前登录用户
    :param db: 数据库会话
    :return: 生成器对象, 用于处理WebSocket连接, 返回对话ID
    """
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id,
        models.Conversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # 生成输出文件名
    output_filename = f"conversation_{conversation.id}"

    # 调用AI处理流程
    generator = main_process(
        input_path=conversation.file_path,
        username=current_user.username,
        doubao_app_id=settings.DOUBAO_APP_ID,
        doubao_token=settings.DOUBAO_TOKEN,
        deepseek_api_key=settings.DEEPSEEK_API_KEY,
        output_filename=output_filename,
        query="Notes",
        new_message="",
        extra_requirements=extra_requirements,
    )

    # 返回生成器以便WebSocket处理流式输出
    return {"generator": generator, "conversation_id": conversation_id}

@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    conversation_id: int,
    token: str
):
    """WebSocket端点用于实时通信"""
    await manager.connect(websocket, conversation_id)

    try:
        # 验证用户
        user = await auth.get_current_user(token)
        db = SessionLocal()

        conversation = db.query(models.Conversation).filter(
            models.Conversation.id == conversation_id,
            models.Conversation.user_id == user.id
        ).first()

        if not conversation:
            await websocket.send_json(
                {"type": "error", "message": "Conversation not found"}
            )
            await websocket.close()
            return

        while True:
            data = await websocket.receive_json()
            if data["type"] == "process":
                generator = main_process(
                    input_path = conversation.file_path,
                    username=user.username,
                    doubao_app_id=settings.DOUBAO_APP_ID,
                    doubao_token=settings.DOUBAO_TOKEN,
                    deepseek_api_key=settings.DEEPSEEK_API_KEY,
                    output_filename=conversation.filename,
                    query=data.get("query", "Notes"),
                    new_message=data.get("message", ""),
                    extra_requirements=data.get("extra_requirements", ""),
                    conversation_id=conversation_id
                )

                # 迭代生成器并实时发送每个事件
                for event in generator:
                    await websocket.send_json({
                        "type": event[0], # 事件类型 ()
                        "value": event[1], # 事件值 ()
                        "message": event[2] if len(event) > 2 else ""
                    })

                # # 更新数据库中的文件路径
                # if data.get("query") == "Notes":
                #     conversation.notes_path = os.path.join(
                #           settings.UPLOAD_DIR,
                #           str(user.id),
                #           f"conversation_{conversation.id}.md"
                #      )
                # elif data.get("query") == "Quiz":
                #     conversation.quiz_path = os.path.join(
                #           settings.UPLOAD_DIR,
                #           str(user.id),
                #           f"conversation_{conversation.id}_quiz.md"
                #      )

                db.commit()
                await websocket.send_json({"type": "complete"})

            elif data["type"] == "message":
                # 处理用户消息并获取AI回复
                # 读取历史消息并添加新消息到历史消息中
                print("main收到前端消息:", data["message"])
                messages = json.loads(conversation.messages) if conversation.messages else []
                print("main成功读取历史消息:", messages)

                # 调用AI获取回复
                generator = main_process(
                    input_path=conversation.file_path,
                    username=user.username,
                    doubao_app_id=settings.DOUBAO_APP_ID,
                    doubao_token=settings.DOUBAO_TOKEN,
                    deepseek_api_key=settings.DEEPSEEK_API_KEY,
                    output_filename=conversation.filename,
                    query="Q&A",
                    new_message=data["message"],
                    history=messages,
                    conversation_id=conversation_id
                )

                print("main成功调用ai获取聊天回复")
                # 收集并实时发送AI回复的片段
                ai_response = ""
                for event in generator:
                    if event[0] == "llm_chunk":
                        ai_response += event[1]
                        await websocket.send_json({
                            "type": "llm_chunk",
                            "value": event[1]
                        })
                    else: 
                        await websocket.send_json(
                            {
                                "type": event[0],  # 事件类型 ()
                                "value": event[1],  # 事件值 ()
                                "message": event[2] if len(event) > 2 else "",
                            }
                        )

                # 更新历史消息并更新数据库
                messages.append({"role": "user", "content": data["message"]})
                messages.append({"role": "assistant", "content": ai_response})
                print("main成功添加新记录到历史消息中:", messages)
                conversation.messages = json.dumps(messages)
                db.commit()

                await websocket.send_json({"type": "complete"})

    except WebSocketDisconnect:
        # 客户端断开连接
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({"type": "error", "message": "main中的未知错误:"+str(e)})

# Add these new endpoints after the existing conversation endpoints


@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: schemas.UserOut = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a specific conversation and its associated files

    :param conversation_id: ID of the conversation to delete
    :param current_user: Current authenticated user
    :param db: Database session
    :return: Success message
    """
    # Get the conversation
    conversation = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conversation_id,
            models.Conversation.user_id == current_user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        # Delete associated files and directory
        user_dir = os.path.join(
            settings.UPLOAD_DIR, str(current_user.username), str(conversation_id)
        )
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)

        # Delete from database
        db.delete(conversation)
        db.commit()

        return {"message": "Conversation deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {str(e)}",
        )


@app.delete("/conversations/")
def delete_all_conversations(
    current_user: schemas.UserOut = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete all conversations for the current user

    :param current_user: Current authenticated user
    :param db: Database session
    :return: Success message
    """
    try:
        # Get all conversations for the user
        conversations = (
            db.query(models.Conversation)
            .filter(models.Conversation.user_id == current_user.id)
            .all()
        )

        # Delete all associated files and directories
        user_base_dir = os.path.join(settings.UPLOAD_DIR, str(current_user.username))
        for conv in conversations:
            conv_dir = os.path.join(user_base_dir, str(conv.id))
            if os.path.exists(conv_dir):
                shutil.rmtree(conv_dir)

        # Delete all from database
        db.query(models.Conversation).filter(
            models.Conversation.user_id == current_user.id
        ).delete()
        db.commit()

        return {"message": "All conversations deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversations: {str(e)}",
        )


@app.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: int,
    new_name: str = Form(...),
    current_user: schemas.UserOut = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Rename a conversation

    :param conversation_id: ID of the conversation to rename
    :param new_name: New filename for the conversation
    :param current_user: Current authenticated user
    :param db: Database session
    :return: Updated conversation
    """
    conversation = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conversation_id,
            models.Conversation.user_id == current_user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        conversation.filename = new_name
        db.commit()
        db.refresh(conversation)
        return conversation
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rename conversation: {str(e)}",
        )
