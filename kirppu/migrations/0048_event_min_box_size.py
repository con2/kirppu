# Generated by Django 4.2.13 on 2024-06-01 10:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0047_event_registration_disabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='min_box_size',
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]