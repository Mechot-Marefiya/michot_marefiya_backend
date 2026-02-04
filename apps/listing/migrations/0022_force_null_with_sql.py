# Force NULL constraint fix using raw SQL
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('listing', '0021_fix_booking_null_constraints'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE bookings ALTER COLUMN user_id DROP NOT NULL;",
                "ALTER TABLE car_rentals ALTER COLUMN renter_id DROP NOT NULL;",
                "ALTER TABLE event_space_bookings ALTER COLUMN user_id DROP NOT NULL;",
                "ALTER TABLE guest_house_bookings ALTER COLUMN renter_id DROP NOT NULL;",
            ],
            reverse_sql=[
                "ALTER TABLE bookings ALTER COLUMN user_id SET NOT NULL;",
                "ALTER TABLE car_rentals ALTER COLUMN renter_id SET NOT NULL;",
                "ALTER TABLE event_space_bookings ALTER COLUMN user_id SET NOT NULL;",
                "ALTER TABLE guest_house_bookings ALTER COLUMN renter_id SET NOT NULL;",
            ]
        ),
    ]
