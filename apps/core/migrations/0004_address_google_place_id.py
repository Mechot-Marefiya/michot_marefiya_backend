# Generated manually to align the database with the current Address model.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_alter_address_country"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="google_place_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
