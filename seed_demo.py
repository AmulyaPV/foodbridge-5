import os
import django
import datetime
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "foodbridge.settings")
django.setup()

from accounts.models import User, Role, Verification, HotelProfile, NGOProfile, IndividualProfile
from core.models import FoodListing, FoodItem, FoodCategory, ServingUnit, ListingStatus, PickupRequest, RequestStatus, NGONeed, NeedStatus

PASSWORD = "Demo@12345"

# --- 1. Hotels ---
hotels_data = [
    {
        "email": "grandpalace@demo.com",
        "name": "The Grand Palace Hotel",
        "contact": "Vikram Malhotra",
        "phone": "9876543210",
        "address": "45 M.G. Road, Central District, Bengaluru",
        "fssai": "11223344556677",
        "lat": 12.9716, "lng": 77.5946
    },
    {
        "email": "tajgateway@demo.com",
        "name": "Gateway Residency & Banquets",
        "contact": "Sunita Rao",
        "phone": "9876543211",
        "address": "12 Residency Road, Richmond Town, Bengaluru",
        "fssai": "22334455667788",
        "lat": 12.9667, "lng": 77.6000
    },
    {
        "email": "spicekitchen@demo.com",
        "name": "Royal Spice Caterers & Kitchen",
        "contact": "Karthik Nair",
        "phone": "9876543212",
        "address": "88 Koramangala 4th Block, Bengaluru",
        "fssai": "33445566778899",
        "lat": 12.9352, "lng": 77.6245
    },
    {
        "email": "orientalwok@demo.com",
        "name": "Blue Lagoon Fine Dine",
        "contact": "David Fernandez",
        "phone": "9876543213",
        "address": "104 Indiranagar 100ft Road, Bengaluru",
        "fssai": "44556677889900",
        "lat": 12.9784, "lng": 77.6408
    }
]

created_hotels = []
for h in hotels_data:
    user, created = User.objects.get_or_create(username=h["email"], defaults={
        "email": h["email"], "role": Role.HOTEL, "verification_status": Verification.APPROVED
    })
    if created:
        user.set_password(PASSWORD)
        user.save()
    profile, _ = HotelProfile.objects.get_or_create(user=user, defaults={
        "name": h["name"],
        "contact_person": h["contact"],
        "phone": h["phone"],
        "address": h["address"],
        "fssai_number": h["fssai"],
        "latitude": h["lat"],
        "longitude": h["lng"]
    })
    created_hotels.append(profile)

# --- 2. NGOs ---
ngos_data = [
    {
        "email": "annaseva@demo.com",
        "name": "Anna Seva Trust",
        "contact": "Ramesh Kumar",
        "phone": "9123456780",
        "address": "14 Sampangi Rama Nagar, Bengaluru",
        "reg_no": "NGO/BLR/2021/0451",
        "capacity": 250,
        "service_area": "Central Bengaluru & Shanti Nagar",
        "lat": 12.9680, "lng": 77.5920
    },
    {
        "email": "feedthehungry@demo.com",
        "name": "Feed The City Foundation",
        "contact": "Meera Sen",
        "phone": "9123456781",
        "address": "77 Austin Town, Neelasandra, Bengaluru",
        "reg_no": "NGO/BLR/2020/1182",
        "capacity": 400,
        "service_area": "Neelasandra, Ejipura, Koramangala",
        "lat": 12.9610, "lng": 77.6150
    },
    {
        "email": "hopekitchen@demo.com",
        "name": "Hope & Care Shelter",
        "contact": "Rev. Father Anthony",
        "phone": "9123456782",
        "address": "22 Frazer Town, Pulikeshi Nagar, Bengaluru",
        "reg_no": "NGO/BLR/2019/3321",
        "capacity": 180,
        "service_area": "Frazer Town, Cox Town, Shivajinagar",
        "lat": 12.9968, "lng": 77.6133
    },
    {
        "email": "carefoundation@demo.com",
        "name": "Karuna Seva Samithi",
        "contact": "Pooja Hegde",
        "phone": "9123456783",
        "address": "90 Ulsoor Lake Road, Halasuru, Bengaluru",
        "reg_no": "NGO/BLR/2022/8890",
        "capacity": 300,
        "service_area": "Halasuru, Indiranagar, Domlur",
        "lat": 12.9810, "lng": 77.6250
    }
]

created_ngos = []
for n in ngos_data:
    user, created = User.objects.get_or_create(username=n["email"], defaults={
        "email": n["email"], "role": Role.NGO, "verification_status": Verification.APPROVED
    })
    if created:
        user.set_password(PASSWORD)
        user.save()
    profile, _ = NGOProfile.objects.get_or_create(user=user, defaults={
        "name": n["name"],
        "contact_person": n["contact"],
        "phone": n["phone"],
        "address": n["address"],
        "registration_number": n["reg_no"],
        "daily_capacity": n["capacity"],
        "service_area": n["service_area"],
        "latitude": n["lat"],
        "longitude": n["lng"]
    })
    created_ngos.append(profile)

# --- 3. Individual Recipients ---
indivs_data = [
    {
        "email": "anand.sharma@demo.com",
        "name": "Anand Sharma",
        "phone": "9988776655",
        "address": "B-4 Slum Rehabilitation Quarters, Austin Town, Bengaluru",
        "size": 4,
        "lat": 12.9620, "lng": 77.6140
    },
    {
        "email": "fatima.begum@demo.com",
        "name": "Fatima Begum",
        "phone": "9988776656",
        "address": "18 Market Lane, Shivajinagar, Bengaluru",
        "size": 5,
        "lat": 12.9860, "lng": 77.6050
    },
    {
        "email": "mariamm@demo.com",
        "name": "Mariamma Joseph",
        "phone": "9988776657",
        "address": "12 Pottery Road, Frazer Town, Bengaluru",
        "size": 3,
        "lat": 12.9980, "lng": 77.6180
    }
]

