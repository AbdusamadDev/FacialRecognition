# Generated by Django 4.2.5 on 2023-10-17 12:03

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0003_camera_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="camera",
            name="image",
            field=models.ImageField(upload_to="media/camera_images/"),
        ),
    ]
