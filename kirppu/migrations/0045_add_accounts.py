from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


# noinspection PyPep8Naming
def create_default_accounts(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    Account = apps.get_model("kirppu", "Account")
    Counter = apps.get_model("kirppu", "Counter")
    Event = apps.get_model("kirppu", "Event")
    Receipt = apps.get_model("kirppu", "Receipt")

    for event in Event.objects.using(db_alias).only("pk").filter(source_db__isnull=True):
        purchases = (
            Receipt.objects
            .using(db_alias)
            .filter(status="FINI", type="PURCHASE", clerk__event=event)
            .aggregate(sum=models.Sum("total"))
        )["sum"]
        comps = (
            Receipt.objects
            .using(db_alias)
            .filter(status="FINI", type="COMPENSATION", clerk__event=event)
            .aggregate(sum=models.Sum("total"))
        )["sum"]

        if purchases is None or comps is None:
            if purchases is comps and not Counter.objects.using(db_alias).filter(event=event).exists():
                # Nothing that would require Account to be created.
                continue
            # Either some Receipt or a Counter exists for the event. Need Account for it.
            purchases = purchases or 0
            comps = comps or 0

        balance = purchases - comps

        account = Account.objects.using(db_alias).create(
            event=event,
            name="Default",
            balance=balance,
            allow_negative_balance=True,
        )
        # Associate the new account with Counter(s).
        Counter.objects.using(db_alias).filter(event=event).update(default_store_location=account)

        # Associate the new account with the receipts.
        Receipt.objects.using(db_alias).filter(
            status="FINI", type="PURCHASE", clerk__event=event).update(dst_account=account)
        Receipt.objects.using(db_alias).filter(
            status="FINI", type="COMPENSATION", clerk__event=event).update(src_account=account)


class Migration(migrations.Migration):

    dependencies = [
        ('kirppu', '0044_alter_item_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='kirppu.event')),
                ('name', models.CharField(max_length=256)),
                ('balance', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('allow_negative_balance', models.BooleanField(default=False)),
            ],
        ),
        migrations.AlterField(
            model_name='receipt',
            name='type',
            field=models.CharField(choices=[('PURCHASE', 'Purchase'), ('COMPENSATION', 'Compensation'), ('TRANSFER', 'Transfer')], default='PURCHASE', max_length=16),
        ),
        migrations.AddField(
            model_name='counter',
            name='default_store_location',
            field=models.ForeignKey(default=None, help_text='Where the cash will be stored to and received from when using this counter.', null=True, on_delete=django.db.models.deletion.CASCADE, to='kirppu.account'),
        ),
        migrations.AddField(
            model_name='receipt',
            name='dst_account',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='dst_receipts', to='kirppu.account'),
        ),
        migrations.AddField(
            model_name='receipt',
            name='src_account',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='src_receipts', to='kirppu.account'),
        ),
        migrations.RunPython(
            create_default_accounts,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='counter',
            name='default_store_location',
            field=models.ForeignKey(help_text='Where the cash will be stored to and received from when using this counter.', on_delete=django.db.models.deletion.CASCADE, to='kirppu.account'),
        ),
        migrations.AddConstraint(
            model_name='receipt',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('type', 'TRANSFER'), _negated=True), models.Q(('dst_account__isnull', False), ('src_account__isnull', False)), _connector='OR'), name='account_id_nullity'),
        ),
        migrations.AddConstraint(
            model_name='account',
            constraint=models.CheckConstraint(condition=models.Q(('allow_negative_balance', True), ('balance__gte', 0), _connector='OR'), name='balance_negativity'),
        ),
    ]
