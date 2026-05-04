
import asyncio
import uuid
from backend import database, auth
import aiosqlite
from backend.models import UserCreate

async def test_register():
    user = UserCreate(username="testuser_" + str(uuid.uuid4())[:8], password="testpassword")
    print(f"Testing registration for: {user.username}")
    
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute("SELECT id FROM users WHERE username = ?", (user.username,)) as cur:
                if await cur.fetchone():
                    print("Username already registered")
                    return
            
            user_id = str(uuid.uuid4())
            hashed_pw = auth.get_password_hash(user.password)
            print(f"Hashed password: {hashed_pw[:20]}...")
            await db.execute("INSERT INTO users (id, username, hashed_password) VALUES (?, ?, ?)", 
                             (user_id, user.username, hashed_pw))
            await db.commit()
            print("User inserted and committed")
            
        access_token = auth.create_access_token(data={"sub": user_id})
        print(f"Access token generated: {access_token[:20]}...")
        print("Test passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_register())
