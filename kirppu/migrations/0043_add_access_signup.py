from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kirppu', '0042_eventpermission_can_manage_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='access_signup',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='event',
            name='access_signup_token',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.CreateModel(
            name='AccessSignup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creation_time', models.DateTimeField()),
                ('update_time', models.DateTimeField()),
                ('target_set', models.CharField(max_length=255)),
                ('message', models.TextField(max_length=500)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kirppu.event')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('resolution_time', models.DateTimeField(null=True)),
                ('resolution_accepted', models.BooleanField(default=False)),
            ],
            options={
                'unique_together': {('event', 'user')},
            },
        ),
    ]
