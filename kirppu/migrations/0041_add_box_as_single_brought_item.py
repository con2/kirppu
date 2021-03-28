from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0040_remove_itemtype_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='box_as_single_brought_item',
            field=models.BooleanField(default=False, help_text='Should a box be considered a single item when counting max brought items instead of considering its contents individually.'),
        ),
    ]
