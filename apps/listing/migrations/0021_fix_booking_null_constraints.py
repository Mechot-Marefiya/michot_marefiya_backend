# Generated manually to fix NULL constraint issue in 0015
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('listing', '0020_seasonalrate_individual_owner'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='user',
            field=models.ForeignKey(blank=True, help_text='User account of the person making the booking (if logged in)', null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Booker Account'),
        ),
        migrations.AlterField(
            model_name='carrental',
            name='renter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Renter Account'),
        ),
        migrations.AlterField(
            model_name='eventspacebooking',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Booker Account'),
        ),
        migrations.AlterField(
            model_name='guesthousebooking',
            name='renter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Renter Account'),
        ),
    ]
