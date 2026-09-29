"""Tests for Phase 4: Patients & Appointments.

Covers:
- Patients CRUD, search, unique phone per clinic, and soft deactivation (1-13)
- Appointments CRUD, duration derivation, list filters, update, reschedule, cancellation (14-25)
- Validation: inactive records, cross-tenant combinations, working hours boundaries, naive timestamps (26-33)
- Conflict detection: exact, partial, contained, containing, adjacent, different doctors (34-40)
- Availability: candidate slot generation, split shifts, conflicts removal, timezones (41-50)
- Concurrency safety: double-booking prevention (51)
- Tenant isolation: Clinic A vs Clinic B separation (52-57)
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from app.models.appointment import AppointmentStatus
from tests.conftest import get_auth_header, register_user

pytestmark = pytest.mark.asyncio

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


@pytest.fixture
async def setup_clinics(client: AsyncClient):
    """Set up two clinics with owner auth headers and IDs."""
    reg_a = await register_user(
        client,
        clinic_name="Sunrise Clinic",
        owner_name="Dr. Sunrise",
        email="sunrise@example.com",
        password="Password123!",
    )
    headers_a = await get_auth_header(client, "sunrise@example.com", "Password123!")
    clinic_a_id = reg_a.json()["clinic_id"]

    reg_b = await register_user(
        client,
        clinic_name="Moonlight Clinic",
        owner_name="Dr. Moonlight",
        email="moonlight@example.com",
        password="Password123!",
    )
    headers_b = await get_auth_header(client, "moonlight@example.com", "Password123!")
    clinic_b_id = reg_b.json()["clinic_id"]

    return {
        "headers_a": headers_a,
        "clinic_a_id": clinic_a_id,
        "headers_b": headers_b,
        "clinic_b_id": clinic_b_id,
    }


@pytest.fixture
async def clinic_a_setup(client: AsyncClient, setup_clinics):
    """Pre-create a doctor, working hours (Mon 09:00-13:00, 14:00-18:00), a 30m service, and a patient in Clinic A."""
    headers = setup_clinics["headers_a"]

    # 1. Doctor
    doc_res = await client.post(
        "/api/v1/doctors",
        headers=headers,
        json={"name": "Dr. Sarah", "specialty": "Dentistry", "is_active": True},
    )
    assert doc_res.status_code == 201
    doctor = doc_res.json()

    # 2. Working hours: Monday (0) split shifts 09:00-13:00 and 14:00-18:00
    wh1 = await client.post(
        f"/api/v1/doctors/{doctor['id']}/working-hours",
        headers=headers,
        json={"day_of_week": 0, "start_time": "09:00:00", "end_time": "13:00:00"},
    )
    assert wh1.status_code == 201

    wh2 = await client.post(
        f"/api/v1/doctors/{doctor['id']}/working-hours",
        headers=headers,
        json={"day_of_week": 0, "start_time": "14:00:00", "end_time": "18:00:00"},
    )
    assert wh2.status_code == 201

    # 3. Service: Dental Cleaning (30 minutes)
    svc_res = await client.post(
        "/api/v1/services",
        headers=headers,
        json={"name": "Dental Cleaning", "duration_minutes": 30, "price": "50.00"},
    )
    assert svc_res.status_code == 201
    service = svc_res.json()

    # 4. Patient: John Doe
    pat_res = await client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "full_name": "John Doe",
            "phone": "+919876543210",
            "email": "john.doe@example.com",
            "date_of_birth": "1990-05-15",
            "gender": "male",
            "notes": "No allergies",
        },
    )
    assert pat_res.status_code == 201
    patient = pat_res.json()

    return {
        "headers": headers,
        "clinic_id": setup_clinics["clinic_a_id"],
        "doctor": doctor,
        "service": service,
        "patient": patient,
    }


# ===========================================================================
# 1. Patients Tests (1 - 13)
# ===========================================================================


class TestPatients:

    async def test_01_create_patient(self, client: AsyncClient, setup_clinics):
        """1. Create patient successfully."""
        headers = setup_clinics["headers_a"]
        resp = await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "full_name": "Alice Wonderland",
                "phone": "+919111111111",
                "email": "alice@example.com",
                "gender": "female",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["full_name"] == "Alice Wonderland"
        assert data["phone"] == "+919111111111"
        assert data["email"] == "alice@example.com"
        assert data["is_active"] is True
        assert "id" in data
        assert data["clinic_id"] == setup_clinics["clinic_a_id"]

    async def test_02_retrieve_patient(self, client: AsyncClient, setup_clinics):
        """2. Retrieve patient by ID."""
        headers = setup_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Bob Builder", "phone": "+919222222222"},
        )
        patient_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/patients/{patient_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == patient_id
        assert get_resp.json()["full_name"] == "Bob Builder"

    async def test_03_list_patients(self, client: AsyncClient, setup_clinics):
        """3. List patients scoped to clinic."""
        headers = setup_clinics["headers_a"]
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Patient 1", "phone": "+919333333331"},
        )
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Patient 2", "phone": "+919333333332"},
        )

        resp = await client.get("/api/v1/patients", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    async def test_04_search_by_name(self, client: AsyncClient, setup_clinics):
        """4. Search patient by name (case-insensitive substring)."""
        headers = setup_clinics["headers_a"]
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Charlie Chaplin", "phone": "+919444444441"},
        )

        resp = await client.get("/api/v1/patients?search=chaplin", headers=headers)
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["full_name"] == "Charlie Chaplin"

    async def test_05_search_by_phone(self, client: AsyncClient, setup_clinics):
        """5. Search patient by phone substring."""
        headers = setup_clinics["headers_a"]
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Dave Phone", "phone": "+919555555555"},
        )

        resp = await client.get("/api/v1/patients?search=955555", headers=headers)
        assert resp.status_code == 200
        assert any(p["phone"] == "+919555555555" for p in resp.json())

    async def test_06_search_by_email(self, client: AsyncClient, setup_clinics):
        """6. Search patient by email substring."""
        headers = setup_clinics["headers_a"]
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Eve Email", "phone": "+919666666666", "email": "eve@secret.org"},
        )

        resp = await client.get("/api/v1/patients?search=secret.org", headers=headers)
        assert resp.status_code == 200
        assert any(p["email"] == "eve@secret.org" for p in resp.json())

    async def test_07_update_patient(self, client: AsyncClient, setup_clinics):
        """7. Update patient."""
        headers = setup_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Frank Before", "phone": "+919777777777"},
        )
        patient_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/patients/{patient_id}",
            headers=headers,
            json={"full_name": "Frank After", "notes": "Updated note"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["full_name"] == "Frank After"
        assert update_resp.json()["notes"] == "Updated note"

    async def test_08_deactivate_patient(self, client: AsyncClient, setup_clinics):
        """8. Deactivate patient sets is_active=false."""
        headers = setup_clinics["headers_a"]
        create_resp = await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Grace Active", "phone": "+919888888888"},
        )
        patient_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/patients/{patient_id}", headers=headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["is_active"] is False

        # Confirm via get
        get_resp = await client.get(f"/api/v1/patients/{patient_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["is_active"] is False

    async def test_09_duplicate_phone_in_same_clinic_rejected(self, client: AsyncClient, setup_clinics):
        """9. Reject duplicate phone in same clinic (409 Conflict)."""
        headers = setup_clinics["headers_a"]
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Patient X", "phone": "+919999999999"},
        )

        resp2 = await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Patient Y", "phone": "+919999999999"},
        )
        assert resp2.status_code == 409

    async def test_10_same_phone_in_different_clinics_allowed(self, client: AsyncClient, setup_clinics):
        """10. Same phone number is allowed in different clinics."""
        headers_a = setup_clinics["headers_a"]
        headers_b = setup_clinics["headers_b"]

        resp_a = await client.post(
            "/api/v1/patients",
            headers=headers_a,
            json={"full_name": "Clinic A Patient", "phone": "+919000000000"},
        )
        assert resp_a.status_code == 201

        resp_b = await client.post(
            "/api/v1/patients",
            headers=headers_b,
            json={"full_name": "Clinic B Patient", "phone": "+919000000000"},
        )
        assert resp_b.status_code == 201

    async def test_11_cross_tenant_patient_access_returns_404(self, client: AsyncClient, setup_clinics):
        """11. Clinic B cannot access Clinic A's patient (returns 404)."""
        headers_a = setup_clinics["headers_a"]
        headers_b = setup_clinics["headers_b"]

        pat_a = await client.post(
            "/api/v1/patients",
            headers=headers_a,
            json={"full_name": "Clinic A Person", "phone": "+919123456780"},
        )
        pat_id = pat_a.json()["id"]

        resp = await client.get(f"/api/v1/patients/{pat_id}", headers=headers_b)
        assert resp.status_code == 404

    async def test_12_cross_tenant_update_blocked(self, client: AsyncClient, setup_clinics):
        """12. Clinic B cannot update Clinic A's patient (returns 404)."""
        headers_a = setup_clinics["headers_a"]
        headers_b = setup_clinics["headers_b"]

        pat_a = await client.post(
            "/api/v1/patients",
            headers=headers_a,
            json={"full_name": "Target Person", "phone": "+919123456781"},
        )
        pat_id = pat_a.json()["id"]

        resp = await client.patch(
            f"/api/v1/patients/{pat_id}",
            headers=headers_b,
            json={"full_name": "Hacked Name"},
        )
        assert resp.status_code == 404

    async def test_13_cross_tenant_deactivation_blocked(self, client: AsyncClient, setup_clinics):
        """13. Clinic B cannot deactivate Clinic A's patient (returns 404)."""
        headers_a = setup_clinics["headers_a"]
        headers_b = setup_clinics["headers_b"]

        pat_a = await client.post(
            "/api/v1/patients",
            headers=headers_a,
            json={"full_name": "Target Deact", "phone": "+919123456782"},
        )
        pat_id = pat_a.json()["id"]

        resp = await client.delete(f"/api/v1/patients/{pat_id}", headers=headers_b)
        assert resp.status_code == 404


