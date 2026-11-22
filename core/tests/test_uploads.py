"""Photo uploads: a real image is stored, fake or oversized images are rejected."""
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.models import FoodListing
from core.testing import PASSWORD, create_hotel

TEMP_MEDIA = tempfile.mkdtemp()


def _png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(buffer, "PNG")
    return buffer.getvalue()


def _form(photo):
    now = timezone.now()
    fmt = "%Y-%m-%dT%H:%M"
    return {
        "total_servings": "10",
        "pickup_window_start": timezone.localtime(now + timezone.timedelta(minutes=5)).strftime(fmt),
        "pickup_window_end": timezone.localtime(now + timezone.timedelta(hours=1)).strftime(fmt),
        "safe_until": timezone.localtime(now + timezone.timedelta(hours=3)).strftime(fmt),
        "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000",
        "items-0-name": "Rice", "items-0-category": "veg", "items-0-quantity": "10", "items-0-unit": "servings",
        "items-0-cooking_time_note": "", "items-0-allergens_note": "",
        "photos": photo,
    }


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PhotoUploadTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.hotel = create_hotel()
        self.client = Client()
        self.client.login(username=self.hotel.username, password=PASSWORD)

    def test_real_image_is_stored_and_displayed(self):
        photo = SimpleUploadedFile("food.png", _png_bytes(), content_type="image/png")
        response = self.client.post(reverse("core:listing_create"), _form(photo))
        self.assertEqual(response.status_code, 302)
        listing = FoodListing.objects.get()
        self.assertEqual(listing.photos.count(), 1)
        page = self.client.get(reverse("core:listing_detail", args=[listing.pk]))
        self.assertContains(page, "/media/")

    def test_fake_image_is_rejected(self):
        fake = SimpleUploadedFile("food.jpg", b"this is not an image", content_type="image/jpeg")
        response = self.client.post(reverse("core:listing_create"), _form(fake))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FoodListing.objects.exists())
        self.assertContains(response, "not a valid image")

    def test_wrong_extension_is_rejected(self):
        bad = SimpleUploadedFile("food.exe", _png_bytes(), content_type="application/octet-stream")
        response = self.client.post(reverse("core:listing_create"), _form(bad))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FoodListing.objects.exists())
