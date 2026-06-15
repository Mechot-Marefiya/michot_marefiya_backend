from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listing", "0035_alter_contactrevealrequest_buyer_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="booking",
            name="booking_must_have_user_or_guest",
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False)
                    | ~models.Q(guest_phone="")
                ),
                name="booking_must_have_user_or_guest",
            ),
        ),
    ]
