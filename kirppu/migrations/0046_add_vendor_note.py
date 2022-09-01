from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0045_add_accounts'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('text', models.TextField()),
                ('clerk', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kirppu.clerk')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kirppu.vendor')),
                ('erased', models.BooleanField(default=False)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
