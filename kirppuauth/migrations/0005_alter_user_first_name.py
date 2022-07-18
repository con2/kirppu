from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kirppuauth', '0004_auto_20180703_1615'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='first_name',
            field=models.CharField(blank=True, max_length=150, verbose_name='first name'),
        ),
    ]
