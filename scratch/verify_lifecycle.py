import os
import sys
import django

sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'foodbridge.settings')
django.setup()

from decimal import Decimal
from django.utils import timezone
from django.test import Client
from accounts.models import User, Role, HotelProfile, NGOProfile, Verification
from core.models import FoodListing, FoodItem, ListingStatus, RequestStatus
from core.requests_service import create_request, decide_request, cancel_request
from core.inventory_service import get_listing_inventory

# Clean slate setup for test users
user_hotel, _ = User.objects.get_or_create(username='verify_hotel', defaults={'role': Role.HOTEL, 'email': 'vhotel@example.com'})
user_hotel.verification_status = Verification.APPROVED
user_hotel.save()
hotel_profile, _ = HotelProfile.objects.get_or_create(user=user_hotel, defaults={'name': 'Grand Verify Hotel', 'fssai_number': '12345678901234', 'phone': '+919876543210', 'contact_person': 'Manager', 'address': '123 MG Road', 'latitude': 12.9716, 'longitude': 77.5946})

user_ngo1, _ = User.objects.get_or_create(username='verify_ngo1', defaults={'role': Role.NGO, 'email': 'vngo1@example.com'})
user_ngo1.verification_status = Verification.APPROVED
user_ngo1.save()
ngo1_profile, _ = NGOProfile.objects.get_or_create(user=user_ngo1, defaults={'name': 'Care Foundation', 'registration_number': 'REG12345678', 'daily_capacity': 500, 'service_area': 'Bangalore Central', 'phone': '+919876543211', 'contact_person': 'Director', 'address': '456 Brigade Rd', 'latitude': 12.9720, 'longitude': 77.5950})

user_ngo2, _ = User.objects.get_or_create(username='verify_ngo2', defaults={'role': Role.NGO, 'email': 'vngo2@example.com'})
user_ngo2.verification_status = Verification.APPROVED
user_ngo2.save()
ngo2_profile, _ = NGOProfile.objects.get_or_create(user=user_ngo2, defaults={'name': 'Hope Trust', 'registration_number': 'REG87654321', 'daily_capacity': 500, 'service_area': 'Bangalore East', 'phone': '+919876543212', 'contact_person': 'Trustee', 'address': '789 Residency Rd', 'latitude': 12.9730, 'longitude': 77.5960})

# Step A: Hotel posts 4 items
now = timezone.now()
listing = FoodListing.objects.create(
    hotel=hotel_profile,
    title='Breakfast Feast Verification',
    pickup_location='123 MG Road',
    contact_phone='+919876543210',
    total_servings=80,
    servings_available=80,
    pickup_window_start=now,
    pickup_window_end=now + timezone.timedelta(hours=2),
    safe_until=now + timezone.timedelta(hours=4),
    status=ListingStatus.POSTED
)

items_data = [('Puri', 20), ('Vada', 20), ('Idli', 20), ('Sambar', 20)]
created_items = {}
for name, qty in items_data:
    created_items[name] = FoodItem.objects.create(
        listing=listing,
        name=name,
        category='veg',
        quantity=Decimal(qty),
        allocated_quantity=Decimal(0),
        unit='servings'
    )

client_anon = Client(SERVER_NAME='localhost')
client_ngo1 = Client(SERVER_NAME='localhost')
client_ngo1.force_login(user_ngo1)

def print_ui_state(label):
    print(f"\n=== UI STATE: {label} ===")
    inv = get_listing_inventory(listing)
    print(f"Listing Status: {inv['status']} | Available Servings: {inv['servings_available']}")
    for itm in inv['items']:
        print(f"  * {itm['name']}: {itm['remaining']}/{itm['quantity']} remaining (allocated={itm['allocated']})")
    
    # Check Homepage
    resp_home = client_anon.get('/')
    assert resp_home.status_code == 200
    home_has_listing = 'Breakfast Feast Verification' in resp_home.content.decode('utf-8')
    
    # Check NGO Dashboard
    resp_ngo = client_ngo1.get('/food/')
    if resp_ngo.status_code != 200:
        print(f"NGO dashboard returned {resp_ngo.status_code}, redirect url: {getattr(resp_ngo, 'url', None)}")
    assert resp_ngo.status_code == 200
    ngo_has_listing = 'Breakfast Feast Verification' in resp_ngo.content.decode('utf-8')
    
    print(f"  Visible on Homepage (/): {home_has_listing}")
    print(f"  Visible on NGO Dashboard (/food/): {ngo_has_listing}")

print_ui_state("1. Initial State (Posted: 20 each)")

# Step B: NGO 1 requests Puri: 10, Vada: 10
req1 = create_request(
    listing=listing,
    recipient=ngo1_profile,
    item_quantities={
        created_items['Puri'].id: Decimal(10),
        created_items['Vada'].id: Decimal(10),
    }
)
print_ui_state("2. After NGO 1 requests 10 Puri & 10 Vada (Pending - stock should NOT change)")

# Step C: Hotel approves NGO 1
decide_request(req1.id, user_hotel, action="approve_all")
print_ui_state("3. After Hotel approves NGO 1 (Stock deducted: Puri 10, Vada 10 remaining)")

# Step D: NGO 2 requests Puri: 10, Idli: 20 (Idli fully consumed)
req2 = create_request(
    listing=listing,
    recipient=ngo2_profile,
    item_quantities={
        created_items['Puri'].id: Decimal(10),
        created_items['Idli'].id: Decimal(20),
    }
)
decide_request(req2.id, user_hotel, action="approve_all")
print_ui_state("4. After NGO 2 requests & approved for 10 Puri & 20 Idli (Puri: 0, Idli: 0 remaining)")

# Step E: NGO 1 cancels request before collection -> restored
cancel_request(req1.id, user_ngo1, reason='Unable to arrange vehicle')
print_ui_state("5. After NGO 1 cancels before collection (Puri restored to 10, Vada restored to 20)")
