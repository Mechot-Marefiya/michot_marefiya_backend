from decimal import Decimal

from django.db import migrations, models


def backfill_car_rental_mode_prices(apps, schema_editor):
    CarListing = apps.get_model("listing", "CarListing")
    for listing in CarListing.objects.all().iterator():
        changed = False
        if listing.with_driver_base_price is None:
            listing.with_driver_base_price = listing.base_price
            changed = True
        if listing.without_driver_base_price is None:
            listing.without_driver_base_price = listing.base_price
            changed = True
        if changed:
            listing.save(update_fields=["with_driver_base_price", "without_driver_base_price"])


class Migration(migrations.Migration):

    dependencies = [
        ("listing", "0040_carlisting_business_license_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="carlisting",
            name="with_driver_base_price",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Per-day rental price when the renter chooses the with-driver option.", max_digits=10, null=True, verbose_name="With Driver Base Price"),
        ),
        migrations.AddField(
            model_name="carlisting",
            name="without_driver_base_price",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Per-day rental price when the renter chooses the self-drive option.", max_digits=10, null=True, verbose_name="Without Driver Base Price"),
        ),
        migrations.AddField(
            model_name="carrentalitem",
            name="selected_rental_mode",
            field=models.CharField(choices=[("with_driver", "With Driver"), ("without_driver", "Without Driver")], default="with_driver", help_text="Renter-selected driver preference for this booked car.", max_length=32, verbose_name="Selected Rental Mode"),
        ),
        migrations.RunPython(backfill_car_rental_mode_prices, migrations.RunPython.noop),
    ]
