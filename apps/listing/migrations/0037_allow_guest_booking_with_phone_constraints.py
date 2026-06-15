from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listing", "0036_allow_hotel_guest_booking_with_phone"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="carrental",
            name="car_rental_must_have_renter_or_guest",
        ),
        migrations.AddConstraint(
            model_name="carrental",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(renter__isnull=False)
                    | ~models.Q(guest_phone="")
                ),
                name="car_rental_must_have_renter_or_guest",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="guesthousebooking",
            name="guesthouse_booking_must_have_renter_or_guest",
        ),
        migrations.AddConstraint(
            model_name="guesthousebooking",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(renter__isnull=False)
                    | ~models.Q(guest_phone="")
                ),
                name="guesthouse_booking_must_have_renter_or_guest",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="propertyrentalbooking",
            name="property_rental_booking_must_have_renter_or_guest",
        ),
        migrations.AddConstraint(
            model_name="propertyrentalbooking",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(renter__isnull=False)
                    | ~models.Q(guest_phone="")
                ),
                name="property_rental_booking_must_have_renter_or_guest",
            ),
        ),
    ]
