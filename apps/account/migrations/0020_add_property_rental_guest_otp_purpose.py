from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0019_alter_otpchallenge_purpose"),
    ]

    operations = [
        migrations.AlterField(
            model_name="otpchallenge",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("login", "Login"),
                    ("signup", "Signup"),
                    ("password_change", "Password Change"),
                    ("guest_hotel_booking", "Guest Hotel Booking"),
                    ("guest_guesthouse_booking", "Guest Guesthouse Booking"),
                    ("guest_eventspace_booking", "Guest Event Space Booking"),
                    ("guest_car_rental_booking", "Guest Car Rental Booking"),
                    ("guest_property_rental_booking", "Guest Property Rental Booking"),
                    ("guest_car_sale_reveal", "Guest Car Sale Reveal"),
                    ("guest_property_sale_reveal", "Guest Property Sale Reveal"),
                ],
                default="login",
                max_length=32,
                verbose_name="Purpose",
            ),
        ),
    ]
