from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0039_counter_private_key'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='itemtype',
            unique_together={('event', 'order')},
        ),
        migrations.RemoveField(
            model_name='itemtype',
            name='key',
        ),
    ]
