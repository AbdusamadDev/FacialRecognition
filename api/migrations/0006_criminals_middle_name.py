# Generated by Django 4.2.5 on 2023-10-20 11:37

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0005_remove_camera_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="criminals",
            name="middle_name",
            field=models.CharField(default="sss", max_length=120),
        ),
    ]
