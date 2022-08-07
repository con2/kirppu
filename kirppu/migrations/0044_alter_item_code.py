from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0043_add_access_signup'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='code',
            field=models.CharField(blank=True, db_index=True, help_text='Barcode content of the product', max_length=16, null=True, unique=True),
        ),
    ]