# ===========================================================================
# 2. Appointments CRUD & Management (14 - 25)
# ===========================================================================


class TestAppointments:

    async def test_14_create_appointment(self, client: AsyncClient, clinic_a_setup):
        """14. Create appointment successfully."""
        headers = clinic_a_setup["headers"]
        # Monday 10:00 AM Kolkata time (+05:30)
        # Find next Monday:
        # Use fixed Monday: 2026-10-05 is a Monday
        start_at = "2026-10-05T10:00:00+05:30"

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
                "reason": "Routine checkup",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["patient_id"] == clinic_a_setup["patient"]["id"]
        assert data["doctor_id"] == clinic_a_setup["doctor"]["id"]
        assert data["service_id"] == clinic_a_setup["service"]["id"]
        assert data["reason"] == "Routine checkup"

    async def test_15_service_duration_determines_end_at(self, client: AsyncClient, clinic_a_setup):
        """15. Correct service duration (30 min) determines end_at."""
        headers = clinic_a_setup["headers"]
        start_at = "2026-10-05T10:30:00+05:30"

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        expected_end = datetime.fromisoformat(start_at) + timedelta(minutes=30)
        actual_end = datetime.fromisoformat(data["end_at"])
        assert actual_end == expected_end

    async def test_16_retrieve_appointment(self, client: AsyncClient, clinic_a_setup):
        """16. Retrieve appointment by ID."""
        headers = clinic_a_setup["headers"]
        create_resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T11:00:00+05:30",
            },
        )
        appt_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/appointments/{appt_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == appt_id

    async def test_17_list_appointments(self, client: AsyncClient, clinic_a_setup):
        """17. List appointments."""
        headers = clinic_a_setup["headers"]
        await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T11:30:00+05:30",
            },
        )
        resp = await client.get("/api/v1/appointments", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_18_filter_by_doctor(self, client: AsyncClient, clinic_a_setup):
        """18. Filter appointments by doctor_id."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]

        resp = await client.get(f"/api/v1/appointments?doctor_id={doc_id}", headers=headers)
        assert resp.status_code == 200
        assert all(a["doctor_id"] == doc_id for a in resp.json())

    async def test_19_filter_by_patient(self, client: AsyncClient, clinic_a_setup):
        """19. Filter appointments by patient_id."""
        headers = clinic_a_setup["headers"]
        pat_id = clinic_a_setup["patient"]["id"]

        resp = await client.get(f"/api/v1/appointments?patient_id={pat_id}", headers=headers)
        assert resp.status_code == 200
        assert all(a["patient_id"] == pat_id for a in resp.json())

    async def test_20_filter_by_status(self, client: AsyncClient, clinic_a_setup):
        """20. Filter appointments by status."""
        headers = clinic_a_setup["headers"]
        resp = await client.get("/api/v1/appointments?status=scheduled", headers=headers)
        assert resp.status_code == 200
        assert all(a["status"] == "scheduled" for a in resp.json())

    async def test_21_update_appointment_notes_and_reason(self, client: AsyncClient, clinic_a_setup):
        """21. Update appointment non-scheduling fields."""
        headers = clinic_a_setup["headers"]
        create_resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T12:00:00+05:30",
            },
        )
        appt_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/appointments/{appt_id}",
            headers=headers,
            json={"reason": "Updated Reason", "notes": "New Patient Note"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["reason"] == "Updated Reason"
        assert patch_resp.json()["notes"] == "New Patient Note"

    async def test_22_reschedule_appointment(self, client: AsyncClient, clinic_a_setup):
        """22. Reschedule appointment start_at recalculates end_at and validates slot."""
        headers = clinic_a_setup["headers"]
        create_resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T12:30:00+05:30",
            },
        )
        appt_id = create_resp.json()["id"]

        # Reschedule to afternoon shift: 14:30:00
        patch_resp = await client.patch(
            f"/api/v1/appointments/{appt_id}",
            headers=headers,
            json={"start_at": "2026-10-05T14:30:00+05:30"},
        )
        assert patch_resp.status_code == 200
        assert datetime.fromisoformat(patch_resp.json()["start_at"]) == datetime.fromisoformat(
            "2026-10-05T14:30:00+05:30"
        )
        assert datetime.fromisoformat(patch_resp.json()["end_at"]) == datetime.fromisoformat(
            "2026-10-05T15:00:00+05:30"
        )

    async def test_23_cancel_appointment(self, client: AsyncClient, clinic_a_setup):
        """23. Cancel appointment sets status to CANCELLED."""
        headers = clinic_a_setup["headers"]
        create_resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T15:00:00+05:30",
            },
        )
        appt_id = create_resp.json()["id"]

        cancel_resp = await client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=headers)
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    async def test_24_cancelled_appointment_remains_in_history(self, client: AsyncClient, clinic_a_setup):
        """24. Cancelled appointment remains queryable in history."""
        headers = clinic_a_setup["headers"]
        create_resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T15:30:00+05:30",
            },
        )
        appt_id = create_resp.json()["id"]
        await client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=headers)

        get_resp = await client.get(f"/api/v1/appointments/{appt_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "cancelled"

    async def test_25_cancelled_appointment_no_longer_blocks_availability(self, client: AsyncClient, clinic_a_setup):
        """25. Cancelled appointment frees up the slot for a new appointment."""
        headers = clinic_a_setup["headers"]
        start_at = "2026-10-05T16:00:00+05:30"

        # 1. Book
        appt1 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
            },
        )
        assert appt1.status_code == 201

        # 2. Cancel
        await client.post(f"/api/v1/appointments/{appt1.json()['id']}/cancel", headers=headers)

        # 3. Book exact same slot again -> should succeed!
        appt2 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
            },
        )
        assert appt2.status_code == 201


# ===========================================================================
# 3. Validation Tests (26 - 33)
# ===========================================================================


class TestValidation:

    async def test_26_inactive_doctor_cannot_receive_appointment(self, client: AsyncClient, clinic_a_setup):
        """26. Inactive doctor cannot receive new appointments."""
        headers = clinic_a_setup["headers"]
        # Create an inactive doctor
        doc_resp = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Inactive", "is_active": False},
        )
        inactive_doc_id = doc_resp.json()["id"]

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": inactive_doc_id,
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T10:00:00+05:30",
            },
        )
        assert resp.status_code == 422
        assert "inactive doctor" in resp.json()["detail"].lower()

    async def test_27_inactive_service_cannot_be_booked(self, client: AsyncClient, clinic_a_setup):
        """27. Inactive service cannot be booked."""
        headers = clinic_a_setup["headers"]
        svc_resp = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Deprecated Service", "duration_minutes": 30, "is_active": False},
        )
        inactive_svc_id = svc_resp.json()["id"]

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": inactive_svc_id,
                "start_at": "2026-10-05T10:00:00+05:30",
            },
        )
        assert resp.status_code == 422
        assert "inactive service" in resp.json()["detail"].lower()

    async def test_28_inactive_patient_cannot_receive_appointment(self, client: AsyncClient, clinic_a_setup):
        """28. Inactive patient cannot receive new appointments."""
        headers = clinic_a_setup["headers"]
        pat_resp = await client.post(
            "/api/v1/patients",
            headers=headers,
            json={"full_name": "Inactive Patient", "phone": "+919876543000", "is_active": False},
        )
        inactive_pat_id = pat_resp.json()["id"]

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": inactive_pat_id,
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T10:00:00+05:30",
            },
        )
        assert resp.status_code == 422
        assert "inactive patient" in resp.json()["detail"].lower()

    async def test_29_cross_tenant_resource_combination_rejected(self, client: AsyncClient, clinic_a_setup, setup_clinics):
        """29. Mixing resources from Clinic A and Clinic B returns 404."""
        headers_a = clinic_a_setup["headers"]
        headers_b = setup_clinics["headers_b"]

        # Clinic B doctor
        doc_b = await client.post(
            "/api/v1/doctors",
            headers=headers_b,
            json={"name": "Dr. B Doctor"},
        )
        doc_b_id = doc_b.json()["id"]

        # Clinic A tries to use Clinic B doctor
        resp = await client.post(
            "/api/v1/appointments",
            headers=headers_a,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": doc_b_id,
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T10:00:00+05:30",
            },
        )
        assert resp.status_code == 404

    async def test_30_appointment_outside_working_hours_rejected(self, client: AsyncClient, clinic_a_setup):
        """30. Appointment outside working hours (e.g. 08:00 AM when working hours start at 09:00 AM) is rejected."""
        headers = clinic_a_setup["headers"]

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T08:00:00+05:30",
            },
        )
        assert resp.status_code == 422
        assert "outside doctor working hours" in resp.json()["detail"].lower()

    async def test_31_appointment_crossing_working_hour_boundary_rejected(self, client: AsyncClient, clinic_a_setup):
        """31. Appointment crossing split shift boundary (12:45 to 13:15 when morning shift ends at 13:00) is rejected."""
        headers = clinic_a_setup["headers"]

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],  # 30 min duration
                "start_at": "2026-10-05T12:45:00+05:30",  # ends at 13:15
            },
        )
        assert resp.status_code == 422
        assert "outside doctor working hours" in resp.json()["detail"].lower()

    async def test_32_appointment_exactly_ending_at_working_hour_end_accepted(self, client: AsyncClient, clinic_a_setup):
        """32. Appointment ending exactly at shift boundary (12:30 to 13:00) is accepted."""
        headers = clinic_a_setup["headers"]

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T12:30:00+05:30",  # ends exactly at 13:00:00
            },
        )
        assert resp.status_code == 201

    async def test_33_naive_datetime_rejected(self, client: AsyncClient, clinic_a_setup):
        """33. Naive datetime without timezone is rejected with 422."""
        headers = clinic_a_setup["headers"]

        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-05T10:00:00",  # missing offset or Z
            },
        )
        assert resp.status_code == 422


# ===========================================================================
# 4. Conflict Detection Tests (34 - 40)
# ===========================================================================


class TestConflictDetection:

    async def test_34_exact_overlap_rejected(self, client: AsyncClient, clinic_a_setup):
        """34. Exact interval overlap rejected."""
        headers = clinic_a_setup["headers"]
        start_at = "2026-10-12T10:00:00+05:30"  # Next Monday

        # First appointment
        r1 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
            },
        )
        assert r1.status_code == 201

        # Second appointment exact same slot
        r2 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
            },
        )
        assert r2.status_code == 409

    async def test_35_partial_overlap_rejected(self, client: AsyncClient, clinic_a_setup):
        """35. Partial overlap (existing: 10:00-10:30, new: 10:15-10:45) is rejected."""
        headers = clinic_a_setup["headers"]
        # Existing: 10:00 - 10:30
        r1 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-12T10:00:00+05:30",
            },
        )
        assert r1.status_code == 201

        # New: 10:15 - 10:45
        r2 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-12T10:15:00+05:30",
            },
        )
        assert r2.status_code == 409

    async def test_36_existing_appointment_containing_new_rejected(self, client: AsyncClient, clinic_a_setup):
        """36. Existing appointment containing new appointment is rejected."""
        headers = clinic_a_setup["headers"]
        # Create a 60m service
        svc60_res = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Long Service", "duration_minutes": 60},
        )
        svc60_id = svc60_res.json()["id"]

        # Book 10:00 - 11:00
        await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": svc60_id,
                "start_at": "2026-10-12T10:00:00+05:30",
            },
        )

        # Try to book 10:15 - 10:45 (inside 10:00 - 11:00)
        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],  # 30 min
                "start_at": "2026-10-12T10:15:00+05:30",
            },
        )
        assert resp.status_code == 409

    async def test_37_new_appointment_containing_existing_rejected(self, client: AsyncClient, clinic_a_setup):
        """37. New appointment containing existing appointment is rejected."""
        headers = clinic_a_setup["headers"]
        # Existing: 10:15 - 10:45 (30m)
        await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-12T10:15:00+05:30",
            },
        )

        # Create a 60m service
        svc60_res = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Big Service", "duration_minutes": 60},
        )
        svc60_id = svc60_res.json()["id"]

        # New: 10:00 - 11:00 (encompasses 10:15 - 10:45)
        resp = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": svc60_id,
                "start_at": "2026-10-12T10:00:00+05:30",
            },
        )
        assert resp.status_code == 409

    async def test_38_adjacent_appointments_allowed(self, client: AsyncClient, clinic_a_setup):
        """38. Adjacent back-to-back appointments (10:00-10:30 and 10:30-11:00) are allowed."""
        headers = clinic_a_setup["headers"]
        # Slot 1: 10:00 - 10:30
        r1 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-12T10:00:00+05:30",
            },
        )
        assert r1.status_code == 201

        # Slot 2: 10:30 - 11:00
        r2 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-12T10:30:00+05:30",
            },
        )
        assert r2.status_code == 201

    async def test_39_different_doctor_does_not_conflict(self, client: AsyncClient, clinic_a_setup):
        """39. Appointments at same time for different doctors do not conflict."""
        headers = clinic_a_setup["headers"]
        # Create second doctor with working hours
        doc2_res = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Dr. Second Doctor", "is_active": True},
        )
        doc2 = doc2_res.json()
        await client.post(
            f"/api/v1/doctors/{doc2['id']}/working-hours",
            headers=headers,
            json={"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00"},
        )

        time_slot = "2026-10-12T10:00:00+05:30"

        # Book Doctor 1
        r1 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": time_slot,
            },
        )
        assert r1.status_code == 201

        # Book Doctor 2 at exact same time -> Allowed
        r2 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": doc2["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": time_slot,
            },
        )
        assert r2.status_code == 201

    async def test_40_cancelled_appointment_does_not_conflict(self, client: AsyncClient, clinic_a_setup):
        """40. A cancelled appointment does not cause conflict for new bookings."""
        headers = clinic_a_setup["headers"]
        start_at = "2026-10-12T11:00:00+05:30"

        # Create & Cancel
        r1 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
            },
        )
        await client.post(f"/api/v1/appointments/{r1.json()['id']}/cancel", headers=headers)

        # New booking at same slot -> Allowed
        r2 = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": start_at,
            },
        )
        assert r2.status_code == 201


# ===========================================================================
# 5. Availability Tests (41 - 50)
# ===========================================================================


class TestAvailability:

    async def test_41_available_slots_generated_correctly(self, client: AsyncClient, clinic_a_setup):
        """41. Candidate slots generated deterministically within working hours."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]
        svc_id = clinic_a_setup["service"]["id"]  # 30 min duration
        target_date = "2026-10-19"  # Monday

        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date={target_date}",
            headers=headers,
        )
        assert resp.status_code == 200
        slots = resp.json()["slots"]
        assert len(slots) > 0
        # First slot should start at 09:00:00
        assert slots[0]["start_at"].startswith(f"{target_date}T09:00:00")

    async def test_42_service_duration_affects_slots(self, client: AsyncClient, clinic_a_setup):
        """42. Longer service duration produces slots with corresponding end times."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]

        # Create 60m service
        svc60 = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Hour Service", "duration_minutes": 60},
        )
        svc60_id = svc60.json()["id"]

        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc60_id}&date=2026-10-19",
            headers=headers,
        )
        assert resp.status_code == 200
        slots = resp.json()["slots"]
        first_slot = slots[0]
        # Start at 09:00, end at 10:00
        start_dt = datetime.fromisoformat(first_slot["start_at"])
        end_dt = datetime.fromisoformat(first_slot["end_at"])
        assert end_dt - start_dt == timedelta(minutes=60)

    async def test_43_split_shifts_handled(self, client: AsyncClient, clinic_a_setup):
        """43. Split shifts have no slots between 13:00 and 14:00 (lunch break)."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]
        svc_id = clinic_a_setup["service"]["id"]

        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date=2026-10-19",
            headers=headers,
        )
        slots = resp.json()["slots"]

        # No slot can have start time >= 13:00 and < 14:00
        for slot in slots:
            dt = datetime.fromisoformat(slot["start_at"]).astimezone(KOLKATA_TZ)
            assert not (13 <= dt.hour < 14), f"Found slot during split shift gap: {slot}"

    async def test_44_existing_appointments_removed_from_availability(self, client: AsyncClient, clinic_a_setup):
        """44. Booking an appointment removes overlapping candidate slots from availability."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]
        svc_id = clinic_a_setup["service"]["id"]
        target_date = "2026-10-19"

        # Initial slots count
        init_resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date={target_date}",
            headers=headers,
        )
        init_count = len(init_resp.json()["slots"])

        # Book 09:00 - 09:30
        await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": doc_id,
                "service_id": svc_id,
                "start_at": f"{target_date}T09:00:00+05:30",
            },
        )

        after_resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date={target_date}",
            headers=headers,
        )
        after_slots = after_resp.json()["slots"]
        assert len(after_slots) < init_count
        assert not any(s["start_at"].startswith(f"{target_date}T09:00:00") for s in after_slots)

    async def test_45_cancelled_appointments_do_not_remove_availability(self, client: AsyncClient, clinic_a_setup):
        """45. Cancelled appointment does not diminish available slots."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]
        svc_id = clinic_a_setup["service"]["id"]
        target_date = "2026-10-26"

        init_resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date={target_date}",
            headers=headers,
        )
        init_count = len(init_resp.json()["slots"])

        # Book and cancel
        appt = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": doc_id,
                "service_id": svc_id,
                "start_at": f"{target_date}T09:00:00+05:30",
            },
        )
        await client.post(f"/api/v1/appointments/{appt.json()['id']}/cancel", headers=headers)

        after_resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date={target_date}",
            headers=headers,
        )
        assert len(after_resp.json()["slots"]) == init_count

    async def test_46_no_working_hours_returns_empty_slots(self, client: AsyncClient, clinic_a_setup):
        """46. Sunday (weekday=6) where doctor has no working hours returns empty slots."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]
        svc_id = clinic_a_setup["service"]["id"]
        # 2026-10-18 is a Sunday
        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date=2026-10-18",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["slots"] == []

    async def test_47_inactive_doctor_returns_empty_slots(self, client: AsyncClient, clinic_a_setup):
        """47. Inactive doctor returns empty slots."""
        headers = clinic_a_setup["headers"]
        doc = await client.post(
            "/api/v1/doctors",
            headers=headers,
            json={"name": "Inactive Availability Doc", "is_active": False},
        )
        doc_id = doc.json()["id"]

        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={clinic_a_setup['service']['id']}&date=2026-10-19",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["slots"] == []

    async def test_48_inactive_service_returns_empty_slots(self, client: AsyncClient, clinic_a_setup):
        """48. Inactive service returns empty slots."""
        headers = clinic_a_setup["headers"]
        svc = await client.post(
            "/api/v1/services",
            headers=headers,
            json={"name": "Inactive Availability Svc", "duration_minutes": 30, "is_active": False},
        )
        svc_id = svc.json()["id"]

        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={clinic_a_setup['doctor']['id']}&service_id={svc_id}&date=2026-10-19",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["slots"] == []

    async def test_49_cross_tenant_doctor_or_service_availability_rejected(self, client: AsyncClient, clinic_a_setup, setup_clinics):
        """49. Querying availability with another clinic's doctor returns 404."""
        headers_b = setup_clinics["headers_b"]
        doc_a_id = clinic_a_setup["doctor"]["id"]
        svc_a_id = clinic_a_setup["service"]["id"]

        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_a_id}&service_id={svc_a_id}&date=2026-10-19",
            headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_50_timezone_handled_correctly(self, client: AsyncClient, clinic_a_setup):
        """50. Slot start_at and end_at timestamps contain the clinic's local timezone offset."""
        headers = clinic_a_setup["headers"]
        doc_id = clinic_a_setup["doctor"]["id"]
        svc_id = clinic_a_setup["service"]["id"]

        resp = await client.get(
            f"/api/v1/appointments/available-slots?doctor_id={doc_id}&service_id={svc_id}&date=2026-10-19",
            headers=headers,
        )
        assert resp.status_code == 200
        first_slot = resp.json()["slots"][0]
        # Kolkata offset is +05:30
        assert "+05:30" in first_slot["start_at"]
        assert "+05:30" in first_slot["end_at"]


