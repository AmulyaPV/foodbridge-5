"""Small reusable checks for phone numbers, ids and uploaded files."""
import os
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import RegexValidator

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CERTIFICATE_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}


def validate_phone(value):
    digits = re.sub(r"\D", "", value)
    if not re.fullmatch(r"\+?[\d\s\-()]+", value) or not 10 <= len(digits) <= 13:
        raise ValidationError("Enter a valid phone number with 10 to 13 digits.")


validate_licence_number = RegexValidator(
    r"^[A-Za-z0-9][A-Za-z0-9\-/ ]{5,29}$",
    "Use 6 to 30 letters, numbers, dashes or slashes.",
)
validate_registration_number = RegexValidator(
    r"^[A-Za-z0-9][A-Za-z0-9\-/. ]{3,39}$",
    "Use 4 to 40 letters, numbers, dashes, dots or slashes.",
)


def _check_upload(file, allowed, label):
    """Checks only fresh uploads. A file already stored was checked when it was uploaded."""
    if not isinstance(file, UploadedFile):
        return
    extension = os.path.splitext(file.name)[1].lower()
    if extension not in allowed:
        raise ValidationError(f"{label} must be one of: {', '.join(sorted(allowed))}.")
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    if file.size > limit:
        raise ValidationError(
            f"{label} is too big ({file.size / 1024 / 1024:.1f} MB). The limit is {settings.MAX_UPLOAD_MB} MB."
        )


def _check_is_real_image(file, label):
    """A renamed text file must not pass as a picture: let Pillow actually open it."""
    if not isinstance(file, UploadedFile):
        return
    from PIL import Image, UnidentifiedImageError

    try:
        file.seek(0)
        with Image.open(file) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ValidationError(f"{label} is not a valid image file.")
    finally:
        file.seek(0)


def validate_photo_file(file):
    _check_upload(file, IMAGE_EXTENSIONS, "Photo")
    _check_is_real_image(file, "Photo")


def validate_certificate_file(file):
    _check_upload(file, CERTIFICATE_EXTENSIONS, "Certificate")
    if isinstance(file, UploadedFile) and os.path.splitext(file.name)[1].lower() in IMAGE_EXTENSIONS:
        _check_is_real_image(file, "Certificate")
    if isinstance(file, UploadedFile) and os.path.splitext(file.name)[1].lower() == ".pdf":
        head = file.read(5)
        file.seek(0)
        if head != b"%PDF-":
            raise ValidationError("This file does not look like a real PDF.")
