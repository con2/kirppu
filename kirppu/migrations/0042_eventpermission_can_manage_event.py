from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0041_add_box_as_single_brought_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventpermission',
            name='can_manage_event',
            field=models.BooleanField(default=False),
        ),
    ]
