"""Helpers that build real accounts for tests (nothing here runs outside the test suite)."""
import itertools

from accounts.models import HotelProfile, IndividualProfile, NGOProfile, Role, User, Verification

PASSWORD = "Str0ng-Passw0rd!"
_counter = itertools.count(1)


def _status(approved):
    return Verification.APPROVED if approved else Verification.PENDING


def create_admin(email="admin@example.com"):
    return User.objects.create_user(username=email, email=email, password=PASSWORD, role=Role.ADMIN)


def create_hotel(email=None, name=None, approved=True, lat=12.9716, lng=77.5946, **profile_extra):
    n = next(_counter)
    email = email or f"hotel{n}@example.com"
    user = User.objects.create_user(
        username=email, email=email, password=PASSWORD, role=Role.HOTEL, verification_status=_status(approved)
    )
    HotelProfile.objects.create(
        user=user, name=name or f"Hotel {n}", contact_person="Asha Rao", phone="9876543210",
        address="12 MG Road, Bengaluru", latitude=lat, longitude=lng,
        fssai_number=f"10000000{n:06d}", **profile_extra,
    )
    return user


def create_ngo(email=None, name=None, approved=True, lat=12.9352, lng=77.6245, capacity=100, **profile_extra):
    n = next(_counter)
    email = email or f"ngo{n}@example.com"
    user = User.objects.create_user(
        username=email, email=email, password=PASSWORD, role=Role.NGO, verification_status=_status(approved)
    )
    NGOProfile.objects.create(
        user=user, name=name or f"NGO {n}", contact_person="Ravi Kumar", phone="9123456780",
        address="4 Church Street, Bengaluru", latitude=lat, longitude=lng,
        registration_number=f"NGO/{n:05d}/2020", daily_capacity=capacity, service_area="Central Bengaluru",
        **profile_extra,
    )
    return user


def create_individual(email=None, name=None, approved=True, lat=12.9600, lng=77.6000, household=3, **profile_extra):
    n = next(_counter)
    email = email or f"person{n}@example.com"
    user = User.objects.create_user(
        username=email, email=email, password=PASSWORD, role=Role.INDIVIDUAL, verification_status=_status(approved)
    )
    IndividualProfile.objects.create(
        user=user, name=name or f"Person {n}", phone="9012345678", address="7 Lake View Road, Bengaluru",
        latitude=lat, longitude=lng, household_size=household, **profile_extra,
    )
    return user
