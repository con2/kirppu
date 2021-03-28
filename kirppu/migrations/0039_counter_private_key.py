from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0038_event_source_db'),
    ]

    operations = [
        migrations.AddField(
            model_name='counter',
            name='private_key',
            field=models.CharField(blank=True, default=None, max_length=32, null=True, unique=True),
        ),
    ]