# ===========================================================================
# 6. Concurrency Safety Test (51)
# ===========================================================================


class TestConcurrency:

    async def test_51_concurrent_appointment_booking_prevented(self, client: AsyncClient, clinic_a_setup):
        """51. Two concurrent booking requests for the exact same slot: only one succeeds, the other gets 409."""
        headers = clinic_a_setup["headers"]
        slot_time = "2026-10-19T11:00:00+05:30"

        payload = {
            "patient_id": clinic_a_setup["patient"]["id"],
            "doctor_id": clinic_a_setup["doctor"]["id"],
            "service_id": clinic_a_setup["service"]["id"],
            "start_at": slot_time,
        }

        # Fire two concurrent POST requests
        res1, res2 = await asyncio.gather(
            client.post("/api/v1/appointments", headers=headers, json=payload),
            client.post("/api/v1/appointments", headers=headers, json=payload),
        )

        status_codes = {res1.status_code, res2.status_code}
        # Exactly one must succeed (201) and one must receive conflict (409)
        assert status_codes == {201, 409}, f"Unexpected concurrent status codes: {res1.status_code}, {res2.status_code}"


# ===========================================================================
# 7. Tenant Isolation Tests (52 - 57)
# ===========================================================================


class TestTenantIsolation:

    async def test_52_clinic_b_cannot_retrieve_clinic_a_appointment(self, client: AsyncClient, clinic_a_setup, setup_clinics):
        """52. Clinic B cannot retrieve Clinic A's appointment (404)."""
        headers_a = clinic_a_setup["headers"]
        headers_b = setup_clinics["headers_b"]

        appt = await client.post(
            "/api/v1/appointments",
            headers=headers_a,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-19T10:00:00+05:30",
            },
        )
        appt_id = appt.json()["id"]

        resp = await client.get(f"/api/v1/appointments/{appt_id}", headers=headers_b)
        assert resp.status_code == 404

    async def test_53_clinic_b_cannot_modify_clinic_a_appointment(self, client: AsyncClient, clinic_a_setup, setup_clinics):
        """53. Clinic B cannot modify Clinic A's appointment (404)."""
        headers_a = clinic_a_setup["headers"]
        headers_b = setup_clinics["headers_b"]

        appt = await client.post(
            "/api/v1/appointments",
            headers=headers_a,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-19T10:30:00+05:30",
            },
        )
        appt_id = appt.json()["id"]

        resp = await client.patch(
            f"/api/v1/appointments/{appt_id}",
            headers=headers_b,
            json={"reason": "Hacked Reason"},
        )
        assert resp.status_code == 404

    async def test_54_clinic_b_cannot_cancel_clinic_a_appointment(self, client: AsyncClient, clinic_a_setup, setup_clinics):
        """54. Clinic B cannot cancel Clinic A's appointment (404)."""
        headers_a = clinic_a_setup["headers"]
        headers_b = setup_clinics["headers_b"]

        appt = await client.post(
            "/api/v1/appointments",
            headers=headers_a,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-19T11:30:00+05:30",
            },
        )
        appt_id = appt.json()["id"]

        resp = await client.post(f"/api/v1/appointments/{appt_id}/cancel", headers=headers_b)
        assert resp.status_code == 404

    async def test_55_clinic_b_cannot_see_clinic_a_appointments_in_list(self, client: AsyncClient, clinic_a_setup, setup_clinics):
        """55. Clinic B listing appointments sees zero Clinic A appointments."""
        headers_a = clinic_a_setup["headers"]
        headers_b = setup_clinics["headers_b"]

        await client.post(
            "/api/v1/appointments",
            headers=headers_a,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-19T12:00:00+05:30",
            },
        )

        resp = await client.get("/api/v1/appointments", headers=headers_b)
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_56_foreign_key_restricts_deletion_of_patient_with_appointments(
        self, client: AsyncClient, clinic_a_setup, db_session
    ):
        """56. Database foreign key RESTRICT prevents accidental physical deletion of patient with appointments."""
        from sqlalchemy import text
        headers = clinic_a_setup["headers"]

        appt = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-19T12:30:00+05:30",
            },
        )
        assert appt.status_code == 201

        # Attempting physical raw DELETE on patient must fail with foreign key violation
        with pytest.raises(Exception):
            await db_session.execute(
                text(f"DELETE FROM patients WHERE id = '{clinic_a_setup['patient']['id']}'")
            )
            await db_session.commit()
        await db_session.rollback()

    async def test_57_foreign_key_restricts_deletion_of_doctor_with_appointments(
        self, client: AsyncClient, clinic_a_setup, db_session
    ):
        """57. Database foreign key RESTRICT prevents accidental physical deletion of doctor with appointments."""
        from sqlalchemy import text
        headers = clinic_a_setup["headers"]

        appt = await client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_id": clinic_a_setup["patient"]["id"],
                "doctor_id": clinic_a_setup["doctor"]["id"],
                "service_id": clinic_a_setup["service"]["id"],
                "start_at": "2026-10-19T14:00:00+05:30",
            },
        )
        assert appt.status_code == 201

        # Attempting DELETE on doctor via API must fail with 409 Conflict because of FK restrict, protecting historical appointments
        del_resp = await client.delete(f"/api/v1/doctors/{clinic_a_setup['doctor']['id']}", headers=headers)
        assert del_resp.status_code == 409
