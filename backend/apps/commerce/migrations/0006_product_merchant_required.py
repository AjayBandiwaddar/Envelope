import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('commerce', '0005_backfill_reference_merchant'),
    ]
    operations = [
        migrations.AlterField(
            model_name='product',
            name='merchant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products', to='commerce.merchant',
            ),
        ),
    ]