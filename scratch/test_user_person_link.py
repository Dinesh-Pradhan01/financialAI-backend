import asyncio
import uuid
import logging
from sqlalchemy import select, delete
from app.database.connection import db_manager
from app.database.models import Person
from app.auth.model import User
from app.auth.service import get_or_create_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestUserPersonLink")

async def test_flow():
    # 1. Initialize database connection and run migrations
    logger.info("Initializing database connection for migrations...")
    db_manager.connect()
    await db_manager.create_tables()
    await db_manager.disconnect()  # Closes connection pool and clears asyncpg statement cache

    logger.info("Re-connecting with a fresh connection pool for the test flow...")
    db_manager.connect()

    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_firebase_id = f"fb_{uuid.uuid4().hex[:12]}"

    async with db_manager.session_factory() as session:
        try:
            # 2. Test auto-creation for a new user
            logger.info(f"Testing registration and sync for email: {test_email}...")
            user = await get_or_create_user(session, test_firebase_id, test_email, email_verified=True)
            await session.commit()

            # Assertions
            assert user.firebase_id == test_firebase_id, "Firebase ID mismatch"
            assert user.email == test_email, "Email mismatch"
            assert user.person_id is not None, "person_id should not be None after sync"
            logger.info(f"✔ New User successfully created with linked person_id: {user.person_id}")

            # Verify Person row exists in persons table
            person_result = await session.execute(select(Person).where(Person.id == user.person_id))
            person = person_result.scalar_one_or_none()
            assert person is not None, "Person record was not created in the database!"
            assert person.email == test_email, "Person email does not match user email"
            logger.info("✔ Associated Person record successfully verified in persons table")

            # 3. Test migration logic (user exists but person_id is null)
            test_migration_email = f"migrate_{uuid.uuid4().hex[:8]}@example.com"
            test_migration_fb_id = f"fb_migrate_{uuid.uuid4().hex[:12]}"

            # Manually insert a user with person_id = None
            logger.info(f"Inserting mock legacy user with null person_id for: {test_migration_email}...")
            legacy_user = User(
                firebase_id=test_migration_fb_id,
                email=test_migration_email,
                email_verified=False,
                person_id=None
            )
            session.add(legacy_user)
            await session.flush()
            await session.commit()
            logger.info("Legacy user inserted successfully.")

            # Call get_or_create_user (simulate sync/login)
            logger.info("Simulating sync/login to trigger migration...")
            synced_user = await get_or_create_user(session, test_migration_fb_id, test_migration_email)
            await session.commit()

            # Assertions
            assert synced_user.person_id is not None, "person_id should be populated after migration!"
            logger.info(f"✔ Legacy User successfully migrated. Linked person_id: {synced_user.person_id}")

            # Verify Person row exists
            migrated_person_result = await session.execute(select(Person).where(Person.id == synced_user.person_id))
            migrated_person = migrated_person_result.scalar_one_or_none()
            assert migrated_person is not None, "Person record was not created during migration!"
            logger.info("✔ Migrated Person record successfully verified in persons table")

            # 4. Clean up test records
            logger.info("Cleaning up test database records...")
            # Cleanup synced_user
            await session.execute(delete(User).where(User.id == user.id))
            await session.execute(delete(Person).where(Person.id == user.person_id))
            # Cleanup migrated_user
            await session.execute(delete(User).where(User.id == synced_user.id))
            await session.execute(delete(Person).where(Person.id == synced_user.person_id))
            await session.commit()
            logger.info("✔ Database cleanup completed.")
            logger.info("🎉 All user-person link verification tests passed successfully!")

        except Exception as e:
            logger.error(f"❌ Test failed with error: {e}", exc_info=True)
            await session.rollback()
            raise e
        finally:
            await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(test_flow())
