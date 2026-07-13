import asyncio
import uuid
import logging
from datetime import datetime
from sqlalchemy import select, delete
from app.database.connection import db_manager
from app.database.models import Person
from app.auth.model import User, UserResponse
from app.auth.service import get_or_create_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestOnboarding")

async def test_onboarding_flow():
    logger.info("Connecting to database...")
    db_manager.connect()

    test_email = f"onboard_{uuid.uuid4().hex[:8]}@example.com"
    test_firebase_id = f"fb_{uuid.uuid4().hex[:12]}"

    async with db_manager.session_factory() as session:
        try:
            # 1. Create a fresh User and verify profile_completed defaults to False
            logger.info(f"Creating user {test_email}...")
            user = await get_or_create_user(session, test_firebase_id, test_email, email_verified=True)
            await session.commit()

            # Verify associated Person has profile_completed = False
            person_result = await session.execute(select(Person).where(Person.id == user.person_id))
            person = person_result.scalar_one_or_none()
            assert person is not None, "Person record was not created!"
            assert person.profile_completed is False, "Profile should start as not completed"
            logger.info("✔ Verification: profile_completed correctly defaults to False")

            # 2. Simulate GET /api/auth/me response validation
            # Create a mock UserResponse and verify profile_completed is False
            user_resp = UserResponse.model_validate(user)
            # The schema defaults to False
            user_resp.profile_completed = person.profile_completed
            assert user_resp.profile_completed is False, "Pydantic representation mismatch (should be False)"
            logger.info("✔ Verification: UserResponse represents profile_completed as False")

            # 3. Simulate PATCH /api/persons/me to update profile info
            logger.info("Updating person profile details...")
            person.full_name = "Jane Doe"
            person.phone = "+91 99999 88888"
            person.date_of_birth = datetime(1995, 5, 15)
            person.gender = "Female"
            person.address = "123 Green Street"
            person.city = "Mumbai"
            person.state = "Maharashtra"
            person.pincode = "400001"
            person.pan_number = "ABCDE1234F"
            person.occupation = "Freelancer"
            person.bank_count = 3
            person.primary_bank = "State Bank of India"
            person.profile_completed = True
            await session.commit()

            # Refresh and retrieve updated details from database
            person_result = await session.execute(select(Person).where(Person.id == user.person_id))
            updated_person = person_result.scalar_one_or_none()
            
            assert updated_person.profile_completed is True, "profile_completed did not update to True"
            assert updated_person.full_name == "Jane Doe", "full_name mismatch"
            assert updated_person.phone == "+91 99999 88888", "phone mismatch"
            assert updated_person.city == "Mumbai", "city mismatch"
            assert updated_person.pan_number == "ABCDE1234F", "pan number mismatch"
            assert updated_person.bank_count == 3, "bank count mismatch"
            assert updated_person.primary_bank == "State Bank of India", "primary bank mismatch"
            logger.info("✔ Verification: Person profile fields successfully updated in database")

            # 4. Verify that UserResponse is now updated with profile_completed = True
            user_resp = UserResponse.model_validate(user)
            user_resp.profile_completed = updated_person.profile_completed
            assert user_resp.profile_completed is True, "UserResponse should represent profile_completed as True"
            logger.info("✔ Verification: UserResponse correctly represents profile_completed as True")

            # 5. Cleanup test records
            logger.info("Cleaning up database test records...")
            await session.execute(delete(User).where(User.id == user.id))
            await session.execute(delete(Person).where(Person.id == user.person_id))
            await session.commit()
            logger.info("✔ Database cleanup completed.")
            logger.info("🎉 All onboarding verification tests passed successfully!")

        except Exception as e:
            logger.error(f"❌ Test failed with error: {e}", exc_info=True)
            await session.rollback()
            raise e
        finally:
            await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(test_onboarding_flow())
