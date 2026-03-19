from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Enum, Boolean, func, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import enum
from config import DATABASE_URL
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

class Gender(enum.Enum):
    MALE = "male"
    FEMALE = "female"

class CommentHistory(Base):
    __tablename__ = 'comment_history'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'))
    post_link = Column(String)
    comment_text = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)  # Добавляем поле для отслеживания успешности
    
    account = relationship("Account", back_populates="comment_history")

class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    display_name = Column(String)
    gender = Column(Enum(Gender))
    session_data = Column(JSON)  # Хранит все данные сессии
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    commented_posts = Column(JSON, default=list)
    error_count = Column(Integer, default=0)
    hourly_comments = Column(JSON, default=list)  # Список timestamp'ов комментариев за последний час
    comments_history = Column(JSON, default=list)  # Список всех комментариев с метаданными
    
    # Новые поля для хранения данных сессии
    dc_id = Column(Integer)
    server_address = Column(String)
    port = Column(Integer)
    auth_key = Column(Text)  # Хранит ключ авторизации в base64
    user_id = Column(Integer)
    phone = Column(String)
    app_id = Column(Integer)
    app_hash = Column(String)
    device_model = Column(String)
    system_version = Column(String)
    app_version = Column(String)
    lang_code = Column(String)
    system_lang_code = Column(String)
    comment_history = relationship("CommentHistory", back_populates="account")

    def add_comment_timestamp(self, session):
        """Добавляет timestamp комментария и очищает старые"""
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        
        if not self.hourly_comments:
            self.hourly_comments = []
            
        # Удаляем старые timestamp'ы
        self.hourly_comments = [ts for ts in self.hourly_comments if datetime.fromisoformat(ts) > hour_ago]
        
        # Добавляем новый timestamp
        self.hourly_comments.append(now.isoformat())
        session.commit()

    def can_comment(self) -> bool:
        """Проверяет, может ли аккаунт оставить комментарий"""
        if not self.hourly_comments:
            return True
            
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        
        # Считаем комментарии за последний час
        recent_comments = sum(1 for ts in self.hourly_comments 
                            if datetime.fromisoformat(ts) > hour_ago)
        
        return recent_comments < 50  # Лимит 50 комментариев в час

    @classmethod
    def get_statistics(cls, session):
        """Получение статистики по аккаунтам"""
        try:
            total_accounts = session.query(func.count(cls.id)).scalar()
            active_accounts = session.query(func.count(cls.id)).filter(cls.is_active == True).scalar()
            blocked_accounts = session.query(func.count(cls.id)).filter(cls.is_active == False).scalar()
            
            male_accounts = session.query(func.count(cls.id)).filter(cls.gender == Gender.MALE).scalar()
            female_accounts = session.query(func.count(cls.id)).filter(cls.gender == Gender.FEMALE).scalar()
            
            # Подсчет комментариев через CommentHistory
            total_comments = session.query(func.count(CommentHistory.id)).scalar()
            successful_comments = session.query(func.count(CommentHistory.id)).filter(CommentHistory.success == True).scalar()
            failed_comments = session.query(func.count(CommentHistory.id)).filter(CommentHistory.success == False).scalar()
            
            # Подсчет уникальных постов
            unique_posts = session.query(func.count(func.distinct(CommentHistory.post_link))).scalar()
            
            # Подсчет комментариев за последний час
            now = datetime.utcnow()
            hour_ago = now - timedelta(hours=1)
            hourly_comments = session.query(func.count(CommentHistory.id)).filter(
                CommentHistory.timestamp > hour_ago
            ).scalar()
            
            return {
                "total_accounts": total_accounts,
                "active_accounts": active_accounts,
                "blocked_accounts": blocked_accounts,
                "male_accounts": male_accounts,
                "female_accounts": female_accounts,
                "total_comments": total_comments,
                "successful_comments": successful_comments,
                "failed_comments": failed_comments,
                "unique_posts": unique_posts,
                "hourly_comments": hourly_comments,
                "average_comments_per_account": total_comments / total_accounts if total_accounts > 0 else 0
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {str(e)}")
            return {
                "total_accounts": 0,
                "active_accounts": 0,
                "blocked_accounts": 0,
                "male_accounts": 0,
                "female_accounts": 0,
                "total_comments": 0,
                "successful_comments": 0,
                "failed_comments": 0,
                "unique_posts": 0,
                "hourly_comments": 0,
                "average_comments_per_account": 0
            }

    def add_comment(self, post_link: str, comment_text: str, timestamp: datetime, success: bool = True):
        """Добавление комментария в историю"""
        comment = CommentHistory(
            post_link=post_link,
            comment_text=comment_text,
            timestamp=timestamp,
            success=success
        )
        self.comment_history.append(comment)
        
        # Добавляем ссылку на пост в список прокомментированных
        if not self.commented_posts:
            self.commented_posts = []
        if post_link not in self.commented_posts:
            self.commented_posts.append(post_link)
            
        # Обновляем время последнего использования только при успешном комментарии
        if success:
            self.last_used = timestamp
            self.error_count = 0  # Сбрасываем счетчик ошибок при успешном комментарии
        else:
            self.error_count += 1
            if self.error_count >= 3:
                self.is_active = False

    def has_commented_on_post(self, post_link: str) -> bool:
        """Проверка, комментировал ли аккаунт данный пост"""
        return any(comment.post_link == post_link for comment in self.comment_history)

    def get_comment_history(self) -> List[Dict]:
        """Получение истории комментариев"""
        return self.comments_history or []

    def get_commented_posts(self) -> List[str]:
        """Получение списка прокомментированных постов"""
        return self.commented_posts or []

    def __repr__(self):
        return f"<Account {self.username}>"

# Создаем движок базы данных
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Создаем все таблицы
Base.metadata.create_all(engine) 