from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0035_add_vendor_to_receipt'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='receipt',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('type', 'COMPENSATION'), ('vendor__isnull', False)), models.Q(models.Q(_negated=True, type='COMPENSATION'), ('vendor__isnull', True)), _connector='OR'), name='vendor_id_nullity'),
        ),
    ]
