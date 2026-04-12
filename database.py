from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:////./messenger.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize DB with index creation"""
    Base.metadata.create_all(bind=engine)
    
    # Create indexes for frequently queried fields
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rooms_name ON rooms(name)"))
            conn.commit()
        except Exception as e:
            print(f"Index creation: {e}")
