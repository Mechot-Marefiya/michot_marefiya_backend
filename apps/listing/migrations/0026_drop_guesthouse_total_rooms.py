# Generated manually to align the guest house table with the current model.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("listing", "0025_alter_carlisting_base_price_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE IF EXISTS guest_houses DROP COLUMN IF EXISTS total_rooms;",
            reverse_sql="ALTER TABLE IF EXISTS guest_houses ADD COLUMN IF NOT EXISTS total_rooms integer;",
        ),
    ]
