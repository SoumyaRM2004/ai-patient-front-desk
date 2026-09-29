"""Comprehensive tests for Phase 3: Clinic Configuration.

Covers:
- Doctors CRUD & tenant isolation (tests 1-8)
- Services CRUD & tenant isolation (tests 9-16)
- Doctor working hours CRUD & tenant isolation (tests 17-25)
- Input validation (tests 26-29)
- Tenant integrity & cascade behavior (tests 30-34)
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.doctor import Doctor
from app.models.doctor_working_hour import DoctorWorkingHour
from app.models.service import Service
from tests.conftest import get_auth_header, register_user

pytestmark = pytest.mark.asyncio


# Helper fixture to create two clinics with tokens and headers
@pytest.fixture
async def two_clinics(client: AsyncClient):
    """Register two distinct clinics and return their auth headers and registration data."""
    reg_a = await register_user(
        client,
        clinic_name="Clinic A",
        owner_name="Owner A",
        email="clinic_a@example.com",
        password="passwordA123",
    )
    data_a = reg_a.json()
    headers_a = await get_auth_header(client, "clinic_a@example.com", "passwordA123")

    reg_b = await register_user(
        client,
        clinic_name="Clinic B",
        owner_name="Owner B",
        email="clinic_b@example.com",
        password="passwordB123",
    )
    data_b = reg_b.json()
    headers_b = await get_auth_header(client, "clinic_b@example.com", "passwordB123")

    return {
        "clinic_a": data_a,
        "headers_a": headers_a,
        "clinic_b": data_b,
        "headers_b": headers_b,
    }


# ===========================================================================
# 1. Doctors Tests
# ===========================================================================


class TestDoctors:

    async def test_01_create_doctor_successfully(self, client: AsyncClient, two_clinics):
        """1. Create doctor successfully for the current clinic."""
        headers = two_clinics["headers_a"]
        clinic_id = two_clinics["clinic_a"]["clinic_id"]

        response = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={
                "name": "Dr. Alice Smith",
                "specialty": "Cardiology",
                "phone": "+1234567890",
                "email": "alice@example.com",
                "is_active": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Dr. Alice Smith"
        assert data["specialty"] == "Cardiology"
        assert data["phone"] == "+1234567890"
        assert data["email"] == "alice@example.com"
        assert data["is_active"] is True
        assert data["clinic_id"] == clinic_id
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_02_get_doctors_for_current_clinic(self, client: AsyncClient, two_clinics):
        """2. Get doctors belonging only to the current clinic."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        # Clinic A creates two doctors
        await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. A1", "specialty": "Pediatrics"},
        )
        await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. A2", "specialty": "Neurology"},
        )

        # Clinic B creates one doctor
        await client.post(
            "/api/v1/doctors",
            headers=headers_b,
            json={"name": "Dr. B1", "specialty": "Dermatology"},
        )

        # Clinic A retrieves doctors
        resp_a = await client.get("/api/v1/doctors", headers=headers_a)
        assert resp_a.status_code == 200
        doctors_a = resp_a.json()
        assert len(doctors_a) == 2
        names_a = [d["name"] for d in doctors_a]
        assert "Dr. A1" in names_a
        assert "Dr. A2" in names_a
        assert "Dr. B1" not in names_a

    async def test_03_get_individual_doctor(self, client: AsyncClient, two_clinics):
        """3. Get individual doctor by ID."""
        headers = two_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Bob", "specialty": "Oncology"},
        )
        doctor_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/doctors/{doctor_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == doctor_id
        assert get_resp.json()["name"] == "Dr. Bob"

    async def test_04_update_doctor(self, client: AsyncClient, two_clinics):
        """4. Update an existing doctor."""
        headers = two_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Carol", "specialty": "General Medicine"},
        )
        doctor_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/doctors/{doctor_id}",
            headers=headers,
            json={"specialty": "Family Medicine", "is_active": False},
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["specialty"] == "Family Medicine"
        assert data["is_active"] is False
        assert data["name"] == "Dr. Carol"  # unchanged

    async def test_05_delete_doctor(self, client: AsyncClient, two_clinics, db_session):
        """5. Delete an existing doctor."""
        headers = two_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Dave", "specialty": "Dentistry"},
        )
        doctor_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/doctors/{doctor_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify not found after deletion
        get_resp = await client.get(f"/api/v1/doctors/{doctor_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_06_cannot_access_other_clinic_doctor(self, client: AsyncClient, two_clinics):
        """6. Clinic B cannot access Clinic A's doctor (returns 404)."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        create_resp = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. Clinic A Exclusive"},
        )
        doctor_id = create_resp.json()["id"]

        # Clinic B tries to read Clinic A's doctor
        resp = await client.get(f"/api/v1/doctors/{doctor_id}", headers=headers_b)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Doctor not found"

    async def test_07_cannot_update_other_clinic_doctor(self, client: AsyncClient, two_clinics):
        """7. Clinic B cannot update Clinic A's doctor (returns 404)."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        create_resp = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. Clinic A Target"},
        )
        doctor_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/doctors/{doctor_id}",
            headers=headers_b,
            json={"name": "Hacked Name"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Doctor not found"

    async def test_08_cannot_delete_other_clinic_doctor(self, client: AsyncClient, two_clinics):
        """8. Clinic B cannot delete Clinic A's doctor (returns 404)."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        create_resp = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. Clinic A Protected"},
        )
        doctor_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/doctors/{doctor_id}", headers=headers_b)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Doctor not found"


# ===========================================================================
# 2. Services Tests
# ===========================================================================


class TestServices:

    async def test_09_create_service_successfully(self, client: AsyncClient, two_clinics):
        """9. Create service successfully for current clinic."""
        headers = two_clinics["headers_a"]
        clinic_id = two_clinics["clinic_a"]["clinic_id"]

        response = await client.post(
            "/api/v1/services",
            headers=headers,
            json={
                "name": "General Consultation",
                "description": "Comprehensive initial exam",
                "duration_minutes": 30,
                "price": "75.50",
                "is_active": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "General Consultation"
        assert data["description"] == "Comprehensive initial exam"
        assert data["duration_minutes"] == 30
        assert Decimal(str(data["price"])) == Decimal("75.50")
        assert data["clinic_id"] == clinic_id
        assert data["is_active"] is True
        assert "id" in data

    async def test_10_get_services_for_current_clinic(self, client: AsyncClient, two_clinics):
        """10. Get services belonging only to current clinic."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        await client.post(
            "/api/v1/services",
            headers=headers_a,
            json={"name": "Service A1", "duration_minutes": 15},
        )
        await client.post(
            "/api/v1/services",
            headers=headers_a,
            json={"name": "Service A2", "duration_minutes": 45},
        )
        await client.post(
            "/api/v1/services",
            headers=headers_b,
            json={"name": "Service B1", "duration_minutes": 60},
        )

        resp_a = await client.get("/api/v1/services", headers=headers_a)
        assert resp_a.status_code == 200
        services_a = resp_a.json()
        assert len(services_a) == 2
        names_a = [s["name"] for s in services_a]
        assert "Service A1" in names_a
        assert "Service A2" in names_a
        assert "Service B1" not in names_a

    async def test_11_get_individual_service(self, client: AsyncClient, two_clinics):
        """11. Get individual service by ID."""
        headers = two_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "X-Ray", "duration_minutes": 20, "price": "120.00"},
        )
        service_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/services/{service_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == service_id
        assert get_resp.json()["name"] == "X-Ray"

    async def test_12_update_service(self, client: AsyncClient, two_clinics):
        """12. Update an existing service."""
        headers = two_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Blood Test", "duration_minutes": 10, "price": "40.00"},
        )
        service_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/services/{service_id}",
            headers=headers,
            json={"duration_minutes": 15, "price": "45.00"},
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()
        assert data["duration_minutes"] == 15
        assert Decimal(str(data["price"])) == Decimal("45.00")

    async def test_13_delete_service(self, client: AsyncClient, two_clinics):
        """13. Delete an existing service."""
        headers = two_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Eye Exam", "duration_minutes": 30},
        )
        service_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/services/{service_id}", headers=headers)
        assert del_resp.status_code == 204

        get_resp = await client.get(f"/api/v1/services/{service_id}", headers=headers)
        assert get_resp.status_code == 404

    async def test_14_cannot_access_other_clinic_service(self, client: AsyncClient, two_clinics):
        """14. Clinic B cannot access Clinic A's service (returns 404)."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        create_resp = await client.post(
            "/api/v1/services",
            headers=headers_a,
            json={"name": "Private Service A", "duration_minutes": 30},
        )
        service_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/services/{service_id}", headers=headers_b)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Service not found"

    async def test_15_cannot_update_other_clinic_service(self, client: AsyncClient, two_clinics):
        """15. Clinic B cannot update Clinic A's service (returns 404)."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        create_resp = await client.post(
            "/api/v1/services",
            headers=headers_a,
            json={"name": "Private Service A", "duration_minutes": 30},
        )
        service_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/services/{service_id}",
            headers=headers_b,
            json={"name": "Hacked Service"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Service not found"

    async def test_16_cannot_delete_other_clinic_service(self, client: AsyncClient, two_clinics):
        """16. Clinic B cannot delete Clinic A's service (returns 404)."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        create_resp = await client.post(
            "/api/v1/services",
            headers=headers_a,
            json={"name": "Private Service A", "duration_minutes": 30},
        )
        service_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/services/{service_id}", headers=headers_b)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Service not found"


# ===========================================================================
# 3. Doctor Working Hours Tests
# ===========================================================================


class TestDoctorWorkingHours:

    async def test_17_create_valid_working_hours(self, client: AsyncClient, two_clinics):
        """17. Create valid working hours (including multiple slots per day / split shifts)."""
        headers = two_clinics["headers_a"]
        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Shift Specialist"},
        )
        doctor_id = doc_resp.json()["id"]

        # Morning shift: 09:00 - 13:00 on Monday (0)
        wh1 = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={
                "day_of_week": 0,
                "start_time": "09:00:00",
                "end_time": "13:00:00",
                "is_active": True,
            },
        )
        assert wh1.status_code == 201
        data1 = wh1.json()
        assert data1["doctor_id"] == doctor_id
        assert data1["day_of_week"] == 0
        assert data1["start_time"] == "09:00:00"
        assert data1["end_time"] == "13:00:00"

        # Afternoon shift: 14:00 - 18:00 on Monday (0) (split shift support)
        wh2 = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={
                "day_of_week": 0,
                "start_time": "14:00:00",
                "end_time": "18:00:00",
                "is_active": True,
            },
        )
        assert wh2.status_code == 201
        assert wh2.json()["id"] != data1["id"]

    async def test_18_reject_invalid_day_of_week(self, client: AsyncClient, two_clinics):
        """18. Reject day_of_week < 0 or > 6."""
        headers = two_clinics["headers_a"]
        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Week Test"},
        )
        doctor_id = doc_resp.json()["id"]

        resp_neg = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": -1, "start_time": "09:00:00", "end_time": "17:00:00"},
        )
        assert resp_neg.status_code == 422

        resp_too_high = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 7, "start_time": "09:00:00", "end_time": "17:00:00"},
        )
        assert resp_too_high.status_code == 422

    async def test_19_reject_start_time_gte_end_time(self, client: AsyncClient, two_clinics):
        """19. Reject start_time >= end_time."""
        headers = two_clinics["headers_a"]
        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Time Test"},
        )
        doctor_id = doc_resp.json()["id"]

        # Equal
        resp_equal = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 1, "start_time": "10:00:00", "end_time": "10:00:00"},
        )
        assert resp_equal.status_code == 422

        # Inverted
        resp_inv = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 1, "start_time": "17:00:00", "end_time": "09:00:00"},
        )
        assert resp_inv.status_code == 422

    async def test_20_get_doctor_working_hours(self, client: AsyncClient, two_clinics):
        """20. Get doctor's working hours."""
        headers = two_clinics["headers_a"]
        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Schedule Reader"},
        )
        doctor_id = doc_resp.json()["id"]

        await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 2, "start_time": "08:00:00", "end_time": "12:00:00"},
        )
        await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 4, "start_time": "13:00:00", "end_time": "17:00:00"},
        )

        resp = await client.get(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
        )
        assert resp.status_code == 200
        slots = resp.json()
        assert len(slots) == 2
        assert slots[0]["day_of_week"] == 2
        assert slots[1]["day_of_week"] == 4

    async def test_21_update_working_hours(self, client: AsyncClient, two_clinics):
        """21. Update existing working hours record."""
        headers = two_clinics["headers_a"]
        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Modifiable Schedule"},
        )
        doctor_id = doc_resp.json()["id"]

        create_wh = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 3, "start_time": "09:00:00", "end_time": "12:00:00"},
        )
        wh_id = create_wh.json()["id"]

        # Update end time
        patch_resp = await client.patch(
            f"/api/v1/doctors/{doctor_id}/working-hours/{wh_id}",
            headers=headers,
            json={"end_time": "15:00:00"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["end_time"] == "15:00:00"

    async def test_22_delete_working_hours(self, client: AsyncClient, two_clinics):
        """22. Delete working hours record."""
        headers = two_clinics["headers_a"]
        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Deletable Schedule"},
        )
        doctor_id = doc_resp.json()["id"]

        create_wh = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 4, "start_time": "09:00:00", "end_time": "12:00:00"},
        )
        wh_id = create_wh.json()["id"]

        del_resp = await client.delete(
            f"/api/v1/doctors/{doctor_id}/working-hours/{wh_id}",
            headers=headers,
        )
        assert del_resp.status_code == 204

        # Verify not in list anymore
        list_resp = await client.get(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
        )
        assert len(list_resp.json()) == 0

    async def test_23_cannot_create_working_hours_for_other_clinic_doctor(
        self, client: AsyncClient, two_clinics
    ):
        """23. Clinic B cannot create working hours for Clinic A's doctor."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. Clinic A Exclusive"},
        )
        doctor_id = doc_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers_b,
            json={"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Doctor not found"

    async def test_24_cannot_access_other_clinic_working_hours(
        self, client: AsyncClient, two_clinics
    ):
        """24. Clinic B cannot access Clinic A doctor's working hours."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. Clinic A Target"},
        )
        doctor_id = doc_resp.json()["id"]

        await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers_a,
            json={"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00"},
        )

        resp = await client.get(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers_b,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Doctor not found"

    async def test_25_cannot_modify_other_clinic_working_hours(
        self, client: AsyncClient, two_clinics
    ):
        """25. Clinic B cannot modify or delete Clinic A's working hours."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. Clinic A Guarded"},
        )
        doctor_id = doc_resp.json()["id"]

        wh_resp = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers_a,
            json={"day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00"},
        )
        wh_id = wh_resp.json()["id"]

        # Try PATCH
        patch_resp = await client.patch(
            f"/api/v1/doctors/{doctor_id}/working-hours/{wh_id}",
            headers=headers_b,
            json={"end_time": "18:00:00"},
        )
        assert patch_resp.status_code == 404

        # Try DELETE
        del_resp = await client.delete(
            f"/api/v1/doctors/{doctor_id}/working-hours/{wh_id}",
            headers=headers_b,
        )
        assert del_resp.status_code == 404


# ===========================================================================
# 4. Validation Tests
# ===========================================================================


class TestValidation:

    async def test_26_reject_invalid_service_duration(self, client: AsyncClient, two_clinics):
        """26. Reject service duration <= 0."""
        headers = two_clinics["headers_a"]

        resp_zero = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Zero Duration", "duration_minutes": 0},
        )
        assert resp_zero.status_code == 422

        resp_neg = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Negative Duration", "duration_minutes": -15},
        )
        assert resp_neg.status_code == 422

    async def test_27_reject_negative_price(self, client: AsyncClient, two_clinics):
        """27. Reject negative price."""
        headers = two_clinics["headers_a"]

        resp = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Negative Price Service", "duration_minutes": 30, "price": "-10.00"},
        )
        assert resp.status_code == 422

    async def test_28_reject_empty_doctor_name(self, client: AsyncClient, two_clinics):
        """28. Reject empty or whitespace-only doctor name."""
        headers = two_clinics["headers_a"]

        resp_empty = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": ""},
        )
        assert resp_empty.status_code == 422

        resp_spaces = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "   "},
        )
        assert resp_spaces.status_code == 422

    async def test_29_reject_empty_service_name(self, client: AsyncClient, two_clinics):
        """29. Reject empty or whitespace-only service name."""
        headers = two_clinics["headers_a"]

        resp_empty = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "", "duration_minutes": 30},
        )
        assert resp_empty.status_code == 422

        resp_spaces = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "   ", "duration_minutes": 30},
        )
        assert resp_spaces.status_code == 422


# ===========================================================================
# 5. Tenant Integrity & Advanced Scenarios
# ===========================================================================


class TestTenantIntegrity:

    async def test_30_every_returned_resource_belongs_to_authenticated_clinic(
        self, client: AsyncClient, two_clinics
    ):
        """30. Ensure every returned resource strictly matches current_user.clinic_id."""
        headers_a = two_clinics["headers_a"]
        clinic_a_id = two_clinics["clinic_a"]["clinic_id"]

        headers_b = two_clinics["headers_b"]
        clinic_b_id = two_clinics["clinic_b"]["clinic_id"]

        # Clinic A resources
        doc_a = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. All A"},
        )
        svc_a = await client.post(
            "/api/v1/services",
            headers=headers_a,
            json={"name": "Svc All A", "duration_minutes": 30},
        )

        # Clinic B resources
        doc_b = await client.post(
            "/api/v1/doctors",
            headers=headers_b,
            json={"name": "Dr. All B"},
        )
        svc_b = await client.post(
            "/api/v1/services",
            headers=headers_b,
            json={"name": "Svc All B", "duration_minutes": 30},
        )

        # Verify A listings
        docs_a = (await client.get("/api/v1/doctors", headers=headers_a)).json()
        assert all(d["clinic_id"] == clinic_a_id for d in docs_a)

        svcs_a = (await client.get("/api/v1/services", headers=headers_a)).json()
        assert all(s["clinic_id"] == clinic_a_id for s in svcs_a)

        # Verify B listings
        docs_b = (await client.get("/api/v1/doctors", headers=headers_b)).json()
        assert all(d["clinic_id"] == clinic_b_id for d in docs_b)

        svcs_b = (await client.get("/api/v1/services", headers=headers_b)).json()
        assert all(s["clinic_id"] == clinic_b_id for s in svcs_b)

    async def test_31_doctor_working_hour_cannot_cross_clinics(
        self, client: AsyncClient, two_clinics
    ):
        """31. Ensure working hour cannot be queried or manipulated through another clinic's doctor."""
        headers_a = two_clinics["headers_a"]
        headers_b = two_clinics["headers_b"]

        doc_a = await client.post(
            "/api/v1/doctors",
            headers=headers_a,
            json={"name": "Dr. Target A"},
        )
        doc_a_id = doc_a.json()["id"]

        doc_b = await client.post(
            "/api/v1/doctors",
            headers=headers_b,
            json={"name": "Dr. Target B"},
        )
        doc_b_id = doc_b.json()["id"]

        wh_a = await client.post(
            f"/api/v1/doctors/{doc_a_id}/working-hours",
            headers=headers_a,
            json={"day_of_week": 0, "start_time": "09:00:00", "end_time": "12:00:00"},
        )
        wh_a_id = wh_a.json()["id"]

        # Clinic A tries to update wh_a through doc_b_id (doctor mismatch within Clinic A)
        # Even if both doctors existed in Clinic A, wh_a does not belong to doc_b
        # Here doc_b is also in another clinic -> 404
        resp = await client.patch(
            f"/api/v1/doctors/{doc_b_id}/working-hours/{wh_a_id}",
            headers=headers_a,
            json={"end_time": "13:00:00"},
        )
        assert resp.status_code == 404

    async def test_32_doctor_delete_cascades_to_working_hours(
        self, client: AsyncClient, two_clinics, db_session
    ):
        """32. Deleting a doctor cascades at the database level and removes working hours."""
        headers = two_clinics["headers_a"]

        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Cascade Test"},
        )
        doctor_id = doc_resp.json()["id"]

        wh_resp = await client.post(
            f"/api/v1/doctors/{doctor_id}/working-hours",
            headers=headers,
            json={"day_of_week": 1, "start_time": "08:00:00", "end_time": "16:00:00"},
        )
        wh_id = uuid.UUID(wh_resp.json()["id"])

        # Delete doctor
        del_resp = await client.delete(f"/api/v1/doctors/{doctor_id}", headers=headers)
        assert del_resp.status_code == 204

        # Directly query DB session to confirm working hour was removed
        result = await db_session.execute(
            select(DoctorWorkingHour).where(DoctorWorkingHour.id == wh_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_33_filter_doctors_and_services_by_active_status(
        self, client: AsyncClient, two_clinics
    ):
        """33. Filtering by is_active query param returns only matching records."""
        headers = two_clinics["headers_a"]

        await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Active Doc", "is_active": True},
        )
        await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Inactive Doc", "is_active": False},
        )

        active_docs = (await client.get("/api/v1/doctors?is_active=true", headers=headers)).json()
        assert len(active_docs) == 1
        assert active_docs[0]["name"] == "Active Doc"

        inactive_docs = (await client.get("/api/v1/doctors?is_active=false", headers=headers)).json()
        assert len(inactive_docs) == 1
        assert inactive_docs[0]["name"] == "Inactive Doc"

    async def test_34_partial_working_hour_update_validates_resulting_times(
        self, client: AsyncClient, two_clinics
    ):
        """34. Updating only start_time or only end_time validates against the existing opposite time."""
        headers = two_clinics["headers_a"]

        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Boundary Checker"},
        )
        doc_id = doc_resp.json()["id"]

        wh_resp = await client.post(
            f"/api/v1/doctors/{doc_id}/working-hours",
            headers=headers,
            json={"day_of_week": 1, "start_time": "10:00:00", "end_time": "14:00:00"},
        )
        wh_id = wh_resp.json()["id"]

        # Try updating start_time to 15:00:00 (after existing end_time 14:00:00)
        resp1 = await client.patch(
            f"/api/v1/doctors/{doc_id}/working-hours/{wh_id}",
            headers=headers,
            json={"start_time": "15:00:00"},
        )
        assert resp1.status_code == 422

        # Try updating end_time to 09:00:00 (before existing start_time 10:00:00)
        resp2 = await client.patch(
            f"/api/v1/doctors/{doc_id}/working-hours/{wh_id}",
            headers=headers,
            json={"end_time": "09:00:00"},
        )
        assert resp2.status_code == 422
