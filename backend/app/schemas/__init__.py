from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentStatus,
    AppointmentUpdate,
    AvailableSlot,
    AvailableSlotsResponse,
)
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserResponse,
)
from app.schemas.doctor import DoctorCreate, DoctorResponse, DoctorUpdate
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate
from app.schemas.service import ServiceCreate, ServiceResponse, ServiceUpdate
from app.schemas.working_hour import (
    WorkingHourCreate,
    WorkingHourResponse,
    WorkingHourUpdate,
)

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "RegisterResponse",
    "TokenResponse",
    "UserResponse",
    "DoctorCreate",
    "DoctorUpdate",
    "DoctorResponse",
    "ServiceCreate",
    "ServiceUpdate",
    "ServiceResponse",
    "WorkingHourCreate",
    "WorkingHourUpdate",
    "WorkingHourResponse",
    "PatientCreate",
    "PatientUpdate",
    "PatientResponse",
    "AppointmentCreate",
    "AppointmentUpdate",
    "AppointmentResponse",
    "AppointmentStatus",
    "AvailableSlot",
    "AvailableSlotsResponse",
]
