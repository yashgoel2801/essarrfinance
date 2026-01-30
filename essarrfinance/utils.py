import string
import random
from io import BytesIO
from django.http import HttpResponse
from django.core.files.base import ContentFile
from PIL import Image, ImageOps
import os

from django.utils.text import slugify


def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, new_slug=None):
    """
    This is for a Django project and it assumes your instance 
    has a model with a slug field and a title character (char) field.
    """
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(instance.Name)

    Klass = instance.__class__
    qs_exists = Klass.objects.filter(slug=slug).exists()
    if qs_exists:
        new_slug = "{slug}-{randstr}".format(
            slug=slug,
            randstr=random_string_generator(size=4)
        )
        return unique_slug_generator(instance, new_slug=new_slug)
    return slug
    
    
def compress_image(image_field, quality=70, max_width=1200):
    """
    Compresses an image from an ImageField and returns a ContentFile.
    """
    if not image_field:
        return None
        
    img = Image.open(image_field)
    
    # Fix orientation based on EXIF data
    img = ImageOps.exif_transpose(img)
    
    # Convert to RGB if necessary (e.g. for PNG with transparency saved as JPEG)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    # Resize if too large
    if img.width > max_width:
        output_size = (max_width, int((max_width / img.width) * img.height))
        img.thumbnail(output_size, Image.Resampling.LANCZOS)
        
    output = BytesIO()
    img.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    
    # Get the original filename and change extension to .jpg
    name = os.path.split(image_field.name)[-1]
    name = os.path.splitext(name)[0] + ".jpg"
    
    return ContentFile(output.read(), name=name)