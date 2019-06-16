# Generated by Django 2.2.1 on 2019-06-02 12:41

from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0026_add_accounting_permission'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clerk',
            name='access_key',
            field=models.CharField(blank=True, help_text='Access code assigned to the clerk. 14 hexlets.', max_length=128, null=True, validators=[django.core.validators.RegexValidator('^[0-9a-fA-F]{14}$', message='Must be 14 hex chars.')], verbose_name='Access key value'),
        ),
        migrations.AlterField(
            model_name='clerk',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name='clerk',
            constraint=models.CheckConstraint(check=models.Q(('user__isnull', False), ('access_key__isnull', False), _connector='OR'), name='required_values'),
        ),
        migrations.AddConstraint(
            model_name='clerk',
            constraint=models.UniqueConstraint(fields=('access_key',), name='unique_access_key'),
        ),
        migrations.AddConstraint(
            model_name='clerk',
            constraint=models.UniqueConstraint(fields=('user',), name='unique_user'),
        ),
    ]