created_indivs = []
for ind in indivs_data:
    user, created = User.objects.get_or_create(username=ind["email"], defaults={
        "email": ind["email"], "role": Role.INDIVIDUAL, "verification_status": Verification.APPROVED
    })
    if created:
        user.set_password(PASSWORD)
        user.save()
    profile, _ = IndividualProfile.objects.get_or_create(user=user, defaults={
        "name": ind["name"],
        "contact_person": ind["name"],
        "phone": ind["phone"],
        "address": ind["address"],
        "household_size": ind["size"],
        "latitude": ind["lat"],
        "longitude": ind["lng"]
    })
    created_indivs.append(profile)

# --- 4. Listings & Items ---
now = timezone.now()

listings_info = [
    {
        "hotel": created_hotels[0],
        "title": "Fresh Paneer Butter Masala, Dal Makhani & Roti",
        "storage": "Kept in hot food warmers at 65°C. Clean stainless steel containers.",
        "servings": 60,
        "start": now - datetime.timedelta(hours=1),
        "end": now + datetime.timedelta(hours=4),
        "safe_until": now + datetime.timedelta(hours=5),
        "items": [
            ("Paneer Butter Masala", FoodCategory.VEG, 30, ServingUnit.SERVINGS, "Dairy"),
            ("Dal Makhani", FoodCategory.VEG, 30, ServingUnit.SERVINGS, "Dairy"),
            ("Tandoori Roti", FoodCategory.VEGAN, 120, ServingUnit.SERVINGS, "Gluten")
        ]
    },
    {
        "hotel": created_hotels[1],
        "title": "Vegetable Pulao & Mixed Veg Curry",
        "storage": "Sealed banquet transport chafing trays, hot condition.",
        "servings": 45,
        "start": now,
        "end": now + datetime.timedelta(hours=3),
        "safe_until": now + datetime.timedelta(hours=4),
        "items": [
            ("Vegetable Pulao", FoodCategory.VEG, 45, ServingUnit.SERVINGS, "None"),
            ("Mixed Vegetable Korma", FoodCategory.VEG, 45, ServingUnit.SERVINGS, "Nuts")
        ]
    },
    {
        "hotel": created_hotels[2],
        "title": "South Indian Lunch Meals (Sambar, Rasam, Rice)",
        "storage": "Packed in insulated hot catering containers.",
        "servings": 80,
        "start": now - datetime.timedelta(minutes=30),
        "end": now + datetime.timedelta(hours=2),
        "safe_until": now + datetime.timedelta(hours=3),
        "items": [
            ("Steamed Sona Masoori Rice", FoodCategory.VEGAN, 80, ServingUnit.SERVINGS, "None"),
            ("Drumstick Sambar & Rasam", FoodCategory.VEGAN, 80, ServingUnit.SERVINGS, "Mustard")
        ]
    },
    {
        "hotel": created_hotels[3],
        "title": "Assorted Sandwiches, Veg Fried Rice & Spring Rolls",
        "storage": "Individually packed buffet surplus boxes, cool & dry.",
        "servings": 35,
        "start": now,
        "end": now + datetime.timedelta(hours=5),
        "safe_until": now + datetime.timedelta(hours=6),
        "items": [
            ("Vegetable Fried Rice", FoodCategory.VEGAN, 25, ServingUnit.SERVINGS, "Soy"),
            ("Club Sandwiches", FoodCategory.VEG, 20, ServingUnit.SERVINGS, "Gluten, Dairy")
        ]
    }
]

created_listings = []
for l_info in listings_info:
    listing, _ = FoodListing.objects.get_or_create(
        hotel=l_info["hotel"],
        title=l_info["title"],
        defaults={
            "pickup_location": l_info["hotel"].address,
            "contact_phone": l_info["hotel"].phone,
            "storage_notes": l_info["storage"],
            "total_servings": l_info["servings"],
            "servings_available": l_info["servings"],
            "pickup_window_start": l_info["start"],
            "pickup_window_end": l_info["end"],
            "safe_until": l_info["safe_until"],
            "status": ListingStatus.POSTED
        }
    )
    for iname, icat, iqty, iunit, iall in l_info["items"]:
        FoodItem.objects.get_or_create(
            listing=listing, name=iname,
            defaults={"category": icat, "quantity": iqty, "unit": iunit, "allergens_note": iall}
        )
    created_listings.append(listing)

# --- 5. Needs Board ---
needs_info = [
    (created_ngos[0], 50, now + datetime.timedelta(hours=8), "Immediate Need: 50 Veg Meals for Night Shelter"),
    (created_ngos[1], 80, now + datetime.timedelta(hours=20), "Cooked Rice/Pulao for 80 Destitute Persons")
]

for ngo, qty, by_when, notes in needs_info:
    NGONeed.objects.get_or_create(
        ngo=ngo, notes=notes,
        defaults={"servings_needed": qty, "needed_by": by_when, "status": NeedStatus.OPEN}
    )

print("Demo seed completed successfully!")
print("Hotels created:", len(created_hotels))
print("NGOs created:", len(created_ngos))
print("Individuals created:", len(created_indivs))
print("Listings created:", len(created_listings))